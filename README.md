# TODO
- Check if in batch mode when one game ends, others will continue.  
- Add a cancel for batching. Since we often run tests and dont wait for batch results this may waste tokens.  

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
Requirements
- `pip install -r requirements.txt`
Set env vars (or copy .env.example to .env and edit)

```bash
export OPENAI_API_KEY=
export STOCKFISH_PATH=
```
- `python play_one.py --model gpt-4o-mini --prompt-mode plaintext`


## Notes
- The **agent** only validates/normalizes the move. All strategy testing is handled by the engine opponent and results.
- The code uses the OpenAI **Responses API** for free-form LLM replies and the **Agents SDK** for the validator tool.
- If your Agents SDK import path differs, adjust `agent_normalizer.py` imports accordingly (see comments).



## Config-driven runs (simplified)
You can run experiments with just a config file. Outputs are always written:

See the Notes in the configuration section for all supported fields.


Run it with:

```bash
python -u scripts/run.py --configs test-configs/config.json
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
  - batch → OpenAI Batches API (offline)


Batch status
- Batch creation and progress are logged to the console during runs (status changes, request counts, timestamps, progress %, duration).
- For deeper inspection or downloads, use the OpenAI web UI.

Troubleshooting
- Ensure your chosen model in the JSON/CLI targets a Responses-capable model (e.g., gpt-4o-mini) and upgrade the SDK: pip install -U openai