# Chess episode: fixed plan, before model responses

2026-09-09. Fresh user budget: $20 OpenAI total. Experiments have a $17 cumulative cap; narration and QA have $3. No Anthropic requests.

Three API models: GPT-6 Astra, GPT-5.6 Sol, GPT-5.6 Luna. All use `reasoning.effort=low`, a 2,048-token total output cap (including hidden reasoning), provider-default sampling, the same prompt, and no tools. These are API models, not a test of the ChatGPT interface.

## Twelve positions

Seed 9009 generates six king/queen/king and six king/rook/king positions. Half in each group have Black to move. Each valid position has one to three immediate mating moves. Exhaustive legal-move enumeration establishes the answer key without an engine. Every model gets each position once. We report legal-response counts and immediate-mate counts separately. This is a small constructed demonstration, not a representative chess benchmark or a statistical ranking.

Prompts contain FEN, a labeled ASCII board, full game move history when present, and alphabetically sorted legal UCI moves. The answer key and engine evaluations never enter prompts. The instruction is to play the best move, without revealing that every puzzle is mate in one. The same instruction is used in games. Each reply is a JSON move plus a public intention of at most twelve words. Commentary is not scored as analysis and does not establish why a model chose a move.

No repairs, retries, move substitutions, or engine assistance. Format, illegal-move and incomplete-provider failures remain distinct. A failed game move is a protocol forfeit, never labeled checkmate. Transport uncertainty stops work with its reservation retained.

## Games, in this order

1. Astra as White against Stockfish 18.
2. Astra as Black against Stockfish 18.
3. Astra against itself, independent fresh request per side per turn.

All start from the standard initial board, no opening book, no supplied strategy or opening sequence. Stockfish uses 1 thread, 16 MB hash, normal skill 20, strength limiting off, and 2,000 search nodes per move with its hash cleared. This is deliberately a small search allowance, not full-strength Stockfish and not an Elo-calibrated opponent. Engine binary SHA and UCI identity are recorded. No tablebases.

Each game stops on rules termination, a claimable draw (claimed automatically), protocol forfeit, 240 plies, or shared experiment budget. A move cap/budget cap leaves `*` (unfinished), not a draw. No resignation is forced by an evaluation. The film features the longest rules-completed game; ties follow game order. All games are reported, including failures and unfinished games. The game shown is explicitly an illustration, not typical performance.

Post-game analysis may use Stockfish at 100,000 nodes per position. This evaluation is never provided to the players. Scores are from White's perspective and are engine estimates; mating claims shown in the film must also be verified through legal moves.

## Tokens and costs

OpenAI's model-specific `responses/input_tokens` endpoint counts the exact submitted instructions and input. Actual returned `usage` is authoritative. We retain input/output counts, cache details, reasoning-token details, raw JSON, exact model returned, request IDs, latency, and input-count deltas. Reasoning tokens are included in output, not added twice. All calls reserve maximum possible output and 1.25 times normal input price before dispatch, covering possible cache-write pricing without assuming discounts. The same conservative bound is recomputed from actual usage. It is a planning bound, not an invoice. Unknown usage keeps its reservation.

Pricing and model IDs verified from official documentation on 2026-09-09:

- [GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra): $10 input / $50 output per million tokens.
- [GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol): $4 / $20.
- [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna): $0.20 / $1.20.
- [Input-token endpoint](https://developers.openai.com/api/reference/typescript/resources/responses/subresources/input_tokens).

No film claims are written before seeing results. Narration must use plain sentences, few analogies, exact board demonstrations, and a clearly closed ending. Both landscape and separately composed vertical editions must remain below 180 seconds.

## Documented follow-up (added after the primary engine games)

After seeing all 36 puzzle successes and Astra's two Stockfish losses, we added the identical two-color engine challenge for Sol and Luna. Astra's self-play was still in progress. The four games are defined in `evidence/episode-02/followup-protocol.json`, committed before their first request. Prompts, reasoning setting, token cap, engine settings, opening position, draw policy and existing cumulative dollar cap remain identical. These additional games are descriptive follow-up evidence, not part of a preregistered ranking. The original film-selection rule remains unchanged. Every attempt and game is retained.
