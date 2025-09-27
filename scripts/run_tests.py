"""
RUN_TEST.py — Test harness for batch-running configs
- Thin wrapper that invokes scripts/run.py for each config file in a list/dir/glob.
- Ensures stable ordering, prints per-config status and durations, then a summary.

New (parallel batches):
When you point --configs to a directory (or pass --parallel / --jobs>1), we launch one
run.py process per config immediately (subject to an optional concurrency cap) so that
all OpenAI batch submissions occur up front. We then monitor the processes, optionally
stopping remaining ones on the first failure if --stop-on-error is set.

Options:
    * --dry-run: print commands without executing
    * --stop-on-error: halt on first non-zero exit (in parallel mode terminates others)
    * --python: choose interpreter (defaults to current)
    * --parallel: force parallel mode (otherwise auto-enabled if any --configs part is a directory)
    * --jobs N: limit simultaneous processes (default: all). Ignored in sequential mode.
"""
import argparse
import glob
import os
import subprocess
import sys
import time
from typing import List


def collect_config_files(spec: str) -> List[str]:
    files: List[str] = []
    parts = [p.strip() for p in spec.split(',') if p.strip()]
    for p in parts:
        if any(ch in p for ch in ['*', '?', '[']):
            files.extend(glob.glob(p))
        elif os.path.isdir(p):
            files.extend(glob.glob(os.path.join(p, '*.json')))
        elif os.path.isfile(p):
            files.append(p)
    # De-duplicate and sort for stable order
    return sorted(set(files))


def _run_sequential(files: List[str], python_exec: str, run_py: str, dry_run: bool, stop_on_error: bool):
    results = []
    t0 = time.time()
    for cfg in files:
        cmd = [python_exec, '-u', run_py, '--configs', cfg]
        print('Running:', ' '.join(cmd))
        if dry_run:
            results.append({'config': cfg, 'returncode': 0, 'duration': 0.0, 'skipped': True})
            continue
        start = time.time()
        proc = subprocess.run(cmd)
        dur = time.time() - start
        results.append({'config': cfg, 'returncode': proc.returncode, 'duration': dur, 'skipped': False})
        if proc.returncode != 0 and stop_on_error:
            break
    return results, time.time() - t0


def _run_parallel(files: List[str], python_exec: str, run_py: str, dry_run: bool, stop_on_error: bool, jobs: int | None):
    if dry_run:
        for cfg in files:
            cmd = [python_exec, '-u', run_py, '--configs', cfg]
            print('[DRY-RUN] Would run:', ' '.join(cmd))
        return [{'config': f, 'returncode': 0, 'duration': 0.0, 'skipped': True} for f in files], 0.0

    # Simple job limiter (token bucket loop)
    pending = list(files)
    procs = []  # each: dict(config, Popen, start, done, returncode, duration)
    started = 0
    max_jobs = jobs if jobs and jobs > 0 else len(files)
    t0 = time.time()
    failed_early = False
    while pending or any(not p.get('done') for p in procs):
        # Launch while capacity and pending
        while pending and sum(1 for p in procs if not p.get('done')) < max_jobs:
            cfg = pending.pop(0)
            cmd = [python_exec, '-u', run_py, '--configs', cfg]
            print('Launching:', ' '.join(cmd))
            p = subprocess.Popen(cmd)
            procs.append({'config': cfg, 'p': p, 'start': time.time(), 'done': False})
            started += 1
        # Poll
        for entry in procs:
            if entry['done']:
                continue
            rc = entry['p'].poll()
            if rc is not None:
                entry['done'] = True
                entry['returncode'] = rc
                entry['duration'] = time.time() - entry['start']
                status = 'OK' if rc == 0 else f'FAIL({rc})'
                print(f"[DONE] {os.path.basename(entry['config'])}: {status} {entry['duration']:.1f}s")
                if rc != 0 and stop_on_error:
                    failed_early = True
        if failed_early:
            # Terminate all still-running
            for entry in procs:
                if not entry['done'] and entry['p'].poll() is None:
                    try:
                        entry['p'].terminate()
                    except Exception:
                        pass
            break
        time.sleep(0.3)

    wall = time.time() - t0
    # Normalize result list shape
    results = []
    for e in procs:
        results.append({
            'config': e['config'],
            'returncode': e.get('returncode', -999) if not dry_run else 0,
            'duration': e.get('duration', 0.0),
            'skipped': False
        })
    return results, wall


def _print_summary(results: List[dict], wall_time: float):
    total = len(results)
    failed = [r for r in results if r['returncode'] != 0]
    succeeded = [r for r in results if r['returncode'] == 0]
    print('\nSummary:')
    print(f'Configs attempted: {total}  OK={len(succeeded)}  FAIL={len(failed)}')
    for r in results:
        status = 'OK' if r['returncode'] == 0 else f'FAIL({r["returncode"]})'
        if r['skipped']:
            status = 'SKIPPED'
        print(f'- {os.path.basename(r["config"])}: {status}  {r["duration"]:.1f}s')
    print(f'Wall time: {wall_time:.1f}s')
    if failed:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description='Run scripts/run.py over a set of config files (sequential or parallel).')
    ap.add_argument('--configs', default='configs/test-configs/*.json',
                    help='Comma-separated list of files, dirs, or globs (default: configs/test-configs/*.json)')
    ap.add_argument('--python', default=sys.executable,
                    help='Python interpreter to use (default: current)')
    ap.add_argument('--stop-on-error', action='store_true', help='Stop on first non-zero exit (terminates others in parallel mode).')
    ap.add_argument('--dry-run', action='store_true', help='Print commands instead of executing.')
    ap.add_argument('--parallel', action='store_true', help='Force parallel mode (otherwise auto if any spec part is a directory).')
    ap.add_argument('--jobs', type=int, default=0, help='Max parallel jobs (0 => all). Only relevant in parallel mode.')
    args = ap.parse_args()

    parts = [p.strip() for p in args.configs.split(',') if p.strip()]
    files = collect_config_files(args.configs)
    if not files:
        print(f'No config files found for spec: {args.configs}', file=sys.stderr)
        sys.exit(1)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    run_py = os.path.join(repo_root, 'scripts', 'run.py')
    if not os.path.isfile(run_py):
        print(f'Could not find runner at {run_py}', file=sys.stderr)
        sys.exit(2)

    auto_parallel = any(os.path.isdir(p) for p in parts if os.path.exists(p))
    parallel_mode = args.parallel or auto_parallel
    mode_label = 'PARALLEL' if parallel_mode else 'SEQUENTIAL'
    print(f"Mode: {mode_label}  (files={len(files)} jobs={args.jobs if parallel_mode else 'n/a'})")

    if parallel_mode:
        results, wall = _run_parallel(files, args.python, run_py, args.dry_run, args.stop_on_error, args.jobs)
    else:
        results, wall = _run_sequential(files, args.python, run_py, args.dry_run, args.stop_on_error)

    _print_summary(results, wall)


if __name__ == '__main__':
    main()
