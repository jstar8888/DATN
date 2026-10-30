import asyncio
import json
import logging
from uuid import uuid4

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from utils.event_bus import global_event_bus

router = APIRouter(prefix="/api/agent", tags=["AI Agent"])
logger = logging.getLogger(__name__)
_run_tasks = set()


class ChatbotRequest(BaseModel):
  question: str = Field(..., min_length=1, description="Câu hỏi gửi tới chatbot")


async def _run_chatbot(run_id: str, question: str):
  try:
    from agents.langgraph_orchestrator import app as chatbot_workflow

    result = await asyncio.to_thread(
        chatbot_workflow.invoke,
        {"question": question, "run_id": run_id},
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
  except Exception:
    logger.exception("Chatbot xử lý câu hỏi thất bại (run_id=%s)", run_id)
    global_event_bus.publish_event(
        run_id,
        "run",
        "failed",
        {"message": "Chatbot không thể xử lý câu hỏi lúc này."},
        agent="orchestrator",
    )


@router.post(
    "/chatbot",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bắt đầu xử lý câu hỏi qua chatbot AI",
)
async def chatbot(payload: ChatbotRequest):
  run_id = str(uuid4())
  global_event_bus.publish_event(
      run_id,
      "run",
      "running",
      {"question": payload.question},
      agent="orchestrator",
  )
  task = asyncio.create_task(_run_chatbot(run_id, payload.question))
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