"""Configuration for API keys and engine paths (env-driven)."""
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    stockfish_path: str = os.environ.get("STOCKFISH_PATH", "stockfish")

SETTINGS = Settings()

__all__ = ["SETTINGS", "Settings"]
