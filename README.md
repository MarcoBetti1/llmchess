# LLM Chess (Gateway-ready, head-to-head)

A minimal chess harness for pitting language models against each other (or a human) one move at a time. Everything runs through a single OpenAI-compatible `POST /chat/completions` endpoint, making it easy to point at Vercel AI Gateway or any OpenAI-compatible backend by changing the base URL and API key.

## Goals

- Competitive model evaluation: run LLM vs LLM games with per-move legality enforcement.
- Simple, provider-agnostic transport: one chat request per turn; no batching.
- Gateway-ready: configure `LLMCHESS_LLM_BASE_URL` and `LLMCHESS_LLM_API_KEY` to use Vercel AI Gateway.
- UI-ready logs: structured history and conversation snapshots for downstream visualization.

## How a turn works

1. **State capture** – `GameRunner` reads the current FEN, SAN history, and a natural-language history from `python-chess`.
2. **Prompt assembly** – `PromptConfig` builds chat messages (plaintext, FEN, or hybrid). The messages are sent via `llm_client` to the configured `/chat/completions` endpoint.
3. **Parsing & validation** – A simple regex/first-token extractor pulls a move candidate; `move_validator.normalize_move` checks legality against the board and salvages SAN/UCI if possible.
4. **Referee decision** – `Referee` applies moves, tracks termination, and ends the game immediately on any illegal move.
5. **Logging** – Each ply records raw LLM text, normalized move, legality, and metadata. Structured history and conversation JSON are emitted for downstream UI/analysis.

## Core components

- `src/llmchess_simple/game.py` – `GameRunner` orchestrates a single game, collects metrics, and exports logs.
- `src/llmchess_simple/llm_opponent.py` – `LLMOpponent` for head-to-head model play.
- `src/llmchess_simple/user_opponent.py` – `UserOpponent` for interactive human moves (validated before applying).
- `src/llmchess_simple/prompting.py` – `PromptConfig` and builders for plaintext/FEN/hybrid prompts with optional instruction templates.
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

Model strings can be any OpenAI-compatible IDs (e.g., `openai/gpt-4o`, `anthropic/claude-3-sonnet` when routed through Gateway).



Generated artifacts (if `conversation_log_path` is set in `GameConfig`):

- `conv_*.json` – chat messages and raw replies (with actor/model tags).
- `hist_*.json` – structured move history with UCI/SAN, legality, FEN snapshots, and participant metadata.

## Running an experiment 
Because the project is library-only, you run experiments with a tiny Python script: 
1) Set env for your endpoint/key (e.g., Vercel AI Gateway):
```bash
export LLMCHESS_LLM_BASE_URL=https://ai-gateway.vercel.sh/v1
export LLMCHESS_LLM_API_KEY=$AI_GATEWAY_API_KEY
```
2) Create run_game.py:
```python
### Imports
from src.llmchess_simple.game import GameRunner, GameConfig
from src.llmchess_simple.llm_opponent import LLMOpponent
from src.llmchess_simple.user_opponent import UserOpponent

### pick two models; can be the same for mirror matches
white = LLMOpponent(model="openai/gpt-4o")
black = LLMOpponent(model="openai/gpt-4o-mini")

cfg = GameConfig(conversation_log_path="runs/demo")  # optional logging
runner = GameRunner(model=white.model, opponent=black, cfg=cfg)
result = runner.play()
print(result)
print(runner.summary())

# LLM vs human (interactive)
human_opp = UserOpponent()
runner = GameRunner(model="openai/gpt-4o", opponent=human_opp, cfg=GameConfig())
runner.play()

# LLM vs LLM
opp = LLMOpponent(model="openai/gpt-4o", provider_options={"gateway": {"order": ["openai"]}})
runner = GameRunner(model="openai/gpt-4o", opponent=opp, cfg=GameConfig())
result = runner.play()
print("Result:", result)
print("Metrics:", runner.summary())
```
3) Run it:
```bash
python run_game.py
```
Outputs: console logs plus optional runs/demo/conv_*.json and runs/demo/hist_*.json if you set conversation_log_path. Adjust PromptConfig via GameConfig(prompt_cfg=...) for different modes/instructions.

## Prompting modes & customization

`PromptConfig` supports:

- `mode`: `"plaintext"`, `"fen"`, or `"fen+plaintext"`.
- `starting_context_enabled`: include a first-move hint when the LLM starts as White.
- `instruction_line`: final instruction (e.g., ask for SAN or UCI).
- `extra_instructions`: optional freeform template inserted before `instruction_line`.

Pass a customized `PromptConfig` into `GameConfig(prompt_cfg=...)` or set `opponent_prompt_cfg` for the opponent side.

## Notes

- Any illegal move immediately forfeits the game for the side that produced it.
- One chat request per turn
- Logs and outputs are structured to plug into a UI for replay/analysis.

## Frontend UI (Next.js + Tailwind)

A Next.js UI lives in `ui/` with three primary surfaces:

- `/live` – Live LLM vs LLM games with boards, last-move highlights, and a conversation dialog fed by `/api/games/live` and `/api/games/{id}/conversation`.
- `/experiments` – Start experiments and browse progress snapshots from `/api/experiments` and `/api/experiments/{id}/results`.
- `/play` – Human vs LLM board that enforces legality locally (chess.js) and is wired to the `POST /api/human-games` flow.

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
