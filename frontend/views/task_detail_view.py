import streamlit as st


def render_task_detail(task_data: dict):
    task = task_data.get("task", {})
    reports = task_data.get("reports", [])

    st.markdown(f"### 🧾 Chi tiết Task: {task.get('task_name', '')}")
    st.markdown("#### Thông tin task")
    info_col1, info_col2, info_col3 = st.columns(3)
    with info_col1:
        st.text_input(
            "Mã task",
            value=task.get("task_id", ""),
            disabled=True,
            key=f"task_detail_id_{task.get('task_id')}",
        )
        st.text_input(
            "Người thực hiện",
            value=(
                f"{task_data.get('assignee_name')} "
                f"({task.get('assignee_employee_id', '')})"
                if task_data.get("assignee_name")
                else task.get("assignee_employee_id", "")
            ),
            disabled=True,
            key=f"task_detail_assignee_{task.get('task_id')}",
        )
    with info_col2:
        st.text_input(
            "Thời gian thực hiện",
            value=f"{task.get('start_date', '')} – {task.get('end_date', '')}",
            disabled=True,
            key=f"task_detail_dates_{task.get('task_id')}",
        )
        st.text_input(
            "Số giờ dự kiến",
            value=str(task.get("estimated_hours", "")),
            disabled=True,
            key=f"task_detail_estimated_{task.get('task_id')}",
        )
    with info_col3:
        st.text_input(
            "Trạng thái",
            value=task.get("status", ""),
            disabled=True,
            key=f"task_detail_status_{task.get('task_id')}",
        )
        st.text_input(
            "Số giờ thực tế",
            value=str(task.get("actual_hours", "")),
            disabled=True,
            key=f"task_detail_actual_{task.get('task_id')}",
        )

    st.markdown("#### Tiến độ thực hiện")
    if reports:
        for report in reports:
            with st.container(border=True):
                st.markdown(f"**Ngày báo cáo:** {report.get('report_date', '')}")
                st.write(report.get("content") or "Không có nội dung báo cáo.")
                if report.get("content_url"):
                    st.markdown(f"[Mở tài liệu liên quan]({report['content_url']})")
                if report.get("note"):
                    st.caption(f"Ghi chú báo cáo: {report['note']}")
    else:
        st.info("Task chưa có báo cáo tiến độ.")

    st.markdown("#### Ghi chú của task")
    st.write(task.get("note") or "Task chưa có ghi chú.")
