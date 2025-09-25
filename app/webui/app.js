(() => {
  // ===== Existing viewer references =====
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

  // ===== New UI references =====
  const testRunForm = document.getElementById('testRunForm');
  const testRunStatus = document.getElementById('testRunStatus');
  const testProgressEl = document.getElementById('testProgress');
  const analysisBox = document.getElementById('analysisBox');
  const playForm = document.getElementById('playForm');
  const playBoardEl = document.getElementById('playBoard');
  const playConversationEl = document.getElementById('playConversation');
  const playMovesEl = document.getElementById('playMoves');
  const playStatus = document.getElementById('playStatus');
  const btnHumanMove = document.getElementById('btnHumanMove');
  const playHint = document.getElementById('playHint');
  const llmWaiting = document.getElementById('llmWaiting');
  const llmPendingPanel = document.getElementById('llmPendingPanel');
  const llmTimerEl = document.getElementById('llmTimer');
  const llmLastDurationEl = document.getElementById('llmLastDuration');

  // ===== State =====
  let allGames = [];
  let currentGame = null;
  let fens = [];
  let idx = 0;
  let playing = false;
  let timer = null;
  let flipped = false;
  let activeRunId = null;
  let playSessionId = null;
  let playFlipped = false; // future orientation toggle
  let pendingHumanMove = null; // {from,to,uci}
  let currentLegalMoves = []; // array of {uci, from, to, promotion}
  let pollTimer = null;
  let playHumanColor = null; // 'white' | 'black'
  let llmTimerHandle = null;

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

  function escapeHtml(s) { return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

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

  // ===== Tabs =====
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');
  tabButtons.forEach(btn => btn.addEventListener('click', () => {
    tabButtons.forEach(b => b.classList.remove('active'));
    tabPanels.forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  }));

  // ===== Test Run form =====
  testRunForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    testRunStatus.textContent = 'Starting run...';
    testProgressEl.textContent = '';
    const fd = new FormData(testRunForm);
    const body = {}; fd.forEach((v,k)=> body[k]=v);
    body.games = parseInt(body.games || '1', 10);
    const res = await fetch('/api/test/run', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const j = await res.json();
    activeRunId = j.run_id; testRunStatus.textContent = 'Run ID: ' + activeRunId;
    attachRunStream(activeRunId);
  });

  function attachRunStream(id){
    const ev = new EventSource('/api/test/stream/' + id);
    ev.addEventListener('progress', (e) => {
      const d = JSON.parse(e.data);
      testProgressEl.textContent += `[cycle ${d.cycle}] active=${d.active_count}\n`;
      testProgressEl.scrollTop = testProgressEl.scrollHeight;
    });
    ev.addEventListener('done', (e) => {
      const arr = JSON.parse(e.data);
      testProgressEl.textContent += 'DONE. Games: ' + arr.length + '\n';
      loadGames(); loadAnalysis();
    });
    ev.addEventListener('end', () => ev.close());
  }

  async function loadAnalysis(){
    try { const r = await fetch('/api/test/analysis'); const d = await r.json(); analysisBox.textContent = `Indexed: ${d.games_indexed}\nW:${d.wins} D:${d.draws} L:${d.losses}`; }
    catch { analysisBox.textContent = 'Analysis failed'; }
  }

  // ===== Interactive Play =====
  playForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(playForm); const body = {}; fd.forEach((v,k)=> body[k]=v);
    playStatus.textContent = 'Starting game...';
    try {
      const r = await fetch('/api/play/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
      let text = await r.text();
      let j;
      try { j = JSON.parse(text); } catch(parseErr){ throw new Error('Server response not JSON: '+ text.slice(0,120)); }
      if(!r.ok){ throw new Error(j.error || r.status + ' ' + r.statusText); }
      playSessionId = j.session_id; 
      playStatus.textContent = 'Session ' + playSessionId + ' started';
      const llmColor = (j.llm_color || 'white').toLowerCase();
      playHumanColor = llmColor === 'white' ? 'black' : 'white';
      playFlipped = (playHumanColor === 'black');
      playBoardEl.classList.remove('disabled');
      btnHumanMove.disabled = true; 
      pendingHumanMove = null; playHint.textContent = '';
      await refreshPlayState();
    } catch(err){
      playStatus.textContent = 'Failed to start: ' + err;
    }
  });

  btnHumanMove?.addEventListener('click', async () => {
    if(!playSessionId || !pendingHumanMove) return;
    btnHumanMove.disabled = true;
    const uci = pendingHumanMove.uci;
    pendingHumanMove = null;
    playHint.textContent = '';
    try { await fetch('/api/play/human_move', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: playSessionId, uci})}); } catch {}
    await refreshPlayState();
  });

  async function refreshPlayState(){
    const r = await fetch('/api/play/state/' + playSessionId); const d = await r.json();
    drawBoardPlay(d.fen, d); renderConversation(d.conversation||[]); renderPlayMoves(d.moves||[]);
    currentLegalMoves = d.legal_moves || [];
    const humanTurn = d.human_turn;
    updatePendingPanel(d);
    if(d.result && d.result !== '*') {
      playStatus.textContent = `Game over: ${d.result} (${d.termination_reason||'normal'})`;
      llmWaiting.hidden = true; clearPolling(); btnHumanMove.disabled = true; return;
    }
    if(humanTurn){
      llmWaiting.hidden = true;
      playHint.textContent = 'Your move: drag a piece, then click Submit Move';
      btnHumanMove.disabled = !pendingHumanMove;
      clearPolling();
    } else {
      playHint.textContent = '';
      btnHumanMove.disabled = true;
      llmWaiting.hidden = true; // replaced by pending panel
      ensurePolling();
    }
  }
  function ensurePolling(){ if(pollTimer) return; pollTimer = setInterval(()=>{ if(playSessionId) refreshPlayState(); }, 1800); }
  function clearPolling(){ if(pollTimer){ clearInterval(pollTimer); pollTimer=null; } }
  function renderConversation(msgs){ playConversationEl.textContent = msgs.map(m=>`${m.role}> ${m.content}`).join('\n'); playConversationEl.scrollTop = playConversationEl.scrollHeight; }
  function renderPlayMoves(moves){
    playMovesEl.innerHTML='';
    const filtered = moves.filter(m=>m.san && m.actor && m.actor !== 'termination');
    filtered.forEach(m=>{
      const li=document.createElement('li');
      const plySpan=document.createElement('span'); plySpan.className='ply'; plySpan.textContent = m.ply;
      const sanSpan=document.createElement('span'); sanSpan.className='san'; sanSpan.textContent = m.san;
      const actorSpan=document.createElement('span'); actorSpan.className='actor'; actorSpan.textContent = m.actor;
      li.appendChild(plySpan); li.appendChild(sanSpan); li.appendChild(actorSpan); playMovesEl.appendChild(li);
    });
  }
  function updatePendingPanel(d){
    if(!llmPendingPanel) return;
    if(d.llm_pending){
      llmPendingPanel.classList.remove('hidden');
      llmTimerEl.textContent = (d.llm_pending_for_ms/1000).toFixed(1)+'s';
    } else {
      if(d.llm_last_duration_ms){ llmLastDurationEl.textContent = `Last: ${(d.llm_last_duration_ms/1000).toFixed(2)}s`; }
      llmPendingPanel.classList.add('hidden');
    }
  }
  function drawBoardPlay(fen, state){
    const placement = fen.split(' ')[0]; const rows=placement.split('/'); const grid=[]; for(let r=0;r<8;r++){ const row=rows[r]; const out=[]; for(const ch of row){ if(/^[1-8]$/.test(ch)){ for(let i=0;i<parseInt(ch,10);i++) out.push(''); } else out.push(ch);} grid.push(out);} let rs=[...grid]; if(playFlipped){ rs=rs.slice().reverse().map(r=>r.slice().reverse()); }
    // Build index mapping for orientation to coordinate names
    const fileNames = ['a','b','c','d','e','f','g','h'];
    function coordFromDisplay(rc){ // rc: {r,c} in displayed orientation
      let boardR = playFlipped ? 7-rc.r : rc.r;
      let boardC = playFlipped ? 7-rc.c : rc.c;
      const rank = 8 - boardR;
      const file = fileNames[boardC];
      return file + rank;
    }
    playBoardEl.innerHTML='';
    const humanTurn = state?.human_turn;
    const legalByFrom = {};
    (state?.legal_moves||[]).forEach(m => { (legalByFrom[m.from] ||= []).push(m); });

    // Drag & click state
    let selectedFrom = null; // square name
    let ghostEl = null; // floating piece element during drag
    let dragging = false;

    function clearHighlights(){
      playBoardEl.querySelectorAll('.sq').forEach(sq=>{
        sq.classList.remove('selected-from','legal-target','hover-target');
      });
    }
    function highlightFrom(from){
      clearHighlights();
      const originCell = playBoardEl.querySelector(`.sq[data-square="${from}"]`);
      if(originCell) originCell.classList.add('selected-from');
      (legalByFrom[from]||[]).forEach(m=>{
        const tgt = playBoardEl.querySelector(`.sq[data-square="${m.to}"]`);
        if(tgt) tgt.classList.add('legal-target');
      });
    }
    function commitMove(from,to){
      const mv = (legalByFrom[from]||[]).find(m=>m.to===to);
      if(mv){
        pendingHumanMove = {from, to, uci: mv.uci};
        playHint.textContent = `${mv.uci} ready`;
        btnHumanMove.disabled = false;
      }
      cancelSelection();
    }
    function cancelSelection(){
      selectedFrom = null; dragging = false; if(ghostEl){ ghostEl.remove(); ghostEl=null; }
      clearHighlights();
    }
    function startDrag(cell){
      if(!cell) return; const sq = cell.dataset.square; if(!sq) return; selectedFrom = sq; highlightFrom(sq); dragging = true; btnHumanMove.disabled = true;
      // create ghost
      const pieceSpan = cell.querySelector('span');
      if(pieceSpan){
        ghostEl = document.createElement('div');
        ghostEl.className = 'drag-ghost';
        ghostEl.textContent = pieceSpan.textContent;
        document.body.appendChild(ghostEl);
      }
    }
    function updateGhostPosition(ev){ if(!ghostEl) return; ghostEl.style.left = (ev.clientX - 24) + 'px'; ghostEl.style.top = (ev.clientY - 24) + 'px'; }
    function squareAtPoint(ev){ const el = document.elementFromPoint(ev.clientX, ev.clientY); if(!el) return null; return el.closest('.sq'); }
    function onPointerDown(e){
      if(!humanTurn) return;
      const cell = e.currentTarget; const sq = cell.dataset.square;
      if(!sq || !legalByFrom[sq]) return;
      e.preventDefault();
      if(selectedFrom === sq){ cancelSelection(); return; }
      startDrag(cell);
    }
    function onPointerMove(e){ if(!dragging) return; updateGhostPosition(e); const cell = squareAtPoint(e); playBoardEl.querySelectorAll('.sq.hover-target').forEach(x=>x.classList.remove('hover-target')); if(cell){ const tgtSq = cell.dataset.square; if(tgtSq && selectedFrom && isLegalTarget(selectedFrom, tgtSq)) cell.classList.add('hover-target'); } }
    function onPointerUp(e){ if(!dragging) return; const cell = squareAtPoint(e); if(cell && selectedFrom){ const tgtSq = cell.dataset.square; if(tgtSq && isLegalTarget(selectedFrom, tgtSq)) { commitMove(selectedFrom, tgtSq); return; } }
      cancelSelection(); }
    function isLegalTarget(from,to){ return !!(legalByFrom[from] && legalByFrom[from].some(m=>m.to===to)); }
    // Click (non-drag) fallback
    playBoardEl.addEventListener('click', (e)=>{ if(!humanTurn) return; const cell = e.target.closest('.sq'); if(!cell) return; const sq = cell.dataset.square; if(!sq) return; if(selectedFrom && selectedFrom !== sq && isLegalTarget(selectedFrom, sq)){ commitMove(selectedFrom, sq); } else if(legalByFrom[sq]) { selectedFrom = sq; highlightFrom(sq); btnHumanMove.disabled = true; playHint.textContent = 'Select destination'; } });

    if(humanTurn){
      document.addEventListener('pointermove', onPointerMove, {passive:true});
      document.addEventListener('pointerup', onPointerUp, {once:true});
    }
    for(let r=0;r<8;r++){
      for(let c=0;c<8;c++){
        const cell=document.createElement('div'); cell.className='sq '+(((r+c)%2===0)?'light':'dark'); const p=rs[r][c];
        const squareName = coordFromDisplay({r,c}); cell.dataset.square = squareName;
        if(p){ const span=document.createElement('span'); span.className= /[A-Z]/.test(p)?'white':'black'; span.textContent = pieceGlyph(p); cell.appendChild(span);}        
        if(humanTurn) { cell.addEventListener('pointerdown', onPointerDown); }
        playBoardEl.appendChild(cell);
      }
    }
  }

  // ===== Init =====
  function initBoardGrid(){ boardEl?.style.setProperty('--rows',8); boardEl?.style.setProperty('--cols',8); playBoardEl?.style.setProperty('--rows',8); playBoardEl?.style.setProperty('--cols',8);}  
  initBoardGrid();
  // Pre-game: show starting position but disable interactions until session starts
  if(playBoardEl){
    playBoardEl.classList.add('disabled');
    drawBoardPlay('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1', {human_turn:false, legal_moves:[]});
  }
  loadGames(); loadAnalysis();
})();
