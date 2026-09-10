from __future__ import annotations
"""
LLM client facade over the Vercel AI Gateway (OpenAI-compatible transport; configurable base URL).

The rest of the code should not care which SDK is in use. This module talks to
the Gateway with `model` + `messages` and returns raw text responses.
"""
from typing import Optional, List, Dict
import logging

from openai import OpenAI

from .config import SETTINGS

log = logging.getLogger("llm_client")

SYSTEM = "You are a strong chess player. When asked for a move, decide the best move."


_CLIENT = None


def _client():
    # Offline imports must not require credentials. Disable SDK retries so an
    # uncertain paid request is never silently sent again.
    global _CLIENT
    if _CLIENT is None:
        if not SETTINGS.llm_api_key:
            raise RuntimeError("Set LLMCHESS_LLM_API_KEY before requesting a move")
        _CLIENT = OpenAI(api_key=SETTINGS.llm_api_key, base_url=SETTINGS.api_base, max_retries=0)
    return _CLIENT


# ------------------------- Chat wrappers -------------------------
def ask_for_best_move_conversation(messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
    """Given a chat-style conversation (including system message), request the next move."""
    if not model:
        raise ValueError("Model is required; set it in your JSON config (key 'model') or CLI.")
    modern = model.split("/")[-1].startswith(("gpt-5", "gpt-6"))
    limits = {"reasoning_effort": "low", "max_completion_tokens": 2048} if modern else {"max_tokens": 2048}
    rsp = _client().chat.completions.create(
        model=model, messages=messages, timeout=SETTINGS.responses_timeout_s, **limits,
    )
    text = _extract_text(rsp)
    if not text:
        raise RuntimeError("Provider returned no move text; transport failure is not a chess loss")
    return text.strip()


# Convenience wrappers retained for compatibility (plaintext/FEN prompts constructed elsewhere)
def ask_for_best_move_plain(side: str, history_text: str = "", model: Optional[str] = None) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Side to move: {side}\nMove history:\n{history_text or '(none)'}\nRespond with the best legal chess move."},
    ]
    return ask_for_best_move_conversation(messages, model=model)


def ask_for_best_move_raw(fen: str, pgn_tail: str = "", side: str = "", model: Optional[str] = None) -> str:
    parts = [f"Position (FEN): {fen}"]
    if side:
        parts.append(f"Side to move: {side}")
    if pgn_tail:
        parts.append(f"Recent moves (PGN tail):\n{pgn_tail}")
    parts.append("Respond with the best chess move.")
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "\n".join(parts)},
    ]
    return ask_for_best_move_conversation(messages, model=model)


def _extract_text(rsp) -> str:
    try:
        if hasattr(rsp, "choices") and rsp.choices:
            msg = rsp.choices[0].message
            content = getattr(msg, "content", None)
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict):
                        if c.get("type") == "text" and isinstance(c.get("text"), str):
                            parts.append(c["text"])
                        continue
                    if hasattr(c, "text"):
                        t = getattr(c, "text", None)
                        if isinstance(t, str):
                            parts.append(t)
                if parts:
                    return "\n".join(parts)
    except Exception:
        log.exception("Failed to extract text from response")
    return ""
