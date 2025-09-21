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


def main():
    ap = argparse.ArgumentParser(description='Run scripts/run.py over a set of config files.')
    ap.add_argument('--configs', default='test-configs/*.json',
                    help='Comma-separated list of files, dirs, or globs (default: test-configs/*.json)')
    ap.add_argument('--python', default=sys.executable,
                    help='Python interpreter to use (default: current)')
    ap.add_argument('--mode', choices=['sequential', 'batch'], default=None,
                    help='Optional mode override forwarded to scripts/run.py')
    ap.add_argument('--games-per-batch', type=int, default=None,
                    help='Optional chunk size forwarded to scripts/run.py')
    ap.add_argument('--stop-on-error', action='store_true', help='Stop on first non-zero exit.')
    ap.add_argument('--dry-run', action='store_true', help='Print commands instead of executing.')
    args = ap.parse_args()

    files = collect_config_files(args.configs)
    if not files:
        print(f'No config files found for spec: {args.configs}', file=sys.stderr)
        sys.exit(1)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    run_py = os.path.join(repo_root, 'scripts', 'run.py')
    if not os.path.isfile(run_py):
        print(f'Could not find runner at {run_py}', file=sys.stderr)
        sys.exit(2)

    results = []
    t0 = time.time()
    for cfg in files:
        cmd = [args.python, '-u', run_py, '--configs', cfg]
        if args.mode:
            cmd += ['--mode', args.mode]
        if args.games_per_batch is not None:
            cmd += ['--games-per-batch', str(args.games_per_batch)]

        print('Running:', ' '.join(cmd))
        if args.dry_run:
            results.append({'config': cfg, 'returncode': 0, 'duration': 0.0, 'skipped': True})
            continue

        start = time.time()
        proc = subprocess.run(cmd)
        dur = time.time() - start
        results.append({'config': cfg, 'returncode': proc.returncode, 'duration': dur, 'skipped': False})
        if proc.returncode != 0 and args.stop_on_error:
            break

    # Summary
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
    print(f'Wall time: {time.time() - t0:.1f}s')

    # Exit non-zero if any failed
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
