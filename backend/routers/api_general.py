import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from datamodel.schema import AttendanceCreate, BehaviorCreate
from database.supabase_general_service import SupabaseService
from routers.api_authentication import require_role
import requests

router = APIRouter(
    prefix="/api/sheet-attendance",
    tags=["Attendance Operations"],
)
behavior_router = APIRouter(
    prefix="/api/general",
    tags=["General HR Operations"],
)

db = SupabaseService()
VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
VIETNAM_UTC_OFFSET = timezone(timedelta(hours=7))

# URL Web App được cung cấp sau khi bạn Deploy Google Apps Script dưới dạng Web App
# APPS_SCRIPT_WEB_APP_URL = "https://script.google.com/macros/s/AKfycbzEXBN8Hiu81CZzkxamLGHU3AGRLl1AeJ1LVkKPeBOAx7jOaP2iNAl2wsf_lJN398d4/exec"
APPS_SCRIPT_WEB_APP_URL = os.getenv("APPS_SCRIPT_WEB_APP_URL")

class AttendanceActionPayload(BaseModel):
    action: Literal["check_in", "check_out"] = Field(
        ..., description="Hành động: 'check_in' hoặc 'check_out'"
    )
    timestamp: datetime = Field(..., description="Thời điểm chấm công thực tế")

class SyncAttendancePayload(BaseModel):
    attendance_date: date = Field(..., description="Ngày chấm công của bảng")
    records: List[AttendanceCreate] = Field(..., description="Danh sách bản ghi chấm công từ Sheet")


def format_sheet_time(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Thời gian từ Google Apps Script phải là chuỗi.")

    try:
        parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            return time.fromisoformat(value).strftime("%H:%M")
        except ValueError as exc:
            raise ValueError(
                f"Định dạng thời gian không hợp lệ từ Google Apps Script: {value}"
            ) from exc

    if parsed_datetime.date() == date(1899, 12, 30):
        if parsed_datetime.tzinfo is None:
            return parsed_datetime.strftime("%H:%M")
        return parsed_datetime.astimezone(VIETNAM_UTC_OFFSET).strftime("%H:%M")

    if parsed_datetime.tzinfo is None:
        parsed_datetime = parsed_datetime.replace(tzinfo=VIETNAM_TIMEZONE)
    else:
        parsed_datetime = parsed_datetime.astimezone(VIETNAM_TIMEZONE)
    return parsed_datetime.strftime("%H:%M")


# ==========================================
# 1. API nhận yêu cầu từ Streamlit để đẩy lên Google Sheet
# ==========================================
@router.post("/record", status_code=status.HTTP_200_OK)
def record_attendance_to_sheet(
    payload: AttendanceActionPayload,
    employee: Dict = Depends(require_role("Member", "Team Lead")),
):
    """
    Nhận yêu cầu check-in hoặc check-out từ thành viên đăng nhập,
    tự động lấy employee_id từ token và gọi Google Apps Script để ghi lên Google Sheet[cite: 2].
    """
    try:
        employee_id = employee["employee_id"]
        attendance_timestamp = payload.timestamp
        if attendance_timestamp.tzinfo is None:
            attendance_timestamp = attendance_timestamp.replace(
                tzinfo=VIETNAM_TIMEZONE
            )
        else:
            attendance_timestamp = attendance_timestamp.astimezone(VIETNAM_TIMEZONE)
        date_str = attendance_timestamp.date().isoformat()
        time_str = attendance_timestamp.strftime("%H:%M")

        sheet_payload = {
            "action": payload.action,
            "employee_id": employee_id,
            "date": date_str,
            "time": time_str
        }

        # Gọi HTTP POST tới Google Apps Script Web App
        response = requests.post(APPS_SCRIPT_WEB_APP_URL, json=sheet_payload, timeout=15)
        res_data = response.json()

        if response.status_code == 200 and res_data.get("status") == "success":
            return {
                "success": True,
                "message": f"Đã ghi nhận {payload.action} lên Google Sheet thành công cho nhân viên {employee_id}"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Google Apps Script trả về lỗi: {res_data.get('message', 'Không xác định')}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể kết nối tới Google Sheet: {str(e)}"
        )


# ==========================================
# 2. API nhận dữ liệu từ Google Sheet để đồng bộ lên Supabase
# ==========================================
@router.post("/sync-to-supabase", status_code=status.HTTP_200_OK)
def sync_attendance_to_supabase(payload: SyncAttendancePayload):
    """
    API do Google Apps Script gọi (thông qua menu trên Sheet) 
    để đồng bộ dữ liệu chấm công từ Sheet lên bảng attendance trên Supabase[cite: 1].
    """
    try:
        attendance_date_str = payload.attendance_date.isoformat()
        synced_count = 0

        for record in payload.records:
            data = record.dict()
            data["attendance_date"] = attendance_date_str
            if data.get("check_in"):
                data["check_in"] = data["check_in"].isoformat()
            if data.get("check_out"):
                data["check_out"] = data["check_out"].isoformat()

            # Kiểm tra xem nhân viên đã có bản ghi chấm công ngày đó trên Supabase chưa
            existing = db.select(
                "attendance",
                filters={
                    "employee_id": data["employee_id"],
                    "attendance_date": attendance_date_str
                }
            )

            if existing:
                db.update("attendance", data, filters={
                    "employee_id": data["employee_id"],
                    "attendance_date": attendance_date_str
                })
            else:
                db.insert("attendance", data)
            
            synced_count += 1

        return {
            "success": True,
            "message": f"Đồng bộ thành công {synced_count} bản ghi lên Supabase.",
            "total_synced": synced_count
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi đồng bộ vào Supabase: {str(e)}"
        )
    



    # ==========================================
# 3. API kiểm tra trạng thái chấm công từ Google Sheet
# ==========================================
@router.get("/status", status_code=status.HTTP_200_OK)
def get_attendance_status(
    target_date: date = Query(..., description="Ngày cần kiểm tra định dạng YYYY-MM-DD"),
    employee: Dict = Depends(require_role("Member", "Team Lead")),
):
    """
    Gọi sang Google Apps Script để lấy trạng thái chấm công hiện tại của nhân viên trong ngày,
    trả về state và kèm theo thời gian check_in / check_out nếu có.
    """
    try:
        employee_id = employee["employee_id"]

        sheet_payload = {
            "action": "check_status",
            "employee_id": employee_id,
            "date": target_date.isoformat()
        }

        try:
            response = requests.post(
                APPS_SCRIPT_WEB_APP_URL, json=sheet_payload, timeout=15
            )
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Không thể kết nối tới Google Apps Script: {exc}"
            ) from exc

        try:
            res_data = response.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google Apps Script trả về dữ liệu không phải JSON."
            ) from exc

        if response.status_code != 200 or not isinstance(res_data, dict):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google Apps Script trả về phản hồi không hợp lệ."
            )

        if res_data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Google Apps Script trả về lỗi: "
                    f"{res_data.get('message', 'Không xác định')}"
                )
            )

        attendance_state = res_data.get("state")
        if attendance_state not in {
            "no_sheet",
            "not_checked_in",
            "not_checked_out",
            "completed",
        }:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Google Apps Script không trả về trạng thái chấm công hợp lệ."
            )

        try:
            check_in = format_sheet_time(res_data.get("check_in"))
            check_out = format_sheet_time(res_data.get("check_out"))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=str(exc)
            ) from exc

        return {
            "success": True,
            "state": attendance_state,
            "check_in": check_in,
            "check_out": check_out,
            "message": res_data.get("message", "")
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Không thể lấy trạng thái từ Google Sheet: {str(e)}"
        )


@behavior_router.post("/behaviors", status_code=status.HTTP_201_CREATED)
def create_behavior(
    payload: BehaviorCreate,
    employee: Dict = Depends(
        require_role("Project Manager", "Team Lead")
    ),
):
    """Record a behavior entry for an employee in Supabase."""
    try:
        target_employee = db.select(
            "employee",
            columns="employee_id, system_level, position",
            filters={"employee_id": payload.employee_id},
            limit=1,
        )
        if not target_employee:
            raise HTTPException(status_code=404, detail="Không tìm thấy nhân viên.")

        if employee.get("system_level") == "Team Lead":
            target = target_employee[0]
            if (
                target.get("system_level") != "Member"
                or target.get("position") != employee.get("position")
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Team Lead chỉ có thể ghi nhận vi phạm của member cùng nhóm.",
                )

        record = payload.model_dump(mode="json")
        project_id = record.get("related_project_id")
        task_id = record.get("related_task_id")

        if project_id:
            projects = db.select(
                "project", filters={"project_id": project_id}, limit=1
            )
            if not projects:
                raise HTTPException(status_code=404, detail="Không tìm thấy dự án.")

            if employee.get("system_level") == "Team Lead":
                leader_projects = db.select(
                    "project_leaders",
                    columns="project_id",
                    filters={
                        "employee_id": employee["employee_id"],
                        "project_id": project_id,
                    },
                    limit=1,
                )
                if not leader_projects:
                    raise HTTPException(
                        status_code=403,
                        detail="Team Lead chỉ có thể chọn dự án đang phụ trách.",
                    )

        if task_id:
            tasks = db.select(
                "task", filters={"task_id": task_id}, limit=1
            )
            if not tasks:
                raise HTTPException(status_code=404, detail="Không tìm thấy task.")

            task_project_id = tasks[0].get("project_id")
            if project_id and task_project_id != project_id:
                raise HTTPException(
                    status_code=400,
                    detail="Task không thuộc dự án đã chọn.",
                )
            if employee.get("system_level") == "Team Lead" and not project_id:
                leader_projects = db.select(
                    "project_leaders",
                    columns="project_id",
                    filters={
                        "employee_id": employee["employee_id"],
                        "project_id": task_project_id,
                    },
                    limit=1,
                )
                if not leader_projects:
                    raise HTTPException(
                        status_code=403,
                        detail="Team Lead chỉ có thể chọn task thuộc dự án đang phụ trách.",
                    )

        created_records = db.insert("behavior", record)
        if not created_records:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Không thể lưu ghi nhận vi phạm vào Supabase.",
            )
        return {"success": True, "behavior": created_records[0]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi lưu ghi nhận vi phạm: {exc}",
        ) from exc