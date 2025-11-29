# Test configuration JSON reference

This guide explains every field accepted by `scripts/run.py` when you launch experiments from JSON files (see `tests/` for examples). The runner loads each file, builds one or more `GameRunner` instances, and records results under the directory you provide in the config.

Configuration precedence works per file: all defaults live inside `scripts/run.py` and `GameConfig` in `src/llmchess_simple/game.py`. If a key is missing, the code falls back to the default shown.

## Quick checklist

Every JSON config **must** include:

- `model` – OpenAI-compatible model name that supports chat/completions (for example `gpt-4o-mini`).
- `out_dir` – Destination directory for logs and metrics. The runner creates it if needed.
- When `opponent` is `"llm"`, also provide `opponent_model`.

## Top-level keys

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `model` | string | **required** | Used on every chat/completions call for the primary LLM. Empty strings raise an error. |
| `provider` | string | `null` | Optional provider override for the primary LLM; otherwise uses `LLMCHESS_PROVIDER` from settings. |
| `provider_options` | object | `null` | Optional providerOptions payload forwarded to the gateway (e.g., routing hints). |
| `opponent` | string (`"llm"` \| `"user"`) | `"llm"` | Choose another LLM opponent or an interactive human user. |
| `opponent_model` | string | `null` | Required when `opponent` is `"llm"`; model name for the opposing side. |
| `opponent_provider` | string | `null` | Optional provider override for the opponent LLM. Defaults to `provider`/`LLMCHESS_PROVIDER`. |
| `opponent_provider_options` | object | `null` | Optional providerOptions for the opponent side. |
| `opponent_name` | string | `null` | Optional display label for the opponent (headers/logs). |
| `games` | integer ≥ 1 | `1` | Number of games to run for this configuration. When `color`/`llm_color` is `"both"`, the runner doubles this count (half as White, half as Black). |
| `mode` | string (`"sequential"` \| `"orchestrated"` \| legacy `"parallel"/"batch"`) | `"sequential"` | `"sequential"` plays games one after another; `"orchestrated"` advances many LLM-vs-LLM games in lockstep with one chat request per active turn. Legacy values map to these modes. |
| `out_dir` | string | **required** | Directory that will receive conversation logs, structured histories, and `results.jsonl`. Any missing parent directories are created. |
| `log_level` | string | `"INFO"` | Per-config logging level (e.g. `"DEBUG"`, `"WARNING"`). Applies to the root logger before the games start. |
| `color` | string (`"white"` \| `"black"` \| `"both"`) | `"white"` | Preferred LLM side. Alias: `llm_color`. `"both"` plays the specified number of games twice—first as White, then as Black. |
| `max_plies` | integer | `480` | Hard ceiling on half-moves. Once reached the game stops and is scored as a draw unless it ended earlier. |
| `pgn_tail` | integer | `20` | Number of recent plies included in the PGN tail that feeds prompt builders (used for FEN + plaintext prompts). |
| `verbose_llm` | boolean | `false` | When true, prints the raw LLM response, candidate move, and legality assessment to the console for each LLM turn. |
| `prompt` | object | `{}` | Nested structure that customises how prompts are built (see [Prompt settings](#prompt-settings)). |
| `opponent_prompt` | object | `{}` | Optional prompt override for the opponent when `opponent` is `"llm"` (same shape as `prompt`). |
| `conversation_mode` | boolean | `false` | Currently unused placeholder. Present for legacy configs; toggling it has no effect. |

**Legality rule:** Any illegal move from either side immediately ends the game with a loss for the offending model. There is no longer a configurable illegal-move allowance. Human inputs are validated and must be legal before they are applied.

### LLM opponents

To run head-to-head model evaluations, set `opponent` to `"llm"` and supply `opponent_model`. You can optionally provide `opponent_provider`, `opponent_prompt`, and `opponent_name` to customise the opposing side independently of the primary LLM. Use `opponent: "user"` for interactive human games (sequential mode only).

## Prompt settings

The optional `prompt` object feeds `PromptConfig` in `src/llmchess_simple/prompting.py`. All keys are optional:

| Key | Type | Default | Effect |
| --- | --- | --- | --- |
| `mode` | string (`"plaintext"` \| `"fen"` \| `"fen+plaintext"`) | `"plaintext"` | Selects the prompt template. `"plaintext"` lists moves in natural language, `"fen"` sends only FEN + PGN tail, and `"fen+plaintext"` combines both. |
| `starting_context_enabled` | boolean | `true` | Adds “Game start. You are White…” when the LLM plays the very first move. Useful for letting the model know it is starting as White. |
| `instruction_line` | string | `"Provide only your best legal move in SAN."` | Appended to the user message to steer output format. Swap this to demand UCI, algebraic notation, etc. |
| `instructions_template` | string | `null` | Optional additional guidance inserted before `instruction_line` (multi-line friendly). Useful for experiments with style or reasoning hints. |

`PromptConfig` has additional fields (`system_plaintext`, `system_fen`, `request_format`) that remain code-only; use `instructions_template` when you need to inject richer instructions without editing code.

## Colour handling

- Provide either `color` or `llm_color`; both work. Values are case-insensitive.
- When set to `"both"`, sequential mode plays `games` as White followed by `games` as Black. Orchestrated mode schedules twice as many games in one sweep (first half White, second half Black).
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
