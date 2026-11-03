from pathlib import Path
from typing import Any
import logging
from agents.agent_rag_search import RAGSearchAgent
from agents.agent_router import RouterAgent
from agents.agent_sql_expert import SQLGraphAgent
from agents.agent_sql_executor import SQLExecutorAgent
from agents.agent_synthesizer import SynthesizerAgent
from agents.agent_query_rewriter import QueryRewriterAgent  # Agent viết lại câu hỏi theo ngữ cảnh
from agents.guardrails import (
    input_guardrail_node,
    route_after_input_guardrail,
)
from database.supabase_general_service import SupabaseService  # Dùng để gọi DB lấy/lưu lịch sử
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict
from utils.event_bus import global_event_bus

router = RouterAgent()
query_rewriter = QueryRewriterAgent()  # Khởi tạo QueryRewriterAgent
db = SupabaseService()                 # Khởi tạo Service kết nối Supabase

config_dir = Path(__file__).resolve().parents[1] / "config"
sql_expert = SQLGraphAgent(
    str(config_dir / "table_relationships_and_paths.json"),
    semantic_profiles_path=str(config_dir / "table_semantic_profiles.json"),
)
sql_executor = SQLExecutorAgent()
rag_search = RAGSearchAgent()
synthesizer = SynthesizerAgent()


class HRGraphState(TypedDict, total=False):
  question: str          # Câu hỏi thô từ người dùng
  clean_question: str    # Câu hỏi sau khi đã được QueryRewriter biên dịch
  chat_id: str           # Mã phiên hội thoại
  title: str             # Tiêu đề phiên hội thoại
  user_id: str           # Mã nhân viên/người dùng
  run_id: str
  intent: str
  sql_question: str
  rag_question: str
  sql_query: str
  sql_data: Any
  rag_data: Any
  sql_branch_message: str
  raw_data: Any
  final_answer: str
  guardrail_action: str
  guardrail_stage: str
  guardrail_reason: str
  guardrail_rule: str | None
  semantic_system_context: str


def query_rewriter_node(state: HRGraphState) -> dict[str, Any]:
  """
  Node đầu tiên: Đọc lịch sử chat từ Supabase và gọi QueryRewriterAgent 
  để biến câu hỏi cụt lủn/mơ hồ thành câu hỏi độc lập.
  """
  run_id = state.get("run_id")
  chat_id = state.get("chat_id")
  user_id = state.get("user_id")
  raw_question = state["question"]

  if run_id:
    global_event_bus.publish_event(
        run_id,
        "query_rewriter",
        "started",
        {"message": "Đang đọc lịch sử và biên dịch câu hỏi theo ngữ cảnh."},
        agent="query_rewriter",
    )

  chat_history = []
  title = raw_question.strip()[:60] or "Cuộc trò chuyện mới"
  if chat_id and user_id:
    try:
      # Lấy lịch sử tin nhắn cũ từ bảng chat_messages (sắp xếp tăng dần theo thời gian)
      messages = db.select(
          "chat_messages",
          filters={"chat_id": chat_id, "user_id": user_id},
          order_by="created_at",
          desc=False,
      )
      # Format lại danh sách message để truyền vào rewriter
      chat_history = [
          {"role": msg.get("role"), "content": msg.get("content")}
          for msg in messages
          if msg.get("role") in {"user", "assistant"}
      ]
      title = next(
          (
              msg.get("title")
              for msg in messages
              if msg.get("title")
          ),
          None,
      ) or next(
          (
              msg["content"].strip()[:60]
              for msg in messages
              if msg.get("role") == "user" and msg.get("content", "").strip()
          ),
          title,
      )
    except Exception:
      logger_exc = logging.getLogger(__name__)
      logger_exc.exception("Không thể tải lịch sử chat cho chat_id=%s", chat_id)

  # Gọi agent biên dịch câu hỏi
  clean_question = query_rewriter.rewrite(
      chat_history=chat_history,
      current_question=raw_question,
      run_id=run_id,
  )

  if run_id:
    global_event_bus.publish_event(
        run_id,
        "query_rewriter",
        "completed",
        {"clean_question": clean_question},
        agent="query_rewriter",
    )

  # Trả về câu hỏi đã làm sạch để các node sau sử dụng
  return {"clean_question": clean_question, "title": title}


def guardrail_node(state: HRGraphState):
  run_id = state.get("run_id")
  # Sử dụng clean_question để kiểm tra guardrail thay vì câu hỏi thô
  working_state = {**state, "question": state.get("clean_question", state["question"])}
  
  if run_id:
    global_event_bus.publish_event(
        run_id,
        "guardrail",
        "started",
        {"message": "Đang kiểm tra an toàn và phạm vi câu hỏi."},
        agent="guardrails",
    )
  try:
    result = input_guardrail_node(working_state)
  except Exception:
    if run_id:
      global_event_bus.publish_event(
          run_id,
          "guardrail",
          "failed",
          {"message": "Không thể kiểm tra an toàn câu hỏi."},
          agent="guardrails",
      )
    raise

  action = result["guardrail_action"]
  if action != "allow":
    result.update({"intent": "BLOCKED", "raw_data": []})
    if action == "review":
      result["final_answer"] = (
          "Yêu cầu cần được kiểm tra thêm trước khi xử lý."
      )

  if run_id:
    global_event_bus.publish_event(
        run_id,
        "guardrail",
        "completed",
        {
            "action": action,
            "stage": result["guardrail_stage"],
            "reason": result["guardrail_reason"],
            "matched_rule": result["guardrail_rule"],
        },
        agent="guardrails",
    )
  return result


def router_node(state: HRGraphState) -> dict[str, Any]:
  # Router nhận câu hỏi đã được làm sạch (clean_question)
  target_question = state.get("clean_question", state["question"])
  result = router.route(
      target_question,
      run_id=state.get("run_id"),
      semantic_context=state.get("semantic_system_context"),
  )
  if result["intent"] == "OUT_OF_SCOPE":
    result["raw_data"] = []
  return result


def sql_node(state: HRGraphState):
  run_id = state["run_id"]
  global_event_bus.publish_event(
      run_id,
      "sql",
      "started",
      {"message": "Đang xử lý nhánh SQL."},
      agent="orchestrator",
  )
  try:
    target_q = state.get("sql_question", state.get("clean_question", state["question"]))
    result = sql_expert.process(target_q, run_id=run_id)
    sql_query = result["sql_query"]
    if sql_query == "-- INSUFFICIENT_SCHEMA":
      message = (
          "Mình chưa thể truy vấn vì chưa xác định được bảng phù hợp "
          "với câu hỏi này."
      )
      global_event_bus.publish_event(
          run_id,
          "sql",
          "completed",
          {"result": "insufficient_schema"},
          agent="orchestrator",
      )
      if state["intent"] == "SQL":
        return {"final_answer": message, "sql_data": [], "raw_data": []}
      return {
          "sql_query": sql_query,
          "sql_data": [],
          "sql_branch_message": message,
      }
    if sql_query == "-- NEEDS_CLARIFICATION":
      message = (
          "Câu hỏi chưa đủ rõ để tạo truy vấn. Bạn vui lòng bổ sung "
          "thông tin cần tra cứu."
      )
      global_event_bus.publish_event(
          run_id,
          "sql",
          "completed",
          {"result": "needs_clarification"},
          agent="orchestrator",
      )
      if state["intent"] == "SQL":
        return {"final_answer": message, "sql_data": [], "raw_data": []}
      return {
          "sql_query": sql_query,
          "sql_data": [],
          "sql_branch_message": message,
      }

    raw_data = sql_executor.process(sql_query, run_id=run_id)
  except Exception:
    global_event_bus.publish_event(
        run_id,
        "sql",
        "failed",
        {"message": "Không thể xử lý truy vấn SQL."},
        agent="orchestrator",
    )
    raise

  global_event_bus.publish_event(
      run_id,
      "sql",
      "completed",
      {"has_data": bool(raw_data), "row_count": len(raw_data)},
      agent="orchestrator",
  )
  result = {"sql_query": sql_query, "sql_data": raw_data}
  if state["intent"] == "SQL":
    result["raw_data"] = raw_data
  return result


def rag_node(state: HRGraphState):
  run_id = state["run_id"]
  global_event_bus.publish_event(
      run_id,
      "rag",
      "started",
      {"message": "Đang xử lý nhánh RAG."},
      agent="orchestrator",
  )
  try:
    target_q = state.get("rag_question", state.get("clean_question", state["question"]))
    rag_data = rag_search.search(target_q, run_id=run_id)
  except Exception:
    global_event_bus.publish_event(
        run_id,
        "rag",
        "failed",
        {"message": "Không thể tìm kiếm nội dung tài liệu."},
        agent="orchestrator",
    )
    raise
  global_event_bus.publish_event(
      run_id,
      "rag",
      "completed",
      {"has_chunks": bool(rag_data), "chunk_count": len(rag_data)},
      agent="orchestrator",
  )
  result = {"rag_data": rag_data}
  if state["intent"] == "RAG":
    result["raw_data"] = rag_data
  return result


def synthesizer_node(state: HRGraphState):
  if state["intent"] == "HYBRID":
    raw_data = {
        "sql_data": state.get("sql_data", []),
        "rag_data": state.get("rag_data", []),
    }
    if state.get("sql_branch_message"):
      raw_data["sql_branch_message"] = state["sql_branch_message"]
  else:
    raw_data = state["raw_data"]

  # Synthesizer có thể nhận thêm lịch sử nếu muốn, ở đây dùng câu hỏi gốc của user
  answer = synthesizer.synthesize(
      state["question"], raw_data, run_id=state["run_id"]
  )
  return {"final_answer": answer, "raw_data": raw_data}


def save_history_node(state: HRGraphState) -> dict[str, Any]:
  """
  Node cuối cùng: Lưu lại lịch sử chat (câu hỏi của user và câu trả lời của bot)
  vào bảng chat_messages trên Supabase khi phiên chat hoàn thành thành công.
  """
  chat_id = state.get("chat_id")
  user_id = state.get("user_id")
  question = state.get("question")
  final_answer = state.get("final_answer")
  title = state.get("title") or (
      question.strip()[:60] if question else "Cuộc trò chuyện mới"
  )

  if chat_id and user_id and question and final_answer:
    try:
      # 1. Lưu câu hỏi của user
      db.insert("chat_messages", {
          "user_id": user_id,
          "chat_id": chat_id,
          "title": title,
          "role": "user",
          "content": question
      })
      # 2. Lưu câu trả lời của trợ lý (assistant)
      db.insert("chat_messages", {
          "user_id": user_id,
          "chat_id": chat_id,
          "title": title,
          "role": "assistant",
          "content": final_answer
      })
    except Exception:
      logger_exc = logging.getLogger(__name__)
      logger_exc.exception("Lưu lịch sử chat vào Supabase thất bại cho chat_id=%s", chat_id)

  return {}


# Xây dựng LangGraph Workflow
workflow = StateGraph(HRGraphState)

# Thêm các Node vào đồ thị
workflow.add_node("query_rewriter", query_rewriter_node) # Node mới đầu tiên
workflow.add_node("input_guardrail", guardrail_node)
workflow.add_node("router", router_node)
workflow.add_node("sql_processor", sql_node)
workflow.add_node("rag_processor", rag_node)
workflow.add_node("synthesizer", synthesizer_node)
workflow.add_node("save_history", save_history_node)       # Node mới cuối cùng

# Thiết lập điểm bắt đầu đi từ query_rewriter
workflow.set_entry_point("query_rewriter")


def decide_next_step(state: HRGraphState):
  if state["intent"] == "OUT_OF_SCOPE":
    selected_nodes = []
  elif state["intent"] == "SQL":
    selected_nodes = ["sql_processor"]
  elif state["intent"] == "RAG":
    selected_nodes = ["rag_processor"]
  else:
    selected_nodes = ["sql_processor", "rag_processor"]

  global_event_bus.publish_event(
      state["run_id"],
      "route",
      "completed",
      {
          "intent": state["intent"],
          "selected_nodes": selected_nodes,
      },
      agent="router",
  )
  if state["intent"] == "OUT_OF_SCOPE":
    return "save_history"  # Nếu bị ngoài phạm vi vẫn lưu lại lịch sử hỏi-đáp từ chối
  return selected_nodes if state["intent"] == "HYBRID" else selected_nodes[0]


def decide_after_sql(state: HRGraphState):
  if state["intent"] == "SQL" and state.get("final_answer"):
    return "save_history"
  return "synthesizer"


# Thiết lập các luồng cạnh (Edges)
workflow.add_edge("query_rewriter", "input_guardrail")

workflow.add_conditional_edges(
    "input_guardrail",
    route_after_input_guardrail,
    {"router": "router", "stop": "save_history", "review": "save_history"},
)

workflow.add_conditional_edges(
    "router",
    decide_next_step,
    {
        "sql_processor": "sql_processor",
        "rag_processor": "rag_processor",
        "save_history": "save_history",
    },
)

workflow.add_conditional_edges(
    "sql_processor",
    decide_after_sql,
    {"synthesizer": "synthesizer", "save_history": "save_history"},
)

workflow.add_edge("rag_processor", "synthesizer")
workflow.add_edge("synthesizer", "save_history")
workflow.add_edge("save_history", END)

app = workflow.compile()