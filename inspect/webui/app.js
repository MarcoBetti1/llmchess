(() => {
  const gamesListEl = document.getElementById('gamesList');
  const gameSearchEl = document.getElementById('gameSearch');
  const gameMetaEl = document.getElementById('gameMeta');
  const boardEl = document.getElementById('board');
  const sliderEl = document.getElementById('slider');
  const moveInfoEl = document.getElementById('moveInfo');

  const btnPrev = document.getElementById('btnPrev');
  const btnPlay = document.getElementById('btnPlay');
  const btnNext = document.getElementById('btnNext');
  const btnRestart = document.getElementById('btnRestart');
  const speedEl = document.getElementById('speed');
  const flipEl = document.getElementById('flip');

  // State
  let allGames = [];
  let currentGame = null; // full JSON of selected game
  let fens = []; // [start_fen, ... move[i].fen_after]
  let idx = 0;   // 0..moves.length (ply applied)
  let playing = false;
  let timer = null;
  let flipped = false;

  function uciToPretty(move) {
    if (!move) return '';
    const san = move.san || move.uci || '';
    const actor = move.actor || '';
    const side = move.side || '';
    return `${san} (${side}${actor ? ', ' + actor : ''})`;
  }

  function setPlaying(p) {
    playing = p;
    btnPlay.textContent = playing ? '⏸ Pause' : '▶ Play';
    if (playing) startTimer(); else stopTimer();
  }

  function startTimer() {
    stopTimer();
    const delay = Math.max(50, Math.floor(parseFloat(speedEl.value || '1.0') * 1000));
    timer = setInterval(() => {
      if (!currentGame) return;
      if (idx < fens.length - 1) {
        idx++;
        applyIdx();
      } else {
        setPlaying(false);
      }
    }, delay);
  }
  function stopTimer() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  function drawBoard(fen) {
    const placement = fen.split(' ')[0];
    const rows = placement.split('/');
    const grid = [];
    for (let r = 0; r < 8; r++) {
      const row = rows[r];
      const out = [];
      for (const ch of row) {
        if (/[1-8]/.test(ch)) {
          const n = parseInt(ch, 10);
          for (let i = 0; i < n; i++) out.push('');
        } else {
          out.push(ch);
        }
      }
      grid.push(out);
    }

    // Orientation
    let rs = [...grid];
    if (flipped) {
      rs = rs.slice().reverse().map(r => r.slice().reverse());
    }

    // Render
    boardEl.innerHTML = '';
    for (let r = 0; r < 8; r++) {
      for (let c = 0; c < 8; c++) {
        const cell = document.createElement('div');
        cell.className = 'sq ' + (((r + c) % 2 === 0) ? 'light' : 'dark');
        const p = rs[r][c];
        if (p) {
          const span = document.createElement('span');
          span.className = /[A-Z]/.test(p) ? 'white' : 'black';
          span.textContent = pieceGlyph(p);
          cell.appendChild(span);
        }
        boardEl.appendChild(cell);
      }
    }
  }

  function pieceGlyph(ch) {
    const map = {
      'K': '♔', 'Q': '♕', 'R': '♖', 'B': '♗', 'N': '♘', 'P': '♙',
      'k': '♚', 'q': '♛', 'r': '♜', 'b': '♝', 'n': '♞', 'p': '♟'
    };
    return map[ch] || '?';
  }

  function applyIdx() {
    if (!currentGame) return;
    const moves = currentGame.moves || [];
    const fen = fens[idx] || currentGame.start_fen;
    drawBoard(fen);

    // update slider, move info, metadata
    sliderEl.max = String(Math.max(0, fens.length - 1));
    sliderEl.value = String(idx);
    const total = moves.length;
    let info = '';
    if (idx === 0) {
      info = 'Start position';
    } else {
      const m = moves[idx - 1];
      const moveNo = Math.floor((idx + 1) / 2);
      info = `Ply ${idx}/${total}  Move ${moveNo}  ${uciToPretty(m)}`;
    }
    if (idx >= total && currentGame.result) {
      const tr = currentGame.termination_reason ? ` | Termination: ${currentGame.termination_reason}` : '';
      info += ` | Game over: ${currentGame.result}${tr}`;
    }
    moveInfoEl.textContent = info;

    // Meta
    const h = currentGame.headers || {};
    gameMetaEl.textContent = `Event: ${h.Event || ''} | White: ${h.White || ''} vs Black: ${h.Black || ''} | Date: ${h.Date || ''} | Result: ${currentGame.result || ''}`;
  }

  async function loadGames() {
    const res = await fetch('/api/games');
    const data = await res.json();
    allGames = data.games || [];
    renderGamesList();
  }

  function renderGamesList() {
    const q = (gameSearchEl.value || '').toLowerCase();
    const items = allGames.filter(g =>
      (g.event || '').toLowerCase().includes(q) ||
      (g.white || '').toLowerCase().includes(q) ||
      (g.black || '').toLowerCase().includes(q) ||
      (g.date || '').toLowerCase().includes(q)
    );

    gamesListEl.innerHTML = '';
    for (const g of items) {
      const li = document.createElement('li');
      li.className = 'game-item';
      li.innerHTML = `
        <div class="title">${escapeHtml(g.white)} vs ${escapeHtml(g.black)} <span class="result">${escapeHtml(g.result || '')}</span></div>
        <div class="sub">${escapeHtml(g.event || '')} • ${escapeHtml(g.date || '')}</div>
        <div class="path">${escapeHtml(g.path)}</div>
      `;
      li.addEventListener('click', () => openGame(g.path));
      gamesListEl.appendChild(li);
    }
  }

  async function openGame(path) {
    setPlaying(false);
    idx = 0;
    const res = await fetch(`/api/game?path=${encodeURIComponent(path)}`);
    currentGame = await res.json();
    // Build fen list
    const moves = currentGame.moves || [];
    fens = [currentGame.start_fen];
    for (const m of moves) {
      if (m && m.fen_after) fens.push(m.fen_after);
    }
    applyIdx();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }

  // Controls
  btnPrev.addEventListener('click', () => { if (idx > 0) { idx--; applyIdx(); } });
  btnNext.addEventListener('click', () => { if (currentGame && idx < fens.length - 1) { idx++; applyIdx(); } });
  btnPlay.addEventListener('click', () => setPlaying(!playing));
  btnRestart.addEventListener('click', () => { idx = 0; applyIdx(); });
  speedEl.addEventListener('change', () => { if (playing) startTimer(); });
  flipEl.addEventListener('change', () => { flipped = flipEl.checked; applyIdx(); });

  sliderEl.addEventListener('input', () => {
    idx = parseInt(sliderEl.value, 10) || 0;
    applyIdx();
  });

  // Keyboard
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); if (idx > 0) { idx--; applyIdx(); } }
    else if (e.key === 'ArrowRight') { e.preventDefault(); if (currentGame && idx < fens.length - 1) { idx++; applyIdx(); } }
    else if (e.key === ' ') { e.preventDefault(); setPlaying(!playing); }
  });

  // Init board grid template
  function initBoardGrid() {
    boardEl.style.setProperty('--rows', 8);
    boardEl.style.setProperty('--cols', 8);
  }

  initBoardGrid();
  loadGames();
})();
