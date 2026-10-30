# agent_sql_search.py
import json
from typing import Any, Dict, Optional
from database.supabase_general_service import SupabaseService
from utils.event_bus import global_event_bus


class SqlSearchAgent:
    """Agent tổng hợp dữ liệu SQL thô theo schema chuẩn cho các nhánh OT và Leave Request."""

    def __init__(self):
        self.db = SupabaseService()

    def search(
        self,
        command: str,
        context: Dict[str, Any],
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Thực hiện tổng hợp dữ liệu SQL dựa trên command (OT hoặc Leave_request)."""
        if run_id:
            global_event_bus.publish_event(
                run_id,
                "sql_search_agent",
                "started",
                {"message": f"Bắt đầu tổng hợp dữ liệu SQL cho luồng {command}."},
                agent="sql_search_agent",
            )

        cmd_upper = command.strip().upper()

        try:
            if "OT" in cmd_upper or cmd_upper == "OVERTIME":
                sql_data = self._aggregate_ot_data(context)
            elif "LEAVE" in cmd_upper or "NGHI" in cmd_upper:
                sql_data = self._aggregate_leave_data(context)
            else:
                sql_data = self._aggregate_general_data(context)

            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "sql_search_agent",
                    "completed",
                    {"message": "Đã tổng hợp sql_data thành công."},
                    agent="sql_search_agent",
                )
            return sql_data

        except Exception as e:
            if run_id:
                global_event_bus.publish_event(
                    run_id,
                    "sql_search_agent",
                    "failed",
                    {"message": f"Lỗi tổng hợp dữ liệu SQL: {str(e)}"},
                    agent="sql_search_agent",
                )
            raise

    def _aggregate_ot_data(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Nhánh OT: Lấy thông tin dự án, task, báo cáo công việc, chấm công và hành vi vi phạm."""
        employee_id = ctx.get("employee_id")
        project_id = ctx.get("project_id")
        task_id = ctx.get("task_id")
        ot_id = ctx.get("ot_id")

        ot_request = None
        if ot_id:
            ot_records = self.db.select("overtime", filters={"ot_id": ot_id}, limit=1)
            if ot_records:
                ot_request = ot_records[0]
                employee_id = employee_id or ot_request.get("employee_id")
                project_id = project_id or ot_request.get("project_id")
                task_id = task_id or ot_request.get("task_id")

        project_info = None
        if project_id:
            proj_records = self.db.select("project", filters={"project_id": project_id}, limit=1)
            if proj_records:
                project_info = proj_records[0]

        task_info = None
        if task_id:
            task_records = self.db.select("task", filters={"task_id": task_id}, limit=1)
            if task_records:
                task_info = task_records[0]

        daily_reports = []
        if task_id:
            daily_reports = self.db.select(
                "daily_work_report",
                filters={"task_id": task_id},
                order_by="report_date",
                desc=True,
            )
        elif employee_id and project_id:
            emp_tasks = self.db.select(
                "task",
                filters={"project_id": project_id, "assignee_employee_id": employee_id},
            )
            for t in emp_tasks:
                tid = t.get("task_id")
                if tid:
                    reports = self.db.select("daily_work_report", filters={"task_id": tid})
                    daily_reports.extend(reports)

        employee_info = None
        attendance_logs = []
        behavior_logs = []
        if employee_id:
            emp_records = self.db.select("employee", filters={"employee_id": employee_id}, limit=1)
            if emp_records:
                employee_info = emp_records[0]

            # Sử dụng 'attendance_date' chuẩn theo schema
            attendance_logs = self.db.select(
                "attendance",
                filters={"employee_id": employee_id},
                order_by="attendance_date",
                desc=True,
            )
            behavior_logs = self.db.select("behavior", filters={"employee_id": employee_id})

        return {
            "type": "OT_EVALUATION_DATA",
            "employee_info": employee_info,
            "ot_request": ot_request,
            "project": project_info,
            "task": task_info,
            "daily_reports": daily_reports,
            "attendance": attendance_logs,
            "behavior": behavior_logs,
        }

    def _aggregate_leave_data(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Nhánh Leave_request: Lấy thông tin dự án, task hiện tại, dữ liệu chấm công và lịch sử nghỉ phép."""
        employee_id = ctx.get("employee_id")
        leave_id = ctx.get("leave_id")

        leave_request = None
        if leave_id:
            leave_records = self.db.select("leave_request", filters={"leave_id": leave_id}, limit=1)
            if leave_records:
                leave_request = leave_records[0]
                employee_id = employee_id or leave_request.get("employee_id")

        employee_info = None
        if employee_id:
            emp_records = self.db.select("employee", filters={"employee_id": employee_id}, limit=1)
            if emp_records:
                employee_info = emp_records[0]

        current_tasks = []
        active_projects = []
        if employee_id:
            all_tasks = self.db.select("task", filters={"assignee_employee_id": employee_id})
            current_tasks = [
                t for t in all_tasks if t.get("status") not in ["Hoàn thành", "Đã hủy"]
            ]
            proj_ids = list(set([t["project_id"] for t in current_tasks if "project_id" in t]))
            for pid in proj_ids:
                p_data = self.db.select("project", filters={"project_id": pid})
                if p_data:
                    active_projects.extend(p_data)

        attendance_logs = []
        leave_history = []
        if employee_id:
            attendance_logs = self.db.select(
                "attendance",
                filters={"employee_id": employee_id},
                order_by="attendance_date",
                desc=True,
            )
            leave_history = self.db.select("leave_request", filters={"employee_id": employee_id})

        return {
            "type": "LEAVE_REQUEST_EVALUATION_DATA",
            "employee_info": employee_info,
            "leave_request": leave_request,
            "active_projects": active_projects,
            "current_assigned_tasks": current_tasks,
            "attendance": attendance_logs,
            "leave_history": leave_history,
        }

    def _aggregate_general_data(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        employee_id = ctx.get("employee_id")
        if not employee_id:
            return {"type": "UNKNOWN", "message": "Không đủ thông tin ngữ cảnh."}

        employee_info = self.db.select("employee", filters={"employee_id": employee_id})
        tasks = self.db.select("task", filters={"assignee_employee_id": employee_id})
        attendance = self.db.select("attendance", filters={"employee_id": employee_id})

        return {
            "type": "GENERAL_DATA",
            "employee_info": employee_info[0] if employee_info else None,
            "tasks": tasks,
            "attendance": attendance,
        }