import logging
from agents.configurable_llm import get_retrieval_settings
from database.supabase_general_service import SupabaseService
from script.embedding_service import GeminiEmbeddingService

logger = logging.getLogger(__name__)
supabase_service = SupabaseService()
embedding_service = GeminiEmbeddingService()


def get_top_k_table_matches_from_supabase(
    user_question: str, top_k: int | None = None
) -> list[dict]:
  """Return matching table rows, including similarity when provided by the RPC."""
  match_count = (
      top_k
      if top_k is not None
      else get_retrieval_settings()["table_match_count"]
  )
  # 1. Tạo vector embedding cho câu hỏi của người dùng
  # Lưu ý: Với câu hỏi truy vấn, dùng task_type="RETRIEVAL_QUERY" cho Gemini
  query_vector = embedding_service.generate(
      user_question, task_type="RETRIEVAL_QUERY"
  )

  try:
    # 2. Gọi hàm RPC trên Supabase đã cấu hình pgvector
    data = supabase_service.rpc(
      "match_tables_by_embedding",
      {"query_embedding": query_vector, "match_count": match_count},
    )

    if not data:
      return []

    return data

  except Exception as exc:
    logger.exception("Không thể truy xuất các bảng phù hợp từ Supabase")
    raise RuntimeError(
        "Không thể truy xuất các bảng phù hợp từ Supabase."
    ) from exc


def get_top_k_tables_from_supabase(
    user_question: str, top_k: int | None = None
) -> list:
  """Return the names of the top matching tables."""
  matches = get_top_k_table_matches_from_supabase(user_question, top_k)
  return [item["table_name"] for item in matches]


# --- Ví dụ sử dụng ---
if __name__ == "__main__":
  question = "Cho tôi danh sách nhân viên đi làm muộn và số giờ OT"
  top_tables = get_top_k_tables_from_supabase(question, top_k=3)
  print("Danh sách bảng ứng viên thực tế:", top_tables)