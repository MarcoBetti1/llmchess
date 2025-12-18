"""
LLM Chess (Simplified) package.

Components:
- game: single-game orchestration and metrics
- llm_opponent/user_opponent: opponents (another LLM or an interactive human)
- prompting/move_validator: prompt build and move normalization
- llm_client: minimal Vercel AI Gateway transport (OpenAI-compatible wire format; base_url configurable)
"""
# Package exports are intentionally minimal; import modules directly as needed.
