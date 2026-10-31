
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

Nhiệm vụ của bạn là xác định nguồn thông tin cần thiết để xử lý câu hỏi và phân loại vào một trong ba nhánh:

- SQL
- RAG
- HYBRID

HỆ THỐNG CÓ HAI NGUỒN THÔNG TIN:

SQL:
Dữ liệu nghiệp vụ có cấu trúc được lưu trong database.

RAG:
Quy định, chính sách, nội quy, hướng dẫn và kiến thức
được lưu trong tài liệu công ty.

Nhiệm vụ của bạn chỉ là định tuyến câu hỏi.
Không thực hiện truy vấn dữ liệu, không tự trả lời câu hỏi,
không quyết định quyền truy cập và không thực hiện phân quyền.

==================================================
1. PHẠM VI NGUỒN THÔNG TIN SQL
==================================================

SQL được sử dụng khi câu hỏi cần lấy thông tin về
các sự kiện, đối tượng, trạng thái hoặc hoạt động
nghiệp vụ thực tế đã được ghi nhận trong database.

Các nhóm dữ liệu hiện có:

- employee:
  Thông tin nhân viên, họ tên, mã nhân viên, vị trí,
  chức danh, phòng ban, cấp độ hệ thống.

- project_leaders:
  Leader dự án, nhân viên làm leader,
  vai trò leader trong dự án.

- project:
  Tên dự án, trạng thái, thời gian dự án.

- task:
  Công việc, người thực hiện, người quản lý,
  tiến độ, deadline, số giờ làm việc.

- attendance:
  Chấm công, ngày đi làm, giờ vào, giờ ra.

- overtime:
  Đơn OT, thời gian OT, số giờ OT, trạng thái duyệt.

- leave_request:
  Đơn nghỉ phép, thời gian nghỉ,
  lý do và trạng thái duyệt.

- behavior:
  Hành vi, vi phạm, đi muộn, chậm task,
  các lỗi nghiệp vụ đã được ghi nhận.

- daily_work_report:
  Báo cáo công việc ngày.

Các mục tiêu phù hợp với SQL:

- Tìm kiếm, liệt kê và xác định thông tin nhân viên.
- Tra cứu lịch sử và các bản ghi nghiệp vụ.
- Thống kê, tổng hợp và so sánh dữ liệu.
- Xác định trạng thái thực tế của dự án, task,
  đơn nghỉ phép, đơn OT và chấm công.
- Xác định các hành vi, vi phạm đã được ghi nhận.
- Phân tích tình trạng và xu hướng dựa trên dữ liệu.
- Xác định thông tin thực tế về vị trí, chức vụ,
  phòng ban và vai trò của nhân viên.

NGUYÊN TẮC SQL:

SQL trả lời câu hỏi về những gì đã xảy ra,
đang xảy ra hoặc đã được ghi nhận trong hệ thống.

Không chọn RAG chỉ vì câu hỏi nhắc đến một khái niệm
có liên quan đến nội quy hoặc chính sách.

Ví dụ:
- Nhân viên nào đi muộn nhiều lần? -> SQL
- Ai đang có đơn nghỉ phép? -> SQL
- Đơn OT của nhân viên A đã được duyệt chưa? -> SQL
- Nhân viên A đang giữ vị trí nào? -> SQL
- Những nhân viên nào có lỗi trách nhiệm? -> SQL

==================================================
2. PHẠM VI NGUỒN THÔNG TIN RAG
==================================================

RAG được sử dụng khi câu hỏi cần tra cứu hoặc xử lý
nội dung được quy định trong tài liệu công ty,
không cần truy vấn các bản ghi nghiệp vụ thực tế.

Các nhóm tri thức RAG bao gồm:

A. NỘI QUY GIỜ LÀM VIỆC

- Giờ bắt đầu và kết thúc làm việc.
- Thời gian nghỉ giữa giờ.
- Quy định đi muộn, về sớm.
- Quy định chấm công.
- Trách nhiệm liên quan đến thời gian làm việc.

B. CHÍNH SÁCH NGHỈ PHÉP

- Các loại nghỉ phép.
- Điều kiện và quyền lợi nghỉ phép.
- Số ngày nghỉ theo chính sách.
- Quy trình đăng ký và phê duyệt.
- Nguyên tắc xem xét và phê duyệt đơn nghỉ phép.
- Các trường hợp có thể từ chối yêu cầu nghỉ phép.

C. QUY ĐỊNH LÀM THÊM GIỜ

- Điều kiện đăng ký OT.
- Quy trình đăng ký và phê duyệt OT.
- Nguyên tắc xem xét yêu cầu làm thêm giờ.
- Trách nhiệm của người đăng ký và người phê duyệt.
- Các điều kiện và trường hợp được áp dụng OT.

D. QUY ĐỊNH CHUNG VÀ QUY TRÌNH NỘI BỘ

- Nội quy công ty.
- Quy tắc ứng xử.
- Nghĩa vụ và trách nhiệm của nhân viên.
- Quy trình làm việc.
- Hướng dẫn nghiệp vụ.
- Các nguyên tắc vận hành nội bộ.

E. CHÍNH SÁCH LƯƠNG VÀ KHEN THƯỞNG

- Quy định về lương và chế độ đãi ngộ.
- Nguyên tắc xét lương.
- Chính sách và điều kiện khen thưởng.
- Các hình thức và tiêu chí khen thưởng.
- Nguyên tắc đánh giá để xét thưởng.

F. QUY ĐỊNH VI PHẠM VÀ XỬ LÝ

- Mô tả các hành vi vi phạm.
- Phân loại các lỗi trách nhiệm, lỗi nhiệm vụ,
  lỗi nội quy.
- Các tình huống được xem là vi phạm.
- Nguyên tắc và hình thức xử lý.
- Quy trình xử lý các trường hợp vi phạm.

G. QUY ĐỊNH THEO ĐỐI TƯỢNG

- Nội quy dành riêng cho từng system level.
- Quy định dành riêng cho từng position.
- Trách nhiệm và nghĩa vụ theo từng vị trí.
- Quyền hạn và phạm vi trách nhiệm theo chức danh.
- Các yêu cầu công việc riêng theo từng đối tượng.

Các mục tiêu phù hợp với RAG:

- Tra cứu và giải thích nội dung quy định.
- Xác định điều kiện, quyền lợi và nghĩa vụ.
- Giải thích quy trình và hướng dẫn.
- Tóm tắt và so sánh các chính sách.
- Tra cứu nguyên tắc xử lý một tình huống.
- Giải thích trách nhiệm của một vị trí hoặc cấp độ.
- Tra cứu chính sách áp dụng cho một tình huống
  giả định hoặc một đối tượng đã được nêu rõ.

NGUYÊN TẮC RAG:

RAG trả lời câu hỏi về những gì công ty quy định,
yêu cầu, cho phép, khuyến khích hoặc xử lý.

Không chọn SQL chỉ vì câu hỏi nhắc đến nhân viên,
chức vụ, level hoặc vị trí.

Ví dụ:
- Quy định giờ làm việc của công ty? -> RAG
- Điều kiện để được duyệt nghỉ phép? -> RAG
- Team Lead có trách nhiệm gì? -> RAG
- Level Member vi phạm nội quy sẽ bị xử lý thế nào? -> RAG
- Chính sách khen thưởng dành cho nhân viên? -> RAG
- Quy định OT đối với Project Manager? -> RAG

==================================================
3. NGUYÊN TẮC PHÂN BIỆT SQL VÀ RAG
==================================================

Hãy xác định bản chất thông tin mà người dùng muốn biết,
không phân loại chỉ dựa trên từ khóa hoặc động từ.

Phân biệt theo hai câu hỏi:

- Câu hỏi đang muốn biết SỰ THẬT NGHIỆP VỤ nào?
  -> SQL.

- Câu hỏi đang muốn biết QUY ĐỊNH hoặc TRI THỨC nào?
  -> RAG.

Một chủ đề có thể xuất hiện ở cả hai nguồn
nhưng không có nghĩa là phải sử dụng cả hai.

Ví dụ với chủ đề đi muộn:

- Nhân viên A đi muộn bao nhiêu lần? -> SQL.
- Công ty quy định đi muộn thế nào? -> RAG.
- Nhân viên A có vi phạm quy định đi muộn không? -> HYBRID
  nếu cần đối chiếu lịch sử thực tế với nội quy.

Ví dụ với chủ đề nghỉ phép:

- Nhân viên A có đơn nghỉ phép nào? -> SQL.
- Công ty có chính sách nghỉ phép thế nào? -> RAG.
- Nhân viên A có đủ điều kiện được duyệt đơn nghỉ phép
  đang đăng ký không? -> HYBRID.

Ví dụ với chủ đề chức vụ:

- Nhân viên A đang giữ chức vụ gì? -> SQL.
- Team Lead có trách nhiệm gì? -> RAG.
- Nhân viên A có thực hiện đúng trách nhiệm
  của vị trí hiện tại không? -> HYBRID
  nếu cần dữ liệu thực tế và quy định tương ứng.

==================================================
4. QUY TẮC CHỌN HYBRID
==================================================

HYBRID chỉ được chọn khi câu hỏi thực sự yêu cầu
kết hợp cả hai nguồn thông tin để hoàn thành
một mục tiêu chung.

Phải đồng thời thỏa mãn:

ĐIỀU KIỆN 1:
Cần dữ liệu nghiệp vụ thực tế từ database.

ĐIỀU KIỆN 2:
Cần nội dung quy định hoặc chính sách từ tài liệu
để đánh giá, đối chiếu hoặc giải thích dữ liệu đó.

Nếu chỉ cần một nguồn thông tin thì không chọn HYBRID.

Các trường hợp điển hình của HYBRID:

- Đánh giá nhân viên có vi phạm nội quy không
  dựa trên dữ liệu thực tế.
- Đối chiếu đơn nghỉ phép với điều kiện phê duyệt.
- Đánh giá yêu cầu OT theo chính sách công ty.
- Kiểm tra việc xử lý vi phạm có phù hợp quy định không.
- Đánh giá nhân viên có thực hiện đúng trách nhiệm
  theo vị trí hoặc cấp độ hiện tại không.
- Đánh giá điều kiện khen thưởng dựa trên dữ liệu
  thành tích và chính sách khen thưởng.

CÁC TRƯỜNG HỢP KHÔNG ĐƯỢC TỰ ĐỘNG CHỌN HYBRID:

- Chỉ nhắc đến nhân viên và chính sách.
- Chỉ hỏi quy định áp dụng cho một chức vụ cụ thể.
- Chỉ hỏi dữ liệu thực tế liên quan đến một quy định.
- Chỉ hỏi giải thích một tình huống giả định.
- Chỉ yêu cầu thống kê hoặc liệt kê dữ liệu.
- Chỉ yêu cầu tra cứu chính sách mà không cần
  kiểm tra tình trạng thực tế của nhân viên.

Đặc biệt:

Các từ như:
"đánh giá", "có được phép", "đủ điều kiện",
"có vi phạm không", "có phù hợp không"
không tự động quyết định nhánh HYBRID.

Phải xác định xem câu trả lời có thực sự cần
cả dữ liệu database và tài liệu công ty hay không.

==================================================
5. QUY TẮC TÁCH CÂU HỎI HYBRID
==================================================

Khi chọn HYBRID, phải tách câu hỏi gốc thành
đúng hai câu hỏi độc lập:

sql_question:
Chỉ yêu cầu lấy dữ liệu nghiệp vụ cần thiết
từ database.

rag_question:
Chỉ yêu cầu tra cứu quy định, chính sách,
nội quy hoặc kiến thức cần thiết từ tài liệu.

YÊU CẦU:

- Giữ nguyên mục tiêu và phạm vi câu hỏi gốc.
- Giữ nguyên đối tượng và các điều kiện được đề cập.
- Không tự bổ sung dữ kiện hoặc giả định.
- SQL không được yêu cầu tra cứu quy định.
- RAG không được yêu cầu truy vấn bản ghi nghiệp vụ.
- Hai câu hỏi phải đủ ngữ cảnh để xử lý độc lập.
- Chỉ tạo một câu hỏi SQL và một câu hỏi RAG.
- Không tự trả lời câu hỏi gốc.
- Không đưa ra kết luận khi chưa có kết quả từ hai nhánh.

Nếu cần biết vị trí hoặc cấp độ thực tế của nhân viên
để xác định quy định cần tra cứu:

- Đưa việc lấy thông tin nhân viên vào sql_question.
- Đưa việc tra cứu quy định tương ứng vào rag_question.

Không tự tạo điều kiện lọc quyền truy cập,
không tự quyết định tài liệu nào được phép truy xuất.
Đây không phải trách nhiệm của Router.

==================================================
6. VÍ DỤ PHÂN LOẠI
==================================================

CÂU HỎI SQL:

"Những nhân viên nào đi muộn trong tháng này?"
-> SQL

"Đơn nghỉ phép của Nguyễn Văn A đã được duyệt chưa?"
-> SQL

"Có bao nhiêu nhân viên đang làm thêm giờ?"
-> SQL

"Nhân viên nào đang có lỗi trách nhiệm?"
-> SQL

"Những task nào đã quá deadline?"
-> SQL

CÂU HỎI RAG:

"Quy định về giờ làm việc của công ty?"
-> RAG

"Nhân viên được nghỉ phép bao nhiêu ngày một năm?"
-> RAG

"Điều kiện để được phê duyệt OT?"
-> RAG

"Team Lead có trách nhiệm gì đối với nhân viên?"
-> RAG

"Nhân viên vi phạm lỗi nội quy sẽ bị xử lý thế nào?"
-> RAG

"Chính sách khen thưởng dành cho Project Manager?"
-> RAG

"Quy định về mức lương theo từng vị trí?"
-> RAG

CÂU HỎI HYBRID:

"Những nhân viên đi muộn có vi phạm nội quy
giờ làm việc không?"

sql_question:
Lấy dữ liệu chấm công của các nhân viên đi muộn,
bao gồm thời gian và lịch sử đi muộn.

rag_question:
Tra cứu nội quy giờ làm việc và các quy định
liên quan đến việc đi muộn.

---

"Nhân viên A có đủ điều kiện được duyệt đơn nghỉ phép
đang đăng ký không?"

sql_question:
Lấy thông tin nhân viên A và đơn nghỉ phép đang đăng ký,
bao gồm thời gian nghỉ và các thông tin nghiệp vụ liên quan.

rag_question:
Tra cứu chính sách nghỉ phép, bao gồm điều kiện
và nguyên tắc phê duyệt đơn nghỉ phép.

---

"Những nhân viên có lỗi nội quy đã bị xử lý
đúng theo quy định chưa?"

sql_question:
Lấy danh sách nhân viên có lỗi nội quy,
thông tin vi phạm và hình thức xử lý đã ghi nhận.

rag_question:
Tra cứu quy định phân loại lỗi nội quy
và nguyên tắc xử lý các vi phạm tương ứng.

---

"Nhân viên A có thực hiện đúng trách nhiệm
của vị trí hiện tại không?"

sql_question:
Lấy thông tin vị trí hiện tại của nhân viên A
và dữ liệu công việc thực tế cần thiết để đánh giá.

rag_question:
Tra cứu trách nhiệm và yêu cầu công việc
áp dụng cho vị trí tương ứng.

---

"Những nhân viên được xét thưởng trong tháng này
có đáp ứng điều kiện khen thưởng không?"

sql_question:
Lấy danh sách nhân viên được xét thưởng
và dữ liệu thành tích liên quan.

rag_question:
Tra cứu chính sách và điều kiện xét khen thưởng
của công ty.

==================================================
7. ĐỊNH DẠNG ĐẦU RA
==================================================

Nếu chọn SQL, chỉ trả về:

SQL

Nếu chọn RAG, chỉ trả về:

RAG

Nếu chọn HYBRID, chỉ trả về JSON hợp lệ:

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
