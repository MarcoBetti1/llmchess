# Configuration Reference

This project loads configuration from code in `src/llmchess_simple/config.py`. The loader favors a YAML file named `settings.yml` in the repository root, falls back to environment variables, and finally uses sensible defaults baked into the code. The resulting values are exposed through the frozen dataclass `Settings`, available as `SETTINGS` across the codebase.

## Load order and precedence

1. **`settings.yml`** – if present in the repo root (sibling to `README.md`). Values here override everything else.
2. **Environment variables** – read from the OS _after_ `dotenv.load_dotenv()` runs, so a local `.env` file is honoured.
3. **Code defaults** – the constants defined inside `config.py` are used when no other source provides a value.

> Tip: Boolean flags use a permissive parser. Strings like `"0"`, `"false"`, `"no"`, `"off"`, and `"none"` map to `False`; any other non-empty string maps to `True`.

To access configuration in Python code:

```python
from src.llmchess_simple.config import SETTINGS

print(SETTINGS.openai_api_key)
```

## Settings catalogue

| Key | Default | Type | Used in | Purpose |
| --- | --- | --- | --- | --- |
| `OPENAI_API_KEY` | `""` | string | `providers/openai_provider.py` | Authentication token passed to `openai.OpenAI`. Without it, every OpenAI call fails immediately. Required for any LLM interaction. |
| `STOCKFISH_PATH` | `"stockfish"` | string | `engine_opponent.py` | Absolute or PATH-resolvable location of the Stockfish binary. Controls how the engine opponent process is spawned. |
| `OPENAI_BATCH_COMPLETION_WINDOW` | `"24h"` | string | `providers/openai_provider.py` | Requested completion window when creating Batches API jobs (`client.batches.create`). Shorten to accelerate results, lengthen if queues are busy. |
| `LLMCHESS_ITEMS_PER_BATCH` | `200` | int | `providers/openai_provider.py` | Chunk size when splitting large request sets across multiple Batches API uploads. Set to `0` or negative to submit everything in one batch. |
| `LLMCHESS_TURN_MAX_WAIT_S` | `1200.0` | float seconds | `providers/openai_provider.py` | Upper bound the interactive transport will wait for responses during a single turn (`submit_responses_blocking_all`). Prevents games from stalling indefinitely. |
| `LLMCHESS_BATCH_POLL_S` | `2.0` | float seconds | `providers/openai_provider.py` | Poll interval while waiting for a batch job to finish. Smaller values yield faster updates at the cost of API calls. |
| `LLMCHESS_BATCH_TIMEOUT_S` | `600.0` | float seconds | `providers/openai_provider.py` | Maximum wall-clock time to wait for a batch job before cancelling it and returning no results. Increase for very large batches. |
| `LLMCHESS_RESPONSES_TIMEOUT_S` | `300.0` | float seconds | `providers/openai_provider.py` | Per-request timeout used by the OpenAI Responses API when playing interactively. Raising this helps with slower models; lowering it can speed up retries. |
| `LLMCHESS_RESPONSES_RETRIES` | `4` | int | `providers/openai_provider.py` | Number of automatic retries around the Responses API requests. Failures after the final retry are logged and bubble up as empty answers. |
| `LLMCHESS_MAX_CONCURRENCY` | `8` | int | `providers/openai_provider.py` | Maximum number of concurrent Responses API calls (thread-pool workers). Tune to respect rate limits or to better utilise available quota. |
| `LLMCHESS_USE_GUARD_AGENT` | `True` | bool | `agent_normalizer.py` | Toggles the clean-up guard agent that re-writes raw LLM replies into UCI moves. Disable to save tokens if your model already replies with valid UCI. |

## Sample `settings.yml`

```yaml
# Top-level keys mirror the environment variable names exactly.
OPENAI_API_KEY: sk-your-key-here
STOCKFISH_PATH: /usr/local/bin/stockfish
OPENAI_BATCH_COMPLETION_WINDOW: 6h
LLMCHESS_ITEMS_PER_BATCH: 100
LLMCHESS_MAX_CONCURRENCY: 4
LLMCHESS_USE_GUARD_AGENT: true
```

Place this file at the repository root (next to `requirements.txt`). Any key omitted will continue to derive from the environment or default values shown above.

## When to adjust each knob

- **Scaling load tests** – Decrease `LLMCHESS_ITEMS_PER_BATCH` or `LLMCHESS_MAX_CONCURRENCY` to stay within rate limits, or increase them to push throughput with higher quotas.
- **Long-running models** – Raise `LLMCHESS_RESPONSES_TIMEOUT_S` and `LLMCHESS_TURN_MAX_WAIT_S` so complex models (or self-hosted endpoints) have enough time to respond.
- **Budget-sensitive runs** – Disable `LLMCHESS_USE_GUARD_AGENT` if you prefer to skip the extra agent pass and post-process moves yourself.
- **Observability** – Tighten `LLMCHESS_BATCH_POLL_S` temporarily when you want more up-to-date logs during batch experiments; loosen it to reduce API chatter.

## Troubleshooting quick reference

- **Stockfish fails to start** – Confirm the binary path, or export `STOCKFISH_PATH` before running scripts/tests. The engine helper logs the attempted path when it cannot spawn the process.
- **Blank responses from models** – Look at the logs for final retry failures. Increasing `LLMCHESS_RESPONSES_RETRIES` and `LLMCHESS_RESPONSES_TIMEOUT_S` often helps with throttling.
- **Batch jobs time out** – Extend `OPENAI_BATCH_COMPLETION_WINDOW` and `LLMCHESS_BATCH_TIMEOUT_S`, and consider reducing `LLMCHESS_ITEMS_PER_BATCH` so jobs finish faster.
