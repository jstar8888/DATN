from datetime import date
import streamlit as st
import pandas as pd
from api_client import (
    API_BASE_URL as BACKEND_BASE_URL,
    authenticated_request,
)
from views.attendance_view import render_attendance_view
from views.chatbot_client import ask_chatbot

# Cấu hình URL cơ sở của FastAPI backend
API_BASE_URL = f"{BACKEND_BASE_URL}/api/member"

def render_member_view():
    st.title("👤 Giao diện Nhân viên (Member)")

    # ---------------------------------------------------------
    # Sidebar Navigation: Quản lý menu qua session_state
    # ---------------------------------------------------------
    st.sidebar.markdown("### ️ Chức năng Member")

    if "member_menu" not in st.session_state:
        st.session_state.member_menu = "📋 Task của tôi"

    menu_options = [
        ("📋 Task của tôi", "📋 Task của tôi"),
        ("⏱️ Chấm công", "⏱️ Chấm công"),
        ("⏰ Đăng ký OT", "⏰ Đăng ký Làm thêm giờ (OT)"),
        ("📝 Xin nghỉ phép", "📝 Xin nghỉ phép"),
        ("📊 Báo cáo ngày", "📊 Báo cáo ngày"),
        ("💬 AI Assistant", "💬 AI Assistant"),
    ]

    for label, val in menu_options:
        if st.sidebar.button(
            label, width="stretch", key=f"btn_{val}"
        ):
            st.session_state.member_menu = val

    menu = st.session_state.member_menu
    st.sidebar.markdown("---")

    # ---------------------------------------------------------
    # 1. Menu: Task của tôi (Backend tự xác định nhân viên từ phiên đăng nhập)
    # ---------------------------------------------------------
    if menu == "📋 Task của tôi":
        st.subheader("📋 Danh sách Task được phân công")

        try:
            response = authenticated_request(
                "GET", f"{API_BASE_URL}/me/tasks-summary"
            )
            if response.status_code == 200:
                res_json = response.json()
                total_tasks = res_json.get("total_tasks", 0)
                stats = res_json.get("statistics", {})
                tasks_data = res_json.get("tasks", [])
            else:
                st.error("Không thể tải danh sách task từ server.")
                total_tasks, stats, tasks_data = 0, {}, []
        except Exception as e:
            st.error(f"Lỗi kết nối tới FastAPI backend: {e}")
            total_tasks, stats, tasks_data = 0, {}, []

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric(label="📊 Tổng số Task", value=str(total_tasks))
        with col_m2:
            st.metric(label="📌 Chưa làm", value=str(stats.get("not_started", 0)))
        with col_m3:
            st.metric(label="⏳ Đang làm", value=str(stats.get("in_progress", 0)))
        with col_m4:
            st.metric(label="✅ Đã xong", value=str(stats.get("completed", 0)))

        st.markdown("")

        if tasks_data:
            df_tasks = pd.DataFrame(tasks_data)
            column_mapping = {
                "task_id": "Mã Task",
                "task_name": "Tên Task",
                "project_name": "Dự Án",
                "category": "Hạng Mục",
                "start_date": "Ngày Bắt Đầu",
                "end_date": "Deadline",
                "estimated_hours": "Giờ Dự Kiến",
                "progress_percent": "Tiến Độ (%)",
                "status": "Trạng Thái",
                
            }
            df_tasks_display = df_tasks.rename(columns={k: v for k, v in column_mapping.items() if k in df_tasks.columns})
            df_tasks_display = df_tasks_display.drop(
                columns=["project_id", "actual_hours", "note"],
                errors="ignore",
            )
            st.dataframe(df_tasks_display, width="stretch", hide_index=True)

            st.markdown("### ✏️ Cập nhật tiến độ & Ghi chú Task")
            task_by_id = {
                task["task_id"]: task
                for task in tasks_data
                if task.get("task_id")
            }
            task_ids = list(task_by_id)
            selected_task_id = st.selectbox(
                "Chọn task cần cập nhật",
                options=task_ids,
                format_func=lambda task_id: (
                    f"{task_by_id[task_id].get('task_name', '')} ({task_id})"
                ),
            )
            selected_task = task_by_id[selected_task_id]
            status_options = ["Chưa làm", "Đang làm", "Hoàn thành"]
            current_status = selected_task.get("status")
            if current_status not in status_options:
                status_options.append(current_status)

            with st.form("update_task_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_status = st.selectbox(
                        "Trạng thái",
                        status_options,
                        index=status_options.index(current_status)
                        if current_status in status_options
                        else 0,
                    )
                with col2:
                    current_progress = float(
                        selected_task.get("progress_percent") or 0
                    )
                    new_progress = st.slider(
                        "Tiến độ (%)",
                        0.0,
                        100.0,
                        min(max(current_progress, 0.0), 100.0),
                    )
                    new_actual_hours = st.number_input(
                        "Số giờ thực tế",
                        min_value=0.0,
                        value=max(
                            float(selected_task.get("actual_hours") or 0), 0.0
                        ),
                        step=0.5,
                    )

                new_note = st.text_area(
                    "Ghi chú công việc / Vướng mắc (Blocker)",
                    placeholder="Nhập chi tiết các công việc đã làm hoặc khó khăn gặp phải...",
                )

                if st.form_submit_button("Lưu cập nhật tiến độ", type="primary"):
                    payload = {
                        "status": new_status,
                        "progress_percent": float(new_progress),
                        "actual_hours": float(new_actual_hours),
                        "note": new_note,
                    }
                    try:
                        update_res = authenticated_request(
                            "PATCH",
                            f"{API_BASE_URL}/tasks/{selected_task_id}/progress",
                            json=payload,
                        )
                        if update_res.status_code == 200:
                            st.success(f"🚀 {update_res.json().get('message')}")
                            st.rerun()
                        else:
                            st.error(f"Lỗi từ server: {update_res.text}")
                    except Exception as e:
                        st.error(f"Không thể kết nối đến API server: {e}")
        else:
            st.info("Không có dữ liệu.")

    # ---------------------------------------------------------
    # 2. Menu: Chấm công
    # ---------------------------------------------------------
    elif menu == "⏱️ Chấm công":
        st.subheader("⏱ Quản lý Chấm công Hàng ngày")
        render_attendance_view()

    # ---------------------------------------------------------
    # 3. Menu: Đăng ký Làm thêm giờ (OT) (Kết nối API POST /api/member/overtime)[cite: 9]
    # ---------------------------------------------------------
    elif menu == "⏰ Đăng ký Làm thêm giờ (OT)":
        st.subheader("⏰ Đăng ký Làm thêm giờ (OT)")

        try:
            tasks_response = authenticated_request(
                "GET", f"{API_BASE_URL}/me/tasks-summary"
            )
            assigned_tasks = tasks_response.json().get("tasks", [])
        except Exception as exc:
            st.error(f"Không thể tải dự án và task được giao: {exc}")
            return

        tasks_by_project = {}
        projects_by_id = {}
        for task in assigned_tasks:
            project_id = task.get("project_id")
            if not project_id:
                continue
            projects_by_id[project_id] = task.get("project_name") or project_id
            tasks_by_project.setdefault(project_id, []).append(task)

        no_project_option = "-- Không chọn dự án --"
        project_ids = list(projects_by_id)
        selected_project_id = st.selectbox(
            "Dự án liên quan (không bắt buộc)",
            options=[no_project_option, *project_ids],
            format_func=lambda project_id: (
                no_project_option
                if project_id == no_project_option
                else f"{projects_by_id[project_id]} ({project_id})"
            ),
            key="ot_project_selection",
        )
        eligible_tasks = (
            tasks_by_project.get(selected_project_id, [])
            if selected_project_id != no_project_option
            else []
        )
        tasks_by_id = {
            task["task_id"]: task
            for task in eligible_tasks
            if task.get("task_id")
        }
        no_task_option = "-- Không chọn task --"
        selected_task_id = st.selectbox(
            "Task liên quan (không bắt buộc)",
            options=[no_task_option, *tasks_by_id],
            format_func=lambda task_id: (
                no_task_option
                if task_id == no_task_option
                else f"{tasks_by_id[task_id].get('task_name', '')} ({task_id})"
            ),
            disabled=selected_project_id == no_project_option,
            key=f"ot_task_selection_{selected_project_id}",
        )

        with st.form("ot_form"):
            ot_date = st.date_input("Ngày đăng ký OT", value=date.today())
            ot_hours = st.number_input(
                "Số giờ OT",
                min_value=0.5,
                max_value=8.0,
                value=2.0,
                step=0.5,
            )

            reason = st.text_area("Lý do làm thêm giờ")

            if st.form_submit_button("Gửi đơn đăng ký OT", type="primary"):
                payload = {
                    "ot_date": ot_date.isoformat(),
                    "project_id": (
                        selected_project_id
                        if selected_project_id != no_project_option
                        else None
                    ),
                    "task_id": (
                        selected_task_id
                        if selected_task_id != no_task_option
                        else None
                    ),
                    "reason": reason,
                    "ot_hours": ot_hours,
                    "status": "Chờ duyệt",
                    "note": ""
                }
                try:
                    res = authenticated_request(
                        "POST", f"{API_BASE_URL}/overtime", json=payload
                    )
                    if res.status_code == 200:
                        st.success("Gửi đơn đăng ký OT thành công!")
                    else:
                        st.error(f"Lỗi từ server: {res.json().get('detail', 'Không xác định')}")
                except Exception as e:
                    st.error(f"Không thể kết nối đến API server: {e}")

    # ---------------------------------------------------------
    # 4. Menu: Xin nghỉ phép
    # ---------------------------------------------------------
    elif menu == "📝 Xin nghỉ phép":
        st.subheader("📝 Tạo đơn xin nghỉ phép")
        with st.form("leave_form"):
            leave_col, return_col = st.columns(2)
            with leave_col:
                st.markdown("#### Thời gian bắt đầu nghỉ")
                leave_date = st.date_input("Ngày xin nghỉ", value=date.today())
                leave_shift = st.selectbox("Ca bắt đầu nghỉ", ["Ca sáng", "Ca chiều"])
            with return_col:
                st.markdown("#### Thời gian trở lại làm việc")
                return_date = st.date_input("Ngày trở lại", value=date.today())
                return_shift = st.selectbox("Ca trở lại", ["Ca sáng", "Ca chiều"])

            leave_reason = st.text_area("Lý do xin nghỉ (tuỳ chọn)")

            if st.form_submit_button("Gửi đơn nghỉ phép", type="primary"):
                leave_start = (leave_date, 0 if leave_shift == "Ca sáng" else 1)
                return_start = (return_date, 0 if return_shift == "Ca sáng" else 1)
                if return_start < leave_start:
                    st.error("Thời gian trở lại làm việc không được trước thời gian bắt đầu nghỉ.")
                else:
                    payload = {
                        "leave_period": f"{leave_date.isoformat()} {leave_shift}",
                        "return_period": f"{return_date.isoformat()} {return_shift}",
                        "reason": leave_reason.strip() or None,
                    }
                    try:
                        res = authenticated_request(
                            "POST", f"{API_BASE_URL}/leave-requests", json=payload
                        )
                        if res.status_code == 200:
                            st.success("Gửi đơn xin nghỉ phép thành công!")
                        else:
                            st.error(f"Lỗi từ server: {res.json().get('detail', 'Không xác định')}")
                    except Exception as e:
                        st.error(f"Không thể kết nối đến API server: {e}")

    # ---------------------------------------------------------
    # 5. Menu: Báo cáo ngày (Kết nối API POST /api/member/daily-reports)[cite: 9]
    # ---------------------------------------------------------
    elif menu == "📊 Báo cáo ngày":
        st.subheader("📊 Báo cáo công việc hàng ngày")
        with st.form("daily_report_form"):
            col1, col2 = st.columns(2)
            with col1:
                report_date = st.date_input("Ngày báo cáo", value=date.today())
                project_id_input = st.text_input("Mã Dự án liên quan")
            with col2:
                task_id_input = st.text_input("Mã Task liên quan")
                report_url = st.text_input("Đường dẫn tài liệu / Pull Request (tuỳ chọn)")

            report_content = st.text_area("Nội dung công việc đã thực hiện trong ngày")

            if st.form_submit_button("Gửi báo cáo công việc", type="primary"):
                if project_id_input.strip() and task_id_input.strip() and report_content.strip():
                    payload = {
                        "report_date": report_date.isoformat(),
                        "project_id": project_id_input,
                        "task_id": task_id_input,
                        "content": report_content,
                        "content_url": report_url if report_url else None,
                        "note": ""
                    }
                    try:
                        res = authenticated_request(
                            "POST",
                            f"{API_BASE_URL}/daily-reports",
                            json=payload,
                        )
                        if res.status_code == 200:
                            st.success("Gửi báo cáo công việc thành công!")
                        else:
                            st.error(f"Lỗi từ server: {res.json().get('detail', 'Không xác định')}")
                    except Exception as e:
                        st.error(f"Không thể kết nối đến API server: {e}")
                else:
                    st.warning("Vui lòng điền đầy đủ Mã dự án, Mã task và Nội dung công việc!")

    # ---------------------------------------------------------
    # 6. Menu: AI Assistant (Gọi chatbot qua LangGraph)
    # ---------------------------------------------------------
    elif menu == "💬 AI Assistant":
        st.subheader("💬 AI Assistant (Hỗ trợ Tra cứu thông minh)")

        if "messages" not in st.session_state:
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": "Xin chào! Tôi có thể giúp gì cho bạn về nội quy công ty hoặc tra cứu dữ liệu hệ thống?",
                }
            ]

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        prompt = st.chat_input("Nhập câu hỏi của bạn tại đây...")

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("AI đang xử lý thông qua API..."):
                    try:
                        result = ask_chatbot(prompt)
                        response_content = result["response"]
                    except Exception as e:
                        response_content = f"⚠️ Luồng AI dừng do lỗi: {e}"

                    st.markdown(response_content)

            st.session_state.messages.append(
                {"role": "assistant", "content": response_content}
            )