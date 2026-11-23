import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama


logger = logging.getLogger(__name__)
MODEL_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "agent_models.json"
)

AGENT_MODELS = {
    "query_rewriter": {
        "label": "Query Writer Agent",
        "gemini": "gemini-2.5-flash",
        "ollama": "qwen2.5-coder:7b",
    },
    "router": {
        "label": "Router Agent",
        "gemini": "gemini-2.5-flash",
        "ollama": "qwen2.5-coder:7b",
    },
    "sql_expert": {
        "label": "SQL Expert Agent",
        "gemini": "gemini-2.5-flash",
        "ollama": "qwen2.5-coder:7b",
    },
    "synthesizer": {
        "label": "Synthesizer Agent",
        "gemini": "gemini-2.5-flash",
        "ollama": "qwen2.5-coder:7b",
    },
    "evaluate": {
        "label": "Evaluate Agent",
        "gemini": "gemini-2.5-flash",
        "ollama": "qwen2.5-coder:7b",
    },
    "sql_validator": {
        "label": "SQL Validator Agent",
        "gemini": "gemini-2.5-flash",
        "ollama": "qwen2.5-coder:7b",
    },
}
_config_lock = Lock()


def _read_providers() -> dict[str, str]:
    try:
        with MODEL_CONFIG_PATH.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Không thể đọc cấu hình model agent: {MODEL_CONFIG_PATH}"
        ) from exc

    providers = config.get("agents") if isinstance(config, dict) else None
    expected_agents = set(AGENT_MODELS)
    if not isinstance(providers, dict) or set(providers) != expected_agents:
        raise RuntimeError("Cấu hình model agent thiếu hoặc thừa agent.")
    if any(
        not isinstance(provider, str) or provider not in {"gemini", "ollama"}
        for provider in providers.values()
    ):
        raise RuntimeError("Cấu hình provider của agent không hợp lệ.")
    return providers


def get_agent_model_settings() -> list[dict[str, Any]]:
    with _config_lock:
        providers = _read_providers()

    return [
        {
            "id": agent_id,
            "label": agent_config["label"],
            "provider": providers[agent_id],
            "model": agent_config[providers[agent_id]],
            "options": [
                {"provider": provider, "model": agent_config[provider]}
                for provider in ("gemini", "ollama")
            ],
        }
        for agent_id, agent_config in AGENT_MODELS.items()
    ]


def update_agent_model_settings(
    providers: dict[str, str],
) -> list[dict[str, Any]]:
    if set(providers) != set(AGENT_MODELS):
        raise ValueError("Phải cung cấp cấu hình cho toàn bộ agent.")
    if any(
        not isinstance(provider, str) or provider not in {"gemini", "ollama"}
        for provider in providers.values()
    ):
        raise ValueError("Provider chỉ được là gemini hoặc ollama.")

    with _config_lock:
        temporary_path = MODEL_CONFIG_PATH.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                json.dumps({"agents": providers}, ensure_ascii=False, indent=2)
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, MODEL_CONFIG_PATH)
        except OSError:
            logger.exception("Không thể cập nhật cấu hình model agent")
            raise
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    return get_agent_model_settings()


class ConfigurableChatModel:
    def __init__(
        self,
        agent_id: str,
        temperature: float,
        *,
        ollama_base_url: str = "http://localhost:11434",
        ollama_keep_alive: str = "10m",
        reasoning: bool = False,
    ):
        if agent_id not in AGENT_MODELS:
            raise ValueError(f"Agent chưa được khai báo cấu hình model: {agent_id}")
        self.agent_id = agent_id
        self.temperature = temperature
        self.ollama_base_url = ollama_base_url
        self.ollama_keep_alive = ollama_keep_alive
        self.reasoning = reasoning
        self._models: dict[tuple[str, str], Any] = {}
        self._models_lock = Lock()

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        with _config_lock:
            provider = _read_providers()[self.agent_id]
        model_name = AGENT_MODELS[self.agent_id][provider]
        model_key = (provider, model_name)

        with self._models_lock:
            model = self._models.get(model_key)
            if model is None:
                if provider == "gemini":
                    model = ChatGoogleGenerativeAI(
                        model=model_name,
                        temperature=self.temperature,
                    )
                else:
                    model = ChatOllama(
                        model=model_name,
                        temperature=self.temperature,
                        base_url=self.ollama_base_url,
                        keep_alive=self.ollama_keep_alive,
                        reasoning=self.reasoning,
                    )
                self._models[model_key] = model

        return model.invoke(messages, **kwargs)
