# Agent normalizer quick reference

The agent normalizer sits between the raw response from an LLM and the chess referee. Its job is to extract a valid UCI move (`e2e4`, `e7e8q`, …) from whatever text the model returned. The implementation lives in `src/llmchess_simple/agent_normalizer.py` and follows a three-step cascade:

1. **Regex fast-path** – A single regex (`[a-h][1-8][a-h][1-8][qrbn]?`) scans the raw reply. If it finds something that already looks like UCI, the function returns it immediately.
2. **Guard agent** – When the regex fails and `LLMCHESS_USE_GUARD_AGENT` is truthy, we call a tiny OpenAI Agents flow named `MoveGuard`. It receives the full reply and must answer with either a lowercase UCI move or the word `NONE`.
3. **Fallback token** – If both previous attempts fail, we grab the first word-like token from the reply (letters/numbers/symbols) and return that as a last resort.

The exported coroutine `normalize_with_agent(raw_reply: str) -> str` executes this pipeline and yields a lowercase move candidate. Callers then run the move through `move_validator` to enforce legality.

## Guard agent prompt

The agent is defined as:

```
name = "MoveGuard"
instructions = """
You receive a raw reply.
Ensure it is a chess move and avoid any other text.
Output ONLY the move in UCI (lowercase, include promotion letter if any). If no move is present, output the single word NONE.
"""
model_settings = ModelSettings(temperature=0.0)
```

At call time we pass this user message:

```
RAW REPLY: <model output>
Return only the move in UCI or NONE:
```

The agent’s `final_output` is trimmed and lowercased. If it returns `NONE`, the normalizer continues to the fallback.

## Toggle via config

Set `LLMCHESS_USE_GUARD_AGENT=false` (or add `LLMCHESS_USE_GUARD_AGENT: false` to `settings.yml`) to skip the agent entirely. In that mode the regex or fallback token will be used, which avoids extra tokens but offers weaker cleanup.

## Typical usage

```python
from src.llmchess_simple.agent_normalizer import normalize_with_agent

raw_text = "I'd play e2 to e4 here."
uci = asyncio.run(normalize_with_agent(raw_text))  # -> "e2e4"
```

Downstream, `GameRunner` logs whether the guard agent or fallback was needed via `meta["salvage_used"]` and `meta["validator"]`.
