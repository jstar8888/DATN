from datetime import date, datetime, time
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# ==========================================
# 1. BẢNG NHÂN VIÊN (employee)
# ==========================================
class EmployeeBase(BaseModel):
    employee_id: str = Field(..., description="Mã định danh duy nhất của nhân viên")
    employee_name: str = Field(..., description="Họ và tên nhân viên")
    position: str = Field(..., description="Vị trí/chức danh của nhân viên")
    department: str = Field(..., description="Phòng ban mà nhân viên thuộc về")
    system_level: str = Field(..., description="Cấp độ/quyền hệ thống (PM, Team Lead, Member)")


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeResponse(EmployeeBase):
    id: Optional[int] = Field(None, description="ID số tự tăng (nếu có)")

    class Config:
        from_attributes = True


# ==========================================
# 2. BẢNG DỰ ÁN (project)
# ==========================================
class ProjectBase(BaseModel):
    project_id: str = Field(..., description="Mã định danh duy nhất của dự án")
    project_name: str = Field(..., description="Tên dự án")
    description: Optional[str] = Field(None, description="Mô tả tổng quan về dự án")
    start_date: date = Field(..., description="Ngày bắt đầu dự án")
    end_date: date = Field(..., description="Ngày kết thúc hoặc deadline dự án")
    status: str = Field(..., description="Trạng thái hiện tại của dự án")
    note: Optional[str] = Field(None, description="Ghi chú liên quan đến dự án")


class ProjectLeaderAssignment(BaseModel):
    employee_id: str
    position: str


class ProjectCreate(ProjectBase):
    leaders: List[ProjectLeaderAssignment] = Field(default_factory=list)


class ProjectResponse(ProjectBase):
    id: Optional[int] = None

    class Config:
        from_attributes = True


# ==========================================
# 3. BẢNG TASK (task)
# ==========================================
class TaskBase(BaseModel):
    task_id: str = Field(..., description="Mã định danh duy nhất của Task")
    project_id: str = Field(..., description="Mã dự án mà Task thuộc về")
    task_name: str = Field(..., description="Tên/nội dung ngắn gọn của Task")
    category: str = Field(..., description="Hạng mục chuyên môn (BA, DE, DEV, TEST...)")
    assignee_employee_id: str = Field(..., description="Mã nhân viên trực tiếp thực hiện Task")
    manager_employee_id: str = Field(..., description="Mã nhân viên quản lý Task")
    start_date: date = Field(..., description="Ngày bắt đầu Task")
    end_date: date = Field(..., description="Ngày kết thúc hoặc deadline Task")
    estimated_hours: float = Field(..., description="Số giờ dự kiến thực hiện Task")
    actual_hours: float = Field(..., description="Số giờ thực tế đã thực hiện cho Task")
    progress_percent: float = Field(..., description="Phần trăm hoàn thành Task")
    status: str = Field(..., description="Trạng thái hiện tại của Task")
    note: Optional[str] = Field(None, description="Ghi chú liên quan đến Task")


class TaskCreate(TaskBase):
    pass


class TaskResponse(TaskBase):
    id: Optional[int] = None

    class Config:
        from_attributes = True


# ==========================================
# 4. BẢNG CHẤM CÔNG (attendance)
# ==========================================
class AttendanceBase(BaseModel):
    employee_id: str = Field(..., description="Mã nhân viên được chấm công")
    attendance_date: date = Field(..., description="Ngày chấm công")
    check_in: Optional[datetime] = Field(None, description="Thời điểm nhân viên đến")
    check_out: Optional[datetime] = Field(None, description="Thời điểm nhân viên về")
    status: str = Field(..., description="Trạng thái chấm công")
    note: Optional[str] = Field(None, description="Ghi chú về bản ghi chấm công")


class AttendanceCreate(AttendanceBase):
    pass


class AttendanceResponse(AttendanceBase):
    attendance_id: Optional[str] = Field(None, description="Mã định danh bản ghi chấm công")

    class Config:
        from_attributes = True


# ==========================================
# 5. BẢNG OVERTIME - OT (overtime)
# ==========================================
class OvertimeBase(BaseModel):
    employee_id: str = Field(..., description="Mã nhân viên thực hiện hoặc yêu cầu OT")
    ot_date: date = Field(..., description="Ngày ghi nhận hoặc thực hiện OT")
    project_id: Optional[str] = Field(None, description="Mã dự án liên quan đến OT")
    task_id: Optional[str] = Field(None, description="Mã Task liên quan đến OT")
    reason: str = Field(..., description="Lý do thực hiện OT")
    ot_hours: float = Field(..., description="Số giờ làm thêm")
    kpi_bonus: Optional[float] = Field(None, description="Thông tin cộng KPI liên quan đến OT")
    status: str = Field(..., description="Trạng thái OT (Chờ duyệt, Đã duyệt, Từ chối)")
    note: Optional[str] = Field(None, description="Ghi chú về OT")


class OvertimeCreate(OvertimeBase):
    pass


class OvertimeResponse(OvertimeBase):
    ot_id: Optional[str] = Field(None, description="Mã định danh bản ghi OT")

    class Config:
        from_attributes = True


# ==========================================
# 6. BẢNG NGHỈ PHÉP (leave_request)
# ==========================================
class LeaveRequestBase(BaseModel):
    employee_id: str = Field(..., description="Mã nhân viên yêu cầu nghỉ")
    leave_period: str = Field(..., description="Ngày và ca bắt đầu nghỉ, ví dụ: 2026-06-07 Ca sáng")
    return_period: str = Field(..., description="Ngày và ca trở lại làm việc, ví dụ: 2026-06-08 Ca sáng")
    reason: Optional[str] = Field(None, description="Lý do nghỉ phép")
    kpi_deduction: Optional[float] = Field(0, description="Thông tin trừ KPI liên quan")
    status: str = Field("Chờ duyệt", description="Trạng thái nghỉ phép (Chờ duyệt, Đã duyệt, Từ chối)")
    note: Optional[str] = Field(None, description="Ghi chú về yêu cầu nghỉ")


class LeaveRequestCreate(LeaveRequestBase):
    pass


class LeaveRequestResponse(LeaveRequestBase):
    leave_id: Optional[int] = Field(None, description="Mã định danh yêu cầu nghỉ phép")

    class Config:
        from_attributes = True


# ==========================================
# 7. BẢNG HÀNH VI / LỖI (behavior)
# ==========================================
class BehaviorBase(BaseModel):
    employee_id: str = Field(..., description="Mã nhân viên có hành vi được ghi nhận")
    recorded_date: date = Field(..., description="Ngày ghi nhận hành vi")
    behavior_type: str = Field(
        ...,
        description="Loại vi phạm: Lỗi nhiệm vụ, Lỗi trách nhiệm hoặc Lỗi nội quy",
    )
    description: str = Field(..., description="Mô tả chi tiết hành vi hoặc sự kiện")
    related_project_id: Optional[str] = Field(None, description="Mã dự án liên quan (nếu có)")
    related_task_id: Optional[str] = Field(None, description="Mã Task liên quan (nếu có)")
    note: Optional[str] = Field(None, description="Ghi chú bổ sung về hành vi")


class BehaviorCreate(BehaviorBase):
    behavior_type: Literal["Lỗi nhiệm vụ", "Lỗi trách nhiệm", "Lỗi nội quy"]


class BehaviorResponse(BehaviorBase):
    behavior_id: Optional[str] = Field(None, description="Mã định danh bản ghi hành vi")

    class Config:
        from_attributes = True


# ==========================================
# 8. BẢNG BÁO CÁO CÔNG VIỆC NGÀY (daily_work_report)
# ==========================================
class DailyWorkReportBase(BaseModel):
    employee_id: str = Field(..., description="Mã nhân viên lập báo cáo")
    report_date: date = Field(..., description="Ngày của báo cáo công việc")
    project_id: str = Field(..., description="Mã dự án liên quan")
    task_id: str = Field(..., description="Mã Task liên quan")
    content: str = Field(..., description="Nội dung công việc nhân viên đã thực hiện")
    content_url: Optional[str] = Field(None, description="Đường dẫn tới nội dung hoặc tài liệu liên quan")
    note: Optional[str] = Field(None, description="Ghi chú bổ sung cho báo cáo")


class DailyWorkReportCreate(DailyWorkReportBase):
    pass


class DailyWorkReportResponse(DailyWorkReportBase):
    daily_report_id: Optional[str] = Field(None, description="Mã định danh báo cáo ngày")

    class Config:
        from_attributes = True


# ==========================================
# 9. BẢNG QUẢN LÝ DỰ ÁN - PROJECT LEADER (project_leader)
# ==========================================
class ProjectLeaderBase(BaseModel):
    project_id: str = Field(..., description="Mã dự án liên quan")
    employee_id: str = Field(..., description="Mã nhân viên làm leader trong dự án")
    leader_role: str = Field(..., description="Chức vụ của leader")
    


class ProjectLeaderCreate(ProjectLeaderBase):
    pass


class ProjectLeaderResponse(ProjectLeaderBase):
    id: Optional[int] = Field(None, description="ID số tự tăng của bản ghi phân công")

    class Config:
        from_attributes = True