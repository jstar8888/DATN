from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
from api_client import API_BASE_URL, authenticated_request

API_SHEET_ATTENDANCE_URL = f"{API_BASE_URL}/api/sheet-attendance"
VIETNAM_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def render_attendance_view(state_prefix: str = ""):
    state_key = f"{state_prefix}attendance_state"
    check_in_key = f"{state_prefix}check_in_time"
    check_out_key = f"{state_prefix}check_out_time"
    attendance_date_key = f"{state_prefix}attendance_date"
    error_key = f"{state_prefix}attendance_error"

    today_str = datetime.now(VIETNAM_TIMEZONE).strftime("%Y-%m-%d")

    # Tự động gọi API check status khi load trang
    if state_key not in st.session_state or st.session_state.get(attendance_date_key) != today_str:
        try:
            res = authenticated_request(
                "GET",
                f"{API_SHEET_ATTENDANCE_URL}/status",
                params={"target_date": today_str}
            )
            status_data = res.json()
            if not isinstance(status_data, dict) or status_data.get("success") is not True:
                raise ValueError("Backend trả về dữ liệu trạng thái không hợp lệ.")
            attendance_state = status_data.get("state")
            if attendance_state not in {
                "no_sheet",
                "not_checked_in",
                "not_checked_out",
                "completed",
            }:
                raise ValueError("Backend trả về trạng thái chấm công không hợp lệ.")

            st.session_state[state_key] = attendance_state
            st.session_state[check_in_key] = status_data.get("check_in")
            st.session_state[check_out_key] = status_data.get("check_out")
            st.session_state[attendance_date_key] = today_str
            st.session_state.pop(error_key, None)
        except (RuntimeError, ValueError) as exc:
            st.session_state[state_key] = "error"
            st.session_state[attendance_date_key] = today_str
            st.session_state[error_key] = str(exc)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            "#### Ghi nhận thời gian\n"
            "Hệ thống gọi API backend để ghi thời gian thực lên Google Sheet."
        )
        current_state = st.session_state[state_key]

        # 1. Trường hợp CHƯA CÓ SHEET CHẤM CÔNG
        if current_state == "error":
            st.error(
                "Không thể kiểm tra trạng thái chấm công: "
                f"{st.session_state.get(error_key, 'Lỗi không xác định.')}"
            )
            if st.button("🔄 Thử kiểm tra lại", key=f"{state_prefix}check_again"):
                del st.session_state[state_key]
                st.rerun()

        elif current_state == "no_sheet":
            st.error("⚠️ Hôm nay chưa có bảng chấm công trên hệ thống. Vui lòng liên hệ quản lý để khởi tạo!")
            if st.button("🔄 Kiểm tra lại", key=f"{state_prefix}check_again"):
                del st.session_state[state_key]
                st.rerun()

        # 2. Trường hợp ĐÃ CÓ SHEET nhưng CHƯA CHECK-IN
        elif current_state == "not_checked_in":
            if st.button(
                "📍 Check-in Ngay",
                use_container_width=True,
                type="primary",
                key=f"{state_prefix}attendance_check_in",
            ):
                now = datetime.now(VIETNAM_TIMEZONE)
                payload = {
                    "action": "check_in",
                    "timestamp": now.isoformat(),
                }

                try:
                    authenticated_request(
                        "POST",
                        f"{API_SHEET_ATTENDANCE_URL}/record",
                        json=payload,
                    )
                except RuntimeError as exc:
                    st.error(f"⚠️ Không thể ghi nhận chấm công: {exc}")
                else:
                    st.session_state[state_key] = "not_checked_out"
                    st.session_state[check_in_key] = now.strftime("%H:%M")
                    st.success("✅ Check-in thành công!")
                    st.rerun()

        # 3. Trường hợp ĐÃ CHECK-IN nhưng CHƯA CHECK-OUT
        elif current_state == "not_checked_out":
            st.info(f"⏰ Đã check-in lúc: **{st.session_state.get(check_in_key, 'N/A')}**")
            if st.button(
                "🛑 Check-out Ngay",
                use_container_width=True,
                type="secondary",
                key=f"{state_prefix}attendance_check_out",
            ):
                now = datetime.now(VIETNAM_TIMEZONE)
                payload = {
                    "action": "check_out",
                    "timestamp": now.isoformat(),
                }

                try:
                    authenticated_request(
                        "POST",
                        f"{API_SHEET_ATTENDANCE_URL}/record",
                        json=payload,
                    )
                except RuntimeError as exc:
                    st.error(f"⚠️ Không thể ghi nhận chấm công: {exc}")
                else:
                    st.session_state[check_out_key] = now.strftime("%H:%M")
                    st.session_state[state_key] = "completed"
                    st.success("✅ Check-out thành công!")
                    st.rerun()

        # 4. Trường hợp ĐÃ HOÀN THÀNH
        elif current_state == "completed":
            st.success("🎉 Bạn đã hoàn thành chấm công cho ngày hôm nay!")
            if st.button(
                "🔄 Làm mới trạng thái",
                key=f"{state_prefix}attendance_reset",
                use_container_width=True
            ):
                del st.session_state[state_key]
                st.rerun()

    with col2:
        st.markdown("#### Thông tin chấm công hôm nay")
        
        if current_state in ["not_checked_out", "completed"]:
            st.markdown(
                f"""
                <div style="padding: 12px; background-color: #eff6ff;
                            color: #1e293b; border: 1px solid #bfdbfe;
                            border-radius: 8px; margin-bottom: 15px;">
                    <p style="margin: 4px 0; color: #1e293b;">
                        <strong>📅 Ngày công:</strong>
                        {st.session_state.get(attendance_date_key, today_str)}
                    </p>
                    <p style="margin: 4px 0; color: #1e293b;">
                        <strong>🟢 Giờ vào:</strong>
                        {st.session_state.get(check_in_key, 'Chưa có')}
                    </p>
                    <p style="margin: 4px 0; color: #1e293b;">
                        <strong>🔴 Giờ ra:</strong>
                        {st.session_state.get(check_out_key, 'Chưa có' if current_state == 'not_checked_out' else 'Đang cập nhật')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif current_state == "no_sheet":
            st.warning("🔒 Chưa có bảng chấm công để hiển thị thông tin.")
        elif current_state == "error":
            st.info("Chưa thể tải thông tin chấm công do lỗi kiểm tra trạng thái.")
        else:
            st.info("💡 Bạn chưa thực hiện check-in trong ngày hôm nay.")