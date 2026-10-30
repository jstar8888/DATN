import json
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
# 1. Thay đổi thư viện import LLM sang Ollama
from langchain_ollama import ChatOllama
from langchain_google_genai import ChatGoogleGenerativeAI
from utils.event_bus import global_event_bus
from utils.llm_usage import extract_token_usage


_RPC_FORBIDDEN_KEYWORDS = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(insert|update|delete|merge|drop|alter|truncate|create|"
    r"grant|revoke|call|do|execute|copy|vacuum|refresh|reindex|cluster)"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def _normalize_rpc_query(sql_query: str) -> str:
  sql_query = sql_query.strip()
  if sql_query.endswith(";"):
    sql_query = sql_query[:-1].rstrip()

  if not re.match(r"^(select|with)(\s|$)", sql_query, re.IGNORECASE):
    raise ValueError("SQL chỉ được bắt đầu bằng SELECT hoặc WITH.")
  if ";" in sql_query:
    raise ValueError("SQL không được chứa dấu chấm phẩy bên trong truy vấn.")
  if _RPC_FORBIDDEN_KEYWORDS.search(sql_query):
    raise ValueError(
        "SQL chứa từ khóa không được phép theo quy tắc của RPC."
    )
  return sql_query


class SQLGraphAgent:

  def __init__(
      self,
      json_config_path: str = "table_relationships_and_paths.json",
      semantic_profiles_path: str | None = None,
  ):

    self.llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",  # Hoặc gemini-2.5-pro tùy nhu cầu
    temperature=0.1,
    
)
    
    # 2. Khởi tạo ChatOllama thay vì ChatGoogleGenerativeAI
    # model: Tên mô hình bạn đã tải về trên Ollama (ví dụ: "llama3", "mistral", "qwen2.5")
    # base_url: Địa chỉ Ollama chạy ngầm (mặc định là http://localhost:11434)
    """
    self.llm = ChatOllama(
        model="qwen2.5-coder:7b",  # Thay thế bằng tên mô hình bạn muốn sử dụng
        temperature=0.1,
        base_url="http://localhost:11434",
        reasoning=False,
    )
    """
    self.json_config_path = json_config_path
    self.graph_path_resolver = None
    profiles_path = (
        Path(semantic_profiles_path)
        if semantic_profiles_path
        else Path(__file__).resolve().parents[1]
        / "script"
        / "table_semantic_profiles.json"
    )
    with profiles_path.open("r", encoding="utf-8") as profiles_file:
      profiles_data = json.load(profiles_file)
    self.table_profiles = {
        profile["table_name"]: profile
        for profile in profiles_data["tables"]
    }

  def _get_semantic_context(self, candidate_tables: list[str]) -> list[dict]:
    missing_tables = [
        table_name
        for table_name in candidate_tables
        if table_name not in self.table_profiles
    ]
    if missing_tables:
      raise ValueError(
          "Không tìm thấy semantic profile cho bảng: "
          + ", ".join(missing_tables)
      )

    return [
        self.table_profiles[table_name]
        for table_name in candidate_tables
    ]

  def process(self, user_question: str, run_id: str | None = None) -> dict:
    from tools.graph_path_resolver import GraphPathResolver
    from tools.tables_retriever import get_top_k_tables_from_supabase

    # 1. Truy xuất các bảng liên quan đến câu hỏi
    if run_id:
      global_event_bus.publish_event(
          run_id,
          "table_retrieval",
          "started",
          {"message": "Đang tìm các bảng liên quan."},
          agent="sql_expert",
      )
    try:
      candidate_tables = get_top_k_tables_from_supabase(user_question)
      if not candidate_tables:
        raise RuntimeError("Không tìm thấy bảng phù hợp cho câu hỏi.")
    except Exception:
      if run_id:
        global_event_bus.publish_event(
            run_id,
            "table_retrieval",
            "failed",
            {"message": "Không thể tìm bảng phù hợp."},
            agent="sql_expert",
        )
      raise
    if run_id:
      global_event_bus.publish_event(
          run_id,
          "table_retrieval",
          "completed",
          {"candidate_tables": candidate_tables},
          agent="sql_expert",
      )

    # Gửi schema ngữ nghĩa đầy đủ của các bảng đã truy xuất cho LLM.
    semantic_context = self._get_semantic_context(candidate_tables)
    # 2. Dùng helper để tìm đường join giữa các bảng
    if self.graph_path_resolver is None:
      self.graph_path_resolver = GraphPathResolver(self.json_config_path)
    if run_id:
      global_event_bus.publish_event(
          run_id,
          "join_resolution",
          "started",
          {"message": "Đang xác định đường JOIN."},
          agent="sql_expert",
      )
    try:
      join_blueprint = self.graph_path_resolver.resolve_join_paths(
          candidate_tables
      )
    except Exception:
      if run_id:
        global_event_bus.publish_event(
            run_id,
            "join_resolution",
            "failed",
            {"message": "Không thể xác định đường JOIN."},
            agent="sql_expert",
        )
      raise
    if run_id:
      global_event_bus.publish_event(
          run_id,
          "join_resolution",
          "completed",
          {
              "join_paths": join_blueprint["graph_traversal_steps"],
              "resolved_joins": join_blueprint["resolved_joins"],
          },
          agent="sql_expert",
      )

    # 3. Sinh SQL bằng LLM
    prompt = (
    "Bạn là chuyên gia Text-to-SQL PostgreSQL, chịu trách nhiệm "
    "chuyển câu hỏi tiếng Việt thành truy vấn SQL chính xác về "
    "nghiệp vụ, đúng schema và nhất quán về cấu trúc.\n\n"

    "I. NGUỒN THÔNG TIN\n"
    "- Semantic profiles là nguồn xác định ý nghĩa bảng, cột, grain, "
    "quy tắc nghiệp vụ và cách diễn giải thuật ngữ.\n"
    "- Join blueprint là nguồn xác định các đường JOIN và điều kiện "
    "nối bảng hợp lệ.\n"
    "- Chỉ sử dụng bảng, cột và giá trị nghiệp vụ được cung cấp hoặc "
    "có căn cứ rõ ràng từ ngữ cảnh đầu vào.\n"
    "- Không tự tạo bảng, cột, quan hệ JOIN hoặc giá trị trạng thái.\n\n"

    "II. QUY TRÌNH XÂY DỰNG TRUY VẤN\n"
    "Trước khi sinh SQL, hãy xác định theo thứ tự:\n"
    "1. Mục tiêu: người dùng muốn liệt kê, tra cứu, thống kê, so sánh "
    "hay tổng hợp dữ liệu?\n"
    "2. Grain: mỗi dòng kết quả đại diện cho một đối tượng nào, "
    "ví dụ một nhân viên, một dự án hay một bản ghi chấm công?\n"
    "3. Nguồn dữ liệu: chọn bảng chứa trực tiếp dữ liệu cần trả lời. "
    "Chỉ thêm bảng khi cần lấy thêm thông tin hoặc thực hiện điều kiện "
    "có căn cứ.\n"
    "4. Điều kiện: xác định các bộ lọc về đối tượng, trạng thái, "
    "thời gian và các tiêu chí khác dựa trên câu hỏi.\n"
    "5. Phép tổng hợp: chỉ dùng COUNT, SUM, AVG, MIN, MAX hoặc "
    "các phép tổng hợp khác khi câu hỏi yêu cầu hoặc ngữ nghĩa "
    "nghiệp vụ đòi hỏi.\n"
    "6. JOIN: chỉ nối những bảng thực sự cần thiết và tuân thủ "
    "đúng điều kiện trong join blueprint.\n"
    "7. Sắp xếp và giới hạn: chỉ dùng ORDER BY hoặc LIMIT khi "
    "câu hỏi yêu cầu thứ tự, thứ hạng, số lượng kết quả hoặc "
    "khi có quy tắc nghiệp vụ được cung cấp.\n\n"

    "III. QUY TẮC NGHIỆP VỤ\n"
    "- Phân biệt điều kiện lọc dữ liệu với yêu cầu sắp xếp dữ liệu.\n"
    "- Khi người dùng chỉ rõ một trạng thái, hãy lọc bằng cột trạng "
    "thái tương ứng; không thay thế điều kiện đó bằng sắp xếp theo ngày.\n"
    "- Chỉ diễn giải một thuật ngữ như 'mới', 'đang hoạt động' hoặc "
    "'hoàn thành' theo quy ước được xác định trong semantic profile "
    "hoặc ngữ cảnh đáng tin cậy.\n"
    "- Chỉ dùng ORDER BY theo thời gian khi câu hỏi thực sự yêu cầu "
    "thứ tự thời gian. Không tự coi 'mới' là 'mới nhất theo ngày'.\n"
    "- Không tự suy ra giá trị trạng thái, khoảng thời gian hoặc "
    "điều kiện lọc không được hỗ trợ bởi dữ liệu đầu vào.\n"
    "- Tôn trọng grain của bảng. Không JOIN không cần thiết hoặc "
    "làm nhân bản bản ghi dẫn đến sai số thống kê.\n"
    "- Không dùng SELECT * nếu chỉ cần một số cột cụ thể.\n"
    "- Dùng bí danh bảng nhất quán, ngắn gọn và dễ đọc; nếu JOIN "
    "nhiều bảng, luôn tham chiếu cột bằng bí danh bảng khi cần "
    "để tránh nhập nhằng.\n\n"

    "IV. CẤU TRÚC SQL ĐẦU RA\n"
    "- Truy vấn tra cứu hoặc liệt kê: SELECT các cột cần thiết, "
    "FROM bảng nguồn, WHERE nếu có điều kiện, ORDER BY/LIMIT "
    "chỉ khi phù hợp.\n"
    "- Truy vấn thống kê: SELECT các chiều phân nhóm và phép tổng hợp, "
    "FROM nguồn dữ liệu, JOIN nếu cần, WHERE để lọc trước tổng hợp, "
    "GROUP BY các chiều không tổng hợp, HAVING nếu lọc theo kết quả "
    "tổng hợp, ORDER BY nếu được yêu cầu.\n"
    "- Truy vấn nhiều bảng: xác định bảng nguồn chính trước, sau đó "
    "JOIN theo blueprint. Không thêm JOIN chỉ vì có đường nối.\n"
    "- Không bắt buộc phải có mọi mệnh đề. Chỉ sinh những mệnh đề "
    "thực sự cần thiết cho câu hỏi.\n"
    "- Ưu tiên truy vấn đơn giản nhất có thể trả lời chính xác "
    "câu hỏi nghiệp vụ.\n\n"

    "V. VÍ DỤ VỀ CÁCH DIỄN GIẢI\n"
    "Ví dụ 1:\n"
    "Câu hỏi: 'Liệt kê các dự án đang thực hiện.'\n"
    "Ý định: lọc dự án theo trạng thái, không phải theo thời gian.\n"
    "SQL mẫu:\n"
    "SELECT p.project_id, p.project_name, p.status\n"
    "FROM project AS p\n"
    "WHERE p.status = 'Đang thực hiện'\n"
    "Chỉ dùng giá trị trạng thái trên nếu đó là giá trị thực tế "
    "đã được xác nhận trong schema hoặc ngữ cảnh.\n\n"

    "Ví dụ 2:\n"
    "Câu hỏi: 'Liệt kê 10 dự án có ngày bắt đầu gần đây nhất.'\n"
    "Ý định: sắp xếp theo thời gian giảm dần.\n"
    "SQL mẫu:\n"
    "SELECT p.project_id, p.project_name, p.start_date\n"
    "FROM project AS p\n"
    "ORDER BY p.start_date DESC\n"
    "LIMIT 10\n\n"

    "Ví dụ 3:\n"
    "Câu hỏi: 'Cho biết tên các leader và chức vụ của họ.'\n"
    "Ý định: lấy thông tin nhân viên và vai trò lãnh đạo dự án; "
    "chỉ JOIN các bảng cần thiết theo join blueprint.\n"
    "SQL mẫu:\n"
    "SELECT DISTINCT e.employee_name, e.position, pl.leader_role\n"
    "FROM project_leaders AS pl\n"
    "JOIN employee AS e ON pl.employee_id = e.employee_id\n"
    "Ví dụ này giả định các bảng và cột trên được khai báo trong "
    "semantic profile và điều kiện JOIN được cho phép trong blueprint.\n\n"

    "VI. ĐIỀU KIỆN ĐẦU RA\n"
    "- Chỉ tạo truy vấn SELECT hoặc WITH ... SELECT.\n"
    "- Không tạo INSERT, UPDATE, DELETE hoặc lệnh thay đổi cấu trúc.\n"
    "- Không thêm dấu chấm phẩy ở cuối hoặc ở bất kỳ vị trí nào trong SQL.\n"
    "- RPC kiểm tra từ khóa trên toàn bộ văn bản SQL, kể cả chuỗi và "
    "comment; không dùng các từ khóa bị cấm: INSERT, UPDATE, DELETE, "
    "MERGE, DROP, ALTER, TRUNCATE, CREATE, GRANT, REVOKE, CALL, DO, "
    "EXECUTE, COPY, VACUUM, REFRESH, REINDEX, CLUSTER.\n"
    "- Không thêm comment hoặc nội dung giải thích vào truy vấn.\n"
    "- Nếu schema không đủ để tạo truy vấn hợp lệ, trả về đúng "
    "'-- INSUFFICIENT_SCHEMA'.\n"
    "- Nếu câu hỏi mơ hồ về ý nghĩa nghiệp vụ và không thể xác định "
    "đúng ý định từ ngữ cảnh, không tự đoán. Trả về "
    "'-- NEEDS_CLARIFICATION' để hệ thống xử lý riêng.\n"
    "- Chỉ trả về SQL hoặc một trong các marker được quy định trên. "
    "Tuyệt đối không sinh lời giải thích.\n\n"

    f"Semantic profiles:\n"
    f"{json.dumps(semantic_context, ensure_ascii=False, indent=2)}\n\n"
    f"Join blueprint:\n"
    f"{json.dumps(join_blueprint, ensure_ascii=False, indent=2)}"
)
    if run_id:
      global_event_bus.publish_event(
          run_id,
          "sql_generation",
          "started",
          {"message": "Đang sinh câu truy vấn SQL."},
          agent="sql_expert",
      )
    try:
      res = self.llm.invoke(
          [SystemMessage(content=prompt), HumanMessage(content=user_question)]
      )
      output = res.content.strip()
      query_start = re.search(r"(?im)^\s*(?:SELECT|WITH)\b", output)
      if query_start is not None:
        sql_query = output[query_start.start():].strip()
        if sql_query.endswith("```"):
          sql_query = sql_query[:-3].rstrip()
        sql_query = _normalize_rpc_query(sql_query)
      else:
        marker_match = re.search(
            r"(?m)^\s*-- (INSUFFICIENT_SCHEMA|NEEDS_CLARIFICATION)\s*$",
            output,
        )
        if marker_match is None:
          raise ValueError(
              "SQL expert không trả về SELECT/WITH hoặc marker được hỗ trợ."
          )
        sql_query = f"-- {marker_match.group(1)}"
    except Exception:
      if run_id:
        global_event_bus.publish_event(
            run_id,
            "sql_generation",
            "failed",
            {"message": "Không thể sinh câu truy vấn SQL."},
            agent="sql_expert",
        )
      raise

    if run_id:
      details: dict[str, Any] = {"sql_query": sql_query}
      token_usage = extract_token_usage(res)
      if token_usage is not None:
        details["token_usage"] = token_usage
      global_event_bus.publish_event(
          run_id,
          "sql_generation",
          "completed",
          details,
          agent="sql_expert",
      )
    return {"sql_query": sql_query}