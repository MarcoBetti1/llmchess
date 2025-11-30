# LLM Chess (Gateway-ready, head-to-head)

A minimal chess harness for pitting language models against each other (or a human) one move at a time. Everything runs through a single OpenAI-compatible `POST /chat/completions` endpoint, making it easy to point at Vercel AI Gateway or any OpenAI-compatible backend by changing the base URL and API key.

## Goals

- Competitive model evaluation: run LLM vs LLM games with per-move legality enforcement.
- Simple, provider-agnostic transport: one chat request per turn; no batching.
- Gateway-ready: configure `LLMCHESS_LLM_BASE_URL` and `LLMCHESS_LLM_API_KEY` to use Vercel AI Gateway.
- UI-ready logs: structured history and conversation snapshots for downstream visualization.

## How a turn works

1. **State capture** – `GameRunner` reads the current FEN, SAN history, and a natural-language history from `python-chess`.
2. **Prompt assembly** – `PromptConfig` builds chat messages (plaintext, FEN, or hybrid). Messages are sent via `llm_client` to the configured `/chat/completions` endpoint.
3. **Parsing and validation** – A regex/first-token extractor pulls a move candidate; `move_validator.normalize_move` checks legality and salvages SAN/UCI if possible.
4. **Referee decision** – `Referee` applies moves, tracks termination, and ends the game immediately on any illegal move.
5. **Logging** – Each ply records raw LLM text, normalized move, legality, and metadata. Structured history and conversation JSON are emitted for downstream UI/analysis.

## Core components

- `src/llmchess_simple/game.py` – `GameRunner` orchestrates a single game, collects metrics, and exports logs.
- `src/llmchess_simple/llm_opponent.py` – `LLMOpponent` for head-to-head model play.
- `src/llmchess_simple/user_opponent.py` – `UserOpponent` for interactive human moves.
- `src/llmchess_simple/prompting.py` – `PromptConfig` and builders for plaintext/FEN/hybrid prompts.
- `src/llmchess_simple/llm_client.py` – Thin OpenAI-compatible client; configurable `LLMCHESS_LLM_BASE_URL` and `LLMCHESS_LLM_API_KEY`.
- `src/llmchess_simple/move_validator.py` – Bridges free-form replies to legal UCI/SAN moves.
- `src/llmchess_simple/referee.py` – Applies moves, maintains PGN, and handles termination.

## Configuration

Set environment variables (or `settings.yml`) for the transport:

```bash
export LLMCHESS_LLM_BASE_URL=https://ai-gateway.vercel.sh/v1
export LLMCHESS_LLM_API_KEY=your_gateway_or_openai_key
export LLMCHESS_MAX_CONCURRENCY=4
export LLMCHESS_RESPONSES_TIMEOUT_S=120
```

Model strings can be any OpenAI-compatible IDs (for example, `openai/gpt-4o`, `anthropic/claude-3-sonnet` when routed through Gateway).

Generated artifacts (if `conversation_log_path` is set in `GameConfig`):

- `conv_*.json` – chat messages and raw replies (with actor/model tags).
- `hist_*.json` – structured move history with UCI/SAN, legality, FEN snapshots, and participant metadata.

## Running an experiment (single game example)

```python
from src.llmchess_simple.game import GameRunner, GameConfig
from src.llmchess_simple.llm_opponent import LLMOpponent

white = LLMOpponent(model="openai/gpt-4o")
black = LLMOpponent(model="openai/gpt-4o-mini")

cfg = GameConfig(conversation_log_path="runs/demo")  # optional logging
runner = GameRunner(model=white.model, opponent=black, cfg=cfg)
result = runner.play()
print(result)
print(runner.summary())
```

Set `LLMCHESS_LLM_BASE_URL` and `LLMCHESS_LLM_API_KEY` beforehand to point at your OpenAI-compatible endpoint.

## Backend API (Flask)

Run a minimal API that the Next.js UI consumes and that executes real games:

```bash
python server.py  # listens on http://localhost:8000
```

Logs are written under `runs/<experiment_id>/<game_id>/` by default (configurable via `EXPERIMENT_LOG_DIR`). State persists to `experiments_state.json`.

Supported endpoints:

- `POST /api/experiments`

  Payload fields (only supported ones):
  ```json
  {
    "name": "gpt4o_vs_gpt4omini",
    "players": { "a": { "model": "openai/gpt-4o" }, "b": { "model": "openai/gpt-4o-mini" } },
    "games": { "total": 2, "a_as_white": 1, "b_as_white": 1 },
    "prompt": { "mode": "fen+plaintext" }
  }
  ```
  Returns: `{ "experiment_id": "exp_..." }`

- `GET /api/experiments` – summaries with status, wins, and completed counts.
- `GET /api/experiments/{id}/results` – aggregated wins/illegal-move averages and per-game rows.
- `GET /api/games/{game_id}/conversation` – returns the saved conversation log if present.
- `GET /api/games/{game_id}/history` – returns the saved structured history if present.
- `GET /api/games/live` – placeholder (empty array).

Note: GameRunner ends a game on the first illegal move; there is no configurable illegal-move limit in the UI.

## Prompting modes and customization

`PromptConfig` supports:

- `mode`: `"plaintext"`, `"fen"`, or `"fen+plaintext"`.
- `starting_context_enabled`: include a first-move hint when the LLM starts as White.
- `instruction_line`: final instruction (for example, ask for SAN or UCI).
- `extra_instructions`: optional freeform template inserted before `instruction_line`.

Pass a customized `PromptConfig` into `GameConfig(prompt_cfg=...)` or set `opponent_prompt_cfg` for the opponent side.

## Notes

- Any illegal move immediately forfeits the game for the side that produced it.
- One chat request per turn.
- Logs and outputs are structured to plug into a UI for replay/analysis.

## Frontend UI (Next.js + Tailwind)

A Next.js UI lives in `ui/` with three primary surfaces:

- `/experiments` (Game master) – Start experiments, monitor progress, and watch live board replays from `/api/experiments` and `/api/experiments/{id}/results` plus `/api/games/{id}/history`.
- `/play` – Human vs LLM board that enforces legality locally (chess.js).

Run it locally (Node 18+):

```bash
cd ui
npm install
npm run dev
```

Configure the backend host via `ui/.env.local`:

```
NEXT_PUBLIC_API_BASE=http://localhost:8000
NEXT_PUBLIC_USE_MOCKS=false   # set true to fall back to mock data
```

The UI falls back to mock data when endpoints are unavailable so you can explore the layout before wiring the backend.
