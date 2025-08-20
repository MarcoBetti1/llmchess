# LLM Chess (Simplified)

A lightweight benchmark to test LLMs on chess with a **minimal agent** whose only job is:
1) ensure the model's reply actually contains a chess move, and
2) return it in a strict **UCI** format (e.g., `e2e4`, `e7e8q`).

The game pipeline:
- We prompt a target model (default **gpt-5**) with FEN + (optional) PGN tail and ask for the *best move*.
- We pass the model's free-form reply to a tiny **Agent (Agents SDK)** that calls a Python tool to validate the move
  against the FEN and normalize it to UCI. If invalid, the agent is asked to try again.
- We apply the move and play vs. Stockfish as the opponent.

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Set env vars (or copy .env.example to .env and edit)
export OPENAI_API_KEY=...           # required
export STOCKFISH_PATH=/usr/bin/stockfish  # adjust for your system
# optional: export OPENAI_MODEL=gpt-5

# Play a single game (LLM as White vs Stockfish depth 6)
python scripts/play_one.py --model gpt-5 --depth 6

# Run multiple games sequentially
python scripts/run_many.py --games 5 --model gpt-5 --depth 6
```

## Requirements
- Python 3.10+
- Stockfish (install and set `STOCKFISH_PATH`)
- Packages in `requirements.txt`

## Notes
- The **agent** only validates/normalizes the move. All strategy testing is handled by the engine opponent and results.
- The code uses the OpenAI **Responses API** for free-form LLM replies and the **Agents SDK** for the validator tool.
- If your Agents SDK import path differs, adjust `agent_normalizer.py` imports accordingly (see comments).
