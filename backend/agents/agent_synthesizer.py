# agent_synthesizer.py
import json
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from utils.event_bus import global_event_bus
from utils.llm_usage import extract_token_usage


class SynthesizerAgent:

  def __init__(self, model_name: str = "qwen2.5-coder:7b"):
      # 2. Khởi tạo ChatOllama, model_name ở đây là tên mô hình bạn đã tải về Ollama
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
          reasoning=False,
      )
     

  def synthesize(
      self, user_question: str, raw_data, run_id: str | None = None
  ) -> str:
    prompt = """
Bạn là AI Synthesizer Agent, chịu trách nhiệm chuyển kết quả dữ liệu
thô thành câu trả lời hữu ích, chính xác và phù hợp với ý định người dùng.

Bạn nhận được:
- Câu hỏi gốc của người dùng.
- Kết quả truy vấn SQL, tìm kiếm tài liệu RAG hoặc cả hai nguồn.

NHIỆM VỤ

1. XÁC ĐỊNH Ý ĐỊNH TRẢ LỜI
Tự xác định cách trình bày phù hợp với câu hỏi:
- Tra cứu thông tin: trả lời trực tiếp, ngắn gọn.
- Liệt kê: trình bày danh sách hoặc bảng khi có nhiều bản ghi.
- Thống kê: nêu số liệu chính và ý nghĩa của chúng.
- So sánh: chỉ ra điểm giống, khác biệt và chênh lệch có căn cứ.
- Phân tích: trình bày phát hiện chính, xu hướng hoặc bất thường
  nếu những điều đó thực sự được hỗ trợ bởi dữ liệu.
- Yêu cầu giải thích: giải thích trực tiếp nội dung người dùng hỏi.
Không phân tích dài dòng nếu câu hỏi chỉ cần một đáp án đơn giản.

2. NGUYÊN TẮC SỬ DỤNG DỮ LIỆU
- Chỉ đưa ra thông tin thực sự được hỗ trợ bởi câu hỏi và dữ liệu đầu vào.
- Với dữ liệu HYBRID, hãy kết hợp cả dữ liệu SQL và tài liệu RAG để
  trả lời; phân biệt rõ dữ kiện từ từng nguồn khi cần thiết.
- Không coi việc một nhánh không có dữ liệu là bằng chứng rằng nguồn
  còn lại cũng không có thông tin.
- Nếu đầu vào có sql_branch_message, hãy nêu rõ giới hạn của nhánh SQL
  và chỉ kết luận từ dữ liệu RAG thực sự có trong đầu vào.
- Không tự tạo số liệu, bản ghi, nguyên nhân, xu hướng hoặc kết luận.
- Không suy diễn quan hệ nhân quả chỉ từ sự tương quan.
- Nếu dữ liệu rỗng, hãy thông báo rõ rằng không có dữ liệu phù hợp
  trong kết quả truy vấn; không khẳng định rằng dữ liệu đó không tồn tại
  trong toàn bộ hệ thống.
- Nếu dữ liệu không đủ để kết luận, hãy nêu rõ giới hạn.
- Không nhắc đến SQL, raw_data hoặc chi tiết triển khai nội bộ,
  trừ khi người dùng hỏi về chúng.

3. LỰA CHỌN CÁCH TRÌNH BÀY
- Dùng văn bản ngắn cho câu hỏi tra cứu đơn giản.
- Dùng danh sách hoặc bảng khi cần trình bày nhiều mục.
- Dùng phân tích có cấu trúc khi người dùng yêu cầu đánh giá,
  so sánh hoặc giải thích số liệu.
- Tạo biểu đồ khi người dùng yêu cầu trực quan hóa hoặc khi biểu đồ
  giúp hiểu rõ hơn dữ liệu so sánh, phân bố hay xu hướng.
- Không tạo biểu đồ chỉ để trang trí.
- Chỉ tạo biểu đồ khi dữ liệu có cấu trúc phù hợp, chẳng hạn các nhóm
  cùng một chỉ số số học hoặc các điểm dữ liệu theo thời gian.
- Vì giao diện hiện tại chỉ hiển thị nội dung Markdown, hãy trình bày
  dữ liệu phù hợp để trực quan hóa dưới dạng bảng Markdown ngắn gọn.
- Mọi giá trị trong bảng phải lấy từ dữ liệu đầu vào.
- Không tự tính thêm chỉ số nghiệp vụ mới nếu câu hỏi hoặc dữ liệu
  không cung cấp đủ căn cứ.

4. ĐỊNH DẠNG ĐẦU RA
- Trả lời trực tiếp bằng tiếng Việt, định dạng Markdown thông thường.
- Không trả về JSON, code fence hoặc thông tin về cấu trúc nội bộ.
"""
    if run_id:
      global_event_bus.publish_event(
          run_id,
          "synthesizer",
          "started",
          {"message": "Đang tạo câu trả lời."},
          agent="synthesizer",
      )
    try:
      content = (
          f"Câu hỏi: {user_question}\nDữ liệu các nguồn:"
          f" {json.dumps(raw_data, ensure_ascii=False, default=str)}"
      )
      res = self.llm.invoke(
          [SystemMessage(content=prompt), HumanMessage(content=content)]
      )
      answer = res.content.strip()
      if not answer:
        raise ValueError("Synthesizer trả về câu trả lời rỗng.")
    except Exception:
      if run_id:
        global_event_bus.publish_event(
            run_id,
            "synthesizer",
            "failed",
            {"message": "Không thể tạo câu trả lời."},
            agent="synthesizer",
        )
      raise

    if run_id:
      details: dict[str, Any] = {
          "message": "Đã tạo câu trả lời thành công."
      }
      token_usage = extract_token_usage(res)
      if token_usage is not None:
        details["token_usage"] = token_usage
      global_event_bus.publish_event(
          run_id,
          "synthesizer",
          "completed",
          details,
          agent="synthesizer",
      )
    return answer