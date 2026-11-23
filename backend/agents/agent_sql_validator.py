# agents/agent_sql_validator.py
import re
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from agents.configurable_llm import ConfigurableChatModel
from utils.event_bus import global_event_bus
from utils.llm_usage import extract_token_usage


class SQLValidatorAgent:
  def __init__(self):
    self.llm = ConfigurableChatModel(
        "sql_validator",
        temperature=0.0,  # Đặt bằng 0 để kết quả đánh giá mang tính khách quan, logic cao
        reasoning=False,
    )

  def clean_sql_with_regex(self, raw_sql: str) -> str:
    """Sử dụng Regex và xử lý chuỗi để loại bỏ các ký tự thừa từ LLM."""
    if not raw_sql:
      return ""
    
    sql = raw_sql.strip()
    
    # 1. Loại bỏ Markdown code block nếu có (ví dụ: ```sql ... ``` hoặc ``` ...)
    sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\s*```$", "", sql)
    sql = sql.strip()

    # 2. Loại bỏ dấu ngoặc kép thừa quấn quanh câu truy vấn (nếu có do LLM sinh nhầm)
    if sql.startswith('"') and sql.endswith('"'):
      sql = sql[1:-1].strip()
    elif sql.startswith("'") and sql.endswith("'"):
      sql = sql[1:-1].strip()

    # 3. Chuẩn hóa khoảng trắng và dấu chấm phẩy cuối câu (RPC chuẩn không cần dấu ;)
    sql = re.sub(r"\s+", " ", sql)
    if sql.endswith(";"):
      sql = sql[:-1].strip()

    return sql

  def evaluate(self, question: str, sql_query: str, run_id: str | None = None) -> dict[str, Any]:
    """
    Sử dụng LLM kết hợp để đánh giá xem câu SQL có trả lời đúng câu hỏi hay không.
    Trả về định dạng JSON gồm: {"is_valid": true/false, "reason": "..."}
    """
    if run_id:
      global_event_bus.publish_event(
          run_id,
          "sql_validation",
          "started",
          {"message": "Đang đánh giá chất lượng câu SQL bằng LLM."},
          agent="sql_validator",
      )

    # Bước 1: Làm sạch bằng regex trước khi đưa vào LLM đánh giá
    cleaned_sql = self.clean_sql_with_regex(sql_query)

    # Nếu câu SQL trả về các marker đặc biệt thì cho qua luôn không cần LLM check
    if cleaned_sql in {"-- INSUFFICIENT_SCHEMA", "-- NEEDS_CLARIFICATION"}:
      return {"is_valid": True, "cleaned_sql": cleaned_sql, "reason": "Marker đặc biệt được chấp nhận."}

    prompt = (
        "Bạn là một chuyên gia kiểm định cơ sở dữ liệu PostgreSQL nghiêm ngặt.\n"
        "Nhiệm vụ của bạn là đánh giá xem câu truy vấn SQL được cung cấp có thực sự "
        "giải quyết và trả lời đúng ý nghĩa của câu hỏi người dùng hay không.\n\n"
        f"Câu hỏi của người dùng: {question}\n"
        f"Câu lệnh SQL cần đánh giá:\n{cleaned_sql}\n\n"
        "Yêu cầu trả về kết quả DUY NHẤT dưới dạng JSON thuần túy (không kèm markdown như ```json) với cấu trúc sau:\n"
        "{\n"
        '  "is_valid": true hoặc false,\n'
        '  "reason": "Giải thích ngắn gọn lý do vì sao hợp lệ hoặc không hợp lệ"\n'
        "}"
    )

    try:
      response = self.llm.invoke([HumanMessage(content=prompt)])
      content = response.content.strip()
      
      # Làm sạch JSON trả về từ LLM nếu có bọc trong markdown
      content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
      content = re.sub(r"\s*```$", "", content).strip()

      import json
      result = json.loads(content)
      is_valid = bool(result.get("is_valid", False))
      reason = result.get("reason", "")
    except Exception as e:
      # Nếu lỗi parse JSON, mặc định coi như không hợp lệ để an toàn yêu cầu sinh lại
      is_valid = False
      reason = f"Lỗi phân tích phản hồi từ LLM evaluator: {str(e)}"

    if run_id:
      global_event_bus.publish_event(
          run_id,
          "sql_validation",
          "completed",
          {"is_valid": is_valid, "reason": reason, "cleaned_sql": cleaned_sql},
          agent="sql_validator",
      )

    return {
        "is_valid": is_valid,
        "cleaned_sql": cleaned_sql,
        "reason": reason
    }