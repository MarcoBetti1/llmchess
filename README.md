# TODO
Check if in batch mode when one game ends, others will continue until completion. ()
Orgainze project (play_one outside scripts dir) (). 

Add a cancel for batching. Since we often run tests and dont wait for batch results this may waste tokens.  

Results are automatically written under an output folder per run.  
Use these commands to try the demos:

`python -u scripts/run.py --configs test-configs/batch_demo.json`
`python -u scripts/run.py --configs test-configs/parallel_demo.json`  # uses mode: sequential


# LLM Chess (Simplified)

A lightweight benchmark to test LLMs on chess with light agent system:  
Currently 1 agent who:  

1) ensures the model's reply actually contains a chess move, and
2) return it in a strict **UCI** format (e.g., `e2e4`, `e7e8q`).

The game pipeline:
- We prompt a target model and ask for the *best move*.
- We pass the model's free-form reply to a tiny **Agent (Agents SDK)** that calls a Python tool to validate the move
  against the FEN and normalize it to UCI. If invalid, the agent is asked to try again.
- We apply the move and play


## Quickstart

```bash

pip install -r requirements.txt
# Set env vars (or copy .env.example to .env and edit)
export OPENAI_API_KEY=
export STOCKFISH_PATH=



# Save conversation snapshots every move (defaults enabled)
python play_one.py --model gpt-4o-mini --prompt-mode plaintext

# Multi-game runner documentation
```

## Notes
- The **agent** only validates/normalizes the move. All strategy testing is handled by the engine opponent and results.
- The code uses the OpenAI **Responses API** for free-form LLM replies and the **Agents SDK** for the validator tool.
- If your Agents SDK import path differs, adjust `agent_normalizer.py` imports accordingly (see comments).

---

## Visualize a recorded game (rewatch)

Use the interactive viewer to step through a structured history JSON (hist_*.json):

- Run: python scripts/view_game.py <path-to-hist.json>
- Optional flags: --autoplay (start playing automatically), --delay <seconds> (autoplay speed)
- Controls during viewing:
  - Enter: next move
  - p: previous move
  - a: autoplay (resume)
  - s: pause
  - r: restart from beginning
  - g <ply>: jump to ply number (0..N)
  - + / -: faster / slower autoplay
  - q: quit

Example path from this repo:
- scripts/view_game.py runs/parallel_demo/g001/hist_20250920-122740_std_w.json

Notes
- Viewer uses python-chess to render an ASCII board in the terminal.
- If the game ended due to an illegal move, playback stops at the last legal position and shows the termination info.

---

## Config-driven runs (simplified)
You can run experiments with just a config file. Outputs are always written:

See the Notes in the configuration section for all supported fields.

Example:

```json
{
  "model": "gpt-5-nano",
  "engine": "Stockfish",
  "opponent": "random",
  "games": 2,
  "mode": "batch"
}
```

Run it with:

```bash
python -u scripts/run.py --configs test-configs/batch_demo.json
python -u scripts/run.py --configs test-configs/parallel_demo.json
```


### Configuration file (JSON)

Load configs via `--configs <path or glob>`. Example:

```json
{
  "model": "gpt-4o-mini",
  "opponent": "engine",
  "depth": 6,
  "movetime": null,
  "engine": "Stockfish",
  "llm_color": "white",
  "max_plies": 240,
  "max_illegal": 1,
  "pgn_tail": 20,
  "verbose_llm": false,
  "conversation_mode": false,
  "prompt": {
    "mode": "plaintext",
    "starting_context_enabled": true,
    "instruction_line": "Provide only your best legal move in SAN."
  }
}
```

Notes
- `model`: Target LLM model ID (e.g., `gpt-4o-mini`).
- `opponent`: `engine` (Stockfish) or `random`.
- `depth`: Stockfish search depth (used when `movetime` is null).
- `movetime`: Stockfish movetime in milliseconds; overrides `depth` when set.
- `engine`: Engine name; only `Stockfish` is supported (binary path via `STOCKFISH_PATH`).
- `llm_color`: `white` or `black` — which side the LLM plays.
- `max_plies`: Maximum total plies before truncation.
- `max_illegal`: Illegal LLM moves allowed before termination (when reached, game ends as a loss for the LLM).
- `pgn_tail`: Number of recent plies included when building a PGN tail (used by prompting and future FEN mode).
- `verbose_llm`: When true, prints raw LLM replies to the console.
- `conversation_mode`: Legacy chat-style prompting (bypasses the standard prompt builder).
- `prompt.mode`: Prompting variant — `plaintext` (current) or `fen` (future/scaffolded).
- `prompt.starting_context_enabled`: Include a brief first-move context when the LLM starts as White.
- `prompt.instruction_line`: Final instruction appended to prompts (default asks for best legal move in SAN).
- `games`: Number of games to run for this config.
- `mode`: `sequential` (per-game runner using Responses API) or `batch` (OpenAI Batches API).
- `games_per_batch`: Batch mode chunk size (optional; if omitted, provider/env defaults apply).

---

## Prompting modes

Plaintext
- Includes a move history list (or `(none)` if empty).
- If and only if the LLM is starting the game (White and no moves yet) and the starting context is enabled, the prompt adds: "Game start. You are White. Make the first move of the game."
- Ends with the instruction line (default requests SAN).

FEN (future)
- Will include `Position (FEN): ...` and optional recent PGN tail.
- Same instruction line behavior and optional first-move context.

---

## Per-turn conversation logging

- Always enabled. Each game writes:
  - Conversation snapshot: `conv_YYYYMMDD-HHMMSS_std_w.json` (or `_b.json` when LLM is Black)
  - Structured history for visualization: `hist_YYYYMMDD-HHMMSS_std_w.json`
  - Aggregated per-game metrics to `<out-dir>/results.jsonl`

---

## Batch/concurrent runs and outputs

Run multiple games from JSON configs with per-run output folders and structured histories.

Examples (Windows):
- python scripts\run.py --configs "test-configs\parallel_demo.json,test-configs\batch_demo.json" --mode batch --out-dir .\runs\smoke
- For large sweeps (100 games): copy a config and set "games": 100, then run the same command with --mode batch.

Behavior
- If `--out-dir` is provided, logs are written there; otherwise a timestamped directory under `runs/` is created.
- A JSONL of per-game summaries is written to `<out-dir>/results.jsonl` unless `--out-jsonl` overrides the path.

Structured history JSON
- Contains headers, result, termination reason, and an array of moves with:
  - ply, side, actor (LLM/OPP)
  - uci, san, legal
  - fen_before, fen_after
- This is designed to be consumed by visualization tools.

Batching implementation
- By default, prompts from active games are sent concurrently using the Responses API for low latency.
Modes
- mode: "sequential" | "batch"
  - sequential → direct /responses API (interactive)
  - batch → OpenAI Batches API (offline)

Batch chunking
- games_per_batch: integer; how many game turns to bundle per batch job each cycle. If omitted, provider/env defaults apply (LLMCHESS_ITEMS_PER_BATCH).

Examples
- Sequential single game: `--mode sequential`
- Batch with chunk size 5: `--mode batch --games-per-batch 5`

Environment variables
- STOCKFISH_PATH: path to the Stockfish binary. On macOS: `brew install stockfish` then `which stockfish`.
- OPENAI_BATCH_COMPLETION_WINDOW: default 24h
- LLMCHESS_ITEMS_PER_BATCH: chunk size when batching (default 200)
- LLMCHESS_TURN_MAX_WAIT_S: overall per-turn max wait when using sequential mode (default 1200)
- LLMCHESS_BATCH_POLL_S: batch status poll interval seconds (default 2.0)
- LLMCHESS_BATCH_TIMEOUT_S: per-batch-job polling timeout in batch mode (default 600)
- LLMCHESS_RESPONSES_TIMEOUT_S: per-response timeout seconds (default 300)
- LLMCHESS_RESPONSES_RETRIES: retries for Responses API (default 4)
- LLMCHESS_MAX_CONCURRENCY: max in-flight Responses API requests (default 8)
- LLMCHESS_USE_GUARD_AGENT: set to 0 to disable guard agent normalization

Notes
- Use `mode: "batch"` in config, or `--mode batch` to enable the Batches API.

Batch status
- Batch creation and progress are logged to the console during runs (status changes, request counts, timestamps, progress %, duration).
- For deeper inspection or downloads, use the OpenAI web UI.

Troubleshooting
- Ensure your chosen model in the JSON/CLI targets a Responses-capable model (e.g., gpt-4o-mini) and upgrade the SDK: pip install -U openai
- To disable the guard agent and rely on lightweight regex/validator fallback, set LLMCHESS_USE_GUARD_AGENT=0
