"""Run Manager
Provides in-process management of experiment runs launched via `scripts/run.py`.

Features:
- Start a run with one or more config file paths.
- Track subprocess stdout lines (log buffer) and status.
- Estimate per-run progress by reading appended lines in each config's `results.jsonl`.
- Compute incremental metrics (W/D/L, legal rate, average plies, latency) for games completed in this run only.
- Cancellation support.
- SSE-friendly subscription model (simple polling by generator).

NOTE: This implementation intentionally avoids external dependencies (e.g. watchdog) and
uses periodic polling (1s) of results files. It provides an in-memory registry; if the
Flask process restarts, active runs are not recovered (acceptable for lightweight local use).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any


@dataclass
class ConfigInfo:
    path: str                     # Absolute path to config file
    out_dir: str                  # Out dir extracted from config JSON
    expected_games: int           # Total expected games for this config in this run
    baseline_lines: int = 0       # Lines already present before run start


@dataclass
class RunStatus:
    run_id: str
    config_paths: List[str]
    started_at: float
    process: subprocess.Popen
    python_exe: str
    configs: List[ConfigInfo]
    log_buffer: List[str] = field(default_factory=list)  # last N stdout lines
    log_buffer_limit: int = 500
    status: str = "running"  # running | completed | failed | canceled
    ended_at: Optional[float] = None
    exit_code: Optional[int] = None
    metrics: List[Dict[str, Any]] = field(default_factory=list)  # per-game metrics (incremental)
    metrics_seen_keys: set = field(default_factory=set)  # to dedupe if file reused
    agg: Dict[str, Any] = field(default_factory=dict)
    last_progress_emit: float = 0.0
    sse_listeners: List["SSEListener"] = field(default_factory=list)

    def add_log_line(self, line: str):
        line = line.rstrip('\n')
        if not line:
            return
        self.log_buffer.append(line)
        if len(self.log_buffer) > self.log_buffer_limit:
            self.log_buffer = self.log_buffer[-self.log_buffer_limit:]
        # Push to SSE listeners
        for l in list(self.sse_listeners):
            l.queue_append({"type": "log", "line": line})

    def compute_agg(self):
        total = len(self.metrics)
        w = sum(1 for m in self.metrics if m.get('result') == '1-0')
        l = sum(1 for m in self.metrics if m.get('result') == '0-1')
        d = sum(1 for m in self.metrics if m.get('result') == '1/2-1/2')
        legal_rates = [m.get('llm_legal_rate') for m in self.metrics if isinstance(m.get('llm_legal_rate'), (int, float))]
        avg_legal = sum(legal_rates) / len(legal_rates) if legal_rates else 0.0
        plies = [m.get('plies_total') for m in self.metrics if isinstance(m.get('plies_total'), (int, float))]
        avg_plies = sum(plies) / len(plies) if plies else 0.0
        lat = [m.get('latency_ms_avg') for m in self.metrics if isinstance(m.get('latency_ms_avg'), (int, float))]
        avg_lat = sum(lat) / len(lat) if lat else 0.0
        self.agg = {
            'games_completed': total,
            'w': w,
            'd': d,
            'l': l,
            'win_rate': (w / total) if total else 0.0,
            'avg_legal_rate': avg_legal,
            'avg_plies': avg_plies,
            'avg_latency_ms': avg_lat,
        }
        return self.agg

    @property
    def expected_total_games(self) -> int:
        return sum(c.expected_games for c in self.configs)

    def progress_fraction(self) -> float:
        exp = self.expected_total_games
        if exp <= 0:
            return 0.0
        return min(1.0, len(self.metrics) / exp)


class SSEListener:
    """Lightweight queue for SSE events per client."""
    def __init__(self):
        self._events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._closed = False

    def queue_append(self, event: Dict[str, Any]):
        with self._lock:
            if not self._closed:
                self._events.append(event)

    def pop_batch(self) -> List[Dict[str, Any]]:
        with self._lock:
            if not self._events:
                return []
            batch = self._events[:]
            self._events.clear()
            return batch

    def close(self):
        with self._lock:
            self._closed = True


class RunManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.runs: Dict[str, RunStatus] = {}
        self._lock = threading.Lock()

    # ---------------- Config Helpers ----------------
    def _load_config(self, path: Path) -> Dict[str, Any]:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _expected_games_from_config(self, cfg: Dict[str, Any]) -> int:
        games = int(cfg.get('games', 1))
        color = (cfg.get('color') or cfg.get('llm_color') or 'white').lower()
        if color == 'both':
            return games * 2
        return games

    def _extract_out_dir(self, cfg: Dict[str, Any]) -> str:
        out_dir = cfg.get('out_dir')
        if not out_dir or not isinstance(out_dir, str):
            raise ValueError("Config missing required 'out_dir' string")
        return out_dir

    # ---------------- Public API ----------------
    def start_run(self, config_paths: List[str], python_exe: Optional[str] = None) -> str:
        if not config_paths:
            raise ValueError("No config paths provided")
        abs_paths: List[Path] = []
        configs_meta: List[ConfigInfo] = []
        for p in config_paths:
            ap = (self.project_root / p).resolve() if not os.path.isabs(p) else Path(p).resolve()
            if not ap.exists():
                raise FileNotFoundError(f"Config not found: {p}")
            cfg_json = self._load_config(ap)
            expected = self._expected_games_from_config(cfg_json)
            out_dir = self._extract_out_dir(cfg_json)
            out_dir_abs = (self.project_root / out_dir).resolve() if not os.path.isabs(out_dir) else Path(out_dir).resolve()
            results_file = out_dir_abs / 'results.jsonl'
            baseline = 0
            if results_file.exists():
                try:
                    with open(results_file, 'r', encoding='utf-8') as rf:
                        baseline = sum(1 for _ in rf)
                except Exception:
                    baseline = 0
            configs_meta.append(ConfigInfo(path=str(ap), out_dir=str(out_dir_abs), expected_games=expected, baseline_lines=baseline))
            abs_paths.append(ap)

        run_id = uuid.uuid4().hex[:12]
        python_exe = python_exe or 'python'
        cmd = [python_exe, '-u', str(self.project_root / 'scripts' / 'run.py'), '--configs', ','.join(str(p) for p in abs_paths)]
        proc = subprocess.Popen(cmd, cwd=self.project_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        status = RunStatus(run_id=run_id, config_paths=[str(p) for p in abs_paths], started_at=time.time(), process=proc, python_exe=python_exe, configs=configs_meta)
        with self._lock:
            self.runs[run_id] = status

        threading.Thread(target=self._reader_thread, args=(status,), daemon=True).start()
        threading.Thread(target=self._progress_thread, args=(status,), daemon=True).start()
        return run_id

    def list_runs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._serialize_run(r) for r in self.runs.values()]

    def get_run(self, run_id: str) -> Optional[RunStatus]:
        with self._lock:
            return self.runs.get(run_id)

    def cancel_run(self, run_id: str) -> bool:
        r = self.get_run(run_id)
        if not r:
            return False
        if r.status == 'running' and r.process.poll() is None:
            try:
                r.process.terminate()
                r.status = 'canceled'
                r.ended_at = time.time()
                for l in list(r.sse_listeners):
                    l.queue_append({'type': 'end', 'status': r.status})
                return True
            except Exception:
                return False
        return False

    def attach_sse_listener(self, run_id: str) -> Optional[SSEListener]:
        r = self.get_run(run_id)
        if not r:
            return None
        listener = SSEListener()
        r.sse_listeners.append(listener)
        # Send initial snapshot
        listener.queue_append({'type': 'snapshot', 'status': self._serialize_run(r)})
        return listener

    # ---------------- Internal Threads ----------------
    def _reader_thread(self, status: RunStatus):
        proc = status.process
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                status.add_log_line(line)
        except Exception as e:
            status.add_log_line(f"[run-manager] stdout read error: {e}")
        finally:
            proc.wait()
            status.exit_code = proc.returncode
            if status.status == 'running':
                status.status = 'completed' if proc.returncode == 0 else 'failed'
            status.ended_at = time.time()
            status.compute_agg()
            # Final event
            for l in list(status.sse_listeners):
                l.queue_append({'type': 'end', 'status': status.status, 'agg': status.agg})

    def _progress_thread(self, status: RunStatus):
        # Poll result files while running
        while status.status == 'running':
            self._scan_results(status)
            time.sleep(1.0)
        # One last scan after completion to pick up last lines
        self._scan_results(status)

    def _scan_results(self, status: RunStatus):
        # For each config out_dir read results.jsonl and parse new lines beyond baseline
        for cfg in status.configs:
            results_file = Path(cfg.out_dir) / 'results.jsonl'
            if not results_file.exists():
                continue
            try:
                with open(results_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
            except Exception:
                continue
            new_count = len(lines) - cfg.baseline_lines
            if new_count <= 0:
                continue
            # Parse only lines belonging to this run (the trailing new_count lines)
            for raw in lines[-new_count:]:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    m = json.loads(raw)
                except Exception:
                    continue
                # Dedupe: create a composite key
                key = (
                    m.get('config'),
                    m.get('game_index'),
                    m.get('start_time') or m.get('headers', {}).get('Date')
                )
                if key in status.metrics_seen_keys:
                    continue
                status.metrics_seen_keys.add(key)
                status.metrics.append(m)
            # Update baseline so we don't reparse
            cfg.baseline_lines = len(lines)
        # Recompute aggregation and emit progress event (throttle 0.5s)
        now = time.time()
        if now - status.last_progress_emit > 0.5:
            status.compute_agg()
            progress_payload = {
                'type': 'progress',
                'run_id': status.run_id,
                'fraction': status.progress_fraction(),
                'agg': status.agg,
                'games_completed': len(status.metrics),
                'games_expected': status.expected_total_games,
            }
            for l in list(status.sse_listeners):
                l.queue_append(progress_payload)
            status.last_progress_emit = now

    # ---------------- Serialization ----------------
    def _serialize_run(self, r: RunStatus) -> Dict[str, Any]:
        return {
            'run_id': r.run_id,
            'status': r.status,
            'started_at': r.started_at,
            'ended_at': r.ended_at,
            'exit_code': r.exit_code,
            'configs': [
                {
                    'path': c.path,
                    'out_dir': c.out_dir,
                    'expected_games': c.expected_games,
                } for c in r.configs
            ],
            'progress': {
                'games_completed': len(r.metrics),
                'games_expected': r.expected_total_games,
                'fraction': r.progress_fraction(),
            },
            'agg': r.agg,
            'recent_logs': r.log_buffer[-50:],
        }

    def serialize_run_public(self, run_id: str) -> Optional[Dict[str, Any]]:
        r = self.get_run(run_id)
        if not r:
            return None
        return self._serialize_run(r)


# Singleton accessor (simple pattern; could integrate into Flask app factory)
_RUN_MANAGER: Optional[RunManager] = None


def get_run_manager(project_root: Path) -> RunManager:
    global _RUN_MANAGER
    if _RUN_MANAGER is None:
        _RUN_MANAGER = RunManager(project_root=project_root)
    return _RUN_MANAGER
