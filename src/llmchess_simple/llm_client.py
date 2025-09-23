from __future__ import annotations
"""
LLM client facade over provider transports.

- Parallel Responses API (interactive): low latency per turn, good for live games.
- OpenAI Batches API (offline): submit N requests as one job for large sweeps.

Selection: prefer parallel by default; set prefer_batches=True to force batches.
Chunking controlled by env LLMCHESS_ITEMS_PER_BATCH. Stable API delegates to provider.

"""
from typing import Optional, List, Dict
import logging
from .providers.openai_provider import OpenAIProvider

# Provider registry: in the future, we can add Anthropic, Azure OpenAI, etc.
_PROVIDER = OpenAIProvider()
log = logging.getLogger("llm_client")

SYSTEM = "You are a strong chess player. When asked for a move, decide the best move."
# Conversation mode system prompt (no FEN provided)
SYSTEM_CONV = (
    "You are playing as White in a chess game against a strong engine.\n"
    "Respond with a single legal chess move that benefits you most.\n"
)

def ask_for_best_move_raw(fen: str, pgn_tail: str = "", side: str = "", model: Optional[str]=None) -> str:
    """Ask the target LLM for the best move in free-form text (no strict JSON)."""
    return _PROVIDER.ask_for_best_move_raw(fen, pgn_tail=pgn_tail, side=side, model=model)


def ask_for_best_move_conversation(messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
    """Given an accumulating chat-style conversation (already includes system), ask for next move.

    messages: list of {role, content} dicts. Caller is responsible for appending the latest
    user prompt requesting the move. This function simply sends them and returns raw text.
    """
    return _PROVIDER.ask_for_best_move_conversation(messages, model=model)

def ask_for_best_move_plain(side: str, history_text: str = "", model: Optional[str] = None) -> str:
    """Plain text prompt without FEN. history_text should be a multiline string of past moves.

    Example history_text:
      1. White Pawn e4  Black Knight f6
      2. White Pawn e5  Black Pawn g6
    """
    return _PROVIDER.ask_for_best_move_plain(side, history_text=history_text, model=model)


# ------------------------- Transport facade -------------------------


def _extract_output_text_from_response_obj(resp_obj: dict) -> str:
    """Deprecated: kept for backward compat if any callers import it. Delegates to provider."""
    return OpenAIProvider._extract_output_text_from_response_obj(resp_obj)


def submit_responses_parallel(items: List[Dict], max_concurrency: int = None, request_timeout_s: float = None) -> Dict[str, str]:
    return _PROVIDER.submit_responses_parallel(items, max_concurrency=max_concurrency, request_timeout_s=request_timeout_s)


def submit_responses_batch(items: List[Dict], poll_interval_s: float | None = None, timeout_s: float | None = None) -> Dict[str, str]:
    return _PROVIDER.submit_responses_batch(items, poll_interval_s=poll_interval_s, timeout_s=timeout_s)


def submit_responses_batch_chunked(items: List[Dict], items_per_batch: Optional[int] = None) -> Dict[str, str]:
    return _PROVIDER.submit_responses_batch_chunked(items, items_per_batch=items_per_batch)


def submit_responses_transport(items: List[Dict], prefer_batches: Optional[bool] = None, items_per_batch: Optional[int] = None) -> Dict[str, str]:
    return _PROVIDER.submit_responses_transport(items, prefer_batches=prefer_batches, items_per_batch=items_per_batch)


def submit_responses(items: List[Dict]) -> Dict[str, str]:
    return _PROVIDER.submit_responses(items)


def submit_responses_blocking_all(items: List[Dict], max_wait_s: float = None, prefer_batches: Optional[bool] = None, items_per_batch: Optional[int] = None) -> Dict[str, str]:
    return _PROVIDER.submit_responses_blocking_all(items, max_wait_s=max_wait_s, prefer_batches=prefer_batches, items_per_batch=items_per_batch)
