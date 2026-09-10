# GPT announced checkmate. The king moved.

GPT-6 Astra completed a game against itself in 39 moves. On move 34, its public comment called a rook capture checkmate. The move gave check, but Black had one legal reply. A queen capture in the same position really would have been mate.

The film follows that game from the initial position to its eventual checkmate. Every actual move appears in order; the opening repeats two moves as a teaser. The unplayed queen capture has a persistent **ALTERNATIVE / NOT PLAYED** label. The two exports have the same 2:25.43 edit, independently arranged for 1920×1080 and 1080×1920 at 30 fps.

## What we tested

We used the OpenAI API IDs `gpt-6-astra`, `gpt-5.6-sol`, and `gpt-5.6-luna`, available to this account on September 9, 2026. These are API experiments, not tests of the ChatGPT product. All calls used low reasoning effort, a 2,048-token total output ceiling, the default service tier and provider-default sampling. The ceiling includes reasoning tokens.

Every turn provided the exact FEN, a labeled ASCII board, the complete legal move history and an alphabetically sorted, unranked list of legal UCI moves. The model received no engine scores, suggestions, tools or answer key. It selected a move and supplied a short public comment. Each turn was a new request with the game history, not a continuing conversation with previous commentary. This deliberately tests move choice with accurate state and legal-list assistance; it does **not** test unaided board memory or move legality discovery.

Replies had to contain exactly the JSON keys `move` and `comment`. No move harvesting from prose, correction requests, automatic retries or first-legal-move substitutions were allowed. Comments were requested to be at most 12 words, but their length was not a pass/fail criterion. A local chess rules library validated moves, checkmate, draws and PGN replay.

The [primary protocol](../../evidence/episode-02/protocol.json), [12 cases](../../evidence/episode-02/cases.json) and runner were committed in [594970e](https://github.com/MarcoBetti1/llmchess/commit/594970e) before paid testing. The [source hashes](../../evidence/episode-02/source-identity.json) identify the experiment implementation. Follow-up games were specified separately in [cac3938](https://github.com/MarcoBetti1/llmchess/commit/cac3938) after the puzzle suite and both primary engine games, while self-play was still running. That follow-up is descriptive, not a preregistered model ranking.

## Results

The seeded suite contains six king-and-queen versus king positions and six king-and-rook versus king positions, with six White-to-move and six Black-to-move cases. Each has one to three immediate mating moves, verified by enumerating every legal move. Models were asked to choose the best move; they were not told a mate was available. Each model attempted each position once.

| Model | Legal replies | Immediate checkmates |
|---|---:|---:|
| GPT-6 Astra | 12/12 | 12/12 |
| GPT-5.6 Sol | 12/12 | 12/12 |
| GPT-5.6 Luna | 12/12 | 12/12 |

These are 12 small, constructed three-piece positions, not a representative chess benchmark. Perfect performance here does not imply reliable full-game play.

All games began from the standard initial position. Stockfish 18 used one thread, 16 MiB hash, Skill Level 20, no strength limit, no opening book or tablebases, and **2,000 nodes per move**, with the hash cleared each turn. That is a limited search budget, not full-strength Stockfish or a calibrated Elo opponent. The engine identity, binary hash and settings are saved in every game file. Post-game analysis used 100,000 nodes per position and was never shown to a model.

| Game | Last legal ply | Outcome | Evidence |
|---|---:|---|---|
| Astra White vs Stockfish | 62 | Stockfish checkmated Astra, 31...Rxd3# | [PGN](../../evidence/episode-02/games/astra-white.pgn) |
| Stockfish vs Astra Black | 59 | Stockfish checkmated Astra, 30.Qe2# | [PGN](../../evidence/episode-02/games/astra-black.pgn) |
| Astra vs Astra | 77 | White checkmated Black, 39.Rf8# | [PGN](../../evidence/episode-02/games/astra-self.pgn) |
| Sol White vs Stockfish — follow-up | 36 | Output cap on request for ply 37 | [PGN](../../evidence/episode-02/games/sol-white.pgn) |
| Stockfish vs Sol Black — follow-up | 49 | Output cap on request for ply 50 | [PGN](../../evidence/episode-02/games/sol-black.pgn) |
| Luna White vs Stockfish — follow-up | 22 | Output cap on request for ply 23 | [PGN](../../evidence/episode-02/games/luna-white.pgn) |
| Stockfish vs Luna Black — follow-up | 19 | Output cap on request for ply 20 | [PGN](../../evidence/episode-02/games/luna-black.pgn) |

**The four output-cap stops are not checkmate losses.** Each provider response reported `incomplete` with reason `max_output_tokens` and 2,048 output tokens. The runner awards a protocol forfeit in the PGN result, whose Termination header distinguishes it from a chess result. The JSON records `rules_completed: false` and the failed request. More output allowance might change those games; this experiment did not test that intervention. None of the 235 completed replies selected an illegal move. Four additional replies did not complete.

The primary protocol selected the longest rules-completed game for the film, with ties broken by protocol order. Self-play had 77 plies, longer than the two engine games at 62 and 59. The film concentrates on these three primary games; the table includes every follow-up. No game is omitted from the evidence. There is no Elo estimate or statistical model leaderboard.

## The three moments in the film

1. **27...Qxc3, 28.bxc3.** Black said, “Win a pawn and intensify pressure on the knight.” Its queen captured a pawn and was then taken by White's b-pawn. The displayed material values, pawn 1 and queen about 9, are teaching conventions, not an engine evaluation.
2. **34.Rxf4+ Ke6.** White said, “Capture the rook and deliver checkmate.” Exhaustive legal-move generation gives exactly one reply: `f5e6`, or `Ke6`. The rook leaving e4 opened that escape. The unplayed alternative **34.Qxf4#** leaves the rook on e4 covering e6 and produces immediate checkmate. This comparison requires no evaluation score or inferred private reasoning.
3. **39.Rf8#.** In the actual game, Black survived until move 39. White's rook checks the king on d8 along the eighth rank; the queen on a7 covers c7, d7 and e7. Black has zero legal moves and is in check.

All quoted model lines come directly from saved public `comment` fields. They are not hidden reasoning or reconstructed thoughts. Narrator jokes are written separately. The White and Black character voices are stock synthetic voices, clearly disclosed in the film and upload description.

## Tokens and spending

Before every generation request, the runner called OpenAI's `responses/input_tokens` endpoint for that exact model and input. Afterward it saved the provider's full usage object. **All 239 input counts matched the final usage exactly.** Reasoning tokens are a subset of output tokens and are not charged or counted twice. The recorded cache-read and cache-write token counts were zero.

| Model | Requests | Input tokens | Output tokens | Of output: reasoning | Conservative cost bound |
|---|---:|---:|---:|---:|---:|
| GPT-6 Astra | 149 | 78,234 | 45,520 | 41,244 | $3.253925 |
| GPT-5.6 Sol | 56 | 27,983 | 43,298 | 41,785 | $1.005875 |
| GPT-5.6 Luna | 34 | 15,148 | 17,080 | 16,079 | $0.024283 |
| Total | 239 | 121,365 | 105,898 | 99,108 | **$4.284083** |

The experiment ledger reserved all possible output plus 1.25× normal input pricing before dispatch, then settled against actual usage using the same conservative formula. It assumed no cache discount. Model input/output prices per million were Astra $10/$50, Sol $4/$20, and Luna $0.20/$1.20, recorded with official model-documentation sources in the protocol. At normal rates the observed no-cache generation usage corresponds to $4.0597576; the larger table figure is the enforced planning bound, not an invoice.

Production used 28 speech clips, including revisions, and 28 per-clip transcription checks. Its ledger retains conservative allowances of $0.08 per speech request and $0.01 per transcription, **$2.52 total**. The speech endpoint does not return token usage; no synthetic token count is invented. Combined planning allowance: **$6.804083 of the authorized $20**, under the $17 experiment and $3 production caps. Account billing remains the source of the actual charge. No Anthropic requests were made.

## Audit and limitations

Run `python -m llmchess_lab.analyze` from the repository root to recheck the published episode offline. It verifies source and payload hashes, case answers, exact prompts, request coverage, tokens, ledger arithmetic, every legal move, per-ply FENs, result/termination consistency and PGN replay. The [audit JSON](../../evidence/episode-02/audit.json) contains machine-readable totals. `python -m video.chess.verify` checks the edit against game evidence, quote identity, all 77 main-game plies, caption bounds and its budget. `--media` verifies the encoded streams, decodes the complete exports and checks loudness.

The experiment is a small descriptive case study with one attempt per case and one game per assigned pairing/color. Legal-list assistance, low reasoning, the output ceiling, engine search budget and model aliases all affect the observations. Results may change on another run or after an alias update. API request IDs and raw model IDs are retained; deterministic repeatability of model outputs is not claimed. There is no evidence here that all language models fail at chess or that these models have a particular Elo.

Engine analysis files separate finite centipawn differences from mate transitions. The graph-only ±10,000 mate sentinel is never interpreted as a numerical centipawn loss. Conclusions about checkmate in the film come from legal move enumeration, not that sentinel or a search score.

## Repository work

The main runner and older control room now preserve custom-FEN PGNs and move history, reject illegal engine moves, distinguish provider errors and unfinished caps from rules outcomes, bind the local API to localhost, and visibly identify mock UI data. Current dependencies and model options were refreshed. The separate [llm-chess-lite-2](https://github.com/MarcoBetti1/llm-chess-lite-2) playground now starts with one request and strict exact-token parsing, including long castling, without silently substituting the first legal move. Existing custom graphs remain user-editable and are not used in this experiment.

The repair commits passed Python tests, UI lint/build, dependency audits and GitHub CI. The source, prompts, every response and all seven PGNs are public; API keys, local environment files and Stockfish binaries are excluded. Original chess artwork, score and animation code are in `video/chess`. The user controls publication of the finished video.
