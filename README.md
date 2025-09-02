# TODO
Check if in batch mode when one game ends, others will continue until completion. ()
Orgainze project (play_one outside scripts dir) (). 

Add a cancel for batching. Since we often run tests and dont wait for batch results this may waste tokens.  

In batch demo why is  
```
"out_dir": "runs/batch_demo",
  "log_level": "INFO",
  "conversation_log": {
    "path": "runs/batch_demo" 
```
There 2 paths?

`python -u scripts/run_many.py --configs test/batch_demo.json`
`python -u scripts/run_many.py --configs test/parallel_demo.json`


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



# Save conversation snapshots every move (to a directory)
python play_one.py --model gpt-4o-mini --prompt-mode plaintext --conv-log ./log1 --conv-log-every-turn

# play_many.py documentation
```

## Notes
- The **agent** only validates/normalizes the move. All strategy testing is handled by the engine opponent and results.
- The code uses the OpenAI **Responses API** for free-form LLM replies and the **Agents SDK** for the validator tool.
- If your Agents SDK import path differs, adjust `agent_normalizer.py` imports accordingly (see comments).

---

## Config-driven runs (updated)
You can run experiments with just a config file. The config controls logging and outputs:

- out_dir: directory where conversation logs and results.jsonl are written
- log_level: INFO | DEBUG | WARNING | ERROR
  - At INFO/DEBUG, per-turn conversation snapshots are written.
  - At WARNING/ERROR, only final artifacts are written.
- mode: parallel | batch
- games_per_batch: optional chunk size for batch mode

Example:

```json
{
  "model": "gpt-5-nano",
  "engine": "Stockfish",
  "opponent": "random",
  "games": 2,
  "mode": "batch",
  "out_dir": "runs/g100",
  "log_level": "INFO"
}
```

Run it with:

```bash
python -u scripts/run_many.py --configs test/batch_2-5n.json
```


Core gameplay
- --model: Target LLM (required if not specified in the JSON config)
- --opponent: engine | random (default engine)
- --depth: Stockfish search depth (ignored if --movetime is set)
- --movetime: Stockfish movetime in ms (overrides depth)
- --engine: Engine name to use (Stockfish only for now). Binary path comes from env STOCKFISH_PATH.
- --llm-color: white | black (which side the LLM plays; default white)
- --max-plies: Maximum plies before truncation (default 240)
- --max-illegal: Terminate after this many illegal LLM moves (default 1)

Prompting
- --prompt-mode: plaintext | fen
  - plaintext: always show move history list; if and only if LLM is starting, add a first-move context line
  - fen: scaffolded for later; includes FEN + optional PGN tail
- --no-starting-context: Disable the first-move context hint in prompts
- --instruction-line: Override the final instruction line (default: "Provide only your best legal move in SAN.")
- --conversation: Legacy chat mode (bypasses the modular prompting builder)

Logging and outputs
- --verbose-llm: Log raw LLM replies
- --conv-log: Path to a JSON file or a directory for conversation snapshots
  - If a directory or path with no extension is given, a file like `conv_YYYYMMDD-HHMMSS_std_w.json` is created inside
- --conv-log-every-turn: Write/update the conversation JSON after every move
- --pgn-out: Write final PGN to this path
- --log-level: Python logging level (INFO, DEBUG, ...)

Precedence rules
- CLI option (if provided) overrides config file value.
- Config file overrides internal defaults.

---

## Configuration file (JSON)

Load a config file via `--config <path>`. Example:

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
  },
  "conversation_log": {
    "path": "./log1",        
    "every_turn": true
  }
}
```

Notes
- `prompt.mode` accepts `plaintext` now; `fen` is scaffolded for later experiments.
- `pgn_tail` is still used internally and will be used with FEN prompting to provide move tails.
- `conversation_log.path` can be a directory or a file. If directory, a timestamped JSON is created inside and updated.

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

- Enable with `--conv-log <path>` and `--conv-log-every-turn`.
- If `<path>` is a directory, a file is created inside and updated after every move and again at game end.
- In standard mode, the snapshots include the exact system + user prompt and the raw LLM reply per turn.
- In conversation mode, the live chat history is dumped.

---

## Batch/concurrent runs and outputs

Run multiple games from JSON configs with per-run output folders and structured histories.

Examples (Windows):
- python scripts\run_many.py --configs "test\single_default.json,test\batch_two_games.json" --mode batch --out-dir .\runs\smoke --log-level INFO
- For large sweeps (100 games): copy a config and set "games": 100, then run the same command with --batch.

Behavior
- If --out-dir is provided, a base folder is created and each config gets a subfolder: <out-dir>/<config-name-without-ext>/
- Each game writes:
  - Conversation snapshot: conv_YYYYMMDD-HHMMSS_std_w.json (or _b.json if LLM plays Black)
  - Structured history (for visualization): hist_YYYYMMDD-HHMMSS_std_w.json
- A JSONL of per-game summaries is written to <out-dir>/results.jsonl unless --out-jsonl overrides the path.

Structured history JSON
- Contains headers, result, termination reason, and an array of moves with:
  - ply, side, actor (LLM/OPP)
  - uci, san, legal
  - fen_before, fen_after
- This is designed to be consumed by visualization tools.

Batching implementation
- By default, prompts from active games are sent concurrently using the Responses API for low latency.
Modes
- mode: "parallel" | "batch"
  - parallel → direct /responses API (interactive)
  - batch → OpenAI Batches API (offline)

Batch chunking
- games_per_batch: integer; how many game turns to bundle per batch job each cycle. If omitted, provider/env defaults apply (LLMCHESS_ITEMS_PER_BATCH).

Examples
- Parallel single game: `--mode parallel`
- Batch with chunk size 5: `--mode batch --games-per-batch 5`

Environment variables
- STOCKFISH_PATH: path to the Stockfish binary. On macOS: `brew install stockfish` then `which stockfish`.
- OPENAI_BATCH_COMPLETION_WINDOW: default 24h
- LLMCHESS_ITEMS_PER_BATCH: chunk size when batching (default 200)
- LLMCHESS_TURN_MAX_WAIT_S: overall per-turn max wait when using parallel mode (default 1200)
- LLMCHESS_BATCH_POLL_S: batch status poll interval seconds (default 2.0)
- LLMCHESS_BATCH_TIMEOUT_S: per-batch-job polling timeout in batch mode (default 600)
- LLMCHESS_RESPONSES_TIMEOUT_S: per-response timeout seconds (default 300)
- LLMCHESS_RESPONSES_RETRIES: retries for parallel responses (default 4)
- LLMCHESS_MAX_CONCURRENCY: max in-flight parallel responses (default 8)
- LLMCHESS_USE_GUARD_AGENT: set to 0 to disable guard agent normalization

Notes
- Use `mode: "batch"` in config, or `--mode batch` to enable the Batches API.

Batch status
- Batch creation and progress are logged to the console during runs (status changes, request counts, timestamps, progress %, duration).
- For deeper inspection or downloads, use the OpenAI web UI.

Troubleshooting
- Ensure your chosen model in the JSON/CLI targets a Responses-capable model (e.g., gpt-4o-mini) and upgrade the SDK: pip install -U openai
- To disable the guard agent and rely on lightweight regex/validator fallback, set LLMCHESS_USE_GUARD_AGENT=0
