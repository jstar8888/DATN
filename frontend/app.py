import os

import requests
import streamlit as st
from views.lead_view import render_lead_view
from views.member_view import render_member_view
from views.pm_view import render_pm_view

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
AUTH_API_URL = f"{API_BASE_URL}/api/auth"


def call_auth_api(method, path, **kwargs):
    try:
        response = requests.request(
            method, f"{AUTH_API_URL}{path}", timeout=15, **kwargs
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Không thể kết nối tới Backend API: {exc}") from exc

    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(str(detail))
    return response


# Cấu hình trang Streamlit
st.set_page_config(
    page_title="Hệ thống Quản lý Nhân sự & AI-Agent",
    page_icon="🤖",
    layout="wide",
)

if st.query_params.get("page") == "log_view":
    from views.log_view import render_log_view

    render_log_view()
    st.stop()

# Khởi tạo session_state quản lý trạng thái
if "selected_role" not in st.session_state:
    st.session_state.selected_role = None

if "logging_in_role" not in st.session_state:
    st.session_state.logging_in_role = None

if "user_session" not in st.session_state:
    st.session_state.user_session = None

if "access_token" not in st.session_state:
    st.session_state.access_token = None

if st.session_state.selected_role and not st.session_state.access_token:
    st.session_state.selected_role = None
    st.session_state.user_session = None


def clear_attendance_session_state():
    attendance_keys = [
        key
        for key in st.session_state
        if "attendance" in key or key in {"check_in_time", "check_out_time"}
    ]
    for key in attendance_keys:
        del st.session_state[key]


def logout():
    # Xóa toàn bộ session state liên quan để reset sạch sẽ giao diện và tab cũ
    keys_to_clear = list(st.session_state.keys())
    for key in keys_to_clear:
        del st.session_state[key]
    
    # Xóa query parameters nếu có
    st.query_params.clear()
    st.rerun()


# --- 1. MÀN HÌNH CHỌN VAI TRÒ (Thu gọn khung giữa) ---
if (
    st.session_state.get("selected_role") is None
    and st.session_state.get("logging_in_role") is None
):
    # Tạo bố cục căn giữa để khung giao diện gọn gàng, không bị phình to
    _, main_container, _ = st.columns([1, 2.2, 1])

    with main_container:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            "<h2 style='text-align: center; color: #1E3A8A;'>🚀 HỆ THỐNG QUẢN LÝ NHÂN SỰ & AI-AGENT</h2>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align: center; color: #6B7280; font-size: 15px;'>Vui lòng chọn vai trò của bạn để tiếp tục đăng nhập</p>",
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown(
                """
                <div style="padding: 15px; border: 1px solid #e5e7eb; border-radius: 8px; text-align: center; height: 170px;">
                    <b style="font-size: 16px;">👤 Member</b><br>
                    <p style="font-size: 12px; color: #4b5563; margin-top: 8px;">Thực hiện task, chấm công, OT, nghỉ phép và tra cứu AI.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Chọn Member", use_container_width=True, type="primary"):
                st.session_state.logging_in_role = "Member"
                st.rerun()

        with col2:
            st.markdown(
                """
                <div style="padding: 15px; border: 1px solid #e5e7eb; border-radius: 8px; text-align: center; height: 170px;">
                    <b style="font-size: 16px;">👨‍💻 Team Lead</b><br>
                    <p style="font-size: 12px; color: #4b5563; margin-top: 8px;">Quản lý nhóm, phân công task, duyệt đơn và theo dõi tiến độ.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Chọn Team Lead", use_container_width=True, type="primary"):
                st.session_state.logging_in_role = "Team Lead"
                st.rerun()

        with col3:
            st.markdown(
                """
                <div style="padding: 15px; border: 1px solid #e5e7eb; border-radius: 8px; text-align: center; height: 170px;">
                    <b style="font-size: 16px;">📈 PM</b><br>
                    <p style="font-size: 12px; color: #4b5563; margin-top: 8px;">Quản lý dự án, cấu hình RAG, Profile và AI phân tích.</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Chọn PM", use_container_width=True, type="primary"):
                st.session_state.logging_in_role = "Project Manager (PM)"
                st.rerun()


# --- 2. CỬA SỔ ĐĂNG NHẬP (Thu gọn khung giữa) ---
elif (
    st.session_state.get("logging_in_role") is not None
    and st.session_state.get("selected_role") is None
):
    role = st.session_state.logging_in_role
    
    _, login_container, _ = st.columns([1, 1.2, 1])
    with login_container:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            f"<h3 style='text-align: center; color: #1E3A8A;'>🔐 Đăng nhập - {role}</h3>",
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        employee_fetch_failed = False
        try:
            employees_list = call_auth_api(
                "GET", "/employees", params={"role": role}
            ).json()
        except RuntimeError as exc:
            st.error(f"Không thể tải danh sách tài khoản: {exc}")
            employees_list = []
            employee_fetch_failed = True

        if not employees_list:
            if not employee_fetch_failed:
                st.warning("Không tìm thấy tài khoản nào phù hợp.")
            if st.button("Quay lại", use_container_width=True):
                st.session_state.logging_in_role = None
                st.rerun()
        else:
            account_labels = [
                f"{emp['employee_name']} - {emp['position']}" for emp in employees_list
            ]

            with st.form("login_form"):
                selected_display_name = st.selectbox(
                    "Chọn tài khoản nhân sự",
                    options=range(len(employees_list)),
                    format_func=lambda index: account_labels[index],
                )
                password = st.text_input("Mật khẩu", type="password")

                st.markdown("<br>", unsafe_allow_html=True)
                col_submit, col_back = st.columns(2)
                with col_submit:
                    submitted = st.form_submit_button(
                        "Đăng nhập",
                        use_container_width=True,
                        type="primary",
                    )
                with col_back:
                    back = st.form_submit_button(
                        "Quay lại", use_container_width=True
                    )

                if back:
                    st.session_state.logging_in_role = None
                    st.rerun()

                if submitted:
                    chosen_emp = employees_list[selected_display_name]

                    try:
                        login_data = call_auth_api(
                            "POST",
                            "/login",
                            json={
                                "user_id": chosen_emp["auth_uuid"],
                                "password": password,
                                "role": role,
                            },
                        ).json()

                        st.session_state.access_token = login_data["access_token"]
                        st.session_state.user_session = {
                            "name": login_data["employee"]["employee_name"],
                            "position": login_data["employee"]["position"],
                            "department": login_data["employee"]["department"],
                        }
                        st.session_state.selected_role = role
                        st.session_state.logging_in_role = None
                        st.success(f"Đăng nhập thành công!")
                        st.rerun()

                    except RuntimeError as exc:
                        st.error(str(exc))


# --- 3. GIAO DIỆN SAU KHI ĐĂNG NHẬP THÀNH CÔNG ---
else:
    role = st.session_state.selected_role
    user_info = st.session_state.user_session

    toolbar_spacer, toolbar_button = st.columns([7, 1])
    with toolbar_button:
        st.markdown(
            """
            <a href="?page=log_view" target="_blank" rel="noopener noreferrer"
               style="display:block;text-align:center;padding:0.35rem 0.5rem;
               border:1px solid #d0d7de;border-radius:0.5rem;
               color:inherit;text-decoration:none;font-size: 13px;">
               🔎 Log View ↗
            </a>
            """,
            unsafe_allow_html=True,
        )

    with st.sidebar:
        st.markdown("### 🏢 Hệ thống HR-AI")
        st.info(
            f"Xin chào: **{user_info['name']}**\nVị trí:"
            f" **{user_info['position']}**\nQuyền: **{role}**"
        )

        st.markdown("---")
        if st.button("🚪 Đăng xuất / Đổi tài khoản", use_container_width=True):
            logout()

    # Điều hướng view tương ứng
    if role == "Member":
        render_member_view()
    elif role == "Team Lead":
        render_lead_view()
    else:
        render_pm_view()