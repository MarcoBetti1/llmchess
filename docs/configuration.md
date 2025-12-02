# Configuration Reference

This project loads configuration from code in `src/llmchess_simple/config.py`. The loader favors a YAML file named `settings.yml` in the repository root, falls back to environment variables, and finally uses sensible defaults baked into the code. The resulting values are exposed through the frozen dataclass `Settings`, available as `SETTINGS` across the codebase.

## Load order and precedence

1. **`settings.yml`** – if present in the repo root (sibling to `README.md`). Values here override everything else.
2. **Environment variables** – read from the OS _after_ `dotenv.load_dotenv()` runs, so a local `.env` file is honoured.
3. **Code defaults** – the constants defined inside `config.py` are used when no other source provides a value.


## Settings catalogue

| Key | Default | Type | Used in | Purpose |
| --- | --- | --- | --- | --- |
| `LLMCHESS_LLM_BASE_URL` | `"https://ai-gateway.vercel.sh/v1"` | string | `llm_client.py` | Base URL for the Vercel AI Gateway. Override if your team-specific gateway URL differs. |
| `LLMCHESS_LLM_API_KEY` | `""` | string | `llm_client.py` | Authentication token for the configured Vercel AI Gateway base URL. |
| `LLMCHESS_RESPONSES_TIMEOUT_S` | `300.0` | float seconds | `llm_client.py` | Per-request timeout used by chat/completions calls. Raising this helps with slower models; lowering it can speed up retries. |
| `LLMCHESS_RESPONSES_RETRIES` | `4` | int | `llm_client.py` | Number of automatic retries around chat/completions requests. Failures after the final retry are logged and bubble up as empty answers. |
| `LLMCHESS_MAX_CONCURRENCY` | `8` | int | `llm_client.py` | Maximum number of concurrent chat/completions calls (thread-pool workers). Tune to respect rate limits or to better utilise available quota. |

## Sample `settings.yml`

```yaml
# Top-level keys mirror the environment variable names exactly.
LLMCHESS_LLM_API_KEY: sk-your-vercel-gateway-key
LLMCHESS_LLM_BASE_URL: https://ai-gateway.vercel.sh/v1
LLMCHESS_MAX_CONCURRENCY: 4
LLMCHESS_RESPONSES_TIMEOUT_S: 120
LLMCHESS_USE_GUARD_AGENT: true
```

Place this file at the repository root (next to `requirements.txt`). Any key omitted will continue to derive from the environment or default values shown above.

## When to adjust each knob

- **Pointing at a gateway** – Set `LLMCHESS_LLM_BASE_URL` to your Vercel AI Gateway base URL (team-specific if applicable).
- **Scaling load tests** – Lower `LLMCHESS_MAX_CONCURRENCY` to respect rate limits; raise it to improve throughput when quotas allow.
- **Long-running models** – Raise `LLMCHESS_RESPONSES_TIMEOUT_S` so complex models (or self-hosted endpoints) have enough time to respond.

## Troubleshooting quick reference

- **Blank responses from models** – Look at the logs for final retry failures. Increasing `LLMCHESS_RESPONSES_RETRIES` and `LLMCHESS_RESPONSES_TIMEOUT_S` often helps with throttling.
- **Slow responses** – Bump `LLMCHESS_RESPONSES_TIMEOUT_S` and reduce `LLMCHESS_MAX_CONCURRENCY` to ease pressure on slower or rate-limited backends.
