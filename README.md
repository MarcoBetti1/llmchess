# TODO
Check max illegal var if it works (Y)  
Check prompting methods and clean up pipeline for it ()  
Check if in batch mode when one game ends, others will continue until completion. (Y)  
Fix batch prompting: i think its logic works in batches but it uses individual api requests. (N)  

`python -u scripts/run_many.py --configs test/batch_2-5n.json --batch --out-dir runs/g100 --log-level INFO`


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
export OPENAI_MODEL=
export STOCKFISH_PATH=



# Save conversation snapshots every move (to a directory)
python play_one.py --prompt-mode plaintext --conv-log ./log1 --conv-log-every-turn

# play_many.py documentation
```

## Notes
- The **agent** only validates/normalizes the move. All strategy testing is handled by the engine opponent and results.
- The code uses the OpenAI **Responses API** for free-form LLM replies and the **Agents SDK** for the validator tool.
- If your Agents SDK import path differs, adjust `agent_normalizer.py` imports accordingly (see comments).

---

## Command-line arguments (clean ts up)

Core gameplay
- --model: Target LLM (default from OPENAI_MODEL env or gpt-5)
- --opponent: engine | random (default engine)
- --depth: Stockfish search depth (ignored if --movetime is set)
- --movetime: Stockfish movetime in ms (overrides depth)
- --engine-path: Path to Stockfish binary (overrides STOCKFISH_PATH)
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
  "model": "gpt-5",
  "opponent": "engine",
  "depth": 6,
  "movetime": null,
  "engine_path": null,
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
- python scripts\run_many.py --configs "test\single_default.json,test\batch_two_games.json" --batch --out-dir .\runs\smoke --log-level INFO
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
- To force the OpenAI Batches API (with completion_window, suitable for offline jobs), set:
  - LLMCHESS_USE_OPENAI_BATCH=1
  - Optional: OPENAI_BATCH_COMPLETION_WINDOW=24h
- For interactive chess loops, prefer the default concurrent mode instead of true Batches.

Troubleshooting
- Ensure OPENAI_MODEL targets a Responses-capable model (e.g., gpt-4o-mini) and upgrade the SDK: pip install -U openai
- To disable the guard agent and rely on lightweight regex/validator fallback, set LLMCHESS_USE_GUARD_AGENT=0
