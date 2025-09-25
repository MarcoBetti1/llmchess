"""
Configuration and environment loading for LLM Chess.

- Loads prof.yml (YAML) from repo root if present; falls back to environment variables.
- Exposes SETTINGS with keys used across the project (e.g., OPENAI_API_KEY, STOCKFISH_PATH, tuning knobs).
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


def _parse_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        return s not in ("", "0", "false", "no", "off", "none")
    return bool(v)


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
    # Secrets/keys
    openai_api_key: str

    # Paths
    stockfish_path: str

    # OpenAI batches
    openai_batch_completion_window: str

    # Tuning knobs
    items_per_batch: int
    turn_max_wait_s: float
    batch_poll_s: float
    batch_timeout_s: float
    responses_timeout_s: float
    responses_retries: int
    max_concurrency: int
    use_guard_agent: bool
    partial_retry_max: int


SETTINGS = Settings(
    openai_api_key=_get("OPENAI_API_KEY", ""),
    stockfish_path=_get("STOCKFISH_PATH", "stockfish"),
    openai_batch_completion_window=_get("OPENAI_BATCH_COMPLETION_WINDOW", "24h"),
    items_per_batch=int(_get("LLMCHESS_ITEMS_PER_BATCH", 200, cast=int)),
    turn_max_wait_s=float(_get("LLMCHESS_TURN_MAX_WAIT_S", 1200.0, cast=float)),
    batch_poll_s=float(_get("LLMCHESS_BATCH_POLL_S", 2.0, cast=float)),
    batch_timeout_s=float(_get("LLMCHESS_BATCH_TIMEOUT_S", 600.0, cast=float)),
    responses_timeout_s=float(_get("LLMCHESS_RESPONSES_TIMEOUT_S", 300.0, cast=float)),
    responses_retries=int(_get("LLMCHESS_RESPONSES_RETRIES", 4, cast=int)),
    max_concurrency=int(_get("LLMCHESS_MAX_CONCURRENCY", 8, cast=int)),
    use_guard_agent=_parse_bool(_get("LLMCHESS_USE_GUARD_AGENT", True)),
    partial_retry_max=int(_get("LLMCHESS_PARTIAL_RETRY_MAX", 3, cast=int)),
)
