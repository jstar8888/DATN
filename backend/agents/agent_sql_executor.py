from tools.supabase_executor import SupabaseExecutor
from utils.event_bus import global_event_bus


class SQLExecutorAgent:
  def __init__(self, executor: SupabaseExecutor | None = None):
    self.executor = executor

  def process(self, sql_query: str, run_id: str | None = None) -> list[dict]:
    try:
      if self.executor is None:
        self.executor = SupabaseExecutor()
      if run_id:
        global_event_bus.publish_event(
            run_id,
            "query_execution",
            "started",
            {"message": "Đang thực thi truy vấn."},
            agent="sql_executor",
        )
      raw_data = self.executor.execute_readonly(sql_query)
    except Exception as exc:
      if run_id:
        global_event_bus.publish_event(
            run_id,
            "query_execution",
            "failed",
            {"message": str(exc)},
            agent="sql_executor",
        )
      raise

    if run_id:
      global_event_bus.publish_event(
          run_id,
          "query_execution",
          "completed",
          {"has_data": bool(raw_data)},
          agent="sql_executor",
      )
    return raw_data
