import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def authenticated_request(method: str, url: str, **kwargs):
    access_token = st.session_state.get("access_token")
    if not access_token:
        raise RuntimeError("Phiên đăng nhập không tồn tại. Vui lòng đăng nhập lại.")

    headers = dict(kwargs.pop("headers", {}))
    headers["Authorization"] = f"Bearer {access_token}"
    try:
        response = requests.request(
            method, url, headers=headers, timeout=15, **kwargs
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Không thể kết nối tới Backend API: {exc}") from exc
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"Backend API trả về {response.status_code}: {detail}"
        )
    return response
