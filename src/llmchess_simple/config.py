"""
Configuration and environment loading for LLM Chess.

- Loads settings.yml (YAML) from repo root if present; falls back to environment variables.
- Exposes SETTINGS with keys used across the project (e.g., API keys, provider selection, tuning knobs).
"""
from dataclasses import dataclass
import os
from typing import Any, Callable

# YAML takes precedence
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

# YAML is used for primary configuration
try:
    import yaml  # type: ignore
except Exception:
    yaml = None  # will operate with env-only if PyYAML missing


def _repo_root() -> str:
    # this file: src/llmchess_simple/config.py → repo root is two levels up
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_yaml(path: str) -> dict:
    if not yaml:
        return {}
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


_cfg = _load_yaml(os.path.join(_repo_root(), "settings.yml"))


def _get(name: str, default: Any, cast: Callable[[Any], Any] | None = None) -> Any:
    if name in _cfg:
        val = _cfg[name]
        return cast(val) if cast else val
    env = os.environ.get(name)
    if env is not None:
        return cast(env) if cast else env
    return default


@dataclass(frozen=True)
class Settings:
    # Auth / endpoint (Vercel AI Gateway, OpenAI-compatible wire format)
    llm_api_key: str
    api_base: str

    # Tuning knobs
    responses_timeout_s: float
    responses_retries: int
    max_concurrency: int


SETTINGS = Settings(
    llm_api_key=_get("LLMCHESS_LLM_API_KEY", _get("AI_GATEWAY_API_KEY", "")),
    api_base=_get("LLMCHESS_LLM_BASE_URL", _get("AI_GATEWAY_BASE_URL", "https://ai-gateway.vercel.sh/v1")),
    responses_timeout_s=float(_get("LLMCHESS_RESPONSES_TIMEOUT_S", 300.0, cast=float)),
    responses_retries=int(_get("LLMCHESS_RESPONSES_RETRIES", 4, cast=int)),
    max_concurrency=int(_get("LLMCHESS_MAX_CONCURRENCY", 8, cast=int)),
)
