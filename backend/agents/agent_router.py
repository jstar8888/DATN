
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from utils.event_bus import global_event_bus
from utils.llm_usage import extract_token_usage
from agents.guardrails import HRSemanticScopeDefinition


class RouterAgent:

    def __init__(self, model_name: str = "qwen2.5-coder:7b"):

        '''''
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",  # Hoặc gemini-2.5-pro tùy nhu cầu
            temperature=0.1,
            
        )
        '''''
        
        
        self.llm = ChatOllama(
            model=model_name,
            temperature=0.1,
            base_url="http://localhost:11434",
           # num_predict=5,
            keep_alive="10m",
            reasoning=False,
        )
        

    def route(
        self, user_question: str, run_id: str | None = None, semantic_context: str | None = None
    ) -> dict[str, str]:
        
        # Lấy ngữ cảnh hệ thống và ranh giới nghiệp vụ từ Guardrail
        base_context = semantic_context or HRSemanticScopeDefinition.get_semantic_system_prompt_context()

        prompt = f"""
/no_think

{base_context}

Bạn là bộ định tuyến câu hỏi (Router Agent) cho hệ thống nhân sự.
Nhiệm vụ duy nhất của bạn là phân tích câu hỏi theo phạm vi nghiệp vụ ở trên và phân loại vào một trong các nhánh:

- SQL: Khi câu hỏi yêu cầu lấy dữ liệu bản ghi thực tế, số liệu, trạng thái đã được ghi nhận trong database (như employee, project_leaders, project, task, attendance, overtime, leave_request, behavior, daily_work_report).
- RAG: Khi câu hỏi yêu cầu tra cứu quy định, nội quy, chính sách, hướng dẫn công việc từ tài liệu công ty.
- HYBRID: Khi câu hỏi đòi hỏi kết hợp đồng thời cả dữ liệu thực tế từ database (SQL) và quy định/chính sách từ tài liệu (RAG) để đối chiếu, đánh giá.
- OUT_OF_SCOPE: Khi câu hỏi không thuộc phạm vi nghiệp vụ nội bộ doanh nghiệp được mô tả trong ngữ cảnh hệ thống.

==================================================
QUY TẮC ĐẦU RA:
==================================================
- Nếu chọn SQL, chỉ trả về chữ: SQL
- Nếu chọn RAG, chỉ trả về chữ: RAG
- Nếu chọn OUT_OF_SCOPE, chỉ trả về chữ: OUT_OF_SCOPE
- Nếu chọn HYBRID, phải trả về một JSON hợp lệ duy nhất với định dạng:
{{
  "intent": "HYBRID",
  "sql_question": "Câu hỏi truy vấn dữ liệu database tương ứng",
  "rag_question": "Câu hỏi tra cứu tài liệu quy định tương ứng"
}}

Không sử dụng Markdown, không giải thích bên ngoài định dạng đầu ra.
"""

        try:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "router",
                    "started",
                    {"message": "Đang phân loại câu hỏi dựa trên ngữ nghĩa hệ thống."},
                    agent="router",
                )
            
            res = self.llm.invoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=user_question),
                ]
            )
            response = res.content.strip()
            intent = response.upper()

            if intent == "SQL":
                result = {
                    "intent": "SQL",
                    "sql_question": user_question,
                }
            elif intent == "RAG":
                result = {
                    "intent": "RAG",
                    "rag_question": user_question,
                }
            elif intent == "OUT_OF_SCOPE":
                result = {
                    "intent": "OUT_OF_SCOPE",
                    "final_answer": (
                        "Xin lỗi, tôi là chatbot nội bộ doanh nghiệp nên "
                        "không thể trả lời câu hỏi này."
                    ),
                }
            else:
                try:
                    decision = json.loads(response)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Router trả về định dạng không hợp lệ: {response!r}"
                    ) from exc

                if (
                    not isinstance(decision, dict)
                    or decision.get("intent") != "HYBRID"
                ):
                    raise ValueError(
                        f"Router trả về nhãn không hợp lệ: {response!r}"
                    )

                sql_question = decision.get("sql_question")
                rag_question = decision.get("rag_question")
                if (
                    not isinstance(sql_question, str)
                    or not sql_question.strip()
                    or not isinstance(rag_question, str)
                    or not rag_question.strip()
                ):
                    raise ValueError(
                        "Router HYBRID phải trả về sql_question và rag_question."
                    )

                result = {
                    "intent": "HYBRID",
                    "sql_question": sql_question.strip(),
                    "rag_question": rag_question.strip(),
                }
        except Exception:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "router",
                    "failed",
                    {"message": "Không thể phân loại câu hỏi."},
                    agent="router",
                )
            raise

        if run_id:
            details: dict[str, Any] = {"intent": result["intent"]}
            token_usage = extract_token_usage(res)
            if token_usage is not None:
                details["token_usage"] = token_usage
            global_event_bus.publish_event(
                run_id,
                "router",
                "completed",
                details,
                agent="router",
            )
        return result
