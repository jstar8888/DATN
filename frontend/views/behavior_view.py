from datetime import date

import streamlit as st

from api_client import API_BASE_URL as BACKEND_BASE_URL, authenticated_request

BEHAVIOR_TYPES = ["Lỗi nhiệm vụ", "Lỗi trách nhiệm", "Lỗi nội quy"]


def render_behavior_view(role: str):
    st.subheader("⚠️ Ghi nhận vi phạm")

    if role == "Team Lead":
        api_base_url = f"{BACKEND_BASE_URL}/api/lead"
        employee_path = "/me/members"
        project_path = "/me/projects"
        project_detail_path = "/projects/{project_id}/detail"
    else:
        api_base_url = f"{BACKEND_BASE_URL}/api/pm"
        employee_path = "/employees"
        project_path = "/projects/statistics"
        project_detail_path = "/projects/{project_id}/comprehensive-detail"

    try:
        employees_response = authenticated_request(
            "GET", f"{api_base_url}{employee_path}"
        )
        employees = employees_response.json()
        projects_response = authenticated_request(
            "GET", f"{api_base_url}{project_path}"
        )
        projects_data = projects_response.json()
    except Exception as exc:
        st.error(f"Không thể tải dữ liệu cho form vi phạm: {exc}")
        return

    if isinstance(projects_data, dict):
        projects = projects_data.get("projects", [])
    else:
        projects = projects_data

    employees_by_id = {
        employee["employee_id"]: employee
        for employee in employees
        if employee.get("employee_id")
    }
    employee_ids = list(employees_by_id)
    if not employee_ids:
        st.info("Không có nhân viên phù hợp để ghi nhận vi phạm.")
        return

    project_by_id = {
        project["project_id"]: project
        for project in projects
        if project.get("project_id")
    }
    project_ids = list(project_by_id)

    selected_employee_id = st.selectbox(
        "Chọn nhân viên được ghi nhận",
        options=employee_ids,
        format_func=lambda employee_id: (
            f"{employees_by_id[employee_id].get('employee_name', '')} "
            f"({employee_id})"
        ),
        key=f"{role.lower().replace(' ', '_')}_behavior_employee",
    )
    selected_employee = employees_by_id[selected_employee_id]
    col_id, col_name = st.columns(2)
    with col_id:
        st.text_input(
            "Mã nhân viên",
            value=selected_employee_id,
            disabled=True,
            key=f"{role.lower().replace(' ', '_')}_behavior_employee_id",
        )
    with col_name:
        st.text_input(
            "Tên nhân viên",
            value=selected_employee.get("employee_name", ""),
            disabled=True,
            key=f"{role.lower().replace(' ', '_')}_behavior_employee_name",
        )

    project_choices = ["-- Không chọn dự án --", *project_ids]
    selected_project_id = st.selectbox(
        "Dự án (không bắt buộc)",
        options=project_choices,
        format_func=lambda project_id: (
            "-- Không chọn dự án --"
            if project_id == "-- Không chọn dự án --"
            else (
                f"{project_by_id[project_id].get('project_name', '')} "
                f"({project_id})"
            )
        ),
        key=f"{role.lower().replace(' ', '_')}_behavior_project",
    )

    task_options = []
    if selected_project_id != "-- Không chọn dự án --":
        try:
            detail_response = authenticated_request(
                "GET",
                f"{api_base_url}"
                f"{project_detail_path.format(project_id=selected_project_id)}",
            )
            detail = detail_response.json()
        except Exception as exc:
            st.error(f"Không thể tải task của dự án: {exc}")
            return

        if role == "Team Lead":
            task_options = detail.get("tasks", [])
        else:
            task_groups = detail.get("tasks_grouped_by_manager", {})
            task_options = [
                task
                for tasks in task_groups.values()
                for task in tasks
            ]

    tasks_by_id = {
        task["task_id"]: task for task in task_options if task.get("task_id")
    }
    task_ids = list(tasks_by_id)
    selected_task_id = st.selectbox(
        "Task (không bắt buộc)",
        options=["-- Không chọn task --", *task_ids],
        format_func=lambda task_id: (
            "-- Không chọn task --"
            if task_id == "-- Không chọn task --"
            else f"{tasks_by_id[task_id].get('task_name', '')} ({task_id})"
        ),
        disabled=selected_project_id == "-- Không chọn dự án --",
        key=f"{role.lower().replace(' ', '_')}_behavior_task",
    )

    with st.form(f"{role.lower().replace(' ', '_')}_behavior_form"):
        recorded_date = st.date_input("Ngày ghi nhận", value=date.today())
        behavior_type = st.selectbox("Loại vi phạm", BEHAVIOR_TYPES)
        description = st.text_area("Mô tả chi tiết")
        note = st.text_area("Ghi chú bổ sung (không bắt buộc)")
        submitted = st.form_submit_button("Lưu vi phạm", type="primary")

    if submitted:
        if not description.strip():
            st.warning("Vui lòng nhập mô tả chi tiết vi phạm.")
            return

        payload = {
            "employee_id": selected_employee_id,
            "recorded_date": recorded_date.isoformat(),
            "behavior_type": behavior_type,
            "description": description.strip(),
            "related_project_id": (
                selected_project_id
                if selected_project_id != "-- Không chọn dự án --"
                else None
            ),
            "related_task_id": (
                selected_task_id
                if selected_task_id != "-- Không chọn task --"
                else None
            ),
            "note": note.strip() or None,
        }
        try:
            authenticated_request(
                "POST",
                f"{BACKEND_BASE_URL}/api/general/behaviors",
                json=payload,
            )
        except Exception as exc:
            st.error(f"Không thể lưu vi phạm: {exc}")
            return

        st.success("Đã ghi nhận vi phạm thành công.")
        st.rerun()
