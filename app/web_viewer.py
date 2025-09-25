#!/usr/bin/env python3
import argparse
import json
import os
import threading
import queue
import time
from pathlib import Path
from typing import List, Dict
import sys
import chess  # needed for play state logic

from flask import Flask, jsonify, request, send_from_directory, abort, Response

THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parent.parent  # repository root
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import core modules for running tests and games (after path injection)
try:
    from src.llmchess_simple.batch_orchestrator import BatchOrchestrator
    from src.llmchess_simple.game import GameConfig, GameRunner
    from src.llmchess_simple.human_opponent import HumanOpponent
    from src.llmchess_simple.prompting import PromptConfig
except ModuleNotFoundError as e:
    raise SystemExit(f"Failed to import project modules: {e}. Ensure you run this script from the repository root.")

WEBUI_DIR = PROJECT_ROOT / "app" / "webui"
RUNS_DIR = PROJECT_ROOT / "runs"

app = Flask(
    __name__,
    static_folder=str(WEBUI_DIR),
    static_url_path="/static",
)

# -------------------- In-memory state --------------------
_test_runs: dict[str, dict] = {}
_play_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{int(time.time()*1000):x}"  # simple timestamp hex id


def find_hist_files(base: Path) -> List[Path]:
    files: List[Path] = []
    if not base.exists():
        return files
    for root, _dirs, filenames in os.walk(base):
        for fn in filenames:
            if fn.startswith("hist_") and fn.endswith(".json"):
                files.append(Path(root) / fn)
    files.sort()
    return files


def summarize_game(path: Path) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        headers = data.get("headers", {})
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        # Derive llm_color from new structured history format. Fallback to legacy flag if present.
        llm_color = None
        players = data.get("players") or {}
        llm_entry = players.get("LLM") if isinstance(players, dict) else None
        if isinstance(llm_entry, str) and llm_entry.lower() in ("white", "black"):
            llm_color = llm_entry.lower()
        else:
            legacy_flag = data.get("llm_is_white")
            if isinstance(legacy_flag, bool):
                llm_color = "white" if legacy_flag else "black"
        return {
            "path": rel,
            "event": headers.get("Event", ""),
            "date": headers.get("Date", ""),
            "white": headers.get("White", ""),
            "black": headers.get("Black", ""),
            "result": data.get("result", ""),
            "llm_color": llm_color,
        }
    except Exception:
        # If a file is malformed, skip with minimal info
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        return {"path": rel, "event": "(unreadable)", "date": "", "white": "", "black": "", "result": ""}


@app.route("/")
def index():
    # Serve the app shell
    return send_from_directory(str(WEBUI_DIR), "index.html")


@app.route("/api/games")
def api_games():
    files = find_hist_files(RUNS_DIR)
    items = [summarize_game(p) for p in files]
    # newest first (by path name sort typically timestamped)
    items.sort(key=lambda x: x.get("path", ""), reverse=True)
    return jsonify({"games": items})


@app.route("/api/game")
def api_game():
    rel_path = request.args.get("path", type=str)
    if not rel_path:
        abort(400, "Missing 'path' query parameter")
    # Only allow under runs/
    abs_path = (PROJECT_ROOT / rel_path).resolve()
    try:
        abs_path.relative_to(RUNS_DIR)
    except Exception:
        abort(400, "Path must be under runs/")
    if not abs_path.exists():
        abort(404, "File not found")
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        abort(500, f"Failed to load game: {e}")


@app.route("/health")
def health():
    return jsonify({"ok": True})


# ================== TEST RUN (BATCH) ENDPOINTS ==================
@app.route("/api/test/run", methods=["POST"])
def api_test_run():
    """Start a test run (batch mode). Body JSON fields:
    model, games, opponent(engine|random), depth, movetime_ms, max_illegal, prompt_mode
    Returns run_id.
    """
    data = request.get_json(force=True) or {}
    model = data.get("model")
    games = int(data.get("games", 2))
    opponent = data.get("opponent", "engine")
    depth = data.get("depth", 6)
    movetime = data.get("movetime_ms")
    max_illegal = int(data.get("max_illegal", 1))
    prompt_mode = data.get("prompt_mode", "plaintext")
    color = data.get("color", "white")
    out_dir = data.get("out_dir") or str(RUNS_DIR / "web")
    os.makedirs(out_dir, exist_ok=True)

    pcfg = PromptConfig(mode=prompt_mode)
    gcfg = GameConfig(color=color, max_illegal_moves=max_illegal, prompt_cfg=pcfg, conversation_log_path=out_dir, conversation_log_every_turn=True, game_log=False)
    run_id = _gen_id("run")
    q_progress: "queue.Queue[dict]" = queue.Queue()

    def _thread():
        orch = BatchOrchestrator(model=model, num_games=games, opponent=opponent, depth=depth, movetime_ms=movetime, engine="Stockfish", base_cfg=gcfg, prefer_batches=True)
        def _progress(snap):
            q_progress.put({"type": "progress", "snap": snap})
        summaries = orch.run(progress_cb=_progress)
        q_progress.put({"type": "done", "summaries": summaries})

    t = threading.Thread(target=_thread, daemon=True)
    with _lock:
        _test_runs[run_id] = {"queue": q_progress, "started": time.time(), "model": model}
    t.start()
    return jsonify({"run_id": run_id})


@app.route("/api/test/stream/<run_id>")
def api_test_stream(run_id: str):
    """Server-Sent Events stream of progress for a test run."""
    run = _test_runs.get(run_id)
    if not run:
        abort(404, "run not found")
    q: queue.Queue = run["queue"]  # type: ignore

    def event_stream():
        # Send initial hello
        yield f"event: hello\ndata: {json.dumps({'run_id': run_id})}\n\n"
        while True:
            try:
                item = q.get(timeout=1.0)
            except queue.Empty:
                # periodic keepalive
                yield "event: keepalive\n\n"
                continue
            if item["type"] == "progress":
                payload = item["snap"]
                yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
            elif item["type"] == "done":
                yield f"event: done\ndata: {json.dumps(item['summaries'])}\n\n"
                break
        yield "event: end\n\n"
    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/test/analysis")
def api_test_analysis():
    """Lightweight aggregated stats across existing game histories (legal rate, results)."""
    files = find_hist_files(RUNS_DIR)
    total = 0
    wins = draws = losses = 0
    for p in files:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            res = data.get("result", "*")
            if res == "1-0":
                wins += 1
            elif res == "0-1":
                losses += 1
            elif res == "1/2-1/2":
                draws += 1
            total += 1
        except Exception:
            pass
    return jsonify({"games_indexed": total, "wins": wins, "draws": draws, "losses": losses})


# ================== INTERACTIVE PLAY SESSION ==================
@app.route("/api/play/start", methods=["POST"])
def api_play_start():
    data = request.get_json(force=True) or {}
    model = data.get("model")
    color = data.get("color", "white")
    prompt_mode = data.get("prompt_mode", "plaintext")
    max_illegal = int(data.get("max_illegal", 1))
    pcfg = PromptConfig(mode=prompt_mode)
    human_is_white = (color == "black")  # if model plays black, human is white (kept for clarity / future use)
    # Opponent is human
    human = HumanOpponent()
    gcfg = GameConfig(color=color, max_illegal_moves=max_illegal, prompt_cfg=pcfg, conversation_log_path=None, conversation_log_every_turn=False, game_log=False)
    runner = GameRunner(model=model, opponent=human, cfg=gcfg)
    sess_id = _gen_id("play")
    with _lock:
        _play_sessions[sess_id] = {"runner": runner, "human": human, "llm_pending": False}
    if runner.needs_llm_turn():
        _start_llm_async(sess_id)
    return jsonify({"session_id": sess_id, "fen": runner.ref.board.fen(), "llm_color": color})


@app.route("/api/play/state/<sess_id>")
def api_play_state(sess_id: str):
    sess = _play_sessions.get(sess_id)
    if not sess:
        abort(404, "session not found")
    r: GameRunner = sess["runner"]
    return jsonify(_session_state_payload(r, sess))


def _session_state_payload(r: GameRunner, sess: dict) -> dict:
    conv = r.export_conversation()
    history = r.export_structured_history()
    llm_white = (r.llm_color == "white")
    human_white = not llm_white
    pending = bool(sess.get("llm_pending"))
    human_turn = (r.ref.board.turn == (chess.WHITE if human_white else chess.BLACK)) and r.ref.status() == "*" and not pending
    legal_moves: List[dict] = []
    if human_turn:
        for mv in r.ref.board.legal_moves:
            uci = mv.uci()
            frm = chess.square_name(mv.from_square)
            to = chess.square_name(mv.to_square)
            promo = uci[4] if len(uci) == 5 else None
            legal_moves.append({"uci": uci, "from": frm, "to": to, "promotion": promo})
    pending_for_ms = 0
    if pending:
        start = sess.get("llm_start", 0) or 0
        pending_for_ms = int((time.time() - start) * 1000)
    return {
        "fen": r.ref.board.fen(),
        "result": r.ref.status(),
        "termination_reason": r.termination_reason,
        "conversation": conv,
        "moves": history.get("moves", []),
        "llm_color": "white" if llm_white else "black",
        "human_turn": human_turn,
        "legal_moves": legal_moves,
        "llm_pending": pending,
        "llm_pending_for_ms": pending_for_ms,
        "llm_last_duration_ms": sess.get("llm_last_duration_ms"),
    }

def _start_llm_async(sess_id: str):
    sess = _play_sessions.get(sess_id)
    if not sess:
        return
    if sess.get("llm_pending"):
        return
    r: GameRunner = sess["runner"]
    if r.ref.status() != "*" or not r.needs_llm_turn():
        return
    sess["llm_pending"] = True
    sess["llm_start"] = time.time()

    def _worker():
        try:
            ok, uci, san, ms, meta = r._llm_turn_standard()
            r.records.append({"actor": "LLM", "uci": uci, "ok": ok, "san": san, "ms": ms, "meta": meta})
            if not ok:
                illegal = sum(1 for rec in r.records if rec.get("actor") == "LLM" and not rec.get("ok"))
                if illegal >= r.cfg.max_illegal_moves:
                    r.termination_reason = "illegal_llm_move"
            r.finalize_if_terminated()
        finally:
            sess["llm_pending"] = False
            sess["llm_last_duration_ms"] = int((time.time() - sess.get("llm_start", time.time())) * 1000)
            sess.pop("llm_start", None)

    threading.Thread(target=_worker, daemon=True).start()


@app.route("/api/play/human_move", methods=["POST"])
def api_play_human_move():
    data = request.get_json(force=True) or {}
    sess_id = data.get("session_id")
    uci = data.get("uci")
    sess = _play_sessions.get(sess_id)
    if not sess:
        abort(404, "session not found")
    r: GameRunner = sess["runner"]
    human: HumanOpponent = sess["human"]
    # Apply human move via opponent object and GameRunner.step_opponent mechanics
    try:
        human.provide_move(uci)
        ok, san = r.ref.apply_uci(uci)
        r.records.append({"actor": "HUMAN", "uci": uci, "ok": ok, "san": san})
    except Exception as e:
        abort(400, f"Bad move: {e}")
    # Start async LLM turn if needed
    if r.ref.status() == "*" and r.needs_llm_turn():
        _start_llm_async(sess_id)
    return jsonify(_session_state_payload(r, sess))


@app.route("/api/play/llm_turn", methods=["POST"])
def api_play_llm_turn():
    data = request.get_json(force=True) or {}
    sess_id = data.get("session_id")
    sess = _play_sessions.get(sess_id)
    if not sess:
        abort(404, "session not found")
    r: GameRunner = sess["runner"]
    if r.ref.status() != "*":
        return jsonify(_session_state_payload(r, sess))
    if r.needs_llm_turn():
        _start_llm_async(sess_id)
    return jsonify(_session_state_payload(r, sess))


def main():
    parser = argparse.ArgumentParser(description="LLM Chess web viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Ensure webui assets exist
    if not WEBUI_DIR.exists():
        print(f"Web assets directory not found: {WEBUI_DIR}")
        print("Please ensure the 'webui' folder exists.")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
