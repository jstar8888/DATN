import json
import os
from google import genai
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()  

from embedding_service import GeminiEmbeddingService

# Khởi tạo API Client cho Gemini và Supabase

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# Khởi tạo dịch vụ embedding một lần duy nhất
embedding_service = GeminiEmbeddingService()


def load_json_file(file_path):
  """Đọc file JSON chứa semantic profiles của các bảng."""
  with open(file_path, "r", encoding="utf-8") as f:
    return json.load(f)


def build_table_chunk(table):
  """Chuyển đổi thông tin của 1 bảng thành một đoạn văn bản (chunk) ngữ nghĩa chuẩn hóa."""
  table_name = table.get("table_name", "")
  business_name = table.get("business_name", "")
  table_role = table.get("table_role", "")
  description = table.get("description", "")
  grain = table.get("grain", "")
  common_user_terms = ", ".join(table.get("common_user_terms", []))

  columns_info = []
  for col in table.get("columns", []):
    col_str = (
        f"- {col.get('name')} ({col.get('type')}):"
        f" {col.get('description')} [Role: {col.get('semantic_role')}]"
    )
    columns_info.append(col_str)

  columns_text = "\n".join(columns_info)

  chunk = f"""Table Name: {table_name}
Business Name: {business_name}
Table Role: {table_role}
Description: {description}
Grain: {grain}
Common User Terms: {common_user_terms}
Columns:
{columns_text}
"""
  return chunk.strip()


def main():
  data = load_json_file("table_semantic_profiles.json")
  tables = data.get("tables", [])

  print(f"Đang xử lý tổng cộng {len(tables)} bảng...")

  for table in tables:
    table_name = table.get("table_name")
    print(f"-> Đang xử lý bảng: {table_name}")

    # 1. Tạo phần chunk văn bản cho bảng
    chunk_text = build_table_chunk(table)

    # 2. Vector hóa thông qua service tái sử dụng (task_type mặc định là RETRIEVAL_DOCUMENT)
    vector = embedding_service.generate(chunk_text, task_type="RETRIEVAL_DOCUMENT")

    # 3. Chuẩn bị dữ liệu để lưu vào Supabase
    payload = {
        "table_name": table_name,
        "chunk_text": chunk_text,
        "embedding": vector,
    }

    # Upsert dữ liệu lên Supabase
    supabase.table("table_embeddings").upsert(
        payload, on_conflict="table_name"
    ).execute()
    print(f"   Đã lưu thành công bảng {table_name} lên Supabase!")

  print("Hoàn tất quá trình vector hóa toàn bộ bảng!")


if __name__ == "__main__":
  main()



  '''''
  bây giờ hãy giúp tôi bổ sung thêm 2 api vào api_pm một api đầu tiên là dùng để đẩy các đoạn embdedidng lên supabase có điều là giờ là đẩy các đoạn embedding từ frontend chứ không cần cắt từ file semastic json nữa mà. 1 api khác lấy ra table name và chunking text để hiển thị trên frontend. 2 api này hãy sử dụng các dịch vụ đã viết sẵn trong file supabase_service
  '''''