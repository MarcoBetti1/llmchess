"""
LLM Chess (Simplified) package.

Components:
- game: single-game orchestration and metrics
- llm_opponent/user_opponent: opponents (another LLM or an interactive human)
- prompting/move_validator: prompt build and move normalization
- llm_client: minimal OpenAI-compatible transport (base_url configurable for AI Gateway)
"""
# Package exports are intentionally minimal; import modules directly as needed.
