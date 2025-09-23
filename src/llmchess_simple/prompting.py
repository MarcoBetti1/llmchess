"""
Prompt builders and config for LLM move requests.

- PromptConfig controls mode (plaintext|fen scaffold), starting context, and instruction line.
- build_plaintext_messages(): chat-style messages with side, concise history, and final instruction.
- build_fen_messages(): future scaffold adding FEN and PGN tail (kept for later experiments).

"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class PromptConfig:
    # Mode of prompting: 'plaintext' or 'fen' (scaffold)
    mode: str = "plaintext"
    # Whether to include an explicit starting-context line when the LLM makes the first move
    starting_context_enabled: bool = True
    # How we ask the model to format its output (informational; not enforced here)
    request_format: str = "SAN"
    # System prompts (can be customized later)
    system_plaintext: str = (
        "You are a strong chess player. When asked for a move, provide only the best legal move."
    )
    system_fen: str = (
        "You are a strong chess player. Decide the best legal move from the provided FEN."
    )
    # Instruction line appended to the user message
    instruction_line: str = "Provide only your best legal move in SAN."


def build_plaintext_messages(side: str, history_text: str, is_starting: bool, cfg: PromptConfig) -> list[dict]:
    """Builds a chat-style message list for plaintext prompting.

    Plaintext rules:
    - Always include the move history in a list (or (none) if empty)
    - If and only if the LLM is starting the game and starting_context_enabled, add an explicit starting line
    - Always end with instruction_line requesting the output format
    """
    sys_msg = cfg.system_plaintext

    lines: list[str] = []
    if is_starting and cfg.starting_context_enabled:
        # Explicitly tell the model it's the first move
        lines.append("Game start. You are White. Make the first move of the game.")
    lines.append(f"Side to move: {side}")
    lines.append("Move history:")
    if history_text and history_text.strip():
        lines.append(history_text.strip())
    else:
        lines.append("(none)")
    lines.append(cfg.instruction_line)

    user_content = "\n".join(lines)
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": user_content},
    ]


def build_fen_messages(fen: str, pgn_tail: str, side: str, is_starting: bool, cfg: PromptConfig) -> list[dict]:
    """Scaffold for FEN-based prompting. Not used in the initial tests, kept for future work."""
    sys_msg = cfg.system_fen
    lines: list[str] = []
    if is_starting and cfg.starting_context_enabled and side.lower() == "white":
        lines.append("Game start. You are White. Make the first move of the game.")
    lines.append(f"Position (FEN): {fen}")
    if side:
        lines.append(f"Side to move: {side}")
    if pgn_tail:
        lines.append("Recent moves (PGN tail):")
        lines.append(pgn_tail)
    lines.append(cfg.instruction_line)
    user_content = "\n".join(lines)
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": user_content},
    ]
