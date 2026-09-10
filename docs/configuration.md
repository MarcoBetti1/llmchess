# Configuration

The measured runner and the older interactive app have different transports. Use `llmchess-lab` for recorded, budgeted experiments.

## Laboratory

Set `OPENAI_API_KEY` in a local `.env`, or pass `--env-file /path/to/.env`. Run `llmchess-lab prepare --out /path/to/new/run` to create the fixed episode protocol, then inspect it before `puzzles` or `games`. Use the same `--out` for all commands in a run. Reusing an already received request replays its saved response without billing; an unresolved reservation stops instead of retrying.

The episode has a cumulative $17 experiment cap. Model IDs, verified planning prices, low reasoning effort, and the 2,048 total output-token limit are defined in `src/llmchess_lab/core.py` and recorded in the protocol. A fresh experiment requires a fresh output directory. The separate film production ledger has a $3 cap.

## Interactive Flask app

`src/llmchess_simple/config.py` loads `settings.yml` first, then the process environment (including `.env`), then defaults. Do not commit keys or private settings.

| Setting | Behavior |
| --- | --- |
| `OPENAI_API_KEY` | Uses the direct OpenAI endpoint when no explicit transport overrides are set. |
| `LLMCHESS_LLM_API_KEY` | Explicit key for the configured transport; takes precedence. |
| `LLMCHESS_LLM_BASE_URL` | Explicit OpenAI-compatible endpoint; for example `https://api.openai.com/v1`. |
| `AI_GATEWAY_API_KEY`, `AI_GATEWAY_BASE_URL` | Legacy gateway aliases. |
| `LLMCHESS_RESPONSES_TIMEOUT_S` | Per-request timeout, default 300 seconds. |
| `LLMCHESS_RESPONSES_RETRIES` | Retained for configuration compatibility, but ignored. Automatic retries are disabled. |
| `LLMCHESS_UI_ORIGINS` | Comma-separated browser origins; defaults to `http://localhost:3000,http://127.0.0.1:3000`. |

GPT-5 and GPT-6 interactive requests use low reasoning effort and 2,048 maximum completion tokens. Other compatible models use a 2,048-token output cap. The interactive app does not use the lab's dollar ledger.

The Next.js UI proxies `/api` to the local backend on port 8000. Set `NEXT_PUBLIC_API_BASE` only to override this. Synthetic data requires `NEXT_PUBLIC_USE_MOCKS=true` and is labeled with a visible banner.

A transport failure leaves the game unfinished. It is not a chess loss. Check the request/provider state before manually making another paid attempt.
