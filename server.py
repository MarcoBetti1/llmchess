"""
Minimal Flask API that wires the existing llmchess engine into the UI.

Endpoints:
- POST /api/experiments              -> create/start an experiment (runs games in background)
- GET  /api/experiments              -> list experiment summaries
- GET  /api/experiments/<id>/results -> aggregate results and per-game rows
- POST /api/human-games              -> start a human vs AI game (no disk logging)
- POST /api/human-games/<id>/move    -> submit a human move and receive the AI reply
- GET  /api/games/<game_id>/conversation -> return the saved conversation log (if present)
- GET  /api/games/<game_id>/history       -> return the saved structured history (if present)
- GET  /api/games/live               -> placeholder (empty list)

Experiments are persisted to experiments_state.json and logs land under runs/<exp_id>/<game_id>/.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import chess
from flask import Flask, jsonify, request

from src.llmchess_simple.game import GameConfig, GameRunner
from src.llmchess_simple.llm_opponent import LLMOpponent
from src.llmchess_simple.prompting import DEFAULT_SYSTEM_INSTRUCTIONS, DEFAULT_TEMPLATE, PromptConfig
from src.llmchess_simple.user_opponent import UserOpponent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = Flask(__name__)
lock = threading.Lock()
human_lock = threading.Lock()

STATE_PATH = Path("experiments_state.json")
LOG_ROOT = Path(os.environ.get("EXPERIMENT_LOG_DIR", "runs/demo"))
LOG_ROOT.mkdir(parents=True, exist_ok=True)
MAX_PARALLEL_GAMES = max(1, int(os.environ.get("EXPERIMENT_MAX_CONCURRENCY", 4)))
HUMAN_GAMES: Dict[str, dict] = {}
HUMAN_GAME_TTL_S = 3600  # drop inactive human games after an hour to avoid leaks


def _slugify_experiment_name(name: str) -> str:
    """Return a slug suitable for IDs and folder names (no spaces)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned


def _safe_experiment_dir_name(name: str) -> str:
    """Return a readable yet filesystem-safe directory name (keeps spaces)."""
    cleaned = re.sub(r"[<>:\"/\\\\|?*]+", "_", name.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    if cleaned in {"", ".", ".."}:
        return ""
    return cleaned


def _experiment_identity_from_payload(payload: dict) -> tuple[str, str, str]:
    """
    Derive (experiment_id, display_name, log_dir_name) from the incoming payload.
    - experiment_id: used in API responses/URLs
    - display_name: user-facing name (may contain spaces)
    - log_dir_name: folder on disk; sanitized but keeps spaces when possible
    """
    raw_name = (payload.get("name") or "").strip()
    requested_id = payload.get("experiment_id")
    slug = _slugify_experiment_name(raw_name) if raw_name else ""
    exp_id = requested_id or slug or f"exp_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    folder_source = payload.get("log_dir_name") or raw_name or exp_id
    log_dir_name = _safe_experiment_dir_name(folder_source) or exp_id
    display_name = raw_name or log_dir_name or exp_id
    return exp_id, display_name, log_dir_name


def _experiment_dir_in_use(log_dir_name: str) -> bool:
    """Return True if the log directory already holds any files (existing results)."""
    exp_dir = LOG_ROOT / log_dir_name
    if not exp_dir.exists():
        return False
    try:
        next(exp_dir.iterdir())
        return True
    except StopIteration:
        return False
    except Exception:
        logging.exception("Failed to inspect experiment dir %s", exp_dir)
        return True


def _safe_remove_dir(path: Path) -> bool:
    """Remove a directory under LOG_ROOT safely. Returns True on deletion attempt."""
    try:
        root = LOG_ROOT.resolve()
        target = path.resolve()
        try:
            target.relative_to(root)
        except ValueError:
            logging.warning("Refusing to delete path outside log root: %s", target)
            return False
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            return True
    except Exception:
        logging.exception("Failed to delete directory %s", path)
    return False


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
        exp_dir = LOG_ROOT / (exp.get("log_dir_name") or exp_id)
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
        exp_copy.setdefault("log_dir_name", exp.get("log_dir_name") or exp_id)
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
    # Legacy helper retained for compatibility; no longer used in new prompt flow.
    return "custom"


def _prompt_cfg_from_payload(payload: Optional[dict]) -> PromptConfig:
    payload = payload or {}
    return PromptConfig(
        mode="custom",
        system_instructions=payload.get("system_instructions") or DEFAULT_SYSTEM_INSTRUCTIONS,
        template=payload.get("template") or DEFAULT_TEMPLATE,
        starting_context_enabled=payload.get("starting_context_enabled", True),
    )


def _game_winner_from_result(result: str) -> Optional[str]:
    if result == "1-0":
        return "white"
    if result == "0-1":
        return "black"
    if result in ("1/2-1/2", "draw"):
        return "draw"
    return None


def _ai_color_for_human(human_side: str) -> str:
    return "black" if str(human_side).lower() == "white" else "white"


def _winner_label_from_result(result: str, human_side: str) -> Optional[str]:
    color = _game_winner_from_result(result)
    if color == "draw":
        return "draw"
    if color is None:
        return None
    return "human" if color == human_side else "ai"


def _board_termination_reason(board: chess.Board) -> Optional[str]:
    """Derive a readable termination reason from a finished board."""
    try:
        if board.is_checkmate():
            return "checkmate"
        if board.is_stalemate():
            return "stalemate"
        if board.is_insufficient_material():
            return "insufficient_material"
        if board.is_seventyfive_moves():
            return "seventyfive_move_rule"
        if board.is_fivefold_repetition():
            return "fivefold_repetition"
        if board.is_fifty_moves():
            return "fifty_move_rule"
        if board.is_repetition():
            return "threefold_repetition"
    except Exception:
        pass
    if board.is_game_over():
        return "game_over"
    return None


def _cleanup_stale_human_games(max_age_s: int = HUMAN_GAME_TTL_S):
    now = time.time()
    with human_lock:
        expired = [gid for gid, sess in HUMAN_GAMES.items() if now - sess.get("updated_at", now) > max_age_s]
        for gid in expired:
            HUMAN_GAMES.pop(gid, None)


def _append_conversation(session: dict, msg: dict):
    if not msg or not msg.get("content"):
        return
    session.setdefault("conversation", []).append(msg)
    session["updated_at"] = time.time()


def _record_ai_conversation(session: dict, meta: dict | None, raw_fallback: str | None = None):
    """Store system/user/assistant messages for the AI turn."""
    meta = meta or {}
    raw = meta.get("raw") or meta.get("assistant_raw") or raw_fallback
    sys_prompt = meta.get("system")
    prompt = meta.get("prompt")
    model = session.get("model")
    side = session.get("ai_side")

    if sys_prompt and not session.get("ai_system_logged"):
        _append_conversation(session, {"role": "system", "content": sys_prompt, "actor": "ai", "model": model, "side": side})
        session["ai_system_logged"] = True
    if prompt:
        _append_conversation(session, {"role": "user", "content": prompt, "actor": "ai_prompt", "model": model, "side": side})
    if raw:
        _append_conversation(session, {"role": "assistant", "content": raw, "actor": "ai", "model": model, "side": side})


def _init_experiment_record(payload: dict) -> dict:
    total = int(payload.get("games", {}).get("total", 0) or 0)
    a_as_white = int(payload.get("games", {}).get("a_as_white", total // 2))
    b_as_white = int(payload.get("games", {}).get("b_as_white", total - a_as_white))
    exp_id, display_name, log_dir_name = _experiment_identity_from_payload(payload)
    record = {
        "experiment_id": exp_id,
        "name": display_name,
        "log_dir_name": log_dir_name,
        "status": "queued",
        "players": payload.get("players") or {"a": {"model": "openai/gpt-4o"}, "b": {"model": "openai/gpt-4o-mini"}},
        "games": {"total": total, "completed": 0, "a_as_white": a_as_white, "b_as_white": b_as_white},
        "wins": {"player_a": 0, "player_b": 0, "draws": 0},
        "prompt": {
            "system_instructions": payload.get("prompt", {}).get("system_instructions", DEFAULT_SYSTEM_INSTRUCTIONS),
            "template": payload.get("prompt", {}).get("template", DEFAULT_TEMPLATE),
        },
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


def _side_to_move(board: chess.Board) -> str:
    return "white" if board.turn == chess.WHITE else "black"


def _mark_finished(session: dict, result: str, reason: str):
    runner: GameRunner = session["runner"]
    session["status"] = "finished"
    session["termination_reason"] = reason
    session["winner"] = _winner_label_from_result(result, session["human_side"])
    runner.termination_reason = reason
    try:
        runner.ref.set_result(result, reason)
    except Exception:
        runner.ref.set_result(result or "*", reason)


def _serialize_human_session(session: dict, fen_after_human: Optional[str] = None, ai_move: Optional[dict] = None, fen_after_ai: Optional[str] = None) -> dict:
    board_fen = session["runner"].ref.board.fen()
    return {
        "status": "finished" if session.get("status") == "finished" else "ok",
        "game_status": session.get("status", "running"),
        "fen_after_human": fen_after_human,
        "ai_move": ai_move,
        "fen_after_ai": fen_after_ai,
        "ai_reply_raw": session.get("last_ai_raw"),
        "ai_illegal_move_count": session.get("ai_illegal_move_count", 0),
        "winner": session.get("winner"),
        "termination_reason": session.get("termination_reason"),
        "current_fen": board_fen,
        "side_to_move": _side_to_move(session["runner"].ref.board),
        "conversation": session.get("conversation", []),
    }


def _human_to_move(session: dict) -> bool:
    side = _side_to_move(session["runner"].ref.board)
    return side == session["human_side"]


def _ai_to_move(session: dict) -> bool:
    side = _side_to_move(session["runner"].ref.board)
    return side == session["ai_side"]


def _play_ai_turn(session: dict) -> tuple[Optional[dict], str]:
    """Execute one AI turn using the runner; returns (ai_move_dict, fen_after_ai)."""
    runner: GameRunner = session["runner"]
    try:
        ok, uci, san, ms, meta = runner._llm_turn_standard()
        _record_ai_conversation(session, meta)
    except Exception as exc:  # noqa: BLE001
        logging.exception("AI move failed for human game %s", session.get("id"))
        session["ai_illegal_move_count"] = session.get("ai_illegal_move_count", 0) + 1
        result = "0-1" if session["ai_side"] == "white" else "1-0"
        _mark_finished(session, result, f"ai_move_error:{exc}")
        return None, runner.ref.board.fen()
    session["last_ai_raw"] = meta.get("raw") if meta else None
    runner.records.append({"actor": "LLM", "uci": uci, "ok": ok, "ms": ms, "san": san, "meta": meta})
    runner._global_ply = getattr(runner, "_global_ply", 0) + 1
    session["updated_at"] = time.time()

    if not ok:
        session["ai_illegal_move_count"] = session.get("ai_illegal_move_count", 0) + 1
        result = "0-1" if session["ai_side"] == "white" else "1-0"
        _mark_finished(session, result, "illegal_ai_move")
        return {"uci": uci, "san": san}, runner.ref.board.fen()

    if runner.ref.board.is_game_over():
        result = runner.ref.status()
        if result == "*":
            try:
                result = runner.ref.board.result()
            except Exception:
                result = "*"
        reason = _board_termination_reason(runner.ref.board) or "normal_game_end"
        _mark_finished(session, result, reason)
    return {"uci": uci, "san": san}, runner.ref.board.fen()


def _apply_human_move(session: dict, raw_move: str) -> tuple[Optional[str], bool, Optional[str]]:
    """Apply a human move in SAN or UCI. Returns (san, ok, error_reason)."""
    runner: GameRunner = session["runner"]
    board = runner.ref.board
    mv = None
    raw_move = (raw_move or "").strip()
    if not raw_move:
        return None, False, "missing_move"
    try:
        candidate = chess.Move.from_uci(raw_move)
        if candidate in board.legal_moves:
            mv = candidate
    except Exception:
        mv = None
    if mv is None:
        try:
            candidate = board.parse_san(raw_move)
            if candidate in board.legal_moves:
                mv = candidate
        except Exception:
            mv = None
    if mv is None or mv not in board.legal_moves:
        return None, False, "illegal_move"

    san = runner.ref.engine_apply(mv)
    _append_conversation(session, {"role": "human", "content": f"You played {san} ({mv.uci()})", "actor": "human", "side": session.get("human_side")})
    runner.records.append({"actor": "OPP", "uci": mv.uci(), "ok": True, "san": san, "meta": {"actor": "human", "raw": raw_move}})
    runner._global_ply = getattr(runner, "_global_ply", 0) + 1
    session["updated_at"] = time.time()

    if runner.ref.board.is_game_over():
        result = runner.ref.board.result()
        reason = _board_termination_reason(runner.ref.board) or "normal_game_end"
        _mark_finished(session, result, reason)
    return san, True, None


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
    log_dir_name = exp.get("log_dir_name") or exp_id
    prompt_cfg = _prompt_cfg_from_payload(exp.get("prompt"))
    game_rows: List[dict] = []
    wins = exp.get("wins") or {"player_a": 0, "player_b": 0, "draws": 0}

    # Seed all game rows first so the UI can show pending games.
    for idx in range(total):
        white_is_a = idx < a_as_white
        white_model = exp["players"]["a"]["model"] if white_is_a else exp["players"]["b"]["model"]
        black_model = exp["players"]["b"]["model"] if white_is_a else exp["players"]["a"]["model"]
        game_id = f"{exp_id}_g{idx+1:04d}"
        log_dir = LOG_ROOT / log_dir_name / game_id
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
        game_rows.append(game_row)

    with lock:
        exp = STATE.get(exp_id)
        if exp:
            exp["game_rows"] = game_rows
            exp["games"]["completed"] = exp["games"].get("completed", 0)
            _persist_update()

    max_workers = max(1, min(total, MAX_PARALLEL_GAMES))

    def _play_game(row: dict):
        game_id = row["game_id"]
        white_model = row["white_model"]
        black_model = row["black_model"]
        white_is_a = row["white_player"] == "a"
        log_dir = Path(row.get("conversation_path") or (LOG_ROOT / log_dir_name / game_id)).parent
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
        row_update = {
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

        with lock:
            exp_local = STATE.get(exp_id)
            if not exp_local:
                return
            wins_local = exp_local.get("wins") or {"player_a": 0, "player_b": 0, "draws": 0}
            if winner_color == "white":
                wins_local["player_a" if white_is_a else "player_b"] += 1
            elif winner_color == "black":
                wins_local["player_b" if white_is_a else "player_a"] += 1
            elif winner_color == "draw":
                wins_local["draws"] += 1

            rows = [g for g in exp_local.get("game_rows", []) if g.get("game_id") != game_id]
            rows.append(row_update)
            exp_local["wins"] = wins_local
            exp_local["game_rows"] = rows
            exp_local["games"]["completed"] = exp_local["games"].get("completed", 0) + 1
            _persist_update()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_play_game, row) for row in game_rows]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    with lock:
        exp = STATE.get(exp_id)
        if not exp:
            return
        rows = exp.get("game_rows", [])
        avg_plies = sum(g.get("plies_total", 0) for g in rows) / len(rows) if rows else 0
        avg_duration = sum(g.get("duration_s", 0) for g in rows) / len(rows) if rows else 0
        exp["status"] = "finished"
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

    raw_name = (data.get("name") or "").strip()
    exp_id, display_name, log_dir_name = _experiment_identity_from_payload(data)
    dir_key = (log_dir_name or exp_id).lower()
    name_key = raw_name.lower() if raw_name else None
    with lock:
        for exp in STATE.values():
            existing_dir = (exp.get("log_dir_name") or exp.get("experiment_id") or "").lower()
            existing_name = (exp.get("name") or "").strip().lower()
            if existing_dir == dir_key or (name_key and existing_name and existing_name == name_key):
                return jsonify({"error": "experiment_exists", "message": f"Experiment '{display_name}' already exists."}), 400
    if _experiment_dir_in_use(log_dir_name):
        return (
            jsonify({"error": "experiment_exists", "message": f"Results already exist for experiment '{display_name}'. Pick a new name."}),
            400,
        )

    record = _init_experiment_record({**data, "experiment_id": exp_id, "name": display_name, "log_dir_name": log_dir_name})
    exp_id = record["experiment_id"]
    with lock:
        STATE[exp_id] = record
        _persist_update()
    _start_experiment_thread(exp_id)
    return jsonify({"experiment_id": exp_id, "name": display_name, "log_dir_name": log_dir_name})


@app.route("/api/experiments", methods=["GET"])
def list_experiments():
    values = list(snapshot_state().values())
    summaries = [
        {
            "experiment_id": exp["experiment_id"],
            "name": exp.get("name"),
            "log_dir_name": exp.get("log_dir_name") or exp.get("experiment_id"),
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


@app.route("/api/experiments/<exp_id>", methods=["DELETE"])
def delete_experiment(exp_id: str):
    with lock:
        exp = STATE.get(exp_id)
        if not exp:
            return jsonify({"error": "not_found"}), 404
        if exp.get("status") == "running":
            return jsonify({"error": "experiment_running", "message": "Cannot delete a running experiment."}), 400
        log_dir_name = exp.get("log_dir_name") or exp_id
        STATE.pop(exp_id, None)
        _persist_update()
    removed_paths = []
    for dir_name in {log_dir_name, exp_id}:
        if not dir_name:
            continue
        path = LOG_ROOT / dir_name
        if _safe_remove_dir(path):
            removed_paths.append(str(path))
    return jsonify({"status": "deleted", "experiment_id": exp_id, "removed_paths": removed_paths})


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
            "name": exp.get("name"),
            "log_dir_name": exp.get("log_dir_name") or exp_id,
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


@app.route("/api/human-games", methods=["POST"])
def create_human_game():
    """Start a human vs AI session without writing logs to disk."""
    _cleanup_stale_human_games()
    data = request.get_json(force=True) or {}
    model = data.get("model")
    if not model:
        return jsonify({"error": "model is required"}), 400
    human_side = "black" if str(data.get("human_plays", "white")).lower() == "black" else "white"
    ai_side = _ai_color_for_human(human_side)
    prompt_cfg = _prompt_cfg_from_payload(data.get("prompt"))
    cfg = GameConfig(
        color=ai_side,  # AI plays this color
        prompt_cfg=prompt_cfg,
        opponent_prompt_cfg=prompt_cfg,
        conversation_log_path=None,  # disable file logging for human games
        conversation_log_every_turn=False,
        game_log=False,
    )
    runner = GameRunner(model=model, opponent=UserOpponent(), cfg=cfg)
    start_fen = runner.ref.board.fen()
    game_id = data.get("human_game_id") or f"human_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    session = {
        "id": game_id,
        "runner": runner,
        "model": model,
        "human_side": human_side,
        "ai_side": ai_side,
        "status": "running",
        "winner": None,
        "termination_reason": None,
        "ai_illegal_move_count": 0,
        "last_ai_raw": None,
        "start_fen": start_fen,
        "created_at": time.time(),
        "updated_at": time.time(),
        "conversation": [],
        "ai_system_logged": False,
        "lock": threading.Lock(),
    }

    ai_move = None
    fen_after_ai = None
    if _ai_to_move(session):
        with session["lock"]:
            ai_move, fen_after_ai = _play_ai_turn(session)
    with human_lock:
        HUMAN_GAMES[game_id] = session

    return jsonify(
        {
            "human_game_id": game_id,
            "initial_fen": start_fen,
            "side_to_move": _side_to_move(runner.ref.board),
            "ai_move": ai_move,
            "fen_after_ai": fen_after_ai,
            "ai_reply_raw": session.get("last_ai_raw"),
            "ai_illegal_move_count": session.get("ai_illegal_move_count", 0),
            "status": session.get("status", "running"),
            "winner": session.get("winner"),
            "termination_reason": session.get("termination_reason"),
            "current_fen": runner.ref.board.fen(),
            "conversation": session.get("conversation", []),
        }
    )


@app.route("/api/human-games/<game_id>/move", methods=["POST"])
def human_game_move(game_id: str):
    _cleanup_stale_human_games()
    with human_lock:
        session = HUMAN_GAMES.get(game_id)
    if not session:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(force=True) or {}
    raw_move = data.get("human_move")
    if raw_move is None:
        return jsonify({"error": "human_move is required"}), 400

    with session["lock"]:
        if session.get("status") == "finished":
            return jsonify(_serialize_human_session(session, fen_after_human=session["runner"].ref.board.fen()))
        if not _human_to_move(session):
            return jsonify({"error": "not_human_turn", "side_to_move": _side_to_move(session["runner"].ref.board)}), 400

        san, ok, err = _apply_human_move(session, raw_move)
        if not ok:
            return jsonify({"error": err or "invalid_move"}), 400
        fen_after_human = session["runner"].ref.board.fen()

        ai_move = None
        fen_after_ai = None
        if session.get("status") != "finished" and _ai_to_move(session):
            ai_move, fen_after_ai = _play_ai_turn(session)
        return jsonify(_serialize_human_session(session, fen_after_human=fen_after_human, ai_move=ai_move, fen_after_ai=fen_after_ai))

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
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    # Prevent caching so the UI always sees the freshest state/history
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/api/<path:path>", methods=["OPTIONS"])
def cors_preflight(path: str):
    resp = app.make_response(("", 204))
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
