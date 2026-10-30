import json
from typing import Any

from agents.agent_evaluate import EvaluateAgent
from agents.agent_rag_search import RAGSearchAgent
from agents.agent_sql_search import SqlSearchAgent
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict


class RequestEvaluationState(TypedDict, total=False):
    command: str
    context: dict[str, Any]
    run_id: str
    sql_data: dict[str, Any]
    rag_data: list[dict[str, Any]]
    final_answer: str


def sql_search_node(state: RequestEvaluationState) -> dict[str, Any]:
    sql_data = SqlSearchAgent().search(
        state["command"],
        state["context"],
        run_id=state.get("run_id"),
    )
    return {"sql_data": sql_data}


def rag_search_node(state: RequestEvaluationState) -> dict[str, Any]:
    if state["command"] == "OT":
        query = (
            "Quy định, chính sách và quy trình phê duyệt làm thêm giờ (OT), "
            "bao gồm điều kiện, giới hạn số giờ, yêu cầu báo cáo công việc "
            "và chấm công."
        )
    elif state["command"] == "LEAVE_REQUEST":
        query = (
            "Quy định, chính sách và quy trình phê duyệt đơn xin nghỉ phép, "
            "bao gồm điều kiện nghỉ, hạn mức và yêu cầu bàn giao công việc."
        )
    else:
        raise ValueError(f"Loại yêu cầu đánh giá không hợp lệ: {state['command']}")

    rag_data = RAGSearchAgent().search(query, run_id=state.get("run_id"))
    return {"rag_data": rag_data}


def evaluate_node(state: RequestEvaluationState) -> dict[str, str]:
    rag_data = json.dumps(state.get("rag_data", []), ensure_ascii=False, default=str)
    answer = EvaluateAgent().evaluate(
        command=state["command"],
        rag_data=rag_data,
        sql_data=state["sql_data"],
        run_id=state.get("run_id"),
    )
    return {"final_answer": answer}


workflow = StateGraph(RequestEvaluationState)
workflow.add_node("sql_search", sql_search_node)
workflow.add_node("rag_search", rag_search_node)
workflow.add_node("evaluate", evaluate_node)
workflow.set_entry_point("sql_search")
workflow.add_edge("sql_search", "rag_search")
workflow.add_edge("rag_search", "evaluate")
workflow.add_edge("evaluate", END)

app = workflow.compile()
