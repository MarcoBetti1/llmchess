(() => {
  // ==================== DOM REFS ====================
  const tabs = Array.from(document.querySelectorAll('.tab'));
  const panels = Array.from(document.querySelectorAll('.panel'));
  // Games viewer
  const gamesListEl = document.getElementById('gamesList');
  const gameSearchEl = document.getElementById('gameSearch');
  const gameMetaEl = document.getElementById('gameMeta');
  const boardEl = document.getElementById('board');
  const sliderEl = document.getElementById('slider');
  const moveInfoEl = document.getElementById('moveInfo');
  // Board controls
  const btnPrev = document.getElementById('btnPrev');
  const btnPlay = document.getElementById('btnPlay');
  const btnNext = document.getElementById('btnNext');
  const btnRestart = document.getElementById('btnRestart');
  const speedEl = document.getElementById('speed');
  const flipEl = document.getElementById('flip');
  // Runs panel
  const refreshRunsBtn = document.getElementById('refreshRuns');
  const newRunToggleBtn = document.getElementById('newRunToggle');
  const newRunForm = document.getElementById('newRunForm');
  const configsChooser = document.getElementById('configsChooser');
  const startRunBtn = document.getElementById('startRun');
  const runPythonInput = document.getElementById('runPython');
  const runsListEl = document.getElementById('runsList');
  const runConsoleSection = document.getElementById('runConsoleSection');
  const runStatusLine = document.getElementById('runStatusLine');
  const runLogEl = document.getElementById('runLog');
  const runProgressEl = document.getElementById('runProgress');
  const runProgressBar = runProgressEl.querySelector('.bar');
  const cancelRunBtn = document.getElementById('btnCancelRun');
  // Analysis panel
  const analysisFacetsEl = document.getElementById('analysisFacets');
  const analysisRefreshBtn = document.getElementById('analysisRefresh');
  const analysisRunBtn = document.getElementById('analysisRun');
  const analysisResultsEl = document.getElementById('analysisResults');

  // ==================== STATE ====================
  let allGames = [];
  let currentGame = null;
  let fens = [];
  let idx = 0;
  let playing = false;
  let timer = null;
  let flipped = false;
  let allConfigs = [];
  let runs = [];
  let activeRunId = null;
  let evtSource = null;
  let facetsCache = null;
  let facetSelections = { model: new Set(), config: new Set(), color: new Set(), opponent: new Set() };

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
    try {
      const res = await fetch('/api/games');
      const data = await res.json();
      allGames = data.games || [];
      renderGamesList();
    } catch (e) { console.warn('loadGames failed', e); }
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
    try {
      setPlaying(false);
      idx = 0;
      const res = await fetch(`/api/game?path=${encodeURIComponent(path)}`);
      currentGame = await res.json();
      const moves = currentGame.moves || [];
      fens = [currentGame.start_fen];
      for (const m of moves) if (m && m.fen_after) fens.push(m.fen_after);
      applyIdx();
      switchTab('games');
    } catch (e) { console.error('openGame failed', e); }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }

  // ==================== TAB HANDLING ====================
  function switchTab(name) {
    tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    panels.forEach(p => p.style.display = (p.dataset.panel === name) ? 'block' : 'none');
    if (name === 'runs') { loadRuns(); loadConfigs(); }
    else if (name === 'analysis') { loadFacets(); }
  }
  tabs.forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));

  // ==================== RUNS ====================
  async function loadConfigs() {
    try {
      const r = await fetch('/api/configs');
      const data = await r.json();
      allConfigs = data.configs || [];
      renderConfigsChooser();
    } catch(e) { console.warn('loadConfigs', e); }
  }
  function renderConfigsChooser() {
    if (!configsChooser) return;
    configsChooser.innerHTML='';
    allConfigs.forEach(c => {
      const id = `cfg_${btoa(c.rel_path).replace(/=/g,'')}`;
      const lab = document.createElement('label');
      lab.innerHTML = `<input type="checkbox" value="${escapeHtml(c.rel_path)}" id="${id}" /> <span>${escapeHtml(c.name)}</span>`;
      configsChooser.appendChild(lab);
    });
  }
  async function loadRuns() {
    try { const r = await fetch('/api/runs'); const data = await r.json(); runs = data.runs || []; renderRunsList(); } catch(e) { console.warn('loadRuns', e);} }
  function renderRunsList() {
    runsListEl.innerHTML='';
    runs.sort((a,b)=>(b.started_at||0)-(a.started_at||0));
    runs.forEach(r=>{
      const li = document.createElement('li');
      li.className = (r.run_id===activeRunId)?'active':'';
      const pct = ((r.progress?.fraction)||0)*100;
      li.innerHTML = `<div><strong>${r.run_id}</strong> <span class="pill">${r.status}</span></div><div class="meta">${r.configs.length} cfgs • ${r.progress.games_completed}/${r.progress.games_expected} • ${pct.toFixed(1)}%</div>`;
      li.addEventListener('click', ()=>attachRunStream(r.run_id));
      runsListEl.appendChild(li);
    });
  }
  newRunToggleBtn.addEventListener('click', ()=> newRunForm.classList.toggle('hidden'));
  startRunBtn.addEventListener('click', async ()=>{
    const sel = Array.from(configsChooser.querySelectorAll('input[type=checkbox]:checked')).map(i=>i.value);
    if(!sel.length){ alert('Select configs'); return; }
    startRunBtn.disabled=true;
    try {
      const r = await fetch('/api/runs',{method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({configs: sel, python: runPythonInput.value||undefined})});
      const d = await r.json();
      if(d.run_id){ activeRunId=d.run_id; attachRunStream(activeRunId); loadRuns(); }
      else alert('Failed to start');
    } catch(e){ alert('Start failed: '+e); }
    finally { startRunBtn.disabled=false; }
  });
  cancelRunBtn.addEventListener('click', async ()=>{ if(!activeRunId) return; await fetch(`/api/runs/${activeRunId}/cancel`,{method:'POST'}); });
  refreshRunsBtn.addEventListener('click', loadRuns);
  function appendRunLog(line){ runLogEl.textContent += line+'\n'; runLogEl.scrollTop = runLogEl.scrollHeight; }
  function attachRunStream(runId){
    activeRunId=runId; runConsoleSection.classList.remove('hidden'); runLogEl.textContent=''; runStatusLine.textContent='Streaming '+runId+'...';
    if(evtSource) evtSource.close();
    evtSource = new EventSource(`/api/runs/${runId}/stream`);
    evtSource.onmessage = ev => { try { const data = JSON.parse(ev.data); if(data.type==='log'){ appendRunLog(data.line);} else if(data.type==='progress'){ runStatusLine.textContent=`Games ${data.games_completed}/${data.games_expected} • ${(data.fraction*100).toFixed(1)}%`; runProgressBar.style.width=(data.fraction*100)+'%'; } else if(data.type==='snapshot'){ const pct=(data.status.progress.fraction*100).toFixed(1); runProgressBar.style.width=pct+'%'; runStatusLine.textContent=`${data.status.status} • ${data.status.progress.games_completed}/${data.status.progress.games_expected}`; (data.status.recent_logs||[]).forEach(l=>appendRunLog(l)); } else if(data.type==='end'){ runStatusLine.textContent='Run ended ('+data.status+')'; loadRuns(); } } catch(e){ console.warn('SSE parse', e);} };
    evtSource.onerror = ()=> appendRunLog('[stream error]');
  }

  // ==================== ANALYSIS ====================
  analysisRefreshBtn.addEventListener('click', loadFacets);
  analysisRunBtn.addEventListener('click', runAnalysisQuery);
  async function loadFacets(){ try { const r=await fetch('/api/analysis/facets'); facetsCache=await r.json(); buildFacetUI(); } catch(e){ console.warn('facets', e);} }
  function buildFacetUI(){ if(!facetsCache) return; analysisFacetsEl.innerHTML=''; const groups=[['model',facetsCache.models],['config',facetsCache.configs],['color',facetsCache.colors],['opponent',facetsCache.opponents]]; groups.forEach(([name,vals])=>{ const box=document.createElement('div'); box.className='facet'; box.innerHTML=`<h4>${name}</h4>`; const opts=document.createElement('div'); opts.className='facet-options'; (vals||[]).forEach(v=>{ const id=`${name}_${btoa(v).replace(/=/g,'')}`; const lbl=document.createElement('label'); const checked=facetSelections[name]?.has(v)?'checked':''; lbl.innerHTML=`<input type="checkbox" id="${id}" value="${escapeHtml(v)}" ${checked}/> <span>${escapeHtml(v)}</span>`; lbl.querySelector('input').addEventListener('change',e=>{ if(!facetSelections[name]) facetSelections[name]=new Set(); const tgt=e.target; if(tgt.checked) facetSelections[name].add(v); else facetSelections[name].delete(v); }); opts.appendChild(lbl); }); box.appendChild(opts); analysisFacetsEl.appendChild(box); }); }
  async function runAnalysisQuery(){ const qp=[]; ['model','config','color','opponent'].forEach(k=>{ const set=facetSelections[k]; if(set&&set.size) qp.push(`${k}=${encodeURIComponent(Array.from(set).join(','))}`); }); const url='/api/analysis/query'+(qp.length?'?'+qp.join('&'):''); analysisResultsEl.textContent='Loading...'; try { const r=await fetch(url); const data=await r.json(); renderAnalysisResults(data); } catch(e){ analysisResultsEl.textContent='Error'; } }
  function renderAnalysisResults(d){ const dec=(n,p=2)=> (typeof n==='number'? n.toFixed(p):'-'); const html=`<div class="summary">Games: ${d.total_games} | W:${d.w} D:${d.d} L:${d.l} | Win% ${(d.win_rate*100).toFixed(2)}%</div><div>Avg Legal ${(d.avg_legal_rate*100).toFixed(2)}% | Avg Plies ${dec(d.avg_plies,1)} | Avg Lat ${dec(d.avg_latency_ms,1)} ms</div><div class="active-filters">${renderActiveFilters(d.filters)}</div>`; analysisResultsEl.innerHTML=html; }
  function renderActiveFilters(filters){ if(!filters) return ''; const out=[]; Object.entries(filters).forEach(([k,v])=>{ if(v&&v.length) out.push(`<div class="pill">${k}: ${v.join(',')}</div>`); }); return out.join(''); }

  // ==================== CONTROLS ====================
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

  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); if (idx > 0) { idx--; applyIdx(); } }
    else if (e.key === 'ArrowRight') { e.preventDefault(); if (currentGame && idx < fens.length - 1) { idx++; applyIdx(); } }
    else if (e.key === ' ') { e.preventDefault(); setPlaying(!playing); }
  });

  function initBoardGrid(){ boardEl.style.setProperty('--rows',8); boardEl.style.setProperty('--cols',8); }
  initBoardGrid();
  loadGames();
  switchTab('games');
})();
