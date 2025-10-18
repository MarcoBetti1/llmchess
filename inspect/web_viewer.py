#!/usr/bin/env python3
import argparse
import json
import os
import time
from pathlib import Path
from typing import List, Dict, Any

from flask import Flask, jsonify, request, send_from_directory, abort, Response

# Resolve project root and runs directory
THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parent.parent
WEBUI_DIR = PROJECT_ROOT / "inspect" / "webui"
RUNS_DIR = PROJECT_ROOT / "runs"
TESTS_DIR = PROJECT_ROOT / "tests"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

try:
    from .run_manager import get_run_manager
except Exception:  # fallback when running as script
    from run_manager import get_run_manager  # type: ignore

RUN_MANAGER = get_run_manager(PROJECT_ROOT)

app = Flask(
    __name__,
    static_folder=str(WEBUI_DIR),
    static_url_path="/static",
)


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
        return {
            "path": rel,
            "event": headers.get("Event", ""),
            "date": headers.get("Date", ""),
            "white": headers.get("White", ""),
            "black": headers.get("Black", ""),
            "result": data.get("result", ""),
            "llm_is_white": data.get("llm_is_white"),
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
    items.sort(key=lambda x: x.get("path", ""), reverse=True)
    return jsonify({"games": items, "count": len(items)})


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


# ---------- Run Management Endpoints ----------

@app.route('/api/configs')
def api_configs():
    """List JSON config files in tests directory (one level deep)."""
    configs: List[Dict[str, Any]] = []
    if TESTS_DIR.exists():
        for root, _dirs, files in os.walk(TESTS_DIR):
            for fn in files:
                if fn.endswith('.json'):
                    p = Path(root) / fn
                    try:
                        with open(p, 'r', encoding='utf-8') as f:
                            d = json.load(f)
                        configs.append({
                            'name': fn,
                            'rel_path': p.relative_to(PROJECT_ROOT).as_posix(),
                            'model': d.get('model'),
                            'games': d.get('games'),
                            'color': d.get('color') or d.get('llm_color'),
                            'out_dir': d.get('out_dir'),
                            'mode': d.get('mode'),
                        })
                    except Exception:
                        pass
    return jsonify({'configs': configs})


@app.route('/api/runs', methods=['GET', 'POST'])
def api_runs():
    if request.method == 'POST':
        payload = request.get_json(force=True, silent=True) or {}
        cfgs = payload.get('configs')
        if not isinstance(cfgs, list) or not cfgs:
            abort(400, "'configs' must be a non-empty list of config file paths (relative or absolute)")
        py = payload.get('python')  # optional explicit interpreter
        try:
            run_id = RUN_MANAGER.start_run(cfgs, python_exe=py)
            return jsonify({'run_id': run_id})
        except Exception as e:
            abort(400, f"Failed to start run: {e}")
    else:
        runs = RUN_MANAGER.list_runs()
        return jsonify({'runs': runs})


@app.route('/api/runs/<run_id>')
def api_run_detail(run_id: str):
    data = RUN_MANAGER.serialize_run_public(run_id)
    if not data:
        abort(404, 'Run not found')
    return jsonify(data)


@app.route('/api/runs/<run_id>/cancel', methods=['POST'])
def api_run_cancel(run_id: str):
    ok = RUN_MANAGER.cancel_run(run_id)
    return jsonify({'ok': ok})


@app.route('/api/runs/<run_id>/stream')
def api_run_stream(run_id: str):
    listener = RUN_MANAGER.attach_sse_listener(run_id)
    if not listener:
        abort(404, 'Run not found')

    def gen():
        yield 'retry: 2000\n'  # instruct client for reconnection delay
        while True:
            batch = listener.pop_batch()
            if not batch:
                # Heartbeat
                yield 'event: ping\n' + f'data: {int(time.time())}\n\n'
                time.sleep(1.0)
                continue
            for ev in batch:
                yield 'data: ' + json.dumps(ev) + '\n\n'
                if ev.get('type') == 'end':
                    listener.close()
                    return
    return Response(gen(), mimetype='text/event-stream')


# ---------- Analysis Endpoints ----------

def _iter_results_jsonl(root: Path):
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn == 'results.jsonl':
                p = Path(dirpath) / fn
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                data['_source_results'] = p.as_posix()
                                yield data
                            except Exception:
                                continue
                except Exception:
                    continue


@app.route('/api/analysis/facets')
def api_analysis_facets():
    # Build distinct values for quick filtering UI (model, config, color, opponent)
    models, configs, colors, opponents = set(), set(), set(), set()
    count = 0
    for rec in _iter_results_jsonl(RUNS_DIR):
        count += 1
        if rec.get('model'): models.add(rec['model'])
        if rec.get('config'): configs.add(rec['config'])
        if rec.get('color'): colors.add(rec['color'])
        if rec.get('opponent'): opponents.add(rec['opponent'])
    return jsonify({
        'counts': {'records': count},
        'models': sorted(models),
        'configs': sorted(configs),
        'colors': sorted(colors),
        'opponents': sorted(opponents),
    })


@app.route('/api/analysis/query')
def api_analysis_query():
    # Filters via query params: model, config, color (comma separated allowed)
    def _parse_multi(name: str):
        val = request.args.get(name)
        if not val:
            return None
        return {v.strip() for v in val.split(',') if v.strip()}

    want_model = _parse_multi('model')
    want_config = _parse_multi('config')
    want_color = _parse_multi('color')
    want_opponent = _parse_multi('opponent')

    rows: List[Dict[str, Any]] = []
    for rec in _iter_results_jsonl(RUNS_DIR):
        if want_model and rec.get('model') not in want_model:
            continue
        if want_config and rec.get('config') not in want_config:
            continue
        if want_color and rec.get('color') not in want_color:
            continue
        if want_opponent and rec.get('opponent') not in want_opponent:
            continue
        rows.append(rec)

    # Aggregate lightweight metrics
    total = len(rows)
    w = sum(1 for r in rows if r.get('result') == '1-0')
    l = sum(1 for r in rows if r.get('result') == '0-1')
    d = sum(1 for r in rows if r.get('result') == '1/2-1/2')
    legal = [r.get('llm_legal_rate') for r in rows if isinstance(r.get('llm_legal_rate'), (int, float))]
    avg_legal = sum(legal)/len(legal) if legal else 0.0
    plies = [r.get('plies_total') for r in rows if isinstance(r.get('plies_total'), (int, float))]
    avg_plies = sum(plies)/len(plies) if plies else 0.0
    lat = [r.get('latency_ms_avg') for r in rows if isinstance(r.get('latency_ms_avg'), (int, float))]
    avg_lat = sum(lat)/len(lat) if lat else 0.0

    return jsonify({
        'filters': {
            'model': sorted(list(want_model)) if want_model else None,
            'config': sorted(list(want_config)) if want_config else None,
            'color': sorted(list(want_color)) if want_color else None,
            'opponent': sorted(list(want_opponent)) if want_opponent else None,
        },
        'total_games': total,
        'w': w, 'd': d, 'l': l,
        'win_rate': (w/total) if total else 0.0,
        'avg_legal_rate': avg_legal,
        'avg_plies': avg_plies,
        'avg_latency_ms': avg_lat,
    })


def main():
    parser = argparse.ArgumentParser(description="LLM Chess web viewer")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    # Ensure webui assets exist
    if not WEBUI_DIR.exists():
        print(f"Web assets directory not found: {WEBUI_DIR}")
        print("Please ensure the 'webui' folder exists.")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
