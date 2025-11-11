# Test configuration JSON reference

This guide explains every field accepted by `scripts/run.py` when you launch experiments from JSON files (see `tests/` for examples). The runner loads each file, builds one or more `GameRunner` instances, and records results under the directory you provide in the config.

Configuration precedence works per file: all defaults listed here live inside `scripts/run.py` and `GameConfig` in `src/llmchess_simple/game.py`. If a key is missing, the code falls back to the default shown.

## Quick checklist

Every JSON config **must** include:

- `model` – OpenAI model name that supports the Responses API (for example `gpt-4o-mini`).
- `out_dir` – Destination directory for logs and metrics. The runner creates it if needed.

Everything else is optional.

## Top-level keys

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `model` | string | **required** | Used on every call to the Responses or Batches API. Empty strings raise an error. |
| `opponent` | string (`"engine"` \| `"random"`) | `"engine"` | Chooses Stockfish (`"engine"`) or the built-in random opponent. Stockfish parameters (`depth` / `movetime`) are ignored when `random` is selected. |
| `engine` | string | `"Stockfish"` | Engine label. Only `"Stockfish"` is supported today; other values raise an error. Stockfish’s binary path still comes from `STOCKFISH_PATH` or `settings.yml`. |
| `depth` | integer | `6` | Search depth passed to Stockfish when `movetime` is null. Lower values speed up games; higher costs more CPU. |
| `movetime` | integer (milliseconds) or `null` | `null` | Milliseconds to give Stockfish per move. When set, it overrides `depth`. Leave `null` to stick with fixed depth. |
| `games` | integer ≥ 1 | `1` | Number of games to run for this configuration. When `color`/`llm_color` is `"both"`, the runner doubles this count (half as White, half as Black). |
| `mode` | string (`"sequential"` \| `"batch"` \| `"parallel"`) | `"sequential"` | Selects the transport. `"sequential"` (or legacy `"parallel"`) uses live Responses API calls; `"batch"` uses the OpenAI Batches API with chunking controlled by environment settings. |
| `out_dir` | string | **required** | Directory that will receive conversation logs, structured histories, and `results.jsonl`. Any missing parent directories are created. |
| `log_level` | string | `"INFO"` | Per-config logging level (e.g. `"DEBUG"`, `"WARNING"`). Applies to the root logger before the games start. |
| `color` | string (`"white"` \| `"black"` \| `"both"`) | `"white"` | Preferred LLM side. Alias: `llm_color`. `"both"` plays the specified number of games twice—first as White, then as Black. |
| `max_plies` | integer | `480` | Hard ceiling on half-moves. Once reached the game stops and is scored as a draw unless it ended earlier. |
| `max_illegal` | integer | `1` | Number of illegal LLM moves allowed before terminating the game and recording a loss for the model. |
| `pgn_tail` | integer | `20` | Number of recent plies included in the PGN tail that feeds prompt builders (used for FEN + plaintext prompts). |
| `verbose_llm` | boolean | `false` | When true, prints the raw LLM response, candidate move, and legality assessment to the console for each LLM turn. |
| `prompt` | object | `{}` | Nested structure that customises how prompts are built (see [Prompt settings](#prompt-settings)). |
| `conversation_mode` | boolean | `false` | Currently unused placeholder. Present for legacy configs; toggling it has no effect. |

## Prompt settings

The optional `prompt` object feeds `PromptConfig` in `src/llmchess_simple/prompting.py`. All keys are optional:

| Key | Type | Default | Effect |
| --- | --- | --- | --- |
| `mode` | string (`"plaintext"` \| `"fen"` \| `"fen+plaintext"`) | `"plaintext"` | Selects the prompt template. `"plaintext"` lists moves in natural language, `"fen"` sends only FEN + PGN tail, and `"fen+plaintext"` combines both. |
| `starting_context_enabled` | boolean | `true` | Adds “Game start. You are White…” when the LLM plays the very first move. Useful for letting the model know it is starting as White. |
| `instruction_line` | string | `"Provide only your best legal move in SAN."` | Appended to the user message to steer output format. Swap this to demand UCI, algebraic notation, etc. |

`PromptConfig` has additional fields (`system_plaintext`, `system_fen`, `request_format`) but the loader does not accept them from JSON yet. Adjust them in code if you need custom system prompts.

> **Tip:** If you omit the `prompt` block entirely you still get per-turn conversation logs because the runner wraps every game with `GameConfig(game_log=True, conversation_log_every_turn=True)`.

## Colour handling

- Provide either `color` or `llm_color`; both work. Values are case-insensitive.
- When set to `"both"`, sequential mode plays `games` as White followed by `games` as Black. Batch mode schedules twice as many games at once (first half White, second half Black).
- `GameRunner` ultimately respects `GameConfig.color`, so downstream logic and the exported PGN correctly reflect the selected side.

## Outputs per run

For each game the runner writes:

- Conversation transcript `conv_*.json` capturing the prompt/response pairs.
- Structured history `hist_*.json` with SAN, UCI, legality flags, and termination metadata.
- Aggregated metrics appended to `<out_dir>/results.jsonl`.

Summaries include legal-rate statistics, average latency, PGN, and verification metadata. The orchestrator ensures these files land under the directory you provided via `out_dir`.

## Legacy / ignored keys

The older configs inside `tests/` still include `conversation_mode`. It’s read but not consumed by today’s runner, so feel free to drop it in new files.

If you need to tweak per-game logging destinations or salvage behaviour, edit `scripts/run.py` or `GameConfig` directly—the JSON schema above covers all parameters currently wired to the CLI.
