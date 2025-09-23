"""
LLM Chess (Simplified) package.

Components:
- game: single-game orchestration and metrics
- batch_orchestrator: multi-game batching over Responses/Batches APIs
- engine_opponent/random_opponent: opponents (Stockfish or random)
- prompting/move_validator/agent_normalizer: prompt build and move normalization
- llm_client/providers: provider-agnostic facade and OpenAI transport
"""
# Package exports are intentionally minimal; import modules directly as needed.