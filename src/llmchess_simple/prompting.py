"""
Prompt builders and config for LLM move requests.

- PromptConfig controls mode (plaintext | fen | fen+plaintext), starting context, and instruction line.
- build_plaintext_messages(): chat-style messages with side, concise history, and final instruction.
- build_fen_messages(): FEN scaffold plus optional PGN tail (concise recent SAN sequence).
- build_fen_plaintext_messages(): SAME as plaintext mode but also injects current FEN for explicit board state.

"""
from __future__ import annotations
from dataclasses import dataclass

@dataclass
class PromptConfig:
    """Lightweight configuration for shaping move prompts.

    - mode: the prompting approach; one of:
        * 'plaintext' → natural language move history list
        * 'fen' → FEN + recent PGN tail (no NL history)
        * 'fen+plaintext' (case-insensitive, also allow 'fen_plaintext') → plaintext mode augmented with FEN
    - starting_context_enabled: when True and LLM starts as White, add a one-line intro
    - request_format: informational flag for desired move format (not enforced here)
    - system_*: system strings used per mode
    - instruction_line: appended to user message to request a concise move
    """
    # Mode of prompting: 'plaintext' | 'fen' | 'fen+plaintext'
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
    """Return a minimal chat message list for plaintext prompting.

    Rules:
    - Always include move history (or '(none)')
    - If LLM starts and starting_context_enabled, add a starting-line hint
    - End with instruction_line to request a concise move
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
    """Scaffold for FEN-based prompting (kept for future experiments)."""
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


def build_fen_plaintext_messages(fen: str, side: str, history_text: str, is_starting: bool, cfg: PromptConfig) -> list[dict]:
    """Combined mode: exactly plaintext prompt + an explicit FEN line.

    Structure:
      (optional) Game start line
      Position (FEN): <fen>
      Side to move: <side>
      Move history:
      <annotated NL history or (none)>
      <instruction line>

    Uses the plaintext system prompt (so we don't change model prior) while supplying
    precise board state for disambiguation.
    """
    sys_msg = cfg.system_plaintext
    lines: list[str] = []
    if is_starting and cfg.starting_context_enabled and side.lower() == "white":
        lines.append("Game start. You are White. Make the first move of the game.")
    lines.append(f"Position (FEN): {fen}")
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
