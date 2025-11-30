"""
Minimal Flask API that wires the existing llmchess engine into the UI.

Endpoints:
- POST /api/experiments              -> create/start an experiment (runs games in background)
- GET  /api/experiments              -> list experiment summaries
- GET  /api/experiments/<id>/results -> aggregate results and per-game rows
- GET  /api/games/<game_id>/conversation -> return the saved conversation log (if present)
- GET  /api/games/<game_id>/history       -> return the saved structured history (if present)
- GET  /api/games/live               -> placeholder (empty list)

Experiments are persisted to experiments_state.json and logs land under runs/<exp_id>/<game_id>/.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, request

from src.llmchess_simple.game import GameConfig, GameRunner
from src.llmchess_simple.llm_opponent import LLMOpponent
from src.llmchess_simple.prompting import PromptConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = Flask(__name__)
lock = threading.Lock()

STATE_PATH = Path("experiments_state.json")
LOG_ROOT = Path(os.environ.get("EXPERIMENT_LOG_DIR", "runs/demo"))
LOG_ROOT.mkdir(parents=True, exist_ok=True)


def load_state() -> Dict[str, dict]:
    if not STATE_PATH.exists():
        return {}
    try:
        raw = json.loads(STATE_PATH.read_text())
        return raw if isinstance(raw, dict) else {}
    except Exception:
        logging.exception("Failed to load state; starting fresh")
        return {}


def save_state(state: Dict[str, dict]) -> None:
    try:
        STATE_PATH.write_text(json.dumps(state, indent=2))
    except Exception:
        logging.exception("Failed to save state")


STATE: Dict[str, dict] = load_state()


def _prune_state_from_logs(state: Dict[str, dict]) -> Dict[str, dict]:
    """Drop experiments or game rows whose log folders/files no longer exist."""
    if not state:
        return {}
    refreshed: Dict[str, dict] = {}
    for exp_id, exp in state.items():
        exp_dir = LOG_ROOT / exp_id
        if not exp_dir.exists():
            continue  # skip experiments that no longer have logs
        game_rows = []
        for g in exp.get("game_rows", []):
            game_id = g.get("game_id")
            path = g.get("history_path")
            # Keep rows if their game directory exists, or if a history file already exists.
            game_dir = exp_dir / game_id if game_id else None
            if (game_dir and game_dir.exists()) or (path and Path(path).exists()):
                game_rows.append(g)
        exp_copy = dict(exp)
        exp_copy["game_rows"] = game_rows
        # keep completed count in sync with surviving rows
        try:
            exp_copy.setdefault("games", {})
            exp_copy["games"]["completed"] = len(game_rows)
        except Exception:
            pass
        refreshed[exp_id] = exp_copy
    # persist pruned state
    try:
        STATE_PATH.write_text(json.dumps(refreshed, indent=2))
    except Exception:
        logging.exception("Failed to persist pruned state")
    return refreshed


STATE = _prune_state_from_logs(STATE)


def snapshot_state() -> Dict[str, dict]:
    """
    Return a fresh copy of the persisted state. Falls back to in-memory state if load fails.
    This helps the UI reflect manual deletions or restarts without needing a server reboot.
    """
    try:
        loaded = load_state()
        return _prune_state_from_logs(loaded)
    except Exception:
        logging.exception("Failed to snapshot state from disk; using in-memory STATE")
        return _prune_state_from_logs(STATE.copy())


def _ensure_prompt_mode(mode: Optional[str]) -> str:
    if not mode:
        return "fen+plaintext"
    mode = mode.lower()
    if mode not in {"plaintext", "fen", "fen+plaintext"}:
        return "fen+plaintext"
    return mode


def _game_winner_from_result(result: str) -> Optional[str]:
    if result == "1-0":
        return "white"
    if result == "0-1":
        return "black"
    if result in ("1/2-1/2", "draw"):
        return "draw"
    return None


def _init_experiment_record(payload: dict) -> dict:
    total = int(payload.get("games", {}).get("total", 0) or 0)
    a_as_white = int(payload.get("games", {}).get("a_as_white", total // 2))
    b_as_white = int(payload.get("games", {}).get("b_as_white", total - a_as_white))
    exp_id = payload.get("experiment_id") or f"exp_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    record = {
        "experiment_id": exp_id,
        "name": payload.get("name") or exp_id,
        "status": "queued",
        "players": payload.get("players") or {"a": {"model": "openai/gpt-4o"}, "b": {"model": "openai/gpt-4o-mini"}},
        "games": {"total": total, "completed": 0, "a_as_white": a_as_white, "b_as_white": b_as_white},
        "wins": {"player_a": 0, "player_b": 0, "draws": 0},
        "prompt": {"mode": _ensure_prompt_mode(payload.get("prompt", {}).get("mode"))},
        "illegal_move_limit": int(payload.get("illegal_move_limit", 1)),  # GameRunner ends on first illegal
        "game_rows": [],
        "avg_plies": 0,
        "avg_duration_s": 0,
        "started_at": None,
        "finished_at": None,
    }
    return record


def _persist_update() -> None:
    save_state(STATE)


def _run_experiment(exp_id: str) -> None:
    with lock:
        exp = STATE.get(exp_id)
    if not exp:
        return
    exp["status"] = "running"
    exp["started_at"] = time.time()
    _persist_update()

    total = exp["games"]["total"]
    a_as_white = exp["games"].get("a_as_white", total // 2)
    b_as_white = exp["games"].get("b_as_white", total - a_as_white)
    prompt_mode = exp.get("prompt", {}).get("mode", "fen+plaintext")
    prompt_cfg = PromptConfig(mode=prompt_mode)
    game_rows: List[dict] = exp.get("game_rows") or []
    wins = exp.get("wins") or {"player_a": 0, "player_b": 0, "draws": 0}

    for idx in range(total):
        white_is_a = idx < a_as_white
        white_model = exp["players"]["a"]["model"] if white_is_a else exp["players"]["b"]["model"]
        black_model = exp["players"]["b"]["model"] if white_is_a else exp["players"]["a"]["model"]
        game_id = f"{exp_id}_g{idx+1:04d}"
        log_dir = LOG_ROOT / exp_id / game_id
        log_dir.mkdir(parents=True, exist_ok=True)
        game_row = {
            "game_id": game_id,
            "white_model": white_model,
            "black_model": black_model,
            "white_player": "a" if white_is_a else "b",
            "winner": None,
            "illegal_moves": 0,
            "illegal_white": 0,
            "illegal_black": 0,
            "termination_reason": None,
            "plies_total": 0,
            "duration_s": 0,
            "conversation_path": str(log_dir / "conversation.json"),
            "history_path": str(log_dir / "history.json"),
        }
        with lock:
            game_rows.append(game_row)
            if exp := STATE.get(exp_id):
                exp["game_rows"] = game_rows
                _persist_update()

        cfg = GameConfig(
            color="white",  # main model plays white for this game instance
            prompt_cfg=prompt_cfg,
            opponent_prompt_cfg=prompt_cfg,
            conversation_log_path=str(log_dir),
            conversation_log_every_turn=True,
            game_log=False,
        )
        opp = LLMOpponent(model=black_model, prompt_cfg=prompt_cfg)
        runner = GameRunner(model=white_model, opponent=opp, cfg=cfg)

        result = "*"
        illegal_white = illegal_black = plies_total = 0
        duration_s = 0
        termination_reason = None
        conversation_path = None
        history_path = None
        try:
            result = runner.play()
            metrics = runner.metrics()
            summary = runner.summary()
            illegal_white = metrics.get("llm_illegal_moves", 0)
            illegal_black = metrics.get("opponent_illegal_moves", 0)
            plies_total = metrics.get("plies_total", 0)
            duration_s = metrics.get("duration_s", 0)
            termination_reason = metrics.get("termination_reason")
            conversation_path = str(runner.cfg.conversation_log_path) if runner.cfg.conversation_log_path else None
            history_path = summary.get("structured_history_path") or runner._structured_history_path()
            if history_path:
                history_path = str(history_path)
        except Exception as exc:  # noqa: BLE001
            logging.exception("Experiment %s game %s failed", exp_id, game_id)
            termination_reason = f"error:{exc}"

        winner_color = _game_winner_from_result(result)
        if winner_color == "white":
            wins["player_a" if white_is_a else "player_b"] += 1
        elif winner_color == "black":
            wins["player_b" if white_is_a else "player_a"] += 1
        elif winner_color == "draw":
            wins["draws"] += 1

        # update the row we seeded earlier
        game_rows = [g for g in game_rows if g.get("game_id") != game_id]
        game_rows.append(
            {
                "game_id": game_id,
                "white_model": white_model,
                "black_model": black_model,
                "white_player": "a" if white_is_a else "b",
                "winner": winner_color,
                "illegal_moves": illegal_white + illegal_black,
                "illegal_white": illegal_white,
                "illegal_black": illegal_black,
                "termination_reason": termination_reason,
                "plies_total": plies_total,
                "duration_s": duration_s,
                "conversation_path": conversation_path,
                "history_path": history_path,
            }
        )

        with lock:
            exp = STATE.get(exp_id)
            if not exp:
                return
            exp["games"]["completed"] = idx + 1
            exp["wins"] = wins
            exp["game_rows"] = game_rows
            _persist_update()

    avg_plies = 0
    avg_duration = 0
    if game_rows:
        avg_plies = sum(g.get("plies_total", 0) for g in game_rows) / len(game_rows)
        avg_duration = sum(g.get("duration_s", 0) for g in game_rows) / len(game_rows)

    with lock:
        exp = STATE.get(exp_id)
        if exp:
            exp["status"] = "finished"
            exp["wins"] = wins
            exp["avg_plies"] = avg_plies
            exp["avg_duration_s"] = avg_duration
            exp["finished_at"] = time.time()
            _persist_update()


def _start_experiment_thread(exp_id: str) -> None:
    t = threading.Thread(target=_run_experiment, args=(exp_id,), daemon=True)
    t.start()


def _find_game_record(game_id: str) -> Optional[dict]:
    state = snapshot_state()
    for exp in state.values():
        for g in exp.get("game_rows", []):
            if g.get("game_id") == game_id:
                return g
    return None


@app.route("/api/experiments", methods=["POST"])
def create_experiment():
    data = request.get_json(force=True) or {}
    total = int(data.get("games", {}).get("total", 0) or 0)
    if total <= 0:
        return jsonify({"error": "games.total must be > 0"}), 400
    record = _init_experiment_record(data)
    exp_id = record["experiment_id"]
    with lock:
        STATE[exp_id] = record
        _persist_update()
    _start_experiment_thread(exp_id)
    return jsonify({"experiment_id": exp_id})


@app.route("/api/experiments", methods=["GET"])
def list_experiments():
    values = list(snapshot_state().values())
    summaries = [
        {
            "experiment_id": exp["experiment_id"],
            "name": exp.get("name"),
            "status": exp.get("status", "queued"),
            "players": exp.get("players", {}),
            "games": {
                "total": exp.get("games", {}).get("total", 0),
                "completed": exp.get("games", {}).get("completed", 0),
            },
            "wins": exp.get("wins"),
        }
        for exp in values
    ]
    return jsonify(summaries)


@app.route("/api/experiments/<exp_id>/results", methods=["GET"])
def experiment_results(exp_id: str):
    exp = snapshot_state().get(exp_id)
    if not exp:
        return jsonify({"error": "not found"}), 404
    game_rows = exp.get("game_rows", [])
    total_games = exp.get("games", {}).get("total", 0)
    avg_plies = exp.get("avg_plies", 0)
    wins = exp.get("wins", {"player_a": 0, "player_b": 0, "draws": 0})

    illegal_a_total = illegal_b_total = 0
    for g in game_rows:
        if g.get("white_player") == "a":
            illegal_a_total += g.get("illegal_white", 0)
            illegal_b_total += g.get("illegal_black", 0)
        else:
            illegal_a_total += g.get("illegal_black", 0)
            illegal_b_total += g.get("illegal_white", 0)

    completed = len(game_rows) if game_rows else exp.get("games", {}).get("completed", 0)
    illegal_move_stats = {
        "player_a_avg": (illegal_a_total / completed) if completed else 0,
        "player_b_avg": (illegal_b_total / completed) if completed else 0,
    }

    return jsonify(
        {
            "experiment_id": exp_id,
            "wins": wins,
            "total_games": total_games,
            "avg_game_length_plies": avg_plies,
            "illegal_move_stats": illegal_move_stats,
            "games": [
                {
                    "game_id": g.get("game_id"),
                    "white_model": g.get("white_model"),
                    "black_model": g.get("black_model"),
                    "winner": g.get("winner"),
                    "illegal_moves": g.get("illegal_moves", 0),
                }
                for g in game_rows
            ],
        }
    )


@app.route("/api/games/<game_id>/conversation", methods=["GET"])
def game_conversation(game_id: str):
    rec = _find_game_record(game_id)
    if rec and rec.get("conversation_path") and Path(rec["conversation_path"]).exists():
        with open(rec["conversation_path"], "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    # Fallback: search on disk in case state is stale
    search_root = Path(LOG_ROOT)
    for path in search_root.rglob(f"{game_id}"):
        conv = path / "conversation.json"
        if conv.exists():
            with open(conv, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
    return jsonify({"error": "not found"}), 404


@app.route("/api/games/<game_id>/history", methods=["GET"])
def game_history(game_id: str):
    rec = _find_game_record(game_id)
    if rec and rec.get("history_path") and Path(rec["history_path"]).exists():
        with open(rec["history_path"], "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    # Fallback: search on disk if state is stale or missing
    search_root = Path(LOG_ROOT)
    for path in search_root.rglob(f"{game_id}"):
        # prefer exact history.json, else any hist_* file
        hist_exact = path / "history.json"
        if hist_exact.exists():
            with open(hist_exact, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        for hist_file in path.glob("hist_*.json"):
            with open(hist_file, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
    return jsonify({"error": "not found"}), 404


@app.route("/api/games/live", methods=["GET"])
def games_live():
    # Placeholder: no live registry wired yet.
    return jsonify([])


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    # Prevent caching so the UI always sees the freshest state/history
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/api/<path:path>", methods=["OPTIONS"])
def cors_preflight(path: str):
    resp = app.make_response(("", 204))
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
