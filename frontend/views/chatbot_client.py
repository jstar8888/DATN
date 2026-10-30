import json
import time

import requests

from api_client import API_BASE_URL as BACKEND_BASE_URL, authenticated_request

API_BASE_URL = f"{BACKEND_BASE_URL}/api/agent"


def ask_chatbot(question: str) -> dict:
  response = authenticated_request(
      "POST",
      f"{API_BASE_URL}/chatbot",
      json={"question": question},
  )
  run_id = response.json()["run_id"]
  deadline = time.monotonic() + 600
  events = []
  current_event = None
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
