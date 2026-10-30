from datetime import date, datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from datamodel.schema import *
from database.supabase_general_service import SupabaseService
from routers.api_authentication import require_role

# Import các schema đã định nghĩa (giả sử nằm trong file schemas.py hoặc dùng chung file)
# from schemas import TaskResponse, DailyReportCreate, OvertimeCreate, LeaveCreate

router = APIRouter(
    prefix="/api/member",
    tags=["Member Operations"],
    dependencies=[Depends(require_role("Member"))],
)
db = SupabaseService()  # Khởi tạo SupabaseService để sử dụng trong các API


# Pydantic model chuyên biệt cho việc cập nhật task theo yêu cầu số 2
class TaskUpdatePayload(BaseModel):
    status: Optional[str] = Field(None, description="Trạng thái hiện tại của Task")
    progress_percent: Optional[float] = Field(None, description="Phần trăm hoàn thành Task")
    actual_hours: Optional[float] = Field(
        None, ge=0, description="Số giờ thực tế đã thực hiện"
    )
    note: Optional[str] = Field(None, description="Ghi chú liên quan đến Task")


class AuthenticatedOvertimeCreate(OvertimeCreate):
    employee_id: Optional[str] = None


class AuthenticatedLeaveRequestCreate(LeaveRequestCreate):
    employee_id: Optional[str] = None


class AuthenticatedDailyWorkReportCreate(DailyWorkReportCreate):
    employee_id: Optional[str] = None


# ==========================================
# 1. API lấy ra toàn bộ task của nhân viên kèm tên dự án (ẩn mã dự án/nhân viên) và phân loại
# ==========================================
@router.get("/me/tasks-summary")
def get_employee_tasks(
    employee: Dict = Depends(require_role("Member")),
):
    """
    Lấy toàn bộ task của nhân viên theo employee_id. 
    Frontend nhận được sẽ hiển thị thành bảng task, tính tổng số task, 
    và phân loại: chưa làm, đang làm, đã làm. 
    Đồng thời thay thế mã dự án bằng tên dự án, loại bỏ các trường mã (ID) hiển thị nhạy cảm.
    """
    try:
        # Lấy danh sách task của nhân viên từ bảng task[cite: 1]
        tasks = db.select(
            "task", filters={"assignee_employee_id": employee["employee_id"]}
        )
        
        formatted_tasks = []
        total_tasks = len(tasks)
        not_started = 0
        in_progress = 0
        completed = 0

        for t in tasks:
            status = t.get("status", "")
            
            # Thống kê phân loại trạng thái (có thể điều chỉnh chuỗi trạng thái tuỳ dữ liệu thực tế của bạn)
            if status in ["Chưa làm", "Chưa bắt đầu"]:
                not_started += 1
            elif status in ["Đang làm", "Đang thực hiện"]:
                in_progress += 1
            elif status in ["Đã làm", "Hoàn thành"]:
                completed += 1
            else:
                not_started += 1 # Mặc định nếu không khớp

            # Lấy tên dự án từ bảng project thay vì hiển thị mã dự án[cite: 1]
            project_name = "Không xác định"
            proj_id = t.get("project_id")
            if proj_id:
                proj_data = db.select("project", columns="project_name", filters={"project_id": proj_id})
                if proj_data:
                    project_name = proj_data[0].get("project_name", "Không xác định")

            # Xây dựng cấu trúc trả về loại bỏ hoàn toàn các trường mã dự án, mã nhân viên, mã task hiển thị không cần thiết nếu muốn ẩn
            formatted_tasks.append({
                "task_id": t.get("task_id"),
                "task_name": t.get("task_name"),
                "project_id": proj_id,
                "project_name": project_name, # Đã thay thế mã dự án thành tên dự án
                "category": t.get("category"),
                "start_date": t.get("start_date"),
                "end_date": t.get("end_date"),
                "estimated_hours": t.get("estimated_hours"),
                "actual_hours": t.get("actual_hours"),
                "progress_percent": t.get("progress_percent"),
                "status": status,
                "note": t.get("note")
            })

        return {
            "total_tasks": total_tasks,
            "statistics": {
                "not_started": not_started,
                "in_progress": in_progress,
                "completed": completed
            },
            "tasks": formatted_tasks
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 2. API cập nhật task (status, tiến độ, note) theo task_id
# ==========================================
@router.patch("/tasks/{task_id}/progress")
def update_task_progress(
    payload: TaskUpdatePayload,
    task_id: str = Path(..., description="Mã định danh task"),
    employee: Dict = Depends(require_role("Member")),
):
    """
    Cập nhật thông tin trường status, progress_percent và note (nếu có) của task dựa vào task_id[cite: 1].
    """
    try:
        # Lọc các trường không bị None để update
        update_data = payload.dict(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="Không có dữ liệu nào được cung cấp để cập nhật")

        tasks = db.select(
            "task",
            columns="task_id",
            filters={
                "task_id": task_id,
                "assignee_employee_id": employee["employee_id"],
            },
            limit=1,
        )
        if not tasks:
            raise HTTPException(status_code=404, detail="Không tìm thấy task")

        result = db.update("task", update_data, filters={"task_id": task_id})
        if not result:
            raise HTTPException(status_code=404, detail="Không tìm thấy task hoặc cập nhật thất bại")
            
        return {
            "message": "Cập nhật task thành công",
            "data": result[0]
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 3. API tạo đơn xin nghỉ phép
# ==========================================
@router.post("/leave-requests", response_model=LeaveRequestResponse)
def create_leave_request(
    leave_request: AuthenticatedLeaveRequestCreate,
    employee: Dict = Depends(require_role("Member")),
):
    """
    Tạo mới một đơn xin nghỉ phép với ngày và ca nghỉ/trở lại.
    """
    try:
        data = leave_request.dict(exclude={"employee_id"})
        data["employee_id"] = employee["employee_id"]
        data["status"] = "Chờ duyệt"
            
        result = db.insert("leave_request", data)
        if not result:
            raise HTTPException(status_code=400, detail="Không thể tạo đơn xin nghỉ phép")
        return result[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 4. API tạo đơn xin làm thêm giờ (OT)
# ==========================================
@router.post("/overtime", response_model=OvertimeResponse)
def create_overtime_request(
    overtime: AuthenticatedOvertimeCreate,
    employee: Dict = Depends(require_role("Member")),
):
    """
    Tạo mới một đơn xin làm thêm giờ (OT) cho nhân viên[cite: 1].
    """
    try:
        data = overtime.dict()
        data["employee_id"] = employee["employee_id"]

        if data.get("project_id") or data.get("task_id"):
            assigned_tasks = db.select(
                "task",
                columns="task_id, project_id",
                filters={"assignee_employee_id": employee["employee_id"]},
            )
            if data.get("task_id"):
                matching_tasks = [
                    task
                    for task in assigned_tasks
                    if task.get("task_id") == data["task_id"]
                ]
                if not matching_tasks:
                    raise HTTPException(
                        status_code=403,
                        detail="Bạn chỉ có thể chọn task được phân công cho mình.",
                    )
                if (
                    data.get("project_id")
                    and matching_tasks[0].get("project_id") != data["project_id"]
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Task không thuộc dự án đã chọn.",
                    )
                if not data.get("project_id"):
                    data["project_id"] = matching_tasks[0].get("project_id")
            elif not any(
                task.get("project_id") == data["project_id"]
                for task in assigned_tasks
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Bạn chỉ có thể chọn dự án có task được phân công cho mình.",
                )

        # Trạng thái mặc định khi mới tạo là 'Chờ duyệt'
        if not data.get("status"):
            data["status"] = "Chờ duyệt"
            
        result = db.insert("overtime", data)
        if not result:
            raise HTTPException(status_code=400, detail="Không thể tạo đơn làm thêm giờ")
        return result[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 5. API tạo báo cáo công việc ngày
# ==========================================
@router.post("/daily-reports", response_model=DailyWorkReportResponse)
def create_daily_report(
    report: AuthenticatedDailyWorkReportCreate,
    employee: Dict = Depends(require_role("Member")),
):
    """
    Tạo mới một báo cáo công việc hằng ngày của nhân viên[cite: 1].
    """
    try:
        data = report.dict()
        data["employee_id"] = employee["employee_id"]
        result = db.insert("daily_work_report", data)
        if not result:
            raise HTTPException(status_code=400, detail="Không thể tạo báo cáo công việc ngày")
        return result[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))