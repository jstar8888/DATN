
import os

from dotenv import load_dotenv
from database.supabase_general_service import SupabaseService

load_dotenv()


class SupabaseExecutor:
    def __init__(self, supabase_url: str | None = None, supabase_key: str | None = None):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY")

        if not self.supabase_url:
            raise ValueError("Chưa cấu hình biến môi trường SUPABASE_URL.")

        if not self.supabase_key:
            raise ValueError("Chưa cấu hình biến môi trường SUPABASE_KEY.")

        self.supabase_service = SupabaseService(
            self.supabase_url,
            self.supabase_key,
        )

    def execute_readonly(self, sql_query: str) -> list[dict]:
        """Thực thi truy vấn chỉ đọc thông qua RPC trên Supabase."""

        if not sql_query or not sql_query.strip():
            return []

        if "-- INSUFFICIENT_SCHEMA" in sql_query:
            return []

        try:
            result = self.supabase_service.rpc(
                "execute_raw_sql",
                {"sql_query": sql_query}
            )

            if result is None:
                return []

            # RPC trả JSONB dạng danh sách bản ghi.
            if isinstance(result, list):
                return result

            # Phòng trường hợp RPC trả về một object JSON.
            if isinstance(result, dict):
                return [result]

            raise RuntimeError(
                f"Định dạng kết quả RPC không hợp lệ: {type(result).__name__}"
            )

        except Exception as e:
            raise RuntimeError(
                f"Lỗi khi thực thi SQL qua Supabase RPC: {str(e)}"
            ) from e

    def execute(self, sql_query: str) -> list[dict]:
        """Giữ tương thích tên phương thức cũ, nhưng chỉ cho phép đọc."""
        return self.execute_readonly(sql_query)
