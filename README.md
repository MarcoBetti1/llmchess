# LLM Chess

LLM Chess is a benchmarking harness that asks large language models to play legal games of chess. It balances structure and flexibility: `python-chess` enforces the rules, while lightweight agents and prompts translate every position into text that models can understand. The goal is not to build a chess grandmaster, but to measure whether different prompting strategies, model families, and transports can keep games legal and coherent over many plies.

## How a turn works (high-level flow)

1. **State capture** – `GameRunner` (see `src/llmchess_simple/game.py`) queries `python-chess` for the current FEN, recent SAN history, and an annotated natural-language history.
2. **Prompt assembly** – `PromptConfig` chooses the textual format (plaintext, FEN, or hybrid). The resulting chat messages are sent through `llm_client` using a provider-agnostic chat/completions call.
3. **Guarded parsing** – Raw replies are parsed into a candidate move (simple regex/first-token). `move_validator.normalize_move` double-checks it against the board and salvages legal SAN if needed.
4. **Referee decision** – `Referee` applies the move, tracks illegal attempts, and keeps PGN/metrics up to date. Any illegal response immediately ends the game with a loss for the side that produced it.
5. **Logging** – Every turn records the raw LLM reply, the normalized move, and legality metadata. `conv_*.json` and `hist_*.json` snapshots are regenerated immediately for downstream inspection.

An overview of the text interface (prompts, notation, normalization) lives in [`docs/chess-text-representation.md`](docs/chess-text-representation.md).

## Core components

- **`GameRunner`** orchestrates single games and collects metrics such as legal rate and latency.
- **`LLMOpponent` / `UserOpponent`** supply the adversary for LLM-vs-LLM or human-vs-LLM games.
- **`PromptConfig` & builders** (plaintext, FEN, FEN+plaintext) provide the textual scaffolding for each request.
- **`move_validator`** bridges between free-form replies and `python-chess`, ensuring the final move is legal before applying it.

## Configuration surface

Runtime configuration values (API keys, base URL, provider selection, etc.) load from `settings.yml`, environment variables, or defaults in `config.py`. The LLM layer talks to OpenAI-compatible endpoints (`/models`, `/chat/completions`, `/embeddings`), so pointing at Vercel AI Gateway or another SDK simply means updating `LLMCHESS_LLM_BASE_URL` and `LLMCHESS_LLM_API_KEY`. The precedence rules and full catalogue are covered in [`docs/configuration.md`](docs/configuration.md).

## Minimal usage

There is no CLI runner in this trimmed version. Create a game in Python:

```python
from src.llmchess_simple.game import GameRunner, GameConfig
from src.llmchess_simple.llm_opponent import LLMOpponent

opp = LLMOpponent(model="openai/gpt-4o")  # or "anthropic/claude-..." via gateway
runner = GameRunner(model="openai/gpt-4o", opponent=opp, cfg=GameConfig())
result = runner.play()
print("Result:", result, runner.summary())
```

To play against a human, swap `LLMOpponent` for `UserOpponent()`.

## Prompting modes & notation

You can switch between natural-language histories, FEN-only prompts, or hybrids by editing the `prompt_cfg` in `GameConfig` (and optionally supply `instructions_template` to inject custom guidance). The effect of each mode is detailed in [`docs/chess-text-representation.md`](docs/chess-text-representation.md). Because legality is enforced by `python-chess`, you can experiment freely with different textual representations.

## Documentation map

- [`docs/configuration.md`](docs/configuration.md) – environment and settings reference.
- [`docs/chess-text-representation.md`](docs/chess-text-representation.md) – how prompts and replies encode the game.
