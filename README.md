# LLM Chess

LLM Chess is a benchmarking harness that asks large language models to play legal games of chess. It balances structure and flexibility: `python-chess` enforces the rules, while lightweight agents and prompts translate every position into text that models can understand. The goal is not to build a chess grandmaster, but to measure whether different prompting strategies, model families, and transports can keep games legal and coherent over many plies.

## How a turn works (high-level flow)

1. **State capture** – `GameRunner` (see `src/llmchess_simple/game.py`) queries `python-chess` for the current FEN, recent SAN history, and an annotated natural-language history.
2. **Prompt assembly** – `PromptConfig` chooses the textual format (plaintext, FEN, or hybrid). The resulting chat messages are sent through `llm_client` using the OpenAI Responses API.
3. **Guarded parsing** – The MoveGuard agent (`docs/agent-normalizer.md`) extracts a candidate move in UCI. `move_validator.normalize_move` double-checks it against the board and salvages legal SAN if needed.
4. **Referee decision** – `Referee` applies the move, tracks illegal attempts, and keeps PGN/metrics up to date. Illegal responses increment a counter and can terminate the game once the threshold is hit.
5. **Logging** – Every turn records the raw LLM reply, the normalized move, and legality metadata. `conv_*.json` and `hist_*.json` snapshots are regenerated immediately for downstream inspection.

An overview of the text interface (prompts, notation, normalization) lives in [`docs/chess-text-representation.md`](docs/chess-text-representation.md).

## Core components

- **`GameRunner`** orchestrates single games and collects metrics such as legal rate and latency.
- **`EngineOpponent` / `RandomOpponent`** supply the adversary, with Stockfish controlled via depth or movetime limits.
- **`BatchOrchestrator`** multiplexes many games at once and can switch between live Responses API calls and the OpenAI Batches API.
- **`PromptConfig` & builders** (plaintext, FEN, FEN+plaintext) provide the textual scaffolding for each request.
- **`MoveGuard` agent** cleans up raw LLM outputs; the implementation details are documented in [`docs/agent-normalizer.md`](docs/agent-normalizer.md).
- **`move_validator`** bridges between free-form replies and `python-chess`, ensuring the final move is legal before applying it.

## Configuration surface

Runtime configuration values (API keys, batch timeouts, guard toggles, etc.) load from `settings.yml`, environment variables, or defaults in `config.py`. The precedence rules and full catalogue are covered in [`docs/configuration.md`](docs/configuration.md).

## Experiment configs (JSON)

All experiments are described with JSON files passed to `scripts/run.py`. Each file can control the model, color, opponent, prompt mode, logging verbosity, and more. The complete schema, defaults, and helpful tips are maintained in [`docs/test-configs.md`](docs/test-configs.md).

Typical commands:

```bash
# Run a single config file
python -u scripts/run.py --configs tests/demo-tests/config.json

# Sweep multiple configs (files, directories, or globs)
python -u scripts/run_tests.py --configs "tests/*.json"

# Preview without executing
python -u scripts/run_tests.py --configs "tests/*.json" --dry-run
```

Every config writes its outputs under the provided `out_dir`:

- `results.jsonl` appends per-game summaries (legal rate, latency, termination reason, PGN).
- `conv_*.json` captures the exact prompt/response conversation for the LLM.
- `hist_*.json` stores the structured move history with UCI/SAN, legality flags, and FEN snapshots.

## Prompting modes & notation

You can switch between natural-language histories, FEN-only prompts, or hybrids by editing the `prompt` block in your config. The effect of each mode, plus guidance on requesting SAN vs UCI outputs, is detailed in [`docs/chess-text-representation.md`](docs/chess-text-representation.md). Because legality is ultimately enforced by `python-chess`, you can experiment freely with different textual representations.

### Prompt systems

Set the optional `prompt_system` field in your JSON config to control how many LLM exchanges happen per turn. The default value `"standard"` keeps the existing single-message flow. The new `"legal-move-system-simple"` system introduces a two-step interaction: the model proposes a move, a follow-up question asks whether that move is legal, and only confirmed moves proceed (with up to three retries before falling back to standard validation). The resulting conversation logs capture every stage so you can audit the reasoning.

## Batch orchestration & transports

`BatchOrchestrator` keeps many games in lockstep. Set `mode` to `sequential` (default) to use parallel `/responses` calls with retry/backoff controls, or `mode` to `batch` to upload JSONL payloads to the OpenAI Batches API. Chunking and timeout knobs are controlled via configuration variables (`LLMCHESS_ITEMS_PER_BATCH`, `LLMCHESS_BATCH_TIMEOUT_S`, etc.) described in [`docs/configuration.md`](docs/configuration.md).

During runs, progress and status updates are logged to the console. Each `results.jsonl` can be analyzed post-hoc with tools like `scripts/summarize_results.py` (WIP) or the browser-based viewer described below.

## Web viewer (inspect/web_viewer.py)

Launch a local Flask app for browsing runs:

```bash
python -u inspect/web_viewer.py --port 8000
```

Features include:

- **Games tab** – replay logged games with a board timeline and move metadata.
- **Live Runs tab** – start new sweeps, tail stdout, watch progress bars, and cancel runs via SSE-backed streams.
- **Analysis tab** – slice and aggregate results across all `runs/` directories by model, config, color, or opponent.

The app uses a lightweight in-memory run manager (`inspect/run_manager.py`) that launches `scripts/run.py`, tails logs, and polls `results.jsonl` files to estimate progress. Because the manager is ephemeral, restarting the server clears active-run state.

## Documentation map

- [`docs/configuration.md`](docs/configuration.md) – environment and settings reference.
- [`docs/test-configs.md`](docs/test-configs.md) – JSON config schema for experiments.
- [`docs/chess-text-representation.md`](docs/chess-text-representation.md) – how prompts and replies encode the game.
- [`docs/agent-normalizer.md`](docs/agent-normalizer.md) – MoveGuard agent prompt and behavior.


## Roadmap / open questions

- Support a single config that automatically alternates colors (rather than duplicating entries).
- Streamline config files by moving rarely touched toggles into shared defaults.
- Slim down or relocate the legacy logging hooks that are currently unused.
- Add first-class cancellation for batch jobs to avoid wasting tokens when runs are aborted.
- Explore a “play one” interactive mode for human-vs-LLM experiments.
- On illegal move (before max_illegal), append that move and the fact that it was illegal to next prompt context
- Test for: Fake LLM responses to test guard agent on truth set 
- Pick up a test after pause or failure based off game state and conv hist.