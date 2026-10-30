import asyncio
from datetime import datetime, timezone
from itertools import count
from threading import Lock


class EventBus:
    def __init__(self):
        self.subscribers = {}
        self._events_by_run = {}
        self._lock = Lock()
        self._event_ids = count(1)

    async def subscribe(self):
        queue = asyncio.Queue()
        with self._lock:
            self.subscribers[queue] = asyncio.get_running_loop()
        return queue

    def unsubscribe(self, queue):
        with self._lock:
            self.subscribers.pop(queue, None)

    def publish_sync(self, event_data: dict):
        with self._lock:
            event_data = {**event_data, "event_id": next(self._event_ids)}
            run_id = event_data["run_id"]
            self._events_by_run.setdefault(run_id, []).append(event_data)
            subscribers = list(self.subscribers.items())

        for queue, loop in subscribers:
            if not loop.is_closed():
                loop.call_soon_threadsafe(queue.put_nowait, event_data)

    async def publish(self, event_data: dict):
        self.publish_sync(event_data)

    def publish_event(
        self,
        run_id: str,
        step: str,
        status: str,
        details: dict,
        agent: str | None = None,
    ):
        event_data = {
            "run_id": run_id,
            "time": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "status": status,
            "details": details,
        }
        if agent:
            event_data["agent"] = agent
        self.publish_sync(event_data)

    def get_events(self, run_id: str):
        with self._lock:
            return list(self._events_by_run.get(run_id, []))

    def get_events_since(self, event_id: int, run_id: str | None = None):
        with self._lock:
            events = (
                self._events_by_run.get(run_id, [])
                if run_id
                else (
                    event
                    for run_events in self._events_by_run.values()
                    for event in run_events
                )
            )
            return sorted(
                (
                    event
                    for event in events
                    if event["event_id"] > event_id
                ),
                key=lambda event: event["event_id"],
            )

    def get_runs(self):
        with self._lock:
            runs = [
                {
                    "run_id": run_id,
                    "status": next(
                        (
                            event["status"]
                            for event in reversed(events)
                            if event["step"] == "run"
                        ),
                        "running",
                    ),
                    "started_at": events[0]["time"],
                    "updated_at": events[-1]["time"],
                    "question": events[0]["details"].get("question", ""),
                }
                for run_id, events in self._events_by_run.items()
                if events
            ]
        return sorted(runs, key=lambda run: run["started_at"], reverse=True)


global_event_bus = EventBus()