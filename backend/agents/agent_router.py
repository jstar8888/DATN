
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from utils.event_bus import global_event_bus
from utils.llm_usage import extract_token_usage


class RouterAgent:

    def __init__(self, model_name: str = "qwen2.5-coder:7b"):

        '''
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",  # Hoặc gemini-2.5-pro tùy nhu cầu
            temperature=0.1,
            
        )
        '''
        
        
        self.llm = ChatOllama(
            model=model_name,
            temperature=0.0,
            base_url="http://localhost:11434",
           # num_predict=5,
            keep_alive="10m",
            reasoning=False,
        )
        

    def route(
        self, user_question: str, run_id: str | None = None
    ) -> dict[str, str]:
        prompt = """
/no_think

Bạn là bộ định tuyến câu hỏi cho chatbot quản lý nhân sự.
Nhiệm vụ của bạn là phân loại câu hỏi vào một trong ba nhánh: SQL, RAG hoặc HYBRID.

QUY TẮC 1 - CHỌN SQL:

Chọn SQL nếu câu hỏi cần truy vấn, liệt kê, tìm kiếm,
thống kê hoặc phân tích dữ liệu nghiệp vụ đã lưu trong database.

Các nhóm dữ liệu SQL hiện có:
- employee: nhân viên, họ tên, mã nhân viên, vị trí,
  chức danh, phòng ban, cấp độ hệ thống.
- project_leaders: leader dự án, danh sách leader,
  nhân viên làm leader, vai trò leader trong dự án.
- project: tên dự án, trạng thái, thời gian dự án.
- task: công việc, người thực hiện, người quản lý,
  tiến độ, deadline, số giờ làm việc.
- attendance: chấm công, ngày đi làm, giờ vào, giờ ra.
- overtime: OT, tăng ca, số giờ OT, trạng thái duyệt.
- leave_request: đơn nghỉ phép, thời gian nghỉ,
  lý do và trạng thái duyệt.
- behavior: hành vi, vi phạm, đi muộn, chậm task.
- daily_work_report: báo cáo công việc ngày.

ƯU TIÊN SQL khi câu hỏi đề cập đến dữ liệu có cấu trúc
trong các bảng trên, kể cả khi dùng từ:
"thông tin", "chi tiết", "danh sách", "vị trí",
"chức vụ", "vai trò", "ai", "bao nhiêu", "thống kê".

QUY TẮC 2 - CHỌN RAG:

Chọn RAG nếu câu hỏi cần tra cứu, giải thích hoặc
tóm tắt nội dung trong tài liệu công ty, chẳng hạn:
- Quy định, chính sách, nội quy.
- SOP, quy trình, hướng dẫn.
- Nội dung tài liệu và kiến thức nghiệp vụ.

Không chọn RAG chỉ vì câu hỏi có từ "thông tin"
hoặc yêu cầu giải thích một thuộc tính của nhân viên.

QUY TẮC 3 - CHỌN HYBRID:

Chọn HYBRID khi câu hỏi cần đồng thời:
1. Truy vấn dữ liệu nghiệp vụ từ database.
2. Tra cứu nội dung từ tài liệu công ty.
3. Kết hợp hai nguồn thông tin để giải quyết cùng một yêu cầu.

Khi chọn HYBRID, phải tách câu hỏi ban đầu thành
đúng hai câu hỏi độc lập về mục tiêu truy vấn:

- sql_question: Câu hỏi chỉ phục vụ việc lấy dữ liệu
  cần thiết từ database.
- rag_question: Câu hỏi chỉ phục vụ việc tra cứu
  quy định, chính sách, quy trình hoặc kiến thức
  cần thiết từ tài liệu công ty.

Yêu cầu khi tách câu hỏi:
- Mỗi câu hỏi chỉ phục vụ đúng nhánh tương ứng.
- Giữ nguyên mục tiêu, điều kiện, đối tượng và phạm vi
  được đề cập trong câu hỏi gốc.
- Không tự bổ sung dữ kiện hoặc giả định chưa được cung cấp.
- Không yêu cầu SQL truy vấn nội dung chỉ có trong tài liệu.
- Không yêu cầu RAG tìm kiếm dữ liệu nhân viên hoặc
  các bản ghi nghiệp vụ cụ thể trong database.
- Hai câu hỏi phải có đủ ngữ cảnh để xử lý độc lập.
- Không chia nhỏ thành nhiều câu hỏi SQL hoặc nhiều
  câu hỏi RAG trong giai đoạn thử nghiệm này.
- Không tự trả lời câu hỏi gốc hoặc đưa ra kết luận
  dựa trên dữ liệu chưa được truy xuất.

Nếu câu hỏi chỉ cần một nguồn thông tin để trả lời,
không chọn HYBRID.

QUY TẮC XỬ LÝ CÂU HỎI KẾT HỢP:

- Nếu mục tiêu chính chỉ là truy vấn dữ liệu database,
  chọn SQL.
- Nếu mục tiêu chính chỉ là tra cứu quy định hoặc hướng dẫn,
  chọn RAG.
- Nếu muốn đánh giá, đối chiếu hoặc giải thích dữ liệu
  nghiệp vụ dựa trên quy định, chính sách hoặc tài liệu,
  chọn HYBRID khi cần cả hai nguồn để hoàn thành yêu cầu.

VÍ DỤ PHÂN LOẠI:

"Thông tin các leader" -> SQL

"Thông tin các leader và vị trí của họ" -> SQL

"Danh sách leader và dự án họ phụ trách" -> SQL

"Leader của dự án A là ai?" -> SQL

"Chức vụ hiện tại của nhân viên Nguyễn Văn A?" -> SQL

"Nhân viên nào đi muộn tháng này?" -> SQL

"Các task đang bị trễ?" -> SQL

"Quy định về trách nhiệm của leader?" -> RAG

"Quy trình xin nghỉ phép gồm những bước nào?" -> RAG

"Chính sách nghỉ phép năm của công ty?" -> RAG

"Liệt kê các nhân viên đang có đơn xin nghỉ phép" -> SQL

"Những nhân viên đang xin nghỉ phép có đáp ứng chính sách
nghỉ phép của công ty không?" -> HYBRID

Với ví dụ HYBRID trên:
sql_question: Liệt kê các nhân viên đang có đơn xin nghỉ phép,
kèm thông tin và trạng thái đơn.

rag_question: Truy xuất chính sách nghỉ phép của công ty,
bao gồm điều kiện và quy định phê duyệt.

ĐỊNH DẠNG ĐẦU RA:

Nếu chọn SQL, chỉ trả về:
SQL

Nếu chọn RAG, chỉ trả về:
RAG

Nếu chọn HYBRID, chỉ trả về JSON hợp lệ theo cấu trúc:
{
  "intent": "HYBRID",
  "sql_question": "Câu hỏi dành cho SQL",
  "rag_question": "Câu hỏi dành cho RAG"
}

Không sử dụng Markdown.
Không thêm giải thích bên ngoài định dạng đầu ra.

"""
        try:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "router",
                    "started",
                    {"message": "Đang phân loại câu hỏi."},
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
