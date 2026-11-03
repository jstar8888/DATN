from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from utils.event_bus import global_event_bus
from utils.llm_usage import extract_token_usage

class QueryRewriterAgent:
    def __init__(self, model_name: str = "qwen2.5-coder:7b"):
        self.llm = ChatOllama(
            model=model_name,
            temperature=0.1,
            base_url="http://localhost:11434",
            keep_alive="10m",
            reasoning=False,
        )

    def rewrite(
        self, chat_history: list[dict[str, str]], current_question: str, run_id: str | None = None
    ) -> str:
        """
        Đọc lịch sử hội thoại và câu hỏi hiện tại để biên dịch thành một câu hỏi độc lập, đầy đủ nghĩa.
        """
        # Format lịch sử chat thành dạng text đơn giản để LLM dễ đọc
        formatted_history = "\n".join(
            [f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in chat_history[-5:]] # Lấy 5 lượt gần nhất
        ) if chat_history else "Không có lịch sử trước đó."

        prompt = f"""
/no_think

Bạn là một Trợ lý chuyên biên dịch câu hỏi (Query Rewriter Agent).
Nhiệm vụ của bạn là đọc Lịch sử trò chuyện gần đây và Câu hỏi mới nhất của người dùng.
Hãy viết lại câu hỏi mới thành một CÂU HỎI ĐỘC LẬP, ĐẦY ĐỦ Ý NGHĨA (tự hiểu được mà không cần nhìn lịch sử, thay thế các từ mơ hồ như "nó", "giải thích kĩ hơn", "thế còn anh ấy" thành thực thể cụ thể).

==================================================
LỊCH SỬ TRÒ CHUYỆN GẦN ĐÂY:
==================================================
{formatted_history}

==================================================
CÂU HỎI MỚI NHẤT:
==================================================
{current_question}

==================================================
QUY TẮC ĐẦU RA:
==================================================
- Chỉ trả về DUY NHẤT một câu hỏi đã được viết lại. 
- Không giải thích, không thêm định dạng Markdown hay lời chào.
"""

        try:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "query_rewriter",
                    "started",
                    {"message": "Đang biên dịch câu hỏi theo ngữ cảnh hội thoại."},
                    agent="query_rewriter",
                )
            
            res = self.llm.invoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content=current_question),
                ]
            )
            rewritten_question = res.content.strip()
            
        except Exception:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "query_rewriter",
                    "failed",
                    {"message": "Không thể biên dịch lại câu hỏi."},
                    agent="query_rewriter",
                )
            # Fallback về câu hỏi gốc nếu agent viết lại gặp lỗi
            return current_question

        if run_id:
            details: dict[str, Any] = {"rewritten_question": rewritten_question}
            token_usage = extract_token_usage(res)
            if token_usage is not None:
                details["token_usage"] = token_usage
            global_event_bus.publish_event(
                run_id,
                "query_rewriter",
                "completed",
                details,
                agent="query_rewriter",
            )
            
        return rewritten_question