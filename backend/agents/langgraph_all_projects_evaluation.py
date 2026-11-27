# langgraph_all_projects_evaluation.py
from typing import Any

from agents.agent_evaluate import EvaluateAgent
from agents.agent_sql_search import SqlSearchAgent
from langgraph.graph import END, StateGraph
from datamodel.project_evaluation_schema import AllProjectsEvaluationResult
from typing_extensions import TypedDict


class AllProjectsEvaluationState(TypedDict, total=False):
    context: dict[str, Any]
    run_id: str
    sql_data: dict[str, Any]
    evaluation_result: AllProjectsEvaluationResult
    chart_dfs: dict[str, Any]
    final_answer: str


def sql_search_node(state: AllProjectsEvaluationState) -> dict[str, Any]:
    sql_data = SqlSearchAgent().search(
        command="ALL_PROJECTS",
        context=state.get("context") or {},
        run_id=state.get("run_id"),
    )
    return {"sql_data": sql_data}


def evaluate_node(state: AllProjectsEvaluationState) -> dict[str, Any]:
    sql_data = state.get("sql_data") or {}
    projects = sql_data.get("projects") or []
    tasks = sql_data.get("tasks") or []

    cleaned_result, chart_dfs = EvaluateAgent().evaluate_all_projects(
        projects=projects,
        tasks=tasks,
        run_id=state.get("run_id"),
    )
    return {
        "evaluation_result": cleaned_result,
        "chart_dfs": chart_dfs,
        "final_answer": cleaned_result.executive_summary,
    }


workflow = StateGraph(AllProjectsEvaluationState)
workflow.add_node("sql_search", sql_search_node)
workflow.add_node("evaluate", evaluate_node)

workflow.set_entry_point("sql_search")
workflow.add_edge("sql_search", "evaluate")
workflow.add_edge("evaluate", END)

app = workflow.compile()