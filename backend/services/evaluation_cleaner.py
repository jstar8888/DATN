# evaluation_cleaner.py
import json
import re
from typing import Any, Dict, List
import pandas as pd
from datamodel.project_evaluation_schema import *


def extract_json_block(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    json_str = fenced.group(1) if fenced else text

    if not fenced:
        start = json_str.find("{")
        end = json_str.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = json_str[start : end + 1]

    return json.loads(json_str)


def build_deterministic_metrics(projects: List[Dict[str, Any]], tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tính trước các chỉ số cơ bản từ DB để đối chiếu và làm fallback khi cần."""
    tasks_by_project: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        pid = str(t.get("project_id", ""))
        tasks_by_project.setdefault(pid, []).append(t)

    enriched_projects = []
    for p in projects:
        pid = str(p.get("project_id", ""))
        p_tasks = tasks_by_project.get(pid, [])
        task_count = len(p_tasks)

        est_hours = round(sum(float(t.get("estimated_hours") or 0) for t in p_tasks), 2)
        act_hours = round(sum(float(t.get("actual_hours") or 0) for t in p_tasks), 2)
        avg_progress = (
            round(sum(float(t.get("progress_percent") or 0) for t in p_tasks) / task_count, 2)
            if task_count > 0
            else 0.0
        )
        delayed_tasks = sum(
            1
            for t in p_tasks
            if str(t.get("status", "")).lower() not in {"hoàn thành", "done", "completed", "đã hoàn thành"}
            and float(t.get("progress_percent") or 0) < 100
        )

        enriched_projects.append(
            {
                **p,
                "task_count": task_count,
                "total_estimated_hours": est_hours,
                "total_actual_hours": act_hours,
                "avg_task_progress_percent": avg_progress,
                "unfinished_task_count": delayed_tasks,
            }
        )

    return {
        "total_projects": len(projects),
        "total_tasks": len(tasks),
        "projects": enriched_projects,
    }


def sanitize_evaluation_output(
    raw_llm_text: str,
    projects: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
) -> AllProjectsEvaluationResult:
    """Parse, validate và làm sạch dữ liệu để Streamlit vẽ biểu đồ an toàn."""
    try:
        parsed = extract_json_block(raw_llm_text)
        result = AllProjectsEvaluationResult.model_validate(parsed)
    except Exception:
        result = _fallback_from_raw_data(projects, tasks)

    # Lọc bỏ các dòng thống kê có count <= 0 để biểu đồ tròn gọn đẹp
    result.pie_by_status = [s for s in result.pie_by_status if s.count > 0]
    result.pie_by_feasibility = [s for s in result.pie_by_feasibility if s.count > 0]

    # Chuẩn hóa dữ liệu biểu đồ cột: không để NaN, làm tròn số
    valid_bars = []
    for row in result.bar_projects_comparison:
        valid_bars.append(
            row.model_copy(
                update={
                    "project_name": row.project_name.strip() or row.project_id,
                    "avg_progress_percent": round(max(0.0, min(100.0, float(row.avg_progress_percent))), 1),
                    "estimated_hours": round(max(0.0, float(row.estimated_hours)), 1),
                    "actual_hours": round(max(0.0, float(row.actual_hours)), 1),
                }
            )
        )
    result.bar_projects_comparison = valid_bars

    # Sắp xếp cảnh báo theo mức độ ưu tiên: Cao -> Trung bình -> Thấp
    risk_order = {"Cao": 0, "Trung bình": 1, "Thấp": 2}
    result.risk_warnings.sort(key=lambda w: risk_order.get(w.risk_level, 99))

    return result


def _fallback_from_raw_data(
    projects: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
) -> AllProjectsEvaluationResult:
    metrics = build_deterministic_metrics(projects, tasks)["projects"]
    status_counts: Dict[str, int] = {}
    bars = []

    for p in metrics:
        st_name = str(p.get("status") or "Không xác định")
        status_counts[st_name] = status_counts.get(st_name, 0) + 1
        bars.append(
            ProjectWorkloadBarItem(
                project_id=str(p.get("project_id", "")),
                project_name=str(p.get("project_name", p.get("project_id", ""))),
                avg_progress_percent=p["avg_task_progress_percent"],
                estimated_hours=p["total_estimated_hours"],
                actual_hours=p["total_actual_hours"],
                task_count=p["task_count"],
                overdue_or_at_risk_tasks=p["unfinished_task_count"],
            )
        )

    return AllProjectsEvaluationResult(
        executive_summary="Dữ liệu tổng hợp tự động từ hệ thống (chế độ dự phòng do định dạng phản hồi LLM chưa chuẩn JSON).",
        pie_by_status=[ProjectStatusStat(status=k, count=v) for k, v in status_counts.items()],
        pie_by_feasibility=[],
        bar_projects_comparison=bars,
        risk_warnings=[],
    )


def to_chart_dataframes(result: AllProjectsEvaluationResult) -> Dict[str, pd.DataFrame]:
    """Chuyển đổi sang DataFrame sạch, không có NaN cho Streamlit."""
    df_status = pd.DataFrame([s.model_dump() for s in result.pie_by_status])
    df_feasibility = pd.DataFrame([s.model_dump() for s in result.pie_by_feasibility])
    df_bars = pd.DataFrame([b.model_dump() for b in result.bar_projects_comparison])

    for df in (df_status, df_feasibility, df_bars):
        if not df.empty:
            df.dropna(how="all", inplace=True)

    return {
        "pie_status": df_status,
        "pie_feasibility": df_feasibility,
        "bar_projects": df_bars,
    }