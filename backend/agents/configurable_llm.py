import json
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq


logger = logging.getLogger(__name__)
MODEL_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "agent_models.json"
)

AGENT_MODELS = {
    "query_rewriter": {
        "label": "Query Writer Agent",
        "gemini": "gemini-2.5-flash",
        "groq": "openai/gpt-oss-120b",
        "ollama": "qwen2.5-coder:7b",
    },
    "router": {
        "label": "Router Agent",
        "gemini": "gemini-2.5-flash",
        "groq": "openai/gpt-oss-120b",
        "ollama": "qwen2.5-coder:7b",
    },
    "sql_expert": {
        "label": "SQL Expert Agent",
        "gemini": "gemini-2.5-flash",
        "groq": "openai/gpt-oss-120b",
        "ollama": "qwen2.5-coder:7b",
    },
    "synthesizer": {
        "label": "Synthesizer Agent",
        "gemini": "gemini-2.5-flash",
        "groq": "openai/gpt-oss-120b",
        "ollama": "qwen2.5-coder:7b",
    },
    "evaluate": {
        "label": "Evaluate Agent",
        "gemini": "gemini-2.5-flash",
        "groq": "openai/gpt-oss-120b",
        "ollama": "qwen2.5-coder:7b",
    },
    "sql_validator": {
        "label": "SQL Validator Agent",
        "gemini": "gemini-2.5-flash",
        "groq": "openai/gpt-oss-120b",
        "ollama": "qwen2.5-coder:7b",
    },
}
DEFAULT_TEMPERATURES = {
    "query_rewriter": 0.1,
    "router": 0.1,
    "sql_expert": 0.1,
    "synthesizer": 0.1,
    "evaluate": 0.1,
    "sql_validator": 0.0,
}
DEFAULT_RAG_SEARCH_SETTINGS = {"match_threshold": 0.6, "match_count": 4}
DEFAULT_TABLE_RETRIEVAL_SETTINGS = {"match_count": 3}
_PROVIDERS = {"gemini", "ollama", "groq"}
_config_lock = Lock()


def _read_config() -> dict[str, Any]:
    try:
        with MODEL_CONFIG_PATH.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Không thể đọc cấu hình model agent: {MODEL_CONFIG_PATH}"
        ) from exc

    providers = config.get("agents") if isinstance(config, dict) else None
    expected_agents = set(AGENT_MODELS)
    if not isinstance(providers, dict) or set(providers) - expected_agents:
        raise RuntimeError("Cấu hình model agent thiếu hoặc thừa agent.")
    if set(providers) != expected_agents:
        raise RuntimeError("Cấu hình model agent thiếu hoặc thừa agent.")
    if any(
        not isinstance(provider, str) or provider not in _PROVIDERS
        for provider in providers.values()
    ):
        raise RuntimeError("Cấu hình provider của agent không hợp lệ.")

    temperatures = config.get("temperatures", {})
    if not isinstance(temperatures, dict) or set(temperatures) - expected_agents:
        raise RuntimeError("Cấu hình temperature của agent không hợp lệ.")
    temperatures = {**DEFAULT_TEMPERATURES, **temperatures}
    if any(
        isinstance(temperature, bool)
        or not isinstance(temperature, (int, float))
        or not 0 <= temperature <= 2
        for temperature in temperatures.values()
    ):
        raise RuntimeError("Temperature phải nằm trong khoảng từ 0 đến 2.")

    rag_search = config.get("rag_search", DEFAULT_RAG_SEARCH_SETTINGS)
    if (
        not isinstance(rag_search, dict)
        or set(rag_search) != set(DEFAULT_RAG_SEARCH_SETTINGS)
        or isinstance(rag_search.get("match_threshold"), bool)
        or not isinstance(rag_search.get("match_threshold"), (int, float))
        or not 0 <= rag_search["match_threshold"] <= 1
        or isinstance(rag_search.get("match_count"), bool)
        or not isinstance(rag_search.get("match_count"), int)
        or not 1 <= rag_search["match_count"] <= 100
    ):
        raise RuntimeError("Cấu hình retrieval RAG không hợp lệ.")

    table_retrieval = config.get(
        "table_retrieval", DEFAULT_TABLE_RETRIEVAL_SETTINGS
    )
    if (
        not isinstance(table_retrieval, dict)
        or set(table_retrieval) != set(DEFAULT_TABLE_RETRIEVAL_SETTINGS)
        or isinstance(table_retrieval.get("match_count"), bool)
        or not isinstance(table_retrieval.get("match_count"), int)
        or not 1 <= table_retrieval["match_count"] <= 100
    ):
        raise RuntimeError("Cấu hình retrieval bảng không hợp lệ.")

    return {
        "agents": providers,
        "temperatures": temperatures,
        "rag_search": rag_search,
        "table_retrieval": table_retrieval,
    }


def get_agent_model_settings() -> list[dict[str, Any]]:
    with _config_lock:
        config = _read_config()

    return [
        {
            "id": agent_id,
            "label": agent_config["label"],
            "provider": config["agents"][agent_id],
            "model": agent_config[config["agents"][agent_id]],
            "temperature": config["temperatures"][agent_id],
            "options": [
                {"provider": provider, "model": agent_config[provider]}
                for provider in ("gemini", "ollama", "groq")
            ],
        }
        for agent_id, agent_config in AGENT_MODELS.items()
    ]


def get_retrieval_settings() -> dict[str, Any]:
    with _config_lock:
        config = _read_config()
    return {
        "rag_match_threshold": config["rag_search"]["match_threshold"],
        "rag_match_count": config["rag_search"]["match_count"],
        "table_match_count": config["table_retrieval"]["match_count"],
    }


def update_agent_model_settings(
    providers: dict[str, str],
    temperatures: dict[str, float] | None = None,
    rag_match_threshold: float | None = None,
    rag_match_count: int | None = None,
    table_match_count: int | None = None,
) -> list[dict[str, Any]]:
    if set(providers) != set(AGENT_MODELS):
        raise ValueError("Phải cung cấp cấu hình cho toàn bộ agent.")
    if any(
        not isinstance(provider, str) or provider not in _PROVIDERS
        for provider in providers.values()
    ):
        raise ValueError("Provider chỉ được là gemini, ollama hoặc groq.")
    if temperatures is not None and (
        set(temperatures) != set(AGENT_MODELS)
        or any(
            isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or not 0 <= temperature <= 2
            for temperature in temperatures.values()
        )
    ):
        raise ValueError("Temperature phải được cung cấp cho mọi agent trong khoảng từ 0 đến 2.")
    if (
        rag_match_threshold is not None
        and (
            isinstance(rag_match_threshold, bool)
            or not isinstance(rag_match_threshold, (int, float))
            or not 0 <= rag_match_threshold <= 1
        )
    ):
        raise ValueError("Match threshold phải nằm trong khoảng từ 0 đến 1.")
    for match_count in (rag_match_count, table_match_count):
        if match_count is not None and (
            isinstance(match_count, bool)
            or not isinstance(match_count, int)
            or not 1 <= match_count <= 100
        ):
            raise ValueError("Match count phải là số nguyên từ 1 đến 100.")

    with _config_lock:
        current = _read_config()
        next_config = {
            "agents": providers,
            "temperatures": temperatures or current["temperatures"],
            "rag_search": {
                "match_threshold": (
                    current["rag_search"]["match_threshold"]
                    if rag_match_threshold is None
                    else rag_match_threshold
                ),
                "match_count": (
                    current["rag_search"]["match_count"]
                    if rag_match_count is None
                    else rag_match_count
                ),
            },
            "table_retrieval": {
                "match_count": (
                    current["table_retrieval"]["match_count"]
                    if table_match_count is None
                    else table_match_count
                ),
            },
        }
        temporary_path = MODEL_CONFIG_PATH.with_suffix(".tmp")
        try:
            temporary_path.write_text(
                json.dumps(next_config, ensure_ascii=False, indent=2) + "\n",
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
        self._models: dict[tuple[str, str, float], Any] = {}
        self._models_lock = Lock()

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        with _config_lock:
            config = _read_config()
        provider = config["agents"][self.agent_id]
        temperature = config["temperatures"][self.agent_id]
        model_name = AGENT_MODELS[self.agent_id][provider]
        model_key = (provider, model_name, temperature)

        with self._models_lock:
            model = self._models.get(model_key)
            if model is None:
                if provider == "gemini":
                    model = ChatGoogleGenerativeAI(
                        model=model_name,
                        temperature=temperature,
                    )
                elif provider == "groq":
                    model = ChatGroq(
                        model=model_name,
                        temperature=temperature,
                    )
                else:
                    model = ChatOllama(
                        model=model_name,
                        temperature=temperature,
                        base_url=self.ollama_base_url,
                        keep_alive=self.ollama_keep_alive,
                        reasoning=self.reasoning,
                    )
                self._models[model_key] = model

        return model.invoke(messages, **kwargs)
