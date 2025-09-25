Built for chatgpt, built by chatgpt.  
Trying to bring out one of my llm benchmark ideas. If this line exists then its extremely unfinished.  
### TODO
- **Batch optimization**: See about combining different model-consistent tests where sum (# total games) < Max batch size. (low priority)
- **Config simplifcation**: make config simpler and [more intuitive](#test-params)
- **Log system**: First gotta figure out whats going on here.  
- **Batch cancel**: Since we often run tests and dont wait for batch results this may waste tokens.  (later if running in app, manual for now)
- **Play one**: For fun.  
- **Salvaged Move**: Clairfy when the agent helps vs when the agents response is equal to raw response.
- **Results**: Clarify current system. Hist file is a bit redundant, conv is fine for now.  
- **FEN prompting**: To see if model does better when we attach or substitue FEN game state. Currently "fen+plaintext" as prompting argument. Test this feature.  

# LLM Chess
A lightweight benchmark to test LLMs on chess with light agent system:  

## Agent Normalizer
Agents main purpose is to:

1) ensures the model's reply actually contains a chess move, and
2) return it in a strict **UCI** format (e.g., `e2e4`, `e7e8q`).


To take some weight off the llm I decided to use an agent for verifying/correcting the llms response into something that we can use in a chess game.
Maybe the llms response is "My best move is fxg3", the agent will then return just "fxg3".

- The **agent** only validates/normalizes the move. All strategy testing is handled by the engine opponent and results.
- The code uses the OpenAI **Responses API** for free-form LLM replies and the **Agents SDK** for the validator tool.

## Game Logic
- We prompt a target model and ask for the *best move*.
- We pass the model's free-form reply to a tiny **Agent (Agents SDK)** that calls a Python tool to validate the move
  against the FEN and normalize it to UCI. If invalid, the agent is asked to try again.
- We apply the move and play

### Prompt Flow
raw -> candidate via agent_normalizer -> validate against FEN -> apply if legal; else salvage from raw -> apply -> record/log.  
Conversation logs show raw; structured history shows what actually got played.


## Quickstart (todo)
Make python venv `python -m venv venv`.  
Activate venv `source bin/scripts/activate` on mac.  
Install requirements `pip install -r requirements.txt`.    
Set OPENAI API key in environment as `OPENAI_API_KEY`.   
Make `settings.yaml` file for changing settings and setting engine path.  
Download stockfish and set `STOCKFISH_PATH` settings variable



## Config-driven runs
You can run experiments with just a config file. Outputs are always written:

See [writing tests](#writing-tests) section for all supported fields.

Run it with:

```bash
python -u scripts/run.py --configs tests/demo-tests/demo.json


```

#### Run multiple configs (test automation)

Use the simple wrapper to run all configs in a folder or a custom list. It calls `scripts/run.py` for each file and summarizes results.

```bash
# Run all demo configs
python -u scripts/run_tests.py --configs "tests/*.json"

# Mix files and folders (comma-separated)
python -u scripts/run_tests.py --configs "tests/demo-tests/batch_demo.json,tests/demo-tests/sequential_demo.json"

# Stop on first failure
python -u scripts/run_tests.py --configs "test-folder/*.json" --stop-on-error

# Dry-run to preview commands
python -u scripts/run_tests.py --configs "test-folder/*.json" --dry-run
```

### writing-tests

We load tests in the form of json files via `--configs <path or glob>`. Example:

```json
{
  "model": "gpt-4o",
  "opponent": "random",
  "depth": 6,
  "movetime": null,
  "engine": "Stockfish",
  "llm_color": "black",
  "max_plies": 240,
  "max_illegal": 2,
  "pgn_tail": 20,
  "verbose_llm": false,
  "log_level": "INFO",
  "out_dir": "runs/prelim/4o-black",
  "prompt": {
    "mode": "plaintext",
    "starting_context_enabled": true,
    "instruction_line": "Provide only your best legal move in SAN."
  },
  "games": 10,
  "mode": "batch"
}
```

##### test-params
- `model`: Target LLM model ID (e.g., `gpt-4o-mini`).
- `opponent`: `engine` (Stockfish) or `random`.
- `depth`: Stockfish search depth (used when `movetime` is null).
- `movetime`: Stockfish movetime in milliseconds; overrides `depth` when set.
- `engine`: Engine name; only `Stockfish` is supported (binary path via `STOCKFISH_PATH`).
- `llm_color`: `white`, `black` or `both` — which side the LLM plays. Both runs the test twice one for each side.
- `max_plies`: Maximum total plies before truncation.
- `max_illegal`: Illegal LLM moves allowed before termination (when reached, game ends as a loss for the LLM).
- `pgn_tail`: Number of recent plies included when building a PGN tail (used by prompting and future FEN mode).
- `verbose_llm`: When true, prints raw LLM replies to the console. This is pointless and should remove.
- `log_level`: Python logging level for the run (e.g., `INFO`, `DEBUG`).
- `prompt.mode`: Prompting variant — `plaintext` (current) or `fen` (future/scaffolded).
- `prompt.starting_context_enabled`: Include a brief first-move context when the LLM starts as White.
- `prompt.instruction_line`: Final instruction appended to prompts (default asks for best legal move in SAN).
- `games`: Number of games to run for this config.
- `mode`: `sequential` (per-game runner using Responses API) or `batch` (OpenAI Batches API).

1. Each config controls its own `mode` and `log_level`; (Do we need log level here?)
2. Each config still controls its own `out_dir`; outputs are written there. (Better way to do this?)
3. Uses your current Python interpreter; override with `--python /path/to/python`. (Useful?)

---

## Configure Settings

Primary configuration is read from `prof.yml` at the repo root. All keys can and should be provided as environment variables; when both are present, YAML values take precedence.

Keys
- STOCKFISH_PATH: Full path to Stockfish binary. On Windows, quote or escape backslashes.
- OPENAI_BATCH_COMPLETION_WINDOW: Batch completion window (default: `24h`).
- LLMCHESS_ITEMS_PER_BATCH: Chunk size for Batches API when `mode` is `batch`.
- LLMCHESS_MAX_CONCURRENCY: Parallel /responses concurrency (default: 8).
- LLMCHESS_RESPONSES_TIMEOUT_S, LLMCHESS_RESPONSES_RETRIES, LLMCHESS_TURN_MAX_WAIT_S, LLMCHESS_BATCH_POLL_S, LLMCHESS_BATCH_TIMEOUT_S: Advanced tuning knobs.
- LLMCHESS_USE_GUARD_AGENT: 1 to enable the guard agent (default enabled), 0 to disable.

Environment usage (optional)
- You may still set any of the above as environment variables. This is convenient for CI or one-off runs.
- Examples (Windows PowerShell): `$env:LLMCHESS_ITEMS_PER_BATCH=50`
- Examples (Windows CMD): `set LLMCHESS_ITEMS_PER_BATCH=50`

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

Run multiple games from JSON files with per-run output folders and structured histories.

Structured history JSON
- Contains headers, result, termination reason, and an array of moves with:
  - ply, side, actor (LLM/OPP)
  - uci, san, legal
  - fen_before, fen_after
- This is designed to be consumed by visualization tools.

Batching implementation
- Use `mode: "batch"` in config to enable the Batches API.
- By default, prompts from active games are sent concurrently using the Responses API.
Modes  
- mode: "sequential" | "batch"
  - sequential → direct /responses API (interactive)
  - batch → OpenAI Batches API (offline). Chunking is controlled by `LLMCHESS_ITEMS_PER_BATCH`.


Batch status
- Batch creation and progress are logged to the console during runs (status changes, request counts, timestamps, progress %, duration).
- For deeper inspection or downloads, use the OpenAI web UI.

Troubleshooting
- Ensure your chosen model in the JSON/CLI targets a Responses-capable model (e.g., gpt-4o-mini) and upgrade the SDK: pip install -U openai

## Results
**Work in progress**:
`python -u scripts/summarize_results.py --root runs/prelim --sort-by avg_legal_rate`
Should give stats on a bunch of tests in the provided folder.

## Viewer
**Work in progress**:
First iteration of web app to view games is in inspect folder. Next, allow for visualizing multiple games at once to verify that each game is different, win conditions are met successfully.