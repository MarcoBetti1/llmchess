# Directing constraints

Deliver two complete, separately composed videos: 1920×1080 and 1080×1920, 30 fps, each strictly under 180 seconds. Same narration and evidence. Do not crop a landscape export to make the phone edition.

The board is the main character. Every chess position comes from logged FEN/PGN; every animated move is legal in that position. Keep White at the bottom. All meaningful squares remain visible. Explain an attack by moving the piece and showing its attacked squares, not by reading a dense paragraph. Use one visual point at a time.

Narration: plain, conversational, brisk. No 'delve', 'landscape', 'unlock', 'reveals a deeper truth', chains of analogies, ceremonial conclusions, or claims of intelligence from a tiny sample. End by answering the opening question. No four-minute script sped up to fit three minutes.

First 30 seconds: a real game moment, stakes, one short joke, then the setup. Do not open with the repo history or a methods disclaimer. Explain the required method concretely when the board example makes it relevant. Include limits in concise speech and readable labels. A written report carries the detailed protocol.

Astra's quoted lines are exact public response comments, voiced with a clearly disclosed stock synthetic voice. They are not internal thoughts. Do not fabricate a model comment for a better joke. The narrator can make jokes in the narrator's voice.

Readability: dark pieces have a bright outer contour, pale pieces a dark contour, and every text surface explicitly chooses contrasting foreground/background colors. Review actual encoded frames at phone size. Captions are short, maximum two lines, away from board and platform overlays.

Sound: lively natural narrator, distinct slightly self-important chess-player voice, sparse original musical punctuation and piece clicks. No constant comedy effects or fake crowd. Allow one short pause for the viewer to guess a move. Verify speech against the script by per-clip transcription before final rendering.

The completed edit is 145.433 seconds: 21 shots, 265 spoken words, and 44 caption cues. Its hook is the actual false-mate claim at 34.Rxf4+, followed by the legal escape 34...Ke6. The story shows all 77 self-play plies, one clearly labeled unplayed alternative (34.Qxf4#), and the real 39.Rf8# finish. No move is invented for the plot.

## Build

From the repository root, install `pip install -e '.[video]'` and FFmpeg. The artwork currently uses macOS Avenir Next and Menlo fonts at the paths in `video/chess/art.py`; another OS needs deliberate font substitution and a fresh layout review. This is a production source project, not a cross-platform turnkey video library.

```sh
python -m llmchess_lab.analyze
python -m video.chess.story
# This step makes paid speech / transcription calls only for missing cache entries:
python -m video.chess.sound --env-file /path/to/your/.env
python -m video.chess.verify
python -m video.chess.render --mode both
python -m video.chess.verify --media
python -m video.chess.package
```

Do not rerun experiments or generate speech merely to inspect the released evidence. Speech caches, the final timeline, script, captions, production ledger and verification results are included in the local upload package. The repository contains the source and written production receipts; MP4 files are local delivery artifacts for the user to upload.

The audio uses Cedar narration, Fable for White Astra and Onyx for Black Astra via `gpt-4o-mini-tts-2025-12-15`. Musical pulses and effects are original deterministic synthesis. Per-clip transcription checks accept only reviewed punctuation, numeric-format and homophone differences; captions preserve the approved words. The mix targets −16 LUFS and −1.5 dBTP. The final verifier checks encoded loudness and fully decodes both streams.

The source-keyed scene cache includes the render code, visual code, scene data and experimental evidence. Both exports use H.264 CRF 17, yuv420p, 30 fps and stereo AAC at 48 kHz. Captions are burned in and supplied as a separate SRT. An optional subtitle track on YouTube should not be enabled by default over the burned-in captions.
