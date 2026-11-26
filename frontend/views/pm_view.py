import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from urllib.parse import quote
from api_client import (
    API_BASE_URL as BACKEND_BASE_URL,
    authenticated_request,
)
from views.chatbot_client import render_chatbot
from views.behavior_view import render_behavior_view
from views.task_detail_view import render_task_detail
from datetime import date, datetime, time

# Định nghĩa URL gốc của FastAPI Backend
API_BASE_URL = f"{BACKEND_BASE_URL}/api/pm"


@st.dialog("Xác nhận kết thúc dự án")
def confirm_complete_project(project_id: str, project_name: str):
  st.warning(f"Bạn có chắc chắn muốn kết thúc dự án **{project_name}** không?")
  confirm_col, cancel_col = st.columns(2)
  with confirm_col:
    if st.button(
        "Xác nhận kết thúc",
        type="primary",
        key=f"confirm_complete_project_{project_id}",
    ):
      try:
        authenticated_request(
            "PUT",
            f"{API_BASE_URL}/projects/{project_id}",
            json={"status": "Hoàn thành"},
        )
      except Exception as exc:
        st.error(f"Không thể cập nhật trạng thái dự án: {exc}")
      else:
        st.success("Đã cập nhật dự án thành Hoàn thành.")
        st.rerun()
  with cancel_col:
    if st.button("Hủy", key=f"cancel_complete_project_{project_id}"):
      st.rerun()


def render_pm_view():
  st.title("📈 Giao diện Quản lý Dự án (PM)")

  # ---------------------------------------------------------
  # Sidebar Navigation: Quản lý menu qua session_state
  # ---------------------------------------------------------
  st.sidebar.markdown("### 🗂 Chức năng PM")

  if "pm_menu" not in st.session_state:
    st.session_state.pm_menu = "🚀 Quản lý Dự án"

  pm_menu_options = [
      ("🚀 Quản lý Dự án", "🚀 Quản lý Dự án"),
      ("👥 Quản lý Nhân viên", "👥 Quản lý Nhân viên"),
      ("⚠️ Ghi nhận vi phạm", "⚠️ Ghi nhận vi phạm"),
      ("📊 AI-Agent Tổng hợp Tiến độ", "📊 AI-Agent Tổng hợp Tiến độ"),
      ("🗂️ Quản lý Kho tài liệu (RAG)", "🗂️ Quản lý Kho tài liệu (RAG)"),
      (
          "⚙️ Quản lý Semantic Profile",
          "⚙️ Quản lý Semantic Profile (Text-to-SQL)",
      ),
      ("🕸️ Quản lý Relationship", "🕸️ Quản lý Relationship"),
      ("💬 AI Chatbot Toàn hệ thống", "💬 AI Chatbot Toàn hệ thống"),
      ("🧠 Cấu hình AI Agent", "🧠 Cấu hình AI Agent"),
  ]

  for label, val in pm_menu_options:
    if st.sidebar.button(
        label, width="stretch", key=f"pm_btn_{val}"
    ):
      st.session_state.pm_menu = val

  menu = st.session_state.pm_menu
  st.sidebar.markdown("---")

 # ---------------------------------------------------------
  # 1. Menu: Quản lý Dự án (Kết nối API /projects/statistics & /projects)
  # ---------------------------------------------------------
  if menu == "🚀 Quản lý Dự án":
    if "pm_project_subview" not in st.session_state:
      st.session_state.pm_project_subview = "list" # Các giá trị: "list", "create", "detail"

    if "selected_pm_project" not in st.session_state:
      st.session_state.selected_pm_project = None

    if "selected_pm_task_id" not in st.session_state:
      st.session_state.selected_pm_task_id = None

    # --- MÀN HÌNH 1: TỔNG QUAN DANH SÁCH DỰ ÁN ---
    if st.session_state.pm_project_subview == "list" and st.session_state.selected_pm_project is None:
      st.subheader("🚀 Quản lý Dự án Doanh nghiệp")

      # Nút chuyển sang form thêm mới dự án
      if st.button("➕ Thêm mới Dự án", type="primary"):
        st.session_state.pm_project_subview = "create"
        st.rerun()

      st.markdown("")

      # Gọi API lấy danh sách dự án & thống kê trạng thái
      try:
        res = authenticated_request("GET", f"{API_BASE_URL}/projects/statistics")
        if res.status_code == 200:
          res_data = res.json()
          total = res_data.get("total_projects", 0)
          stats = res_data.get("statistics", {})
          completed = stats.get("completed", 0)
          in_progress = stats.get("in_progress", 0)
          new_proj = stats.get("new", 0)
          projects_list = res_data.get("projects", [])
        else:
          st.error("Không thể tải danh sách dự án từ Backend!")
          return
      except Exception as e:
        st.error(
            f"Lỗi kết nối tới Backend FastAPI: {e} (Hãy đảm bảo server đang chạy)"
        )
        return

      # 4 Card hiển thị metrics tổng quan
      col_m1, col_m2, col_m3, col_m4 = st.columns(4)
      with col_m1:
        st.metric(label="📊 Tổng số Dự án", value=str(total))
      with col_m2:
        st.metric(label="✅ Đã hoàn thành", value=str(completed))
      with col_m3:
        st.metric(label="🔄 Đang tiến hành", value=str(in_progress))
      with col_m4:
        st.metric(label="📌 Dự án mới", value=str(new_proj))

      st.markdown("")
      st.markdown("### 🗂️ Bảng Danh sách Dự án Doanh nghiệp")

      if projects_list:
        # Tổ chức lại hiển thị thành dạng bảng
        df_projects = pd.DataFrame(projects_list)
        
        column_mapping = {
            "project_id": "Mã Dự Án",
            "project_name": "Tên Dự Án",
            "description": "Mô Tả",
            "start_date": "Ngày Bắt Đầu",
            "end_date": "Ngày Kết Thúc",
            "status": "Trạng Thái",
            "note": "Ghi Chú"
        }
        df_projects_display = df_projects.rename(columns={k: v for k, v in column_mapping.items() if k in df_projects.columns})
        df_projects_display = df_projects_display.drop(
            columns=["note", "created_at"],
            errors="ignore",
        )

        st.dataframe(df_projects_display, width="stretch", hide_index=True)

        # Chọn dự án để xem chi tiết
        st.markdown("#### 🔍 Xem Chi Tiết Dự Án")
        project_ids = [p.get("project_id") for p in projects_list if "project_id" in p]
        selected_proj_to_view = st.selectbox("Chọn Mã Dự Án để xem chi tiết", options=["-- Chọn dự án --"] + project_ids)
        
        if selected_proj_to_view != "-- Chọn dự án --":
          if st.button("Xem Chi Tiết Dự Án Này", type="primary"):
            st.session_state.selected_pm_project = selected_proj_to_view
            st.session_state.selected_pm_task_id = None
            st.session_state.pm_project_subview = "detail"
            st.rerun()
      else:
        st.info("Không có dữ liệu.")

    # --- MÀN HÌNH 2: THÊM MỚI DỰ ÁN ---
    elif st.session_state.pm_project_subview == "create":
      if st.button("⬅️ Quay lại danh sách Dự án"):
        st.session_state.pm_project_subview = "list"
        st.rerun()

      st.subheader("➕ Khởi tạo Dự án Mới")

      # Lấy danh sách nhân viên để chọn làm Leader
      try:
        emp_res = authenticated_request("GET", f"{API_BASE_URL}/employees")
        emp_res.raise_for_status()
        employees_list = [
            employee for employee in emp_res.json()
            if employee.get("system_level") == "Team Lead"
        ]
        leader_options = {
            f"{e.get('employee_id')} - {e.get('employee_name')} - {e.get('position')}": {
                "employee_id": e.get("employee_id"),
                "position": e.get("position"),
            }
            for e in employees_list
        }
      except Exception as e:
        st.error(f"Không thể tải danh sách nhân viên: {e}")
        leader_options = {}

      with st.form("create_project_form"):
        ma_du_an_input = st.text_input("Mã Dự án (Ví dụ: PRJ-05)", value="PRJ-05")
        proj_name_input = st.text_input("Tên Dự án mới")
        proj_desc_input = st.text_area("Mô tả tổng quan dự án")

        col1, col2 = st.columns(2)
        with col1:
          start_date = st.date_input("Thời gian bắt đầu")
        with col2:
          end_date = st.date_input("Thời gian kết thúc dự kiến")

        trang_thai_input = st.selectbox(
            "Trạng thái dự án", ["Mới", "Đang thực hiện", "Hoàn thành"]
        )
        
        selected_leader_labels = st.multiselect(
            "👨‍💼 Chọn nhân viên Team Leader tham gia",
            options=list(leader_options.keys())
        )

        submitted = st.form_submit_button("Tạo Dự Án", type="primary")
        if submitted:
          if proj_name_input.strip():
            payload = {
                "project_id": ma_du_an_input,
                "project_name": proj_name_input,
                "description": proj_desc_input,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "status": trang_thai_input,
                "leaders": [leader_options[label] for label in selected_leader_labels],
            }
            try:
              # Kết nối API tạo mới dự án tương ứng endpoint Backend
              res = authenticated_request(
                  "POST", f"{API_BASE_URL}/projects", json=payload
              )
              if res.status_code == 200:
                st.success("Tạo dự án mới thành công!")
                st.session_state.pm_project_subview = "list"
                st.rerun()
              else:
                st.error(f"Lỗi: {res.json().get('detail', 'Không xác định')}")
            except Exception as e:
              st.error(f"Không thể kết nối API: {e}")
          else:
            st.warning("Vui lòng nhập tên dự án!")

    # --- MÀN HÌNH 3: CHI TIẾT 1 DỰ ÁN ---
    elif st.session_state.pm_project_subview == "detail":
      back_col, action_col = st.columns([5, 1])
      with back_col:
        if st.button("⬅️ Quay lại danh sách Dự án"):
          st.session_state.selected_pm_project = None
          st.session_state.selected_pm_task_id = None
          st.session_state.pm_project_subview = "list"
          st.rerun()

      proj_id = st.session_state.selected_pm_project

      try:
        res = authenticated_request(
            "GET", f"{API_BASE_URL}/projects/{proj_id}/comprehensive-detail"
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
      with action_col:
        if proj_info.get("status") != "Hoàn thành" and st.button(
            "Kết thúc dự án",
            type="primary",
            key=f"complete_project_{proj_id}",
        ):
          confirm_complete_project(
              proj_id, proj_info.get("project_name", proj_id)
          )

      st.subheader(f"📂 Chi tiết Dự án: {proj_info.get('project_name')}")
      st.info(
          f"📌 **Thông tin quản lý:**\n- **Mã dự án:** {proj_info.get('project_id')}\n"
          f"- **Mô tả:** {proj_info.get('description')}\n"
          f"- **Thời gian:** {proj_info.get('start_date')} ➔ {proj_info.get('end_date')}\n"
          f"- **Trạng thái:** {proj_info.get('status')}"
      )

      # Hiển thị Leaders tham gia
      st.markdown("### 👨‍💼 Danh sách Leader tham gia")
      leaders = detail_data.get("leaders", [])
      if leaders:
        st.dataframe(pd.DataFrame(leaders), width="stretch", hide_index=True)
      else:
        st.info("Không có dữ liệu.")

      # Hiển thị Task nhóm theo Leader (Quản lý công việc của nhân viên phân chia theo bảng)
      st.markdown("### 📋 Quản lý Công việc (Task) theo từng Leader")
      selected_task_id = st.session_state.selected_pm_task_id
      if selected_task_id:
        if st.button(
            "⬅️ Quay lại danh sách Task",
            key=f"pm_back_to_tasks_{proj_id}",
        ):
          st.session_state.selected_pm_task_id = None
          st.rerun()
        try:
          task_response = authenticated_request(
              "GET",
              f"{API_BASE_URL}/projects/{proj_id}/tasks/"
              f"{selected_task_id}/detail",
          )
          render_task_detail(task_response.json())
        except Exception as exc:
          st.error(f"Không thể tải chi tiết task: {exc}")
      else:
        tasks_grouped = detail_data.get("tasks_grouped_by_manager", {})
        if tasks_grouped:
          for mgr_id, task_list in tasks_grouped.items():
            with st.expander(f"Quản lý bởi Leader ID: {mgr_id} ({len(task_list)} task)", expanded=True):
              if task_list:
                df_tasks_display = pd.DataFrame(task_list).drop(
                    columns=["project_id", "actual_hours", "note"],
                    errors="ignore",
                )
                st.dataframe(df_tasks_display, width="stretch", hide_index=True)
                tasks_by_id = {
                    task["task_id"]: task
                    for task in task_list
                    if task.get("task_id")
                }
                task_ids = list(tasks_by_id)
                selected_group_task_id = st.selectbox(
                    "Chọn task để xem chi tiết",
                    options=task_ids,
                    format_func=lambda task_id: (
                        f"{tasks_by_id[task_id].get('task_name', '')} "
                        f"({task_id})"
                    ),
                    key=f"pm_task_detail_select_{proj_id}_{mgr_id}",
                )
                if st.button(
                    "Xem chi tiết task",
                    key=f"pm_task_detail_button_{proj_id}_{mgr_id}",
                ):
                  st.session_state.selected_pm_task_id = selected_group_task_id
                  st.rerun()
              else:
                st.info("Không có dữ liệu.")
        else:
          st.info("Không có dữ liệu.")

  # ---------------------------------------------------------
  # 2. Menu: Quản lý Nhân viên (Kết nối API /employees)
  # ---------------------------------------------------------
  elif menu == "👥 Quản lý Nhân viên":
    if "selected_employee_detail" not in st.session_state:
      st.session_state.selected_employee_detail = None

    if st.session_state.selected_employee_detail is None:
      st.subheader("👥 Quản lý và Theo dõi Nhân sự Toàn doanh nghiệp")
      try:
        res = authenticated_request("GET", f"{API_BASE_URL}/employees")
        employees_list = res.json() if res.status_code == 200 else []
      except Exception as e:
        st.error(f"Lỗi kết nối API: {e}")
        return

      st.markdown("### 📋 Bảng Danh sách Nhân sự")
      if employees_list:
        df_employees = pd.DataFrame(employees_list)
        emp_column_mapping = {
            "employee_id": "Mã Nhân Viên",
            "employee_name": "Họ và Tên",
            "position": "Chức Vụ",
            "department": "Phòng Ban",
            "system_level": "Cấp Độ Hệ Thống"
        }
        df_employees_display = df_employees.rename(columns={k: v for k, v in emp_column_mapping.items() if k in df_employees.columns})
        st.dataframe(df_employees_display, width="stretch", hide_index=True)

        st.markdown("#### 🔍 Xem Chi Tiết Nhân Sự")
        emp_ids = [e.get("employee_id") for e in employees_list if "employee_id" in e]
        selected_emp_to_view = st.selectbox("Chọn Mã Nhân Viên để xem chi tiết", options=["-- Chọn nhân viên --"] + emp_ids)

        if selected_emp_to_view != "-- Chọn nhân viên --":
          if st.button("Xem Hồ Sơ Nhân Sự Này", type="primary"):
            st.session_state.selected_employee_detail = selected_emp_to_view
            st.rerun()
      else:
        st.info("Không có dữ liệu.")
    else:
      emp_id = st.session_state.selected_employee_detail
      if st.button("⬅️ Quay lại danh sách Nhân viên"):
        st.session_state.selected_employee_detail = None
        st.rerun()

      # Form chọn tháng/năm để xem tổng kết
      col_m, col_y = st.columns(2)
      with col_m:
        selected_month = st.selectbox("Chọn tháng", list(range(1, 13)), index=datetime.now().month - 1)
      with col_y:
        selected_year = st.number_input("Nhập năm", value=datetime.now().year, step=1)

      try:
        res = authenticated_request(
            "GET",
            f"{API_BASE_URL}/employees/{emp_id}/monthly-summary",
            params={"month": selected_month, "year": selected_year},
        )
        emp_data = res.json() if res.status_code == 200 else {}
      except Exception as e:
        st.error(f"Lỗi kết nối API: {e}")
        return

      st.subheader(f"📊 Tổng kết Hiệu suất Nhân sự: {emp_id} (Tháng {selected_month}/{selected_year})")
      summary_metrics = emp_data.get("summary", {})
      role_type = emp_data.get("role_type", "Member")

      col_e1, col_e2, col_e3 = st.columns(3)
      if role_type == "Leader":
        with col_e1:
          st.metric(label="📂 Tổng dự án quản lý", value=f"{summary_metrics.get('total_managed_projects', 0)} dự án")
      else:
        with col_e1:
          st.metric(label="✅ Tổng Task trong tháng", value=f"{summary_metrics.get('total_tasks_in_month', 0)} task")
      
      with col_e2:
        st.metric(label="📅 Số ngày đi làm", value=f"{summary_metrics.get('working_days_count', 0)} ngày")
      with col_e3:
        st.metric(label="⚠ Số lỗi vi phạm", value=f"{summary_metrics.get('violation_count', 0)} lỗi")

      st.markdown("---")
      if role_type == "Leader":
        st.markdown("### 📂 Danh sách dự án đang quản lý")
        managed_projs = emp_data.get("projects_managed", [])
        if managed_projs:
          df_projects_display = pd.DataFrame(managed_projs).drop(
              columns=["note", "created_at"],
              errors="ignore",
          )
          st.dataframe(df_projects_display, width="stretch", hide_index=True)
        else:
          st.info("Không có dữ liệu.")
      else:
        st.markdown("### 📝 Danh sách Task thực hiện trong tháng")
        monthly_tasks = emp_data.get("tasks_in_month", [])
        if monthly_tasks:
          df_tasks_display = pd.DataFrame(monthly_tasks).drop(
              columns=["project_id", "actual_hours", "note"],
              errors="ignore",
          )
          st.dataframe(df_tasks_display, width="stretch", hide_index=True)
        else:
          st.info("Không có dữ liệu.")

  # ---------------------------------------------------------
  # Ghi nhận vi phạm nhân sự
  # ---------------------------------------------------------
  elif menu == "⚠️ Ghi nhận vi phạm":
    render_behavior_view("Project Manager")

  # ---------------------------------------------------------
  # 3. Menu: AI-Agent Tổng hợp Tiến độ
  # ---------------------------------------------------------
  elif menu == "📊 AI-Agent Tổng hợp Tiến độ":
    st.subheader("📊 AI-Agent Tổng hợp & Phân tích Tiến độ Toàn cục")
    if st.button("Chạy Agent phân tích tổng quan dự án", type="primary"):
      try:
        res = authenticated_request(
            "POST", f"{API_BASE_URL}/ai-agent/analyze-progress"
        )
        if res.status_code == 200:
          report = res.json().get("agent_report", {})
          st.info(
              "🤖 **Báo cáo từ AI-Agent:**\n"
              f"- Tổng số dự án active: {report.get('active_projects_count')}\n"
              f"- **Cảnh báo rủi ro:** {report.get('risk_warnings')}\n"
              f"- **Đề xuất:** {report.get('recommendations')}"
          )
        else:
          st.error("Không thể lấy dữ liệu phân tích từ AI-Agent.")
      except Exception as e:
        st.error(f"Lỗi kết nối API: {e}")

  # ---------------------------------------------------------
  # 4. Menu: Quản lý Kho tài liệu RAG
  # ---------------------------------------------------------
  elif menu == "🗂️ Quản lý Kho tài liệu (RAG)":
    st.subheader("🗂 Quản lý Knowledge Data (Tài liệu nội bộ cho RAG)")
    position = st.selectbox(
        "Vị trí ủy quyền",
        [None, "Business Analyst", "Developer", "Tester"],
        format_func=lambda value: value or "Tất cả vị trí",
    )
    system_level = st.selectbox(
        "Cấp độ ủy quyền",
        ["Member", "Team Lead", "Project Manager"],
    )
    uploaded_file = st.file_uploader(
        "Tải lên tài liệu mới (PDF, TXT - Chính sách, Nội quy, Quy trình)",
        type=["pdf", "txt"],
    )
    if uploaded_file is not None:
      st.info(f"Đã chọn file: {uploaded_file.name}")
      if st.button("Xử lý Chunking & Vector hóa vào Supabase", type="primary"):
        try:
          files = {
              "file": (
                  uploaded_file.name,
                  uploaded_file.getvalue(),
                  uploaded_file.type,
              ),
              "system_level": (None, system_level),
          }
          if position is not None:
            files["position"] = (None, position)
          res = authenticated_request(
              "POST",
              f"{API_BASE_URL}/rag/upload-document",
              files=files,
          )
          if res.status_code == 200:
            result = res.json()
            st.success(result.get("message", "Đã xử lý tài liệu thành công."))
            st.caption(
                f"Đã lưu {result.get('chunks_saved', 0)}/"
                f"{result.get('chunks_total', 0)} đoạn tài liệu."
            )
          else:
            st.error(
                f"Lỗi tải lên: {res.json().get('detail', 'Không xác định')}"
            )
        except Exception as e:
          st.error(f"Lỗi kết nối API: {e}")

    st.divider()
    st.subheader("Tải nội dung tài liệu đã lưu")
    try:
      documents_response = authenticated_request(
          "GET", f"{API_BASE_URL}/rag/documents"
      )
      documents = documents_response.json().get("documents", [])
      if documents:
        selected_document = st.selectbox(
            "Chọn tài liệu",
            documents,
            format_func=lambda document: (
                f"{document['document_name']} "
                f"({document['chunk_count']} đoạn) — "
                f"{document['position'] or 'Tất cả vị trí'} / "
                f"{document['system_level']}"
            ),
        )
        if st.button("Tải các chunk của tài liệu"):
          document_name = selected_document["document_name"]
          chunks_response = authenticated_request(
              "GET",
              f"{API_BASE_URL}/rag/documents/{quote(document_name, safe='')}",
          )
          st.session_state.pm_rag_loaded_chunks = chunks_response.json()

        loaded_document = st.session_state.get("pm_rag_loaded_chunks", {})
        if loaded_document.get("document_name") == selected_document["document_name"]:
          st.download_button(
              "Tải xuống JSON",
              data=json.dumps(
                  loaded_document["chunks"], ensure_ascii=False, indent=2
              ).encode("utf-8"),
              file_name=f"{selected_document['document_name']}.chunks.json",
              mime="application/json",
              key=f"download_chunks_{selected_document['document_name']}",
          )
      else:
        st.info("Chưa có tài liệu nào được lưu.")
    except Exception as exc:
      st.error(f"Không thể lấy danh sách/tải tài liệu: {exc}")

  # ---------------------------------------------------------
  # 5. Menu: Quản lý Semantic Profile
  # ---------------------------------------------------------
  elif menu == "⚙️ Quản lý Semantic Profile (Text-to-SQL)":
    st.subheader("⚙️ Quản lý Semantic Table cho Text-to-SQL")
    try:
      res = authenticated_request(
          "GET", f"{API_BASE_URL}/table-embeddings"
      )
      table_embeddings = res.json().get("data", [])
    except Exception as exc:
      st.error(f"Không thể tải semantic data từ Supabase: {exc}")
      table_embeddings = None

    if table_embeddings is not None:
      pending_new_table = st.session_state.pop(
          "pm_semantic_pending_new_table", None
      )
      if pending_new_table:
        new_table_index = next(
            (
                index
                for index, table in enumerate(table_embeddings)
                if table.get("table_name") == pending_new_table
            ),
            None,
        )
        if new_table_index is not None:
          table_embeddings.append(table_embeddings.pop(new_table_index))

      success_message = st.session_state.pop(
          "pm_semantic_success_message", None
      )
      if success_message:
        st.success(success_message)

      if not table_embeddings:
        st.info("Chưa có semantic data nào được lưu trên Supabase.")
      else:
        for table_embedding in table_embeddings:
          table_name = table_embedding.get("table_name")
          chunk_text = table_embedding.get("chunk_text", "")
          if not table_name:
            st.warning("Bỏ qua một bản ghi semantic không có tên bảng.")
            continue

          table_key = quote(str(table_name), safe="")
          edit_state_key = f"pm_semantic_editing_{table_key}"
          text_state_key = f"pm_semantic_chunk_{table_key}"
          is_editing = st.session_state.get(edit_state_key, False)

          st.markdown(f"#### `{table_name}`")
          if st.button(
              "Hủy chỉnh sửa" if is_editing else "Chỉnh sửa",
              key=f"pm_semantic_edit_{table_key}",
          ):
            is_editing = not is_editing
            st.session_state[edit_state_key] = is_editing
            st.session_state[text_state_key] = (
                st.session_state.get(text_state_key, chunk_text)
                if is_editing
                else chunk_text
            )
          elif not is_editing:
            st.session_state[text_state_key] = chunk_text

          st.text_area(
              "Chunk text",
              key=text_state_key,
              height=220,
              disabled=not is_editing,
          )

          if st.button(
              "Đẩy dữ liệu lên Supabase",
              type="primary",
              key=f"pm_semantic_push_{table_key}",
          ):
            try:
              edited_chunk = st.session_state[text_state_key]
              save_response = authenticated_request(
                  "POST",
                  f"{API_BASE_URL}/table-embeddings",
                  json={
                      "table_name": table_name,
                      "chunk_text": edited_chunk,
                  },
              )
              st.session_state[text_state_key] = edited_chunk
              st.session_state[edit_state_key] = False
              st.success(
                  save_response.json().get(
                      "message", f"Đã đẩy semantic data của bảng {table_name}."
                  )
              )
            except Exception as exc:
              st.error(f"Không thể đẩy dữ liệu của bảng {table_name}: {exc}")

          st.divider()

      if st.button(
          "➕ Thêm bảng mới",
          type="primary",
          key="pm_semantic_add_table",
      ):
        st.session_state.pm_semantic_adding_table = True
        st.session_state.pm_semantic_new_table_form_id = (
            st.session_state.get("pm_semantic_new_table_form_id", 0) + 1
        )
        st.rerun()

      if st.session_state.get("pm_semantic_adding_table", False):
        form_id = st.session_state.pm_semantic_new_table_form_id
        table_name_key = f"pm_semantic_new_table_name_{form_id}"
        chunk_text_key = f"pm_semantic_new_chunk_{form_id}"
        st.markdown(
            '<div id="pm-semantic-new-table-form"></div>',
            unsafe_allow_html=True,
        )
        st.subheader("Thêm bảng semantic mới")
        with st.form(f"pm_semantic_new_table_form_{form_id}"):
          new_table_name = st.text_input(
              "Tên bảng",
              key=table_name_key,
          )
          new_chunk_text = st.text_area(
              "Chunk text",
              height=220,
              key=chunk_text_key,
          )
          save_new_table = st.form_submit_button(
              "Lưu bảng mới",
              type="primary",
          )
          cancel_new_table = st.form_submit_button("Hủy")

        components.html(
            """
            <script>
              const target = window.parent.document.getElementById(
                "pm-semantic-new-table-form"
              );
              if (target) {
                target.scrollIntoView({ behavior: "smooth", block: "start" });
              }
            </script>
            """,
            height=0,
        )

        if cancel_new_table:
          st.session_state.pm_semantic_adding_table = False
          st.rerun()
        elif save_new_table:
          normalized_table_name = new_table_name.strip()
          if not normalized_table_name:
            st.error("Vui lòng nhập tên bảng.")
          elif not new_chunk_text.strip():
            st.error("Vui lòng nhập nội dung semantic cho bảng.")
          elif any(
              str(table.get("table_name", "")).strip() == normalized_table_name
              for table in table_embeddings
          ):
            st.error(f"Bảng `{normalized_table_name}` đã tồn tại.")
          else:
            try:
              save_response = authenticated_request(
                  "POST",
                  f"{API_BASE_URL}/table-embeddings",
                  json={
                      "table_name": normalized_table_name,
                      "chunk_text": new_chunk_text,
                  },
              )
              st.session_state.pm_semantic_success_message = (
                  save_response.json().get(
                      "message",
                      f"Đã thêm semantic data cho bảng {normalized_table_name}.",
                  )
              )
              st.session_state.pm_semantic_pending_new_table = (
                  normalized_table_name
              )
              st.session_state.pm_semantic_adding_table = False
              st.rerun()
            except Exception as exc:
              st.error(
                  f"Không thể thêm semantic data cho bảng "
                  f"{normalized_table_name}: {exc}"
              )

  # ---------------------------------------------------------
  # 6. Menu: Quản lý file relationship
  # ---------------------------------------------------------
  elif menu == "🕸️ Quản lý Relationship":
    st.subheader("🕸️ Quản lý file Relationship giữa các bảng")
    try:
      response = authenticated_request(
          "GET", f"{API_BASE_URL}/table-relationships"
      )
      relationship_data = response.json()
      relationship_files = relationship_data.get("files", [])
      active_relationship_file = relationship_data.get("active_file")
      if (
          not isinstance(relationship_files, list)
          or any(not isinstance(filename, str) for filename in relationship_files)
          or active_relationship_file not in relationship_files
      ):
        raise RuntimeError("Backend trả về danh sách file relationship không hợp lệ.")
    except (RuntimeError, ValueError) as exc:
      st.error(f"Không thể tải danh sách file relationship: {exc}")
    else:
      st.caption("Danh sách chỉ hiển thị tên file. Mỗi thời điểm chỉ áp dụng một file.")
      for filename in relationship_files:
        st.write(filename)
      st.info(f"File đang áp dụng: {active_relationship_file}")

      selected_relationship_file = st.selectbox(
          "Chọn file relationship",
          options=relationship_files,
          index=relationship_files.index(active_relationship_file),
          key="pm_relationship_selected_file",
      )
      if st.button(
          "Áp dụng file này",
          type="primary",
          key="pm_relationship_apply",
      ):
        try:
          authenticated_request(
              "PUT",
              f"{API_BASE_URL}/table-relationships/active",
              json={"filename": selected_relationship_file},
          )
        except RuntimeError as exc:
          st.error(f"Không thể áp dụng file relationship: {exc}")
        else:
          st.success(f"Đã áp dụng file {selected_relationship_file}.")
          st.rerun()

      st.markdown("#### Thêm file relationship")
      uploaded_relationship_file = st.file_uploader(
          "Chọn file JSON",
          type=["json"],
          key="pm_relationship_upload",
      )
      if st.button(
          "Tải file lên",
          disabled=uploaded_relationship_file is None,
          key="pm_relationship_upload_button",
      ):
        try:
          authenticated_request(
              "POST",
              f"{API_BASE_URL}/table-relationships",
              files={
                  "file": (
                      uploaded_relationship_file.name,
                      uploaded_relationship_file.getvalue(),
                      "application/json",
                  )
              },
          )
        except RuntimeError as exc:
          st.error(f"Không thể thêm file relationship: {exc}")
        else:
          st.success(
              f"Đã thêm file {uploaded_relationship_file.name}. "
              "File chưa được áp dụng."
          )
          st.rerun()

  # ---------------------------------------------------------
  # 7. Menu: AI Chatbot Toàn hệ thống
  # ---------------------------------------------------------
  elif menu == "💬 AI Chatbot Toàn hệ thống":
    render_chatbot(
        title="💬 AI Chatbot Quản trị Cấp cao",
        greeting=(
            "Xin chào PM! Tôi có thể hỗ trợ bạn tra cứu toàn hệ thống"
            " bằng Text-to-SQL kết hợp RAG."
        ),
        input_placeholder=(
            "Tra cứu thông tin toàn hệ thống bằng ngôn ngữ tự nhiên..."
        ),
        state_prefix="pm_chat",
    )
  elif menu == "🧠 Cấu hình AI Agent":
    st.subheader("🧠 Cấu hình AI Agent và truy xuất")
    st.caption(
        "Chọn mô hình và temperature cho từng agent; cấu hình thêm tham số "
        "truy xuất RAG và bảng."
    )
    try:
      response = authenticated_request(
          "GET", f"{API_BASE_URL}/agent-models"
      )
      settings = response.json()
      if not isinstance(settings, dict):
        raise RuntimeError("Backend trả về cấu hình agent không hợp lệ.")
      agents = settings.get("agents", [])
      if (
          not isinstance(agents, list)
          or not agents
          or any(not isinstance(agent, dict) for agent in agents)
      ):
        raise RuntimeError("Backend không trả về danh sách agent hợp lệ.")
      if not isinstance(settings.get("retrieval"), dict):
        raise RuntimeError("Backend không trả về cấu hình retrieval hợp lệ.")
    except (RuntimeError, ValueError) as exc:
      st.error(f"Không thể tải cấu hình model: {exc}")
    else:
      provider_labels = {
          "gemini": "Gemini",
          "ollama": "Ollama",
          "groq": "Groq",
      }
      with st.form("pm_agent_model_settings"):
        providers = {}
        temperatures = {}
        for agent in agents:
          options = agent.get("options", [])
          option_providers = [
              option.get("provider")
              for option in options
              if option.get("provider") in provider_labels
          ]
          if not option_providers or agent.get("provider") not in option_providers:
            st.error(
                f"Cấu hình provider không hợp lệ cho {agent.get('label', agent.get('id'))}."
            )
            continue
          model_by_provider = {
              option["provider"]: option.get("model", "")
              for option in options
              if option.get("provider") in provider_labels
          }
          selected_provider = st.selectbox(
              agent.get("label", agent["id"]),
              options=option_providers,
              index=option_providers.index(agent["provider"]),
              format_func=lambda provider, models=model_by_provider: (
                  f"{provider_labels[provider]} "
                  f"({models.get(provider, '')})"
              ),
              key=f"agent_model_provider_{agent['id']}",
          )
          providers[agent["id"]] = selected_provider
          temperatures[agent["id"]] = st.slider(
              f"Temperature — {agent.get('label', agent['id'])}",
              min_value=0.0,
              max_value=1.0,
              value=float(agent.get("temperature", 0.1)),
              step=0.1,
              key=f"agent_temperature_{agent['id']}",
          )

        retrieval = settings.get("retrieval", {})
        st.markdown("#### Tìm kiếm tài liệu RAG")
        rag_match_threshold = st.slider(
            "Match threshold",
            min_value=0.0,
            max_value=1.0,
            value=float(retrieval.get("rag_match_threshold", 0.6)),
            step=0.01,
            key="rag_search_match_threshold",
        )
        rag_match_count = st.number_input(
            "Match count — tìm đoạn RAG",
            min_value=1,
            max_value=100,
            value=int(retrieval.get("rag_match_count", 4)),
            step=1,
            key="rag_search_match_count",
        )

        st.markdown("#### Tìm kiếm bảng cho Text-to-SQL")
        table_match_count = st.number_input(
            "Match count — retrieve bảng",
            min_value=1,
            max_value=100,
            value=int(retrieval.get("table_match_count", 3)),
            step=1,
            key="table_retrieval_match_count",
        )

        submitted = st.form_submit_button(
            "Lưu cấu hình", type="primary"
        )
      if submitted:
        if (
            len(providers) != len(agents)
            or len(temperatures) != len(agents)
        ):
          st.error("Không thể lưu do cấu hình agent chưa đầy đủ.")
        else:
          try:
            authenticated_request(
                "PUT",
                f"{API_BASE_URL}/agent-models",
                json={
                    "providers": providers,
                    "temperatures": temperatures,
                    "rag_match_threshold": rag_match_threshold,
                    "rag_match_count": rag_match_count,
                    "table_match_count": table_match_count,
                },
            )
          except RuntimeError as exc:
            st.error(f"Không thể lưu cấu hình: {exc}")
          else:
            st.success("Đã lưu cấu hình agent và tham số truy xuất.")
            st.rerun()