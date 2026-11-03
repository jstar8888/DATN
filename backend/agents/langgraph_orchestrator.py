from pathlib import Path
from typing import Any

from agents.agent_rag_search import RAGSearchAgent
from agents.agent_router import RouterAgent
from agents.agent_sql_expert import SQLGraphAgent
from agents.agent_sql_executor import SQLExecutorAgent
from agents.agent_synthesizer import SynthesizerAgent
from agents.guardrails import (
    input_guardrail_node,
    route_after_input_guardrail,
)
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict
from utils.event_bus import global_event_bus

router = RouterAgent()
config_dir = Path(__file__).resolve().parents[1] / "config"
sql_expert = SQLGraphAgent(
    str(config_dir / "table_relationships_and_paths.json"),
    semantic_profiles_path=str(config_dir / "table_semantic_profiles.json"),
)
sql_executor = SQLExecutorAgent()
rag_search = RAGSearchAgent()
synthesizer = SynthesizerAgent()


class HRGraphState(TypedDict, total=False):
  question: str
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


def guardrail_node(state: HRGraphState):
  run_id = state.get("run_id")
  if run_id:
    global_event_bus.publish_event(
        run_id,
        "guardrail",
        "started",
        {"message": "Đang kiểm tra an toàn và phạm vi câu hỏi."},
        agent="guardrails",
    )
  try:
    result = input_guardrail_node(state)
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
  result = router.route(
      state["question"],
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
    result = sql_expert.process(
        state.get("sql_question", state["question"]), run_id=run_id
    )
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
    rag_data = rag_search.search(
        state.get("rag_question", state["question"]),
        run_id=run_id,
    )
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

  answer = synthesizer.synthesize(
      state["question"], raw_data, run_id=state["run_id"]
  )
  return {"final_answer": answer, "raw_data": raw_data}


workflow = StateGraph(HRGraphState)
workflow.add_node("input_guardrail", guardrail_node)
workflow.add_node("router", router_node)
workflow.add_node("sql_processor", sql_node)
workflow.add_node("rag_processor", rag_node)
workflow.add_node("synthesizer", synthesizer_node)
workflow.set_entry_point("input_guardrail")


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
    return END
  return selected_nodes if state["intent"] == "HYBRID" else selected_nodes[0]


def decide_after_sql(state: HRGraphState):
  if state["intent"] == "SQL" and state.get("final_answer"):
    return END
  return "synthesizer"


workflow.add_conditional_edges(
    "input_guardrail",
    route_after_input_guardrail,
    {"router": "router", "stop": END, "review": END},
)
workflow.add_conditional_edges(
    "router",
    decide_next_step,
    {
        "sql_processor": "sql_processor",
        "rag_processor": "rag_processor",
        END: END,
    },
)
workflow.add_conditional_edges(
    "sql_processor",
    decide_after_sql,
    {"synthesizer": "synthesizer", END: END},
)
workflow.add_edge("rag_processor", "synthesizer")
workflow.add_edge("synthesizer", END)

app = workflow.compile()

if __name__ == "__main__":
  result = app.invoke({
      "question": "Tháng này nhân viên Bảo làm OT mấy giờ?",
      "run_id": "local-test",
  })
  print("\nKẾT QUẢ:", result["final_answer"])
