from __future__ import annotations
from typing import Optional, List, Dict
from openai import OpenAI
from .config import SETTINGS

client = OpenAI(api_key=SETTINGS.openai_api_key)

SYSTEM = "You are a strong chess player. When asked for a move, decide the best move."
# Conversation mode system prompt (no FEN provided)
SYSTEM_CONV = (
    "You are playing as White in a chess game against a strong engine.\n"
    "You will respond with a single legal chess that benifits you the best.\n"
)

def ask_for_best_move_raw(fen: str, pgn_tail: str = "", side: str = "", model: Optional[str]=None) -> str:
    """Ask the target LLM for the best move in free-form text (no strict JSON)."""
    user = (
        f"Position (FEN): {fen}\n"
        + (f"Side to move: {side}\n" if side else "")
        + (f"Recent moves (PGN tail):\n{pgn_tail}\n" if pgn_tail else "")
        + "Respond with the best chess move."
    )
    rsp = client.responses.create(
        model=model or SETTINGS.openai_model,
        input=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    return rsp.output_text.strip()


def ask_for_best_move_conversation(messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
    """Given an accumulating chat-style conversation (already includes system), ask for next move.

    messages: list of {role, content} dicts. Caller is responsible for appending the latest
    user prompt requesting the move. This function simply sends them and returns raw text.
    """
    rsp = client.responses.create(
        model=model or SETTINGS.openai_model,
        input=messages,
    )
    return rsp.output_text.strip()
