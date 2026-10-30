import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List, Optional

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()  

_request_access_token: ContextVar[Optional[str]] = ContextVar(
    "supabase_request_access_token", default=None
)
_request_client: ContextVar[Optional[Client]] = ContextVar(
    "supabase_request_client", default=None
)


@contextmanager
def use_request_access_token(access_token: str) -> Iterator[None]:
    token_context = _request_access_token.set(access_token)
    client_context = _request_client.set(None)
    try:
        yield
    finally:
        _request_client.reset(client_context)
        _request_access_token.reset(token_context)


class SupabaseService:

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        # Lấy từ biến môi trường hoặc truyền trực tiếp
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")

        if not self.url or not self.key:
            raise ValueError(
                "Thiếu SUPABASE_URL hoặc SUPABASE_KEY trong biến môi trường!"
            )

        self.client: Client = create_client(self.url, self.key)

    def _get_client(self) -> Client:
        access_token = _request_access_token.get()
        if not access_token:
            return self.client

        client = _request_client.get()
        if client is None:
            client = create_client(self.url, self.key)
            client.postgrest.auth(access_token)
            _request_client.set(client)
        return client

    def select(
        self,
        table: str,
        columns: str = "*",
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        desc: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Lấy dữ liệu tổng quát từ bất kỳ bảng nào (Select * hoặc select cột chỉ định).

        :param table: Tên bảng (vd: 'projects', 'tasks') :param columns: Các cột
        cần lấy, mặc định '*' :param filters: Dictionary điều kiện lọc {'status':
        'Đang làm', 'id': 1} :param order_by: Tên cột muốn sắp xếp :param desc:
        True nếu muốn giảm dần (descending) :param limit: Giới hạn số lượng bản
        ghi trả về
        """
        query = self._get_client().table(table).select(columns)

        # Xử lý điều kiện lọc (Filters)
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)

        # Xử lý sắp xếp (Ordering)
        if order_by:
            query = query.order(order_by, desc=desc)

        # Xử lý giới hạn (Limit)
        if limit:
            query = query.limit(limit)

        response = query.execute()
        return response.data

    def insert(
        self, table: str, data: Dict[str, Any] | List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Thêm mới dữ liệu vào bảng (hỗ trợ thêm 1 hoặc nhiều bản ghi)."""
        response = self._get_client().table(table).insert(data).execute()
        return response.data

    def upsert(
        self, table: str, data: Dict[str, Any] | List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Thêm mới hoặc cập nhật dữ liệu theo khóa unique/primary key."""
        response = self._get_client().table(table).upsert(data).execute()
        return response.data

    def update(
        self, table: str, data: Dict[str, Any], filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Cập nhật dữ liệu dựa trên điều kiện."""
        query = self._get_client().table(table).update(data)

        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)

        response = query.execute()
        return response.data

    def delete(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Xóa dữ liệu dựa trên điều kiện."""
        query = self._get_client().table(table).delete()

        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)

        response = query.execute()
        return response.data

    def rpc(
        self, function_name: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Gọi hàm RPC (Stored Procedures / Vector Similarity Search trên Supabase)."""
        response = self._get_client().rpc(function_name, params or {}).execute()
        return response.data