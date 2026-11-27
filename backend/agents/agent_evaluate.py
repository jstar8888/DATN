# agent_evaluate.py
import json
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage
from agents.configurable_llm import ConfigurableChatModel

from datamodel.project_evaluation_schema import AllProjectsEvaluationResult
from services.evaluation_cleaner import (
    build_deterministic_metrics,
    sanitize_evaluation_output,
    to_chart_dataframes,
)
from utils.event_bus import global_event_bus
from utils.llm_usage import extract_token_usage


class EvaluateAgent:
    """Evaluate HR requests and project portfolios using LLM-backed analysis."""

    def __init__(self):
        self.llm = ConfigurableChatModel(
            "evaluate",
            temperature=0.1,
            reasoning=False,
        )

    def evaluate(
        self,
        command: str,
        rag_data: str,
        sql_data: Dict[str, Any] | str,
        run_id: Optional[str] = None,
    ) -> str:
        prompt = """
Bạn là AI Evaluate Agent chuyên trách thẩm định, đánh giá tính hợp lệ và rủi ro của các yêu cầu nhân sự (OT, Xin nghỉ phép) bằng cách đối soát 3 nguồn thông tin:
1. COMMAND (Loại việc cần phân tích): Xác định đúng ngữ cảnh nghiệp vụ.
2. RAG_DATA (Quy định & Chính sách): Các căn cứ, điều khoản và hạn mức từ tài liệu nội bộ.
3. SQL_DATA (Dữ liệu thực tế dạng JSON): Thông tin chi tiết về dự án, task, báo cáo công việc hàng ngày, dữ liệu chấm công và vi phạm.

NHIỆM VỤ ĐÁNH GIÁ:
- Đối với OT: Kiểm tra sự phù hợp giữa báo cáo công việc (daily_reports), tiến độ task, lịch sử chấm công (attendance) và quy định số giờ OT tối đa.
- Đối với Leave_request: Kiểm tra các task đang phụ trách (current_assigned_tasks) xem có xung đột tiến độ dự án khi xin nghỉ hay không.
- Chỉ đưa ra thông tin và nhận định được hỗ trợ trực tiếp bởi dữ liệu đầu vào.
- Trình bày kết quả rõ ràng, chuyên nghiệp bằng định dạng Markdown.
"""

        if run_id:
            global_event_bus.publish_event(
                run_id,
                "evaluate_agent",
                "started",
                {"message": f"Bắt đầu đánh giá yêu cầu cho luồng {command}."},
                agent="evaluate_agent",
            )

        try:
            if isinstance(sql_data, dict):
                sql_data_str = json.dumps(sql_data, ensure_ascii=False, default=str)
            else:
                sql_data_str = str(sql_data)

            content = (
                f"=== COMMAND ===\n{command}\n\n"
                f"=== RAG_DATA ===\n{rag_data if rag_data else 'Không có dữ liệu văn bản quy định'}\n\n"
                f"=== SQL_DATA (JSON) ===\n{sql_data_str}"
            )

            res = self.llm.invoke(
                [SystemMessage(content=prompt), HumanMessage(content=content)]
            )
            answer = res.content.strip()
            if not answer:
                raise ValueError("Evaluate Agent trả về kết quả rỗng.")
        except Exception:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "evaluate_agent",
                    "failed",
                    {"message": "Thẩm định thất bại."},
                    agent="evaluate_agent",
                )
            raise

        if run_id:
            details: dict[str, Any] = {
                "message": "Đã hoàn tất đánh giá thành công."
            }
            token_usage = extract_token_usage(res)
            if token_usage is not None:
                details["token_usage"] = token_usage
            global_event_bus.publish_event(
                run_id,
                "evaluate_agent",
                "completed",
                details,
                agent="evaluate_agent",
            )
        return answer

    def evaluate_all_projects(
        self,
        projects: List[Dict[str, Any]],
        tasks: List[Dict[str, Any]],
        run_id: Optional[str] = None,
    ) -> Tuple[AllProjectsEvaluationResult, Dict[str, Any]]:
        prompt = """
    Bạn là AI Project Portfolio Evaluator chuyên đánh giá toàn bộ danh mục dự án và hệ thống task của doanh nghiệp.

    NHIỆM VỤ:
    1. Phân tích toàn bộ dự án (`projects`) và danh sách task (`tasks`) kèm các chỉ số đã tổng hợp (`avg_task_progress_percent`, `total_estimated_hours`, `total_actual_hours`, `unfinished_task_count`).
    2. Thống kê số lượng cho 2 biểu đồ tròn:
    - `pie_by_status`: Phân bố số lượng dự án theo trạng thái hiện tại (`status`).
    - `pie_by_feasibility`: Phân loại mức độ khả thi của các dự án (ví dụ: "Khả thi", "Cần theo dõi", "Rủi ro kém khả thi").
    3. Tổng hợp dữ liệu cho biểu đồ cột (`bar_projects_comparison`) để so sánh từng dự án (tiến độ %, giờ dự kiến vs giờ thực tế, số task chưa hoàn tất).
    4. Lập danh sách `risk_warnings` cho các dự án có dấu hiệu tiến độ không ổn, vượt/lệch giờ làm, nhiều task tồn đọng, sát deadline hoặc có nguy cơ kém khả thi.
    5. CHỈ trả về DUY NHẤT một đối tượng JSON hợp lệ theo schema yêu cầu, KHÔNG thêm lời dẫn hay giải thích ngoài JSON.

    SCHEMA JSON MONG MUỐN:
    {
    "executive_summary": "string",
    "pie_by_status": [{"status": "string", "count": 0}],
    "pie_by_feasibility": [{"status": "string", "count": 0}],
    "bar_projects_comparison": [
        {
        "project_id": "string",
        "project_name": "string",
        "avg_progress_percent": 0.0,
        "estimated_hours": 0.0,
        "actual_hours": 0.0,
        "task_count": 0,
        "overdue_or_at_risk_tasks": 0
        }
    ],
    "risk_warnings": [
        {
        "project_id": "string",
        "project_name": "string",
        "risk_level": "Cao | Trung bình | Thấp",
        "feasibility_status": "Khả thi | Cần theo dõi | Rủi ro kém khả thi",
        "progress_percent": 0.0,
        "reasons": ["string"],
        "recommended_actions": ["string"]
        }
    ]
    }
    """

        if run_id:
            global_event_bus.publish_event(
                run_id,
                "evaluate_agent",
                "started",
                {"message": "Bắt đầu đánh giá toàn bộ dự án và danh sách task."},
                agent="evaluate_agent",
            )

        try:
            aggregated_payload = build_deterministic_metrics(projects, tasks)
            payload_str = json.dumps(aggregated_payload, ensure_ascii=False, default=str)

            res = self.llm.invoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=f"=== PORTFOLIO_DATA (JSON) ===\n{payload_str}"),
                ]
            )
            raw_answer = (res.content or "").strip()
            if not raw_answer:
                raise ValueError("Evaluate Agent trả về kết quả rỗng.")

            cleaned_result = sanitize_evaluation_output(raw_answer, projects, tasks)
            chart_dfs = to_chart_dataframes(cleaned_result)
        except Exception:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "evaluate_agent",
                    "failed",
                    {"message": "Đánh giá toàn bộ dự án thất bại."},
                    agent="evaluate_agent",
                )
            raise

        if run_id:
            details: Dict[str, Any] = {
                "message": "Đã hoàn tất đánh giá toàn bộ dự án và chuẩn hóa dữ liệu biểu đồ."
            }
            token_usage = extract_token_usage(res)
            if token_usage is not None:
                details["token_usage"] = token_usage
            global_event_bus.publish_event(
                run_id,
                "evaluate_agent",
                "completed",
                details,
                agent="evaluate_agent",
            )

        return cleaned_result, chart_dfs