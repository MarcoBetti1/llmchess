from __future__ import annotations
"""
LLM client facade over the Vercel AI Gateway (OpenAI-compatible transport; configurable base URL).

The rest of the code should not care which SDK is in use. This module talks to
the Gateway with `model` + `messages` and returns raw text responses.
"""
from typing import Optional, List, Dict
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from .config import SETTINGS

log = logging.getLogger("llm_client")

SYSTEM = "You are a strong chess player. When asked for a move, decide the best move."
# Conversation mode system prompt (no FEN provided)
SYSTEM_CONV = (
    "You are playing as White in a chess game against a strong opponent.\n"
    "Respond with a single legal chess move that benefits you most.\n"
)


_CLIENT = OpenAI(api_key=SETTINGS.llm_api_key or None, base_url=SETTINGS.api_base or None)


# ------------------------- Chat wrappers -------------------------
def ask_for_best_move_conversation(messages: List[Dict[str, str]], model: Optional[str] = None, provider: Optional[str] = None, provider_options: Optional[Dict] = None) -> str:
    """Given a chat-style conversation (including system message), request the next move."""
    if not model:
        raise ValueError("Model is required; set it in your JSON config (key 'model') or CLI.")
    delay = 0.5
    timeout = SETTINGS.responses_timeout_s
    for attempt in range(SETTINGS.responses_retries + 1):
        try:
            rsp = _CLIENT.chat.completions.create(
                model=model,
                messages=messages,
                timeout=timeout,
                extra_body={"provider_options": provider_options} if provider_options else None,
            )
            text = _extract_text(rsp)
            if text:
                return text.strip()
        except Exception:
            if attempt >= SETTINGS.responses_retries:
                log.exception("Chat request failed after %d attempts", attempt + 1)
                break
            sleep_s = delay * (2 ** attempt) * (0.8 + 0.4 * random.random())
            time.sleep(min(sleep_s, 10.0))
    return ""


def submit_turns(items: List[Dict], provider: Optional[str] = None, max_concurrency: int | None = None, request_timeout_s: float | None = None) -> Dict[str, str]:
    """Submit multiple chat prompts concurrently. Each item must include custom_id, messages, model."""
    if not items:
        return {}
    results: Dict[str, str] = {}
    max_concurrency = max_concurrency or SETTINGS.max_concurrency
    timeout = request_timeout_s or SETTINGS.responses_timeout_s

    def _one(it: Dict) -> tuple[str, str]:
        cid = str(it["custom_id"])
        model = it.get("model")
        msgs = it["messages"]
        text = ask_for_best_move_conversation(msgs, model=model, provider_options=it.get("provider_options"))
        return cid, text

    with ThreadPoolExecutor(max_workers=min(max_concurrency, max(1, len(items)))) as ex:
        futs = [ex.submit(_one, it) for it in items]
        for fut in as_completed(futs):
            try:
                cid, text = fut.result()
                if text:
                    results[cid] = text
            except Exception:
                log.exception("Parallel chat future failed")
    return results


# Convenience wrappers retained for compatibility (plaintext/FEN prompts constructed elsewhere)
def ask_for_best_move_plain(side: str, history_text: str = "", model: Optional[str] = None, provider: Optional[str] = None) -> str:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Side to move: {side}\nMove history:\n{history_text or '(none)'}\nRespond with the best legal chess move."},
    ]
    return ask_for_best_move_conversation(messages, model=model, provider=provider)


def ask_for_best_move_raw(fen: str, pgn_tail: str = "", side: str = "", model: Optional[str] = None, provider: Optional[str] = None) -> str:
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
    return ask_for_best_move_conversation(messages, model=model, provider=provider)


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
