import asyncio
import logging
from uuid import uuid4

from datetime import date
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from pydantic import BaseModel, Field
from datamodel.schema import *
from database.supabase_general_service import SupabaseService
from routers.api_authentication import get_authenticated_employee, require_role
from fastapi.encoders import jsonable_encoder
from utils.event_bus import global_event_bus

router = APIRouter(
    prefix="/api/lead",
    tags=["Lead & PM Operations"],
    dependencies=[Depends(require_role("Team Lead"))],
)
logger = logging.getLogger(__name__)
db = SupabaseService()  # Khởi tạo SupabaseService để sử dụng trong các API
_request_evaluation_tasks: set[asyncio.Task[None]] = set()


class AuthenticatedTaskCreate(TaskCreate):
    manager_employee_id: Optional[str] = None


def _get_leader_member_ids(employee: Dict) -> set[str]:
    """Return member employee IDs sharing the leader's position."""
    leader_position = employee.get("position")
    if not leader_position:
        raise HTTPException(
            status_code=400, detail="Leader chưa được cấu hình vị trí"
        )

    members = db.select(
        "employee",
        columns="employee_id",
        filters={"position": leader_position, "system_level": "Member"},
    )
    return {member["employee_id"] for member in members if member.get("employee_id")}


async def _run_request_evaluation(
    run_id: str,
    command: str,
    context: Dict[str, object],
) -> None:
    try:
        from agents.langgraph_request_evaluation import app as evaluation_workflow

        result = await asyncio.to_thread(
            evaluation_workflow.invoke,
            {"command": command, "context": context, "run_id": run_id},
        )
        global_event_bus.publish_event(
            run_id,
            "run",
            "completed",
            {
                "request_type": command,
                "request_id": context.get("ot_id", context.get("leave_id")),
                "response": result["final_answer"],
                "data": jsonable_encoder(
                    {
                        "sql_data": result["sql_data"],
                        "rag_data": result["rag_data"],
                    }
                ),
            },
            agent="orchestrator",
        )
    except Exception:
        logger.exception(
            "Đánh giá đơn nhân sự thất bại (run_id=%s)", run_id
        )
        global_event_bus.publish_event(
            run_id,
            "run",
            "failed",
            {"message": "Không thể đánh giá đơn yêu cầu lúc này."},
            agent="orchestrator",
        )


def _start_request_evaluation(command: str, context: Dict[str, object]) -> Dict[str, str]:
    run_id = str(uuid4())
    request_id = context.get("ot_id", context.get("leave_id"))
    global_event_bus.publish_event(
        run_id,
        "run",
        "running",
        {
            "question": f"Đánh giá đơn {command} mã {request_id}",
            "request_type": command,
            "request_id": request_id,
        },
        agent="orchestrator",
    )
    task = asyncio.create_task(_run_request_evaluation(run_id, command, context))
    _request_evaluation_tasks.add(task)
    task.add_done_callback(_request_evaluation_tasks.discard)
    return {"status": "running", "run_id": run_id}


def _get_pending_request_for_leader(
    table: str,
    id_column: str,
    request_id: object,
    employee: Dict,
) -> Dict:
    requests = db.select(table, filters={id_column: request_id}, limit=1)
    member_ids = _get_leader_member_ids(employee)
    if not requests or requests[0].get("employee_id") not in member_ids:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn yêu cầu")
    request = requests[0]
    if request.get("status") != "Chờ duyệt":
        raise HTTPException(
            status_code=409,
            detail="Chỉ có thể đánh giá đơn đang chờ duyệt.",
        )
    return request


# ==========================================
# 1. API lấy ra toàn bộ dự án mà leader đang tham gia
# ==========================================
@router.get("/me/projects", summary="Lấy danh sách dự án của leader")
def get_leader_projects(
    employee: Dict = Depends(get_authenticated_employee),
):
    """
    Lấy ra toàn bộ dự án mà leader đang tham gia thông qua bảng nối project_leaders.
    Frontend có thể dùng dữ liệu này để tính tổng số dự án quản lý và số dự án đã hoàn thành.
    """
    try:
        # Lấy danh sách project_id mà leader này tham gia từ bảng project_leaders[cite: 1]
        leader_id = employee["employee_id"]
        pl_records = db.select("project_leaders", columns="project_id", filters={"employee_id": leader_id})
        if not pl_records:
            return {"total_projects": 0, "completed_projects": 0, "projects": []}
        
        project_ids = [item["project_id"] for item in pl_records]
        
        # Lấy thông tin chi tiết của các dự án này từ bảng project[cite: 1]
        projects = []
        for pid in project_ids:
            proj_data = db.select("project", filters={"project_id": pid})
            if proj_data:
                projects.extend(proj_data)
                
        total_projects = len(projects)
        completed_projects = sum(1 for p in projects if p.get("status") == "Hoàn thành")
        
        return {
            "total_projects": total_projects,
            "completed_projects": completed_projects,
            "projects": projects
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 2. API lấy ra thông tin chi tiết 1 dự án
# ==========================================
@router.get("/projects/{project_id}/detail", summary="Lấy thông tin chi tiết của dự án")
def get_project_detail(
    project_id: str = Path(..., description="Mã dự án"),
    employee: Dict = Depends(get_authenticated_employee),
):
    """
    Lấy thông tin dự án và các task do leader đang đăng nhập quản lý.
    """
    try:
        # Lấy thông tin cơ bản dự án[cite: 1]
        project_data = db.select("project", filters={"project_id": project_id})
        if not project_data:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án")
        
        project_info = project_data[0]
        
        # Lấy danh sách task thuộc dự án[cite: 1]
        task_filters = {"project_id": project_id}
        tasks = db.select("task", filters=task_filters)
        
        # Nếu có truyền leader_id để kiểm tra task do leader này quản lý (manager_employee_id)[cite: 1]
        tasks = [
            task
            for task in tasks
            if task.get("manager_employee_id") == employee["employee_id"]
        ]
            
        total_tasks = len(tasks)
        
        return {
            "project": project_info,
            "total_tasks": total_tasks,
            "tasks": tasks
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/projects/{project_id}/tasks/{task_id}/detail",
    summary="Lấy chi tiết task và báo cáo tiến độ cho Team Lead",
)
def get_leader_task_detail(
    project_id: str,
    task_id: str,
    employee: Dict = Depends(get_authenticated_employee),
):
    try:
        task_records = db.select(
            "task",
            filters={
                "project_id": project_id,
                "task_id": task_id,
                "manager_employee_id": employee["employee_id"],
            },
            limit=1,
        )
        if not task_records:
            raise HTTPException(status_code=404, detail="Không tìm thấy task.")

        task = task_records[0]
        assignee_records = db.select(
            "employee",
            columns="employee_id, employee_name",
            filters={"employee_id": task.get("assignee_employee_id")},
            limit=1,
        )
        reports = db.select(
            "daily_work_report",
            filters={"task_id": task_id},
            order_by="report_date",
            desc=True,
        )
        return {
            "task": task,
            "assignee_name": (
                assignee_records[0].get("employee_name")
                if assignee_records
                else None
            ),
            "reports": reports,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 3. API tạo mới 1 task cho member thực hiện
# ==========================================
@router.post("/tasks", summary="Tạo mới 1 task cho member thực hiện", response_model=TaskResponse)
def create_task(
    task: AuthenticatedTaskCreate,
    employee: Dict = Depends(get_authenticated_employee),
):
    """Tạo mới một task cho member thực hiện."""
    try:
        data = task.model_dump(mode="json")
        data["manager_employee_id"] = employee["employee_id"]
        projects = db.select(
            "project",
            columns="project_id, status",
            filters={"project_id": data["project_id"]},
            limit=1,
        )
        if not projects:
            raise HTTPException(status_code=404, detail="Không tìm thấy dự án")

        result = db.insert("task", data)
        if not result:
            raise HTTPException(status_code=400, detail="Không thể tạo task mới")

        if projects[0].get("status") == "Mới":
            updated_project = db.update(
                "project",
                {"status": "Đang thực hiện"},
                filters={"project_id": data["project_id"]},
            )
            if not updated_project:
                raise HTTPException(
                    status_code=500,
                    detail="Đã tạo task nhưng không thể cập nhật trạng thái dự án.",
                )
        return result[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 4. API chỉnh sửa nội dung 1 task
# ==========================================
@router.put("/tasks/{task_id}", summary="Chỉnh sửa nội dung 1 task", response_model=TaskResponse)
def update_task(task_id: str, task_update: TaskCreate):
    """Chỉnh sửa nội dung thông tin của 1 task dựa vào task_id."""
    try:
        data = task_update.dict(exclude_unset=True)
        result = db.update("task", data, filters={"task_id": task_id})
        if not result:
            raise HTTPException(status_code=404, detail="Không tìm thấy task hoặc không thể cập nhật")
        return result[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 5. API lấy ra toàn bộ các báo cáo công việc ngày (sort theo ngày)
# ==========================================
@router.get("/daily-reports", summary="Lấy ra toàn bộ các báo cáo công việc ngày", response_model=List[DailyWorkReportResponse])
def get_daily_reports(
    desc: bool = Query(True, description="Sắp xếp giảm dần theo ngày nếu True, tăng dần nếu False")
):
    """Lấy toàn bộ báo cáo công việc ngày của nhân viên, được sắp xếp theo ngày (report_date)[cite: 1]."""
    try:
        reports = db.select("daily_work_report", order_by="report_date", desc=desc)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 6. API lấy ra các đơn xin làm ngoài giờ chưa duyệt
# ==========================================
@router.get("/overtime/pending", summary="Lấy ra các đơn xin làm ngoài giờ chưa duyệt", response_model=List[OvertimeResponse])
def get_pending_overtime(
    employee: Dict = Depends(get_authenticated_employee),
):
    """Lấy đơn OT chờ duyệt của các member cùng vị trí với leader."""
    try:
        member_ids = _get_leader_member_ids(employee)
        if not member_ids:
            return []
        pending_ots = db.select("overtime", filters={"status": "Chờ duyệt"})
        return [
            request
            for request in pending_ots
            if request.get("employee_id") in member_ids
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/overtime/{ot_id}/evaluate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bắt đầu đánh giá đơn OT đang chờ duyệt",
)
async def evaluate_overtime_request(
    ot_id: str = Path(..., description="Mã đơn OT"),
    employee: Dict = Depends(get_authenticated_employee),
):
    request = _get_pending_request_for_leader(
        "overtime", "ot_id", ot_id, employee
    )
    return _start_request_evaluation("OT", {"ot_id": request["ot_id"]})


# ==========================================
# 7. API cập nhật trạng thái cho đơn xin làm ngoài giờ
# ==========================================
@router.patch("/overtime/{ot_id}/status", summary="Cập nhật trạng thái cho đơn xin làm ngoài giờ")
def update_overtime_status(
    ot_id: str = Path(..., description="Mã đơn OT"),
    status: str = Query(..., description="Trạng thái mới: Đã duyệt hoặc Từ chối"),
    employee: Dict = Depends(get_authenticated_employee),
):
    """Chỉ cho phép leader cập nhật đơn OT của member cùng vị trí."""
    try:
        member_ids = _get_leader_member_ids(employee)
        overtime = db.select("overtime", filters={"ot_id": ot_id}, limit=1)
        if not overtime or overtime[0].get("employee_id") not in member_ids:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn OT")

        result = db.update("overtime", {"status": status}, filters={"ot_id": ot_id})
        if not result:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn OT")
        return {"message": "Cập nhật trạng thái OT thành công", "data": result[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 8. API lấy ra các đơn xin nghỉ phép chưa duyệt
# ==========================================
@router.get("/leave-requests/pending", summary="Lấy ra các đơn xin nghỉ phép chưa duyệt", response_model=List[LeaveRequestResponse])
def get_pending_leave_requests(
    employee: Dict = Depends(get_authenticated_employee),
):
    """Lấy đơn nghỉ phép chờ duyệt của các member cùng vị trí với leader."""
    try:
        member_ids = _get_leader_member_ids(employee)
        if not member_ids:
            return []
        pending_leaves = db.select("leave_request", filters={"status": "Chờ duyệt"})
        return [
            request
            for request in pending_leaves
            if request.get("employee_id") in member_ids
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/leave-requests/{leave_id}/evaluate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Bắt đầu đánh giá đơn nghỉ phép đang chờ duyệt",
)
async def evaluate_leave_request(
    leave_id: int = Path(..., description="Mã đơn nghỉ phép"),
    employee: Dict = Depends(get_authenticated_employee),
):
    request = _get_pending_request_for_leader(
        "leave_request", "leave_id", leave_id, employee
    )
    return _start_request_evaluation(
        "LEAVE_REQUEST", {"leave_id": request["leave_id"]}
    )


# ==========================================
# 9. API cập nhật trạng thái cho đơn xin nghỉ phép
# ==========================================
@router.patch("/leave-requests/{leave_id}/status", summary="Cập nhật trạng thái cho đơn xin nghỉ phép")
def update_leave_request_status(
    leave_id: int = Path(..., description="Mã đơn nghỉ phép"),
    status: str = Query(..., description="Trạng thái mới: Đã duyệt hoặc Từ chối"),
    employee: Dict = Depends(get_authenticated_employee),
):
    """Chỉ cho phép leader cập nhật đơn nghỉ phép của member cùng vị trí."""
    try:
        member_ids = _get_leader_member_ids(employee)
        leave_request = db.select(
            "leave_request", filters={"leave_id": leave_id}, limit=1
        )
        if not leave_request or leave_request[0].get("employee_id") not in member_ids:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn nghỉ phép")

        result = db.update("leave_request", {"status": status}, filters={"leave_id": leave_id})
        if not result:
            raise HTTPException(status_code=404, detail="Không tìm thấy đơn nghỉ phép")
        return {"message": "Cập nhật trạng thái nghỉ phép thành công", "data": result[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 10. API lấy ra toàn bộ thành viên do leader quản lý (tên và mã nhân viên) theo vị trí làm việc
# ==========================================
@router.get("/me/members", summary="Lấy ra toàn bộ thành viên do leader quản lý")
def get_leader_members_by_position(
    employee: Dict = Depends(get_authenticated_employee),
):
    """Lấy tất cả member có cùng vị trí với leader đang đăng nhập."""
    try:
        leader_position = employee.get("position")
        if not leader_position:
            raise HTTPException(
                status_code=400, detail="Leader chưa được cấu hình vị trí"
            )
        return db.select(
            "employee",
            columns="employee_id, employee_name, position, department",
            filters={"position": leader_position, "system_level": "Member"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me/task-assignees", summary="Lấy thành viên cùng vị trí với leader")
def get_leader_task_assignees(
    employee: Dict = Depends(get_authenticated_employee),
):
    """Lấy vị trí của leader và các member có cùng vị trí để phân công task."""
    try:
        leader_id = employee["employee_id"]
        leader_data = db.select(
            "employee",
            columns="employee_id, position",
            filters={"employee_id": leader_id},
        )
        if not leader_data:
            raise HTTPException(status_code=404, detail="Không tìm thấy leader")

        leader_position = leader_data[0].get("position")
        if not leader_position:
            raise HTTPException(
                status_code=400, detail="Leader chưa được cấu hình vị trí"
            )

        members = db.select(
            "employee",
            columns="employee_id, employee_name, position",
            filters={"position": leader_position, "system_level": "Member"},
        )
        return {
            "leader_position": leader_position,
            "members": members,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 11. API thống kê nhân viên do leader quản lý (tổng task, task đang làm, số vi phạm theo tháng)
# ==========================================
@router.get("/me/employee-statistics", summary="Thống kê nhân viên do leader quản lý")
def get_leader_employee_statistics(
    employee: Dict = Depends(get_authenticated_employee),
    month: int = Query(..., description="Tháng cần thống kê (1-12)"),
    year: int = Query(..., description="Năm cần thống kê")
):
    """
    Thống kê các nhân viên do leader quản lý: tổng số task đã làm, số task đang làm,
    và số vi phạm (lấy từ bảng behavior) được sắp xếp theo tháng[cite: 1].
    """
    try:
        leader_id = employee["employee_id"]
        # 1. Xác định danh sách nhân viên do leader này quản lý thông qua task
        tasks = db.select("task", columns="task_id, assignee_employee_id, status, start_date, end_date", filters={"manager_employee_id": leader_id})
        if not tasks:
            return []
        
        member_ids = list(set([t["assignee_employee_id"] for t in tasks if t.get("assignee_employee_id")]))
        
        statistics = []
        for mid in member_ids:
            # Lấy thông tin nhân viên[cite: 1]
            emp_data = db.select("employee", columns="employee_id, employee_name", filters={"employee_id": mid})
            emp_name = emp_data[0]["employee_name"] if emp_data else "Unknown"
            
            # Lọc task của riêng nhân viên này
            emp_tasks = [t for t in tasks if t.get("assignee_employee_id") == mid]
            total_tasks = len(emp_tasks)
            # Giả sử trạng thái đang làm là 'Đang thực hiện' hoặc 'Đang làm'
            working_tasks = sum(1 for t in emp_tasks if t.get("status") in ["Đang thực hiện", "Đang làm"])
            
            # Lấy số vi phạm từ bảng behavior trong tháng/năm yêu cầu[cite: 1]
            behaviors = db.select("behavior", filters={"employee_id": mid})
            violation_count = 0
            for b in behaviors:
                rec_date = b.get("recorded_date")
                if rec_date:
                    # Chuyển đổi chuỗi ngày sang kiểu date nếu cần hoặc so sánh trực tiếp
                    if isinstance(rec_date, str):
                        parsed_date = date.fromisoformat(rec_date)
                    else:
                        parsed_date = rec_date
                    if parsed_date.month == month and parsed_date.year == year:
                        violation_count += 1
                        
            statistics.append({
                "employee_id": mid,
                "employee_name": emp_name,
                "total_tasks": total_tasks,
                "working_tasks": working_tasks,
                "violation_count": violation_count
            })
            
        # Sắp xếp danh sách thống kê theo số vi phạm hoặc tổng task (ví dụ: sort theo tổng số task giảm dần)
        statistics.sort(key=lambda x: x["total_tasks"], reverse=True)
        
        return statistics
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))