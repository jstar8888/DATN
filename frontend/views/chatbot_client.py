import json
import time
from uuid import uuid4

import requests
import streamlit as st

from api_client import API_BASE_URL as BACKEND_BASE_URL, authenticated_request

API_BASE_URL = f"{BACKEND_BASE_URL}/api/agent"


def ask_chatbot(question: str, chat_id: str) -> dict:
  response = authenticated_request(
      "POST",
      f"{API_BASE_URL}/chatbot",
      json={"question": question, "chat_id": chat_id},
  )
  run_id = response.json()["run_id"]
  deadline = time.monotonic() + 600
  events = []
  result = None

  with requests.get(
      f"{API_BASE_URL}/events",
      params={"run_id": run_id},
      stream=True,
      timeout=(10, 30),
  ) as event_response:
    event_response.raise_for_status()
    for line in event_response.iter_lines(chunk_size=1, decode_unicode=True):
      if time.monotonic() >= deadline:
        raise TimeoutError(
            f"Chatbot xử lý quá thời gian cho phép (run_id={run_id})."
        )
      if not line or not line.startswith("data:"):
        continue

      event = json.loads(line.removeprefix("data:").strip())
      events.append(event)
      if event["step"] != "run":
        continue
      if event["status"] == "failed":
        raise RuntimeError(
            event["details"].get("message", "Chatbot xử lý thất bại.")
        )
      if event["status"] == "completed":
        result = {
            "run_id": run_id,
            "status": "completed",
            "events": events,
            **event["details"],
        }
        break

  if result is None:
    raise RuntimeError(f"Luồng sự kiện của chatbot đã đóng (run_id={run_id}).")
  return result


def _load_chat_history(chat_id: str) -> list[dict]:
  response = authenticated_request(
      "GET", f"{API_BASE_URL}/chats/{chat_id}/history"
  )
  return response.json().get("messages", [])


def render_chatbot(
    *,
    title: str,
    greeting: str,
    input_placeholder: str,
    state_prefix: str,
) -> None:
  chat_id_key = f"{state_prefix}_chat_id"
  messages_key = f"{state_prefix}_messages"
  history_key = f"{state_prefix}_history_selection"

  if chat_id_key not in st.session_state:
    st.session_state[chat_id_key] = str(uuid4())
  if messages_key not in st.session_state:
    st.session_state[messages_key] = [
        {"role": "assistant", "content": greeting}
    ]

  try:
    response = authenticated_request("GET", f"{API_BASE_URL}/chats")
    chats = response.json().get("chats", [])
  except Exception as exc:
    chats = []
    st.error(f"Không thể tải lịch sử chat: {exc}")

  new_chat_col, history_col = st.columns([1, 3])
  with new_chat_col:
    if st.button(
        "＋ Đoạn chat mới",
        key=f"{state_prefix}_new_chat",
        use_container_width=True,
    ):
      st.session_state[chat_id_key] = str(uuid4())
      st.session_state[messages_key] = [
          {"role": "assistant", "content": greeting}
      ]
      st.session_state.pop(history_key, None)
      st.rerun()

  chat_options = [chat["chat_id"] for chat in chats if chat.get("chat_id")]
  chats_by_id = {chat["chat_id"]: chat for chat in chats}
  with history_col:
    selected_chat_id = st.selectbox(
        "Lịch sử chat",
        options=[None, *chat_options],
        format_func=lambda chat_id: (
            "Chọn một đoạn chat..."
            if chat_id is None
            else chats_by_id[chat_id].get("title", "Cuộc trò chuyện")
        ),
        key=history_key,
    )

  if selected_chat_id and selected_chat_id != st.session_state[chat_id_key]:
    try:
      history = _load_chat_history(selected_chat_id)
    except Exception as exc:
      st.error(f"Không thể tải nội dung đoạn chat: {exc}")
    else:
      st.session_state[chat_id_key] = selected_chat_id
      st.session_state[messages_key] = [
          {"role": message["role"], "content": message["content"]}
          for message in history
          if message.get("role") in {"user", "assistant"}
      ]
      if not st.session_state[messages_key]:
        st.session_state[messages_key] = [
            {"role": "assistant", "content": greeting}
        ]

  st.subheader(title)
  for message in st.session_state[messages_key]:
    with st.chat_message(message["role"]):
      st.markdown(message["content"])

  prompt = st.chat_input(input_placeholder)
  if prompt:
    st.session_state[messages_key].append(
        {"role": "user", "content": prompt}
    )
    with st.chat_message("user"):
      st.markdown(prompt)

    with st.chat_message("assistant"):
      with st.spinner("AI đang xử lý thông qua API..."):
        try:
          result = ask_chatbot(prompt, st.session_state[chat_id_key])
          response_content = result["response"]
        except Exception as exc:
          response_content = f"⚠️ Luồng AI dừng do lỗi: {exc}"

        st.markdown(response_content)

    st.session_state[messages_key].append(
        {"role": "assistant", "content": response_content}
    )
