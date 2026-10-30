# agent_evaluate.py
import json
from typing import Any, Dict, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.event_bus import global_event_bus
from utils.llm_usage import extract_token_usage


class EvaluateAgent:
    """Agent chịu trách nhiệm đánh giá, thẩm định dữ liệu dựa trên command, rag_data và sql_data."""

    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.1,
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