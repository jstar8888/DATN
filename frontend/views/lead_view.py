from datetime import date
from typing import List, Optional
import streamlit as st
import pandas as pd
from api_client import (
    API_BASE_URL as BACKEND_BASE_URL,
    authenticated_request,
)
from views.attendance_view import render_attendance_view
from views.behavior_view import render_behavior_view
from views.task_detail_view import render_task_detail
from views.chatbot_client import ask_chatbot

# Định nghĩa URL Backend cho Team Lead
API_BASE_URL = f"{BACKEND_BASE_URL}/api/lead"
API_AGENT_BASE_URL = f"{BACKEND_BASE_URL}/api/agent"


@st.fragment(run_every=2)
def _render_request_evaluation(request_key: str):
  evaluation = st.session_state.get("lead_request_evaluation")
  if not evaluation or evaluation.get("request_key") != request_key:
    return

  if evaluation.get("error"):
    st.error(evaluation["error"])
    if st.button("Thử phân tích lại", key="retry_request_evaluation"):
      st.session_state.pop("lead_request_evaluation", None)
      st.rerun()
    return

  result = evaluation.get("result")
  if result:
    st.markdown("#### 🤖 Kết quả phân tích")
    response_text = result.get("response")
    if response_text:
      st.markdown(response_text)
    else:
      st.error("Luồng đánh giá hoàn tất nhưng không có kết quả phân tích.")
    return

  run_id = evaluation.get("run_id")
  if not run_id:
    st.error("Không có mã chạy để lấy kết quả đánh giá.")
    return

  try:
    response = authenticated_request(
        "GET", f"{API_AGENT_BASE_URL}/runs/{run_id}"
    )
    run = response.json()
  except Exception as exc:
    st.error(f"Không thể tải trạng thái phân tích: {exc}")
    return

  if run.get("status") == "completed":
    evaluation["result"] = run
    st.session_state.lead_request_evaluation = evaluation
    st.markdown("#### 🤖 Kết quả phân tích")
    response_text = run.get("response")
    if response_text:
      st.markdown(response_text)
    else:
      st.error("Luồng đánh giá hoàn tất nhưng không có kết quả phân tích.")
  elif run.get("status") == "failed":
    evaluation["error"] = run.get(
        "error", "Không thể đánh giá đơn yêu cầu lúc này."
    )
    st.session_state.lead_request_evaluation = evaluation
    st.error(evaluation["error"])
  else:
    st.info("⏳ Luồng phân tích đang chạy. Kết quả sẽ tự động cập nhật tại đây.")


def render_lead_view():
  st.title("👨‍💻 Giao diện Trưởng nhóm (Team Lead)")

  # ---------------------------------------------------------
  # Sidebar Navigation: Quản lý menu qua session_state
  # ---------------------------------------------------------
  st.sidebar.markdown("### 🗂 Chức năng Team Lead")

  if "lead_menu" not in st.session_state:
    st.session_state.lead_menu = "📌 Quản lý Dự án & Task"

  lead_menu_options = [
      ("📌 Quản lý Dự án & Task", "📌 Quản lý Dự án & Task"),
      ("⏱️ Chấm công", "⏱️ Chấm công"),
      ("⚠️ Ghi nhận vi phạm", "⚠️ Ghi nhận vi phạm"),
      ("📋 Báo cáo thành viên", "📋 Xem báo cáo thành viên"),
      ("⚖ Phê duyệt đơn", "⚖️ Phê duyệt đơn (AI hỗ trợ)"),
      ("📈 Theo dõi tiến độ nhóm", "📈 Theo dõi tiến độ nhóm"),
      ("💬 AI Chatbot Nghiệp vụ", "💬 AI Chatbot Nghiệp vụ"),
  ]

  for label, val in lead_menu_options:
    if st.sidebar.button(
        label, width="stretch", key=f"lead_btn_{val}"
    ):
      st.session_state.lead_menu = val

  menu = st.session_state.lead_menu
  st.sidebar.markdown("---")

  # ---------------------------------------------------------
  # 1. Menu: Quản lý Dự án & Task (backend resolves the signed-in leader)
  # ---------------------------------------------------------
  if menu == "📌 Quản lý Dự án & Task":
    if "selected_project_detail" not in st.session_state:
      st.session_state.selected_project_detail = None

    if "lead_task_subview" not in st.session_state:
      st.session_state.lead_task_subview = "list"  # Các giá trị: "list", "create_task"

    # --- MÀN HÌNH 1: TỔNG QUAN DANH SÁCH DỰ ÁN ---
    if st.session_state.selected_project_detail is None:
      st.subheader("📌 Tổng quan Quản lý Dự án & Task của Trưởng nhóm")

      projects_list = []
      in_progress_count = 0
      completed_count = 0
      new_count = 0
      total_employees_managed = 0

      try:
        res = authenticated_request("GET", f"{API_BASE_URL}/me/projects")
        if res.status_code == 200:
          data = res.json()
          projects_list = data.get("projects", [])
          
          for p in projects_list:
            status = p.get("status", "")
            if status in ["Hoàn thành", "Đã hoàn thành"]:
              completed_count += 1
            elif status in ["Đang thực hiện", "Đang làm"]:
              in_progress_count += 1
            else:
              new_count += 1

        res_members = authenticated_request("GET", f"{API_BASE_URL}/me/members")
        if res_members.status_code == 200:
          members_list = res_members.json()
          total_employees_managed = len(members_list)
      except Exception as e:
        st.error(f"Lỗi kết nối tới Backend API: {e}")

      # Hiển thị 4 thẻ metrics yêu cầu
      col_m1, col_m2, col_m3, col_m4 = st.columns(4)
      with col_m1:
        st.metric(label="🔄 Đang thực hiện", value=str(in_progress_count))
      with col_m2:
        st.metric(label="✅ Đã hoàn thành", value=str(completed_count))
      with col_m3:
        st.metric(label="📌 Dự án mới", value=str(new_count))
      with col_m4:
        st.metric(label="👥 Tổng nhân viên quản lý", value=str(total_employees_managed))

      st.markdown("")
      st.markdown("### 🗂️ Bảng Danh sách Dự án Trưởng nhóm Phụ trách")

      if projects_list:
        df_projects = pd.DataFrame(projects_list)
        column_mapping = {
            "project_id": "Mã Dự Án",
            "project_name": "Tên Dự Án",
            "description": "Mô Tả",
            "start_date": "Ngày Bắt Đầu",
            "end_date": "Ngày Kết Thúc",
            "status": "Trạng Thái",
            
        }
        df_projects_display = df_projects.rename(columns={k: v for k, v in column_mapping.items() if k in df_projects.columns})
        df_projects_display = df_projects_display.drop(
            columns=["note", "created_at"],
            errors="ignore",
        )

        st.dataframe(df_projects_display, width="stretch", hide_index=True)

        st.markdown("#### 🔍 Xem Chi Tiết Dự Án")
        project_ids = [p.get("project_id") for p in projects_list if "project_id" in p]
        selected_proj_to_view = st.selectbox("Chọn Mã Dự Án để xem chi tiết", options=["-- Chọn dự án --"] + project_ids)
        
        if selected_proj_to_view != "-- Chọn dự án --":
          if st.button("Xem Chi Tiết Dự Án Này", type="primary"):
            st.session_state.selected_project_detail = selected_proj_to_view
            st.session_state.lead_task_subview = "list"
            st.rerun()
      else:
        st.info("Không có dữ liệu.")

    # --- MÀN HÌNH 2: CHI TIẾT DỰ ÁN & QUẢN LÝ TASK ---
    else:
      proj_id = st.session_state.selected_project_detail

      # Nút quay lại danh sách dự án chung
      if st.button("⬅️ Quay lại danh sách Dự án"):
        st.session_state.selected_project_detail = None
        st.session_state.lead_task_subview = "list"
        st.rerun()

      try:
        res = authenticated_request(
            "GET", f"{API_BASE_URL}/projects/{proj_id}/detail"
        )
        if res.status_code == 200:
          detail_data = res.json()
        else:
          st.error("Không thể lấy chi tiết dự án từ API!")
          return
      except Exception as e:
        st.error(f"Lỗi kết nối API: {e}")
        return

      proj_info = detail_data.get("project", {})
      st.subheader(f"📂 Chi tiết Dự án: {proj_info.get('project_name')}")
      st.info(
          f"📌 **Thông tin:**\n- **Mã dự án:** {proj_info.get('project_id')}\n"
          f"- **Mô tả:** {proj_info.get('description')}\n"
          f"- **Thời gian:** {proj_info.get('start_date')} ➔ {proj_info.get('end_date')}\n"
          f"- **Trạng thái:** {proj_info.get('status')}"
      )

      # Subview hiển thị danh sách task hoặc form thêm mới task bên trong chi tiết dự án
      if st.session_state.lead_task_subview == "list":
        st.markdown("### 📋 Danh sách Task liên quan trong Dự án")
        
        # Nút chuyển sang form tạo mới task
        if st.button("➕ Thêm mới Task", type="primary"):
          st.session_state.lead_task_subview = "create_task"
          st.rerun()

        st.markdown("")
        tasks = detail_data.get("tasks", [])
        if tasks:
          df_tasks_display = pd.DataFrame(tasks).drop(
              columns=["project_id", "actual_hours", "note"],
              errors="ignore",
          )
          st.dataframe(df_tasks_display, width="stretch", hide_index=True)
          tasks_by_id = {
              task["task_id"]: task
              for task in tasks
              if task.get("task_id")
          }
          task_ids = list(tasks_by_id)
          selected_task_id = st.selectbox(
              "Chọn task để xem chi tiết",
              options=task_ids,
              format_func=lambda task_id: (
                  f"{tasks_by_id[task_id].get('task_name', '')} ({task_id})"
              ),
              key=f"lead_task_detail_select_{proj_id}",
          )
          if st.button(
              "Xem chi tiết task",
              key=f"lead_task_detail_button_{proj_id}",
          ):
            st.session_state.selected_lead_task_id = selected_task_id
            st.session_state.lead_task_subview = "task_detail"
            st.rerun()
        else:
          st.info("Không có dữ liệu.")

      elif st.session_state.lead_task_subview == "create_task":
        if st.button("⬅️ Quay lại danh sách Task"):
          st.session_state.lead_task_subview = "list"
          st.rerun()

        st.markdown("### ✏️ Tạo mới Task cho Thành viên")
        try:
          assignees_res = authenticated_request(
              "GET", f"{API_BASE_URL}/me/task-assignees"
          )
          if assignees_res.status_code != 200:
            st.error(
                f"Không thể tải danh sách member: "
                f"{assignees_res.json().get('detail', 'Không xác định')}"
            )
            return
          assignee_data = assignees_res.json()
          leader_position = assignee_data["leader_position"]
          members = assignee_data["members"]
        except Exception as e:
          st.error(f"Lỗi kết nối API khi tải danh sách member: {e}")
          return

        if not members:
          st.warning(
              f"Không có member nào cùng position '{leader_position}' để phân công."
          )
          return

        member_names = {
            member["employee_id"]: (
                f"{member['employee_id']} - {member['employee_name']}"
            )
            for member in members
        }
        member_ids = list(member_names)

        with st.form("create_task_form"):
          col1, col2 = st.columns(2)
          with col1:
            task_id_input = st.text_input("Mã Task (Ví dụ: TSK-01)", value="TSK-01")
            task_name_input = st.text_input("Tên Task / Nội dung ngắn gọn")
            category_input = st.selectbox(
                "Hạng mục chuyên môn",
                [leader_position],
                disabled=True,
            )
          with col2:
            assignee_input = st.selectbox(
                "Member thực hiện",
                options=member_ids,
                format_func=lambda member_id: member_names[member_id],
            )
            start_d = st.date_input("Ngày bắt đầu task")
            end_d = st.date_input("Ngày kết thúc / deadline")
            est_hours = st.number_input("Số giờ dự kiến", value=8.0)

          if st.form_submit_button("Tạo Task Mới", type="primary"):
            if task_name_input.strip() and assignee_input:
              payload = {
                  "task_id": task_id_input,
                  "project_id": proj_id,
                  "task_name": task_name_input,
                  "category": category_input,
                  "assignee_employee_id": assignee_input,
                  "start_date": str(start_d),
                  "end_date": str(end_d),
                  "estimated_hours": est_hours,
                  "actual_hours": 0.0,
                  "progress_percent": 0.0,
                  "status": "Mới",
                  "note": ""
              }
              try:
                res = authenticated_request(
                    "POST", f"{API_BASE_URL}/tasks", json=payload
                )
                if res.status_code == 200:
                  st.success("Tạo task mới cho member thành công!")
                  st.session_state.lead_task_subview = "list"
                  st.rerun()
                else:
                  st.error(f"Lỗi: {res.json().get('detail', 'Không xác định')}")
              except Exception as e:
                st.error(f"Không thể kết nối API: {e}")
            else:
              st.warning("Vui lòng điền tên task và chọn member thực hiện!")

      elif st.session_state.lead_task_subview == "task_detail":
        if st.button("⬅️ Quay lại danh sách Task"):
          st.session_state.lead_task_subview = "list"
          st.rerun()

        task_id = st.session_state.get("selected_lead_task_id")
        if not task_id:
          st.error("Không tìm thấy task được chọn.")
          st.session_state.lead_task_subview = "list"
          return

        try:
          task_response = authenticated_request(
              "GET",
              f"{API_BASE_URL}/projects/{proj_id}/tasks/{task_id}/detail",
          )
          render_task_detail(task_response.json())
        except Exception as exc:
          st.error(f"Không thể tải chi tiết task: {exc}")

  # ---------------------------------------------------------
  # 2. Menu: Chấm công
  # ---------------------------------------------------------
  elif menu == "⏱️ Chấm công":
    st.subheader("⏱ Quản lý Chấm công Hàng ngày")
    render_attendance_view(state_prefix="lead_")

  elif menu == "⚠️ Ghi nhận vi phạm":
    render_behavior_view("Team Lead")

  # ---------------------------------------------------------
  # 3. Menu: Xem báo cáo thành viên
  # ---------------------------------------------------------
  elif menu == "📋 Xem báo cáo thành viên":
    st.subheader("📋 Quản lý Báo cáo Công việc Hàng ngày của Thành viên")
    try:
      res = authenticated_request("GET", f"{API_BASE_URL}/daily-reports")
      reports = res.json() if res.status_code == 200 else []
    except Exception as exc:
      st.error(f"Không thể tải báo cáo từ Backend: {exc}")
      reports = []

    if reports:
      df_reports = pd.DataFrame(reports)
      st.dataframe(df_reports, width="stretch", hide_index=True)
    else:
      st.info("Không có dữ liệu.")

  # ---------------------------------------------------------
  # 4. Menu: Phê duyệt đơn
  # ---------------------------------------------------------
  elif menu == "⚖️ Phê duyệt đơn (AI hỗ trợ)":
    st.subheader("⚖️ Phê duyệt đơn nghỉ phép / OT")

    selected_request = st.session_state.get("selected_lead_request")
    if selected_request:
      request_type = selected_request["type"]
      request_data = selected_request["request"]
      request_id = request_data.get("ot_id" if request_type == "OT" else "leave_id")
      request_key = f"{request_type}:{request_id}"
      request_label = "làm thêm giờ (OT)" if request_type == "OT" else "nghỉ phép"
      route_segment = (
          f"overtime/{request_id}"
          if request_type == "OT"
          else f"leave-requests/{request_id}"
      )

      if st.button("← Quay lại danh sách", key="back_to_pending_requests"):
        st.session_state.pop("selected_lead_request", None)
        st.session_state.pop("lead_request_evaluation", None)
        st.rerun()

      st.markdown(f"### Chi tiết đơn {request_label} `#{request_id}`")
      st.json(request_data, expanded=True)

      evaluation = st.session_state.get("lead_request_evaluation")
      if not evaluation or evaluation.get("request_key") != request_key:
        try:
          response = authenticated_request(
              "POST",
              f"{API_AGENT_BASE_URL}/request-evaluations",
              json={
                  "request_type": request_type,
                  "request_id": str(request_id),
              },
          )
          evaluation = {
              "request_key": request_key,
              "run_id": response.json()["run_id"],
          }
        except Exception as exc:
          evaluation = {
              "request_key": request_key,
              "error": f"Không thể bắt đầu phân tích đơn: {exc}",
          }
        st.session_state.lead_request_evaluation = evaluation

      if evaluation.get("error"):
        st.error(evaluation["error"])
        if st.button("Thử phân tích lại", key="retry_request_evaluation"):
          st.session_state.pop("lead_request_evaluation", None)
          st.rerun()
      else:
        _render_request_evaluation(request_key)

      st.markdown("---")
      approve_column, reject_column = st.columns(2)
      with approve_column:
        if st.button(
            "Chấp nhận",
            key="approve_selected_request",
            type="primary",
        ):
          try:
            authenticated_request(
                "PATCH",
                f"{API_BASE_URL}/{route_segment}/status",
                params={"status": "Đã duyệt"},
            )
            st.session_state["lead_approval_flash"] = "Đã duyệt đơn thành công!"
            st.session_state.pop("selected_lead_request", None)
            st.session_state.pop("lead_request_evaluation", None)
            st.rerun()
          except Exception as exc:
            st.error(f"Không thể chấp nhận đơn: {exc}")
      with reject_column:
        if st.button("Từ chối", key="reject_selected_request"):
          try:
            authenticated_request(
                "PATCH",
                f"{API_BASE_URL}/{route_segment}/status",
                params={"status": "Từ chối"},
            )
            st.session_state["lead_approval_flash"] = "Đã từ chối đơn."
            st.session_state.pop("selected_lead_request", None)
            st.session_state.pop("lead_request_evaluation", None)
            st.rerun()
          except Exception as exc:
            st.error(f"Không thể từ chối đơn: {exc}")
    else:
      approval_flash = st.session_state.pop("lead_approval_flash", None)
      if approval_flash:
        st.success(approval_flash)

      try:
        ot_res = authenticated_request(
            "GET", f"{API_BASE_URL}/overtime/pending"
        )
        pending_ots = ot_res.json()
      except Exception as exc:
        st.error(f"Không thể tải đơn OT từ Backend: {exc}")
        pending_ots = []

      try:
        leave_res = authenticated_request(
            "GET", f"{API_BASE_URL}/leave-requests/pending"
        )
        pending_leaves = leave_res.json()
      except Exception as exc:
        st.error(f"Không thể tải đơn nghỉ phép từ Backend: {exc}")
        pending_leaves = []

      st.markdown("#### ⏳ Danh sách đơn OT chờ duyệt")
      if pending_ots:
        for ot in pending_ots:
          with st.container(border=True):
            st.markdown(
                f"**Mã đơn:** `{ot.get('ot_id')}` | "
                f"**Nhân viên:** `{ot.get('employee_id')}` | "
                f"**Số giờ OT:** {ot.get('ot_hours')}h"
            )
            st.write(f"**Lý do:** {ot.get('reason') or 'Không có'}")
            if st.button(
                "Chi tiết",
                key=f"detail_ot_{ot.get('ot_id')}",
            ):
              st.session_state.selected_lead_request = {
                  "type": "OT",
                  "request": ot,
              }
              st.session_state.pop("lead_request_evaluation", None)
              st.rerun()
      else:
        st.info("Không có đơn OT chờ duyệt.")

      st.markdown("#### ⏳ Danh sách đơn nghỉ phép chờ duyệt")
      if pending_leaves:
        for leave in pending_leaves:
          with st.container(border=True):
            st.markdown(
                f"**Mã đơn:** `{leave.get('leave_id')}` | "
                f"**Nhân viên:** `{leave.get('employee_id')}`"
            )
            st.markdown(
                f"**Bắt đầu nghỉ:** {leave.get('leave_period')} | "
                f"**Trở lại:** {leave.get('return_period')}"
            )
            st.write(f"**Lý do:** {leave.get('reason') or 'Không có'}")
            if st.button(
                "Chi tiết",
                key=f"detail_leave_{leave.get('leave_id')}",
            ):
              st.session_state.selected_lead_request = {
                  "type": "LEAVE_REQUEST",
                  "request": leave,
              }
              st.session_state.pop("lead_request_evaluation", None)
              st.rerun()
      else:
        st.info("Không có đơn nghỉ phép chờ duyệt.")

  # ---------------------------------------------------------
  # 5. Menu: Theo dõi tiến độ nhóm
  # ---------------------------------------------------------
  elif menu == "📈 Theo dõi tiến độ nhóm":
    st.subheader("📈 Tổng hợp tiến độ Task của Team theo Tháng")
    col_m, col_y = st.columns(2)
    with col_m:
      m_val = st.selectbox("Chọn tháng", list(range(1, 13)), index=date.today().month - 1)
    with col_y:
      y_val = st.number_input("Nhập năm", value=date.today().year, step=1)

    try:
      res = authenticated_request(
          "GET",
          f"{API_BASE_URL}/me/employee-statistics",
          params={"month": m_val, "year": y_val},
      )
      stats_data = res.json() if res.status_code == 200 else []
    except Exception as exc:
      st.error(f"Không thể tải thống kê từ Backend: {exc}")
      stats_data = []

    if stats_data:
      st.dataframe(pd.DataFrame(stats_data), width="stretch", hide_index=True)
    else:
      st.info("Không có dữ liệu.")

  # ---------------------------------------------------------
  # 6. Menu: AI Chatbot Nghiệp vụ
  # ---------------------------------------------------------
  elif menu == "💬 AI Chatbot Nghiệp vụ":
    st.subheader("💬 AI Chatbot Trưởng nhóm (Text-to-SQL)")
    if "lead_messages" not in st.session_state:
      st.session_state.lead_messages = [{
          "role": "assistant",
          "content": (
              "Xin chào Trưởng nhóm! Tôi có thể hỗ trợ bạn phân tích dữ liệu"
              " dự án thông qua API Text-to-SQL."
          ),
      }]

    for message in st.session_state.lead_messages:
      with st.chat_message(message["role"]):
        st.markdown(message["content"])

    lead_prompt = st.chat_input("Nhập câu hỏi nghiệp vụ quản lý...")
    if lead_prompt:
      st.session_state.lead_messages.append(
          {"role": "user", "content": lead_prompt}
      )
      with st.chat_message("user"):
        st.markdown(lead_prompt)

      with st.chat_message("assistant"):
        with st.spinner("AI Agent đang sinh SQL và phân tích dữ liệu..."):
          try:
            result = ask_chatbot(lead_prompt)
            lead_response = result["response"]
          except Exception as e:
            lead_response = (
                f"⚠️ Luồng AI dừng do lỗi: {e}"
            )

          st.markdown(lead_response)

      st.session_state.lead_messages.append(
          {"role": "assistant", "content": lead_response}
      )