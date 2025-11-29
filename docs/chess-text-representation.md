# Chess text representation guide

This document explains how the project turns live chess positions into text prompts for language models and how it interprets their replies. The underlying rules engine is handled by [`python-chess`](https://python-chess.readthedocs.io/), but every move request still travels through natural-language messages. Understanding this flow helps when you tweak prompts, switch notation styles, or inspect run logs.

## 1. Board state source

`GameRunner` owns a `python-chess.Board` instance through `Referee`. For every turn we derive:

- **FEN** via `board.fen()` for precise reconstruction of legal moves.
- **PGN tail** – the last *N* plies (default 20, configurable by `pgn_tail`) formatted as SAN, used when building mixed prompts.
- **Annotated history** – a human-readable list built by `_annotated_history()` in `game.py`, one move per line: `"White Pawn e4"`, `"Black Knight f6"`, etc. This is the primary context string in plaintext prompts.

These artifacts are never guessed; they come directly from the evolving board, so the textual representation always matches the real position enforced by `python-chess`.

## 2. Prompt structure sent to the LLM

All prompt builders live in `src/llmchess_simple/prompting.py`. A `PromptConfig` chooses the format:

| Mode | Function | Textual ingredients |
| --- | --- | --- |
| `plaintext` | `build_plaintext_messages` | Annotated history + side to move. Optional first-move reminder when the LLM starts as White. |
| `fen` | `build_fen_messages` | Current FEN, optional PGN tail, and side to move. |
| `fen+plaintext` | `build_fen_plaintext_messages` | Combination of FEN, side to move, and the annotated history block. |

Regardless of mode, the system prompt defaults to:

```
You are a strong chess player. When asked for a move, provide only the best legal move.
```

The final line of every user prompt comes from `PromptConfig.instruction_line`. By default we ask for SAN: `"Provide only your best legal move in SAN."` Change that string in your JSON config if you want pure UCI or algebraic notation.

### Example (plaintext mode, LLM playing White on move 3)

```
System: You are a strong chess player. When asked for a move, provide only the best legal move.
User:
Side to move: white
Move history:
White Pawn e4
Black Pawn c5
Provide only your best legal move in SAN.
```

The LLM could reply with `Nc3` or something longer like `I will play Nc3`—downstream normalization strips the extra text.

## 3. Expected LLM output and normalization

We aim for a single natural move token, but the pipeline is tolerant:

1. **Quick extraction** – a regex/first-token pass picks a move-like string from the raw reply.
2. **Move validator** (`move_validator.normalize_move`) checks the candidate against the actual board. It accepts both UCI and SAN and computes the final SAN string using `python-chess`.
3. **Salvage path** – if the first pass fails, we attempt to parse the whole raw reply directly; if a legal move name appears anywhere, we still extract it.

The result stored in the turn record contains:

- `uci`: canonical lowercase move (e.g., `e2e4`).
- `san`: notation from `python-chess` (e.g., `e4`).
- `ok`: legality flag. Any illegal output immediately ends the game with a loss for the side that produced it.
- `meta.raw`: original LLM text for auditability.

This makes the communication robust even if the model occasionally adds prose, punctuation, or alternative notation.

## 4. Textual outputs for analysis

Every game produces two JSON artifacts in the run directory:

- **Conversation log (`conv_*.json`)** – an ordered list of `{role, content}` messages showing exactly what the LLM saw and replied with each turn.
- **Structured history (`hist_*.json`)** – includes SAN and UCI for every ply, legality flags, FEN snapshots before/after, and the termination reason. These files drive the inspector UI and are a convenient way to audit how the textual prompts map to the underlying game.

By comparing the conversation log to the structured history you can trace how each textual move was interpreted and validated.

## 5. Switching notation styles

Want the model to emit UCI instead of SAN? Two knobs matter:

1. Update `prompt.instruction_line` in your JSON config (e.g., `"Respond with a single move in UCI."`).
Because legality is still enforced via `python-chess`, you can experiment with multiple representations without touching the core referee logic.

## 6. Future FEN experiments

The `fen` and `fen+plaintext` modes are ready for experiments that rely on exact board state tokens. The `PGN tail` snippet keeps context short while retaining tactical history. These modes are useful when you want to avoid ambiguity inherent to natural-language histories.

---

**Quick recap**

- `python-chess` maintains the truth; text prompts are derived from it every turn.
- Prompts contain either conversational NL history, FEN, or both depending on `PromptConfig`.
- LLM replies are normalized to UCI, validated for legality, and then logged with full context.
- Conversation and structured history logs give you a verbatim record of the textual interface.

Armed with this overview you can safely modify prompts, try alternate notations, or investigate why a model behaved unexpectedly.
