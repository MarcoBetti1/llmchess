# Chess text representation guide

This document explains how the project turns live chess positions into text prompts for language models and how it interprets their replies. The underlying rules engine is handled by [`python-chess`](https://python-chess.readthedocs.io/), but every move request still travels through natural-language messages. Understanding this flow helps when you tweak prompts, switch notation styles, or inspect run logs.

## 1. Board state source

`GameRunner` owns a `python-chess.Board` instance through `Referee`. For every turn we derive:

- **FEN** via `board.fen()` for precise reconstruction of legal moves.
- **PGN tail** – the last *N* plies (default 20, configurable by `pgn_tail_plies`) formatted as SAN.
- **Annotated history** – a human-readable list built by `annotated_history_from_board()` in `llm_play.py`, one move per line: `"White Pawn e4"`, `"Black Knight f6"`, etc. This powers plaintext prompts.

These artifacts are never guessed; they come directly from the evolving board, so the textual representation always matches the real position enforced by `python-chess`.

## 2. Prompt structure sent to the LLM

All prompt builders live in `src/llmchess_simple/prompting.py`. A `PromptConfig` is simple:

- `system_instructions`
- `template` (with placeholders like `{FEN}`, `{SAN_HISTORY}`, `{PLAINTEXT_HISTORY}`, `{SIDE_TO_MOVE}`)
- `expected_notation` (`san` | `uci` | `fen`)

The system prompt defaults to:

```
You are a strong chess player. When asked for a move, provide only the best legal move.
```

By default we ask for SAN in the template. Change the template/system pair if you want UCI or FEN output.

### Example (plaintext template, LLM playing White on move 3)

```
System: You are a strong chess player. When asked for a move, provide only the best legal move.
User:
Side to move: white
Move history:
White Pawn e4
Black Pawn c5
Provide only your best legal move in SAN.
```

The LLM could reply with `Nc3`; downstream parsing enforces the expected notation.

## 3. Expected LLM output and normalization

We aim for a single move token, parsed strictly by the chosen notation:

1. Parse the first line/token (or entire FEN string) according to `expected_notation`.
2. `move_validator.parse_expected_move` checks legality against the current board; any illegal or format error fails the turn.

The result stored in the turn record contains:

- `uci`: canonical lowercase move (e.g., `e2e4`).
- `san`: notation from `python-chess` (e.g., `e4`).
- `ok`: legality flag. Any illegal output immediately ends the game with a loss for the side that produced it.
- `meta.raw`: original LLM text for auditability.

Any illegal output immediately forfeits the game for that side.

## 4. Textual outputs for analysis

Every game produces two JSON artifacts in the run directory:

- **Conversation log (`conv_*.json`)** – an ordered list of `{role, content}` messages showing exactly what the LLM saw and replied with each turn.
- **Structured history (`hist_*.json`)** – includes SAN and UCI for every ply, legality flags, FEN snapshots before/after, and the termination reason. These files drive the inspector UI and are a convenient way to audit how the textual prompts map to the underlying game.

By comparing the conversation log to the structured history you can trace how each textual move was interpreted and validated.

## 5. Switching notation styles

Want the model to emit UCI or FEN instead of SAN? Update `expected_notation` and the prompt template/system to match. Legality is still enforced via `python-chess`.

## 6. Future FEN experiments

FEN-driven prompts are useful when you want to avoid ambiguity inherent to natural-language histories; the PGN tail keeps context short while retaining tactical history.

---

**Quick recap**

- `python-chess` maintains the truth; text prompts are derived from it every turn.
- Prompts contain either conversational NL history, FEN, or both depending on `PromptConfig`.
- LLM replies are normalized to UCI, validated for legality, and then logged with full context.
- Conversation and structured history logs give you a verbatim record of the textual interface.

Armed with this overview you can safely modify prompts, try alternate notations, or investigate why a model behaved unexpectedly.
