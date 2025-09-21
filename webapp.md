### Webapp
WIP!!!
(old doc vvv)
## Visualize a recorded game (rewatch)

Use the interactive viewer to step through a structured history JSON (hist_*.json):

- Run: python scripts/view_game.py <path-to-hist.json>
- Optional flags: --autoplay (start playing automatically), --delay <seconds> (autoplay speed)
- Controls during viewing:
  - Enter: next move
  - p: previous move
  - a: autoplay (resume)
  - s: pause
  - r: restart from beginning
  - g <ply>: jump to ply number (0..N)
  - + / -: faster / slower autoplay
  - q: quit

Example path from this repo:
- scripts/view_game.py runs/parallel_demo/g001/hist_20250920-122740_std_w.json

Notes
- Viewer uses python-chess to render an ASCII board in the terminal.
- If the game ended due to an illegal move, playback stops at the last legal position and shows the termination info.

---