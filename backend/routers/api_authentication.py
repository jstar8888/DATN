import os
import logging
import unicodedata
from functools import lru_cache
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, status
from gotrue.errors import AuthApiError
from pydantic import BaseModel
from supabase import Client, create_client

from database.supabase_general_service import SupabaseService

load_dotenv()

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)
db = SupabaseService()
ROLE_LEVELS = {
    "Member": "Member",
    "Team Lead": "Team Lead",
    "Project Manager (PM)": "Project Manager",
}


class LoginRequest(BaseModel):
    user_id: str
    password: str
    role: str


def convert_name_to_email(full_name: str) -> str:
    normalized = unicodedata.normalize("NFKD", full_name)
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    clean_name = without_accents.replace("đ", "d").replace("Đ", "D").lower()
    return f"{'.'.join(clean_name.split())}@company.com"


@lru_cache(maxsize=1)
def _supabase_auth_client() -> Client:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cấu hình Supabase Auth chưa đầy đủ.",
        )
    return create_client(supabase_url, supabase_key)


def get_authenticated_employee(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    scheme, separator, token = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ.",
        )

    try:
        auth_user = _supabase_auth_client().auth.get_user(token).user
    except AuthApiError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token Supabase không hợp lệ hoặc đã hết hạn.",
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not validate Supabase access token")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không thể xác thực access token với Supabase.",
        ) from exc

    if auth_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token Supabase không hợp lệ hoặc đã hết hạn.",
        )

    employees = db.select(
        "employee",
        columns="employee_id, employee_name, position, department, system_level",
        filters={"auth_uuid": str(auth_user.id)},
        limit=1,
    )
    if not employees:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản Supabase chưa được liên kết với nhân viên.",
        )
    return employees[0]


def require_role(*allowed_roles: str):
    def check_role(
        employee: Dict[str, Any] = Depends(get_authenticated_employee),
    ) -> Dict[str, Any]:
        if employee.get("system_level") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tài khoản không có quyền truy cập chức năng này.",
            )
        return employee

    return check_role


@router.get("/employees")
def get_employees_by_role(role: str):
    system_level = ROLE_LEVELS.get(role)
    if system_level is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vai trò không hợp lệ.",
        )

    employees = db.select(
        "employee",
        columns="auth_uuid, employee_name, position",
        filters={"system_level": system_level},
        order_by="employee_name",
    )
    return employees


@router.post("/login")
def login(payload: LoginRequest):
    system_level = ROLE_LEVELS.get(payload.role)
    if system_level is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vai trò không hợp lệ.",
        )

    employees = db.select(
        "employee",
        columns=(
            "auth_uuid, employee_name, position, department, system_level"
        ),
        filters={"auth_uuid": payload.user_id},
        limit=1,
    )
    if not employees or employees[0].get("system_level") != system_level:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không thuộc vai trò đã chọn.",
        )

    employee = employees[0]
    try:
        auth_response = _supabase_auth_client().auth.sign_in_with_password(
            {
                "email": convert_name_to_email(employee["employee_name"]),
                "password": payload.password,
            }
        )
    except AuthApiError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên tài khoản hoặc mật khẩu không chính xác.",
        ) from None
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error while authenticating with Supabase Auth")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Không thể xác thực với Supabase Auth.",
        ) from exc
    if not auth_response.session or not auth_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tên tài khoản hoặc mật khẩu không chính xác.",
        )
    if str(auth_response.user.id) != employee["auth_uuid"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản Supabase không khớp với nhân viên đã chọn.",
        )

    return {
        "access_token": auth_response.session.access_token,
        "employee": {
            "employee_name": employee["employee_name"],
            "position": employee["position"],
            "department": employee["department"],
            "system_level": employee["system_level"],
        },
    }
