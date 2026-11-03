import asyncio
import json
import logging
from typing import Any, Literal
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database.supabase_general_service import SupabaseService
from routers.api_authentication import require_role
from utils.event_bus import global_event_bus
from routers.api_authentication import get_authenticated_employee

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])
logger = logging.getLogger(__name__)
_run_tasks = set()
db = SupabaseService()


class ChatbotRequest(BaseModel):
  question: str = Field(..., min_length=1, description="Câu hỏi gửi tới chatbot")
  chat_id: str = Field(..., min_length=1, description="Mã phiên hội thoại")


class RequestEvaluationRequest(BaseModel):
  request_type: Literal["OT", "LEAVE_REQUEST"]
  request_id: str = Field(..., min_length=1)


def _get_pending_request_for_leader(
    payload: RequestEvaluationRequest,
    employee: dict[str, Any],
) -> dict[str, Any]:
  if payload.request_type == "OT":
    table, id_column = "overtime", "ot_id"
    request_id: str | int = payload.request_id
  else:
    table, id_column = "leave_request", "leave_id"
    try:
      request_id = int(payload.request_id)
    except ValueError as exc:
      raise HTTPException(
          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
          detail="Mã đơn nghỉ phép phải là số nguyên.",
      ) from exc

  leader_position = employee.get("position")
  if not leader_position:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Leader chưa được cấu hình vị trí",
    )

  members = db.select(
      "employee",
      columns="employee_id",
      filters={"position": leader_position, "system_level": "Member"},
  )
  member_ids = {
      member["employee_id"]
      for member in members
      if member.get("employee_id")
  }
  requests = db.select(table, filters={id_column: request_id}, limit=1)
  if not requests or requests[0].get("employee_id") not in member_ids:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Không tìm thấy đơn yêu cầu",
    )

  request = requests[0]
  if request.get("status") != "Chờ duyệt":
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Chỉ có thể đánh giá đơn đang chờ duyệt.",
    )
  return request


async def _run_request_evaluation(
    run_id: str,
    command: str,
    context: dict[str, Any],
) -> None:
  try:
    from agents.langgraph_request_evaluation import app as evaluation_workflow

    result = await asyncio.to_thread(
        evaluation_workflow.invoke,
        {"command": command, "context": context, "run_id": run_id},
    )
    global_event_bus.publish_event(
        run_id,
        "run",
        "completed",
        {
            "request_type": command,
            "request_id": context.get("ot_id", context.get("leave_id")),
            "response": result["final_answer"],
            "data": jsonable_encoder(
                {
                    "sql_data": result["sql_data"],
                    "rag_data": result["rag_data"],
                }
            ),
        },
        agent="orchestrator",
    )
  except Exception as exc:
    logger.exception("Đánh giá đơn nhân sự thất bại (run_id=%s)", run_id)
    error_message = str(exc) or (
        "Không thể đánh giá đơn yêu cầu lúc này."
    )
    global_event_bus.publish_event(
        run_id,
        "run",
        "failed",
        {"message": error_message},
        agent="orchestrator",
    )


@router.post(
    "/request-evaluations",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bắt đầu đánh giá đơn OT hoặc nghỉ phép",
)
async def start_request_evaluation(
    payload: RequestEvaluationRequest,
    employee: dict[str, Any] = Depends(require_role("Team Lead")),
):
  request = _get_pending_request_for_leader(payload, employee)
  if payload.request_type == "OT":
    command = "OT"
    context = {"ot_id": request["ot_id"]}
  else:
    command = "LEAVE_REQUEST"
    context = {"leave_id": request["leave_id"]}

  run_id = str(uuid4())
  request_id = context.get("ot_id", context.get("leave_id"))
  global_event_bus.publish_event(
      run_id,
      "run",
      "running",
      {
          "question": f"Đánh giá đơn {command} mã {request_id}",
          "request_type": command,
          "request_id": request_id,
      },
      agent="orchestrator",
  )
  task = asyncio.create_task(_run_request_evaluation(run_id, command, context))
  _run_tasks.add(task)
  task.add_done_callback(_run_tasks.discard)
  return {"status": "running", "run_id": run_id}


async def _run_chatbot(
    run_id: str, question: str, chat_id: str, user_id: str
):
  try:
    from agents.langgraph_orchestrator import app as chatbot_workflow

    result = await asyncio.to_thread(
        chatbot_workflow.invoke,
        {
            "question": question,
            "run_id": run_id,
            "chat_id": chat_id,
            "user_id": user_id,
        },
    )
    global_event_bus.publish_event(
        run_id,
        "run",
        "completed",
        {
            "intent": result["intent"],
            "response": result["final_answer"],
            "data": jsonable_encoder(result["raw_data"]),
        },
        agent="orchestrator",
    )
  except Exception as exc:
    logger.exception("Chatbot xử lý câu hỏi thất bại (run_id=%s)", run_id)
    error_message = str(exc) or (
        "Chatbot không thể xử lý câu hỏi lúc này."
    )
    global_event_bus.publish_event(
        run_id,
        "run",
        "failed",
        {"message": error_message},
        agent="orchestrator",
    )


@router.post(
    "/chatbot",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bắt đầu xử lý câu hỏi qua chatbot AI",
)
async def chatbot(
    payload: ChatbotRequest,
    employee: dict[str, Any] = Depends(get_authenticated_employee),
):
  user_id = employee.get("employee_id")
  if not user_id:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Tài khoản chưa được liên kết với mã nhân viên.",
    )

  run_id = str(uuid4())
  global_event_bus.publish_event(
      run_id,
      "run",
      "running",
      {"question": payload.question, "chat_id": payload.chat_id},
      agent="orchestrator",
  )
  task = asyncio.create_task(
      _run_chatbot(run_id, payload.question, payload.chat_id, user_id)
  )
  _run_tasks.add(task)
  task.add_done_callback(_run_tasks.discard)
  return {"status": "running", "run_id": run_id}


@router.get("/runs", summary="Lấy danh sách các lần chạy chatbot")
def list_chatbot_runs():
  return {"runs": global_event_bus.get_runs()}


@router.get("/events", summary="Nhận sự kiện chatbot theo luồng SSE")
async def stream_chatbot_events(
    request: Request,
    run_id: str | None = Query(default=None),
):
  last_event_id = request.headers.get("last-event-id")
  try:
    event_cursor = int(last_event_id) if last_event_id else 0
  except ValueError as exc:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Last-Event-ID phải là số nguyên.",
    ) from exc
  if event_cursor < 0:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Last-Event-ID không được là số âm.",
    )

  queue = await global_event_bus.subscribe()

  async def event_stream():
    replay_event_ids = set()
    try:
      if last_event_id:
        initial_events = global_event_bus.get_events_since(
            event_cursor, run_id
        )
      elif run_id:
        initial_events = global_event_bus.get_events(run_id)
      else:
        initial_events = []

      for event in initial_events:
        replay_event_ids.add(event["event_id"])
        yield (
            f"id: {event['event_id']}\n"
            f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        )
        if event["step"] == "run" and event["status"] in {"completed", "failed"}:
          return

      while not await request.is_disconnected():
        try:
          event = await asyncio.wait_for(queue.get(), timeout=15)
        except asyncio.TimeoutError:
          yield ": keep-alive\n\n"
          continue

        if run_id and event["run_id"] != run_id:
          continue
        if event["event_id"] in replay_event_ids:
          replay_event_ids.remove(event["event_id"])
          continue

        yield (
            f"id: {event['event_id']}\n"
            f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        )
        if (
            run_id
            and event["step"] == "run"
            and event["status"] in {"completed", "failed"}
        ):
          return
    finally:
      global_event_bus.unsubscribe(queue)

  return StreamingResponse(
      event_stream(),
      media_type="text/event-stream",
      headers={
          "Cache-Control": "no-cache",
          "X-Accel-Buffering": "no",
          "Connection": "keep-alive",
      },
  )


@router.get("/runs/{run_id}", summary="Lấy log và kết quả của một lần chạy")
def get_chatbot_run(run_id: str):
  events = global_event_bus.get_events(run_id)
  if not events:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Không tìm thấy lần chạy chatbot này.",
    )

  run_event = next(
      (event for event in reversed(events) if event["step"] == "run"),
      events[0],
  )
  response = {
      "run_id": run_id,
      "status": run_event["status"],
      "events": events,
  }
  if run_event["status"] == "completed":
    response.update(run_event["details"])
  elif run_event["status"] == "failed":
    response["error"] = run_event["details"]["message"]
  return response






from fastapi import Path

# ==========================================
# API 1: Lấy lịch sử trò chuyện theo chat_id
# ==========================================
@router.get("/chats", summary="Lấy danh sách các phiên chat của người dùng")
def list_chat_history(
    employee: dict[str, Any] = Depends(get_authenticated_employee),
):
    user_id = employee.get("employee_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản chưa được liên kết với mã nhân viên.",
        )

    try:
        messages = db.select(
            "chat_messages",
            filters={"user_id": user_id},
            order_by="created_at",
            desc=False,
        )
        chats: dict[str, dict[str, Any]] = {}
        for message in messages:
            chat_id = message.get("chat_id")
            if not chat_id:
                continue

            chat = chats.setdefault(
                chat_id,
                {
                    "chat_id": chat_id,
                    "title": "Cuộc trò chuyện mới",
                    "created_at": message.get("created_at"),
                    "updated_at": message.get("created_at"),
                    "total_messages": 0,
                },
            )
            chat["updated_at"] = message.get("created_at")
            chat["total_messages"] += 1
            if message.get("title"):
                chat["title"] = message["title"]
            elif (
                message.get("role") == "user"
                and chat["title"] == "Cuộc trò chuyện mới"
            ):
                content = (message.get("content") or "").strip()
                if content:
                    chat["title"] = (
                        content if len(content) <= 60 else f"{content[:57]}..."
                    )

        return {
            "chats": sorted(
                chats.values(),
                key=lambda chat: chat.get("updated_at") or "",
                reverse=True,
            )
        }
    except Exception as exc:
        logger.exception("Lấy danh sách lịch sử chat thất bại")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/chats/{chat_id}/history", summary="Lấy lịch sử tin nhắn của một phiên chat")
def get_chat_history(
    chat_id: str = Path(..., description="Mã phiên hội thoại (chat_id)"),
    employee: dict[str, Any] = Depends(get_authenticated_employee),
):
    """
    Lấy toàn bộ lịch sử tin nhắn của một phiên chat cụ thể dựa vào chat_id,
    được sắp xếp theo thời gian tăng dần để đưa vào Agent hoặc hiển thị lên giao diện.
    """
    try:
        user_id = employee.get("employee_id")
        
        # Truy vấn dữ liệu từ bảng chat_messages, lọc theo user_id và chat_id, sắp xếp tăng dần theo created_at
        messages = db.select(
            "chat_messages",
            filters={"chat_id": chat_id, "user_id": user_id},
            order_by="created_at",
            desc=False
        )
        
        return {
            "chat_id": chat_id,
            "title": next(
                (message.get("title") for message in messages if message.get("title")),
                next(
                    (
                        message.get("content", "").strip()[:60]
                        for message in messages
                        if message.get("role") == "user"
                        and message.get("content", "").strip()
                    ),
                    "Cuộc trò chuyện mới",
                ),
            ),
            "total_messages": len(messages),
            "messages": messages
        }
    except Exception as e:
        logger.exception("Lấy lịch sử chat thất bại (chat_id=%s)", chat_id)
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# API 2: Gửi / Lưu một tin nhắn mới vào phiên chat
# ==========================================
class ChatMessageCreate(BaseModel):
    chat_id: str = Field(..., min_length=1, description="Mã phiên hội thoại")
    title: str | None = Field(default=None, description="Tiêu đề phiên hội thoại")
    role: Literal["user", "assistant", "system"] = Field(..., description="Vai trò của người gửi tin nhắn")
    content: str = Field(..., min_length=1, description="Nội dung tin nhắn")


@router.post("/chats/messages", summary="Lưu tin nhắn mới vào lịch sử hội thoại")
def save_chat_message(
    payload: ChatMessageCreate,
    employee: dict[str, Any] = Depends(get_authenticated_employee),
):
    """
    Lưu một tin nhắn mới (của user hoặc assistant) vào bảng chat_messages trên Supabase.
    """
    try:
        user_id = employee.get("employee_id")
        
        data = {
            "user_id": user_id,
            "chat_id": payload.chat_id,
            "title": (
                payload.title
                or (
                    payload.content.strip()[:60]
                    if payload.role == "user"
                    else "Cuộc trò chuyện mới"
                )
            ),
            "role": payload.role,
            "content": payload.content
        }
        
        result = db.insert("chat_messages", data)
        if not result:
            raise HTTPException(status_code=400, detail="Không thể lưu tin nhắn vào cơ sở dữ liệu.")
            
        return {
            "message": "Lưu tin nhắn thành công",
            "data": result[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Lưu tin nhắn thất bại")
        raise HTTPException(status_code=500, detail=str(e))


