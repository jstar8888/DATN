from typing import Any


def extract_token_usage(response: Any) -> dict[str, int] | None:
  response_metadata = getattr(response, "response_metadata", {}) or {}
  if not isinstance(response_metadata, dict):
    response_metadata = {}
  usage_sources = (
      getattr(response, "usage_metadata", None),
      response_metadata.get("usage_metadata"),
      response_metadata.get("token_usage"),
  )
  if not any(isinstance(source, dict) for source in usage_sources):
    return None

  def get_count(*keys: str) -> int | None:
    for source in usage_sources:
      if not isinstance(source, dict):
        continue
      for key in keys:
        value = source.get(key)
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
        ):
          return value
    return None

  input_tokens = get_count("input_tokens", "prompt_tokens", "promptTokenCount")
  output_tokens = get_count(
      "output_tokens", "completion_tokens", "candidatesTokenCount"
  )
  total_tokens = get_count("total_tokens", "totalTokenCount")
  if input_tokens is None and output_tokens is None and total_tokens is None:
    return None

  input_tokens = input_tokens or 0
  output_tokens = output_tokens or 0
  return {
      "input_tokens": input_tokens,
      "output_tokens": output_tokens,
      "total_tokens": (
          total_tokens
          if total_tokens is not None
          else input_tokens + output_tokens
      ),
  }
