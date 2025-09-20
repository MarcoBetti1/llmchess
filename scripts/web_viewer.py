#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
from typing import List, Dict

from flask import Flask, jsonify, request, send_from_directory, abort

# Resolve project root and runs directory
THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parent.parent  # chess2/
WEBUI_DIR = PROJECT_ROOT / "webui"
RUNS_DIR = PROJECT_ROOT / "runs"

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
