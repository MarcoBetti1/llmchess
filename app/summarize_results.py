"""
Summarize benchmark results across runs.

- Scans runs/*/results.jsonl, groups by model and starting color, and aggregates metrics.
- Prints per-group summary ordered by a selected metric and a white-vs-black delta.

"""
import argparse
import json
import os
from collections import defaultdict
from typing import Dict, List, Tuple


def parse_model_and_color(dirname: str) -> Tuple[str, str]:
    base = os.path.basename(dirname.rstrip('/'))
    color = 'unknown'
    model = base
    for c in ('-white', '-black', '_white', '_black'):
        if base.endswith(c):
            color = 'white' if 'white' in c else 'black'
            model = base[: -len(c)]
            break
    return model, color


def read_results_jsonl(path: str) -> List[Dict]:
    rows: List[Dict] = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                # best-effort, skip bad lines
                continue
    return rows


def aggregate(rows: List[Dict]) -> Dict:
    total_games = len(rows)
    total_plies_llm = sum(r.get('plies_llm', 0) for r in rows)
    total_legal = sum(r.get('llm_legal_moves', 0) for r in rows)
    total_illegal = sum(r.get('llm_illegal_moves', 0) for r in rows)
    avg_legal_rate = (
        sum(float(r.get('llm_legal_rate', 0.0)) for r in rows) / total_games
        if total_games else 0.0
    )
    weighted_legal_rate = (total_legal / total_plies_llm) if total_plies_llm else 0.0
    avg_plies_llm = (total_plies_llm / total_games) if total_games else 0.0
    avg_latency = (
        sum(float(r.get('latency_ms_avg', 0.0)) for r in rows) / total_games
        if total_games else 0.0
    )
    results = [r.get('result', '*') for r in rows]
    wins = results.count('1-0')
    losses = results.count('0-1')
    draws = results.count('1/2-1/2')
    return {
        'games': total_games,
        'total_plies_llm': total_plies_llm,
        'total_legal': total_legal,
        'total_illegal': total_illegal,
        'avg_legal_rate': avg_legal_rate,
        'weighted_legal_rate': weighted_legal_rate,
        'avg_plies_llm': avg_plies_llm,
        'avg_latency_ms': avg_latency,
        'wins': wins,
        'draws': draws,
        'losses': losses,
    }


def main():
    ap = argparse.ArgumentParser(description='Summarize prelim results by model and starting color.')
    ap.add_argument('--root', default='runs/prelim', help='Root directory containing model-color subfolders')
    ap.add_argument('--sort-by', default='weighted_legal_rate', choices=['weighted_legal_rate', 'avg_legal_rate', 'avg_plies_llm'], help='Primary metric to sort groups')
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print(f"No such directory: {args.root}")
        return 1

    groups: Dict[Tuple[str, str], Dict] = {}
    for name in sorted(os.listdir(args.root)):
        sub = os.path.join(args.root, name)
        if not os.path.isdir(sub):
            continue
        jsonl = os.path.join(sub, 'results.jsonl')
        if not os.path.isfile(jsonl):
            continue
        rows = read_results_jsonl(jsonl)
        if not rows:
            continue
        model, color = parse_model_and_color(sub)
        groups[(model, color)] = aggregate(rows)

    if not groups:
        print('No results found.')
        return 1

    # Print per-group summary
    print('Per-group summary (model, color):')
    sorted_groups = sorted(groups.items(), key=lambda kv: kv[1].get(args.sort_by, 0.0), reverse=True)
    for (model, color), g in sorted_groups:
        print(f"- {model:16s} {color:5s} | games={g['games']:3d} legal={g['total_legal']:4d}/{g['total_plies_llm']:4d}  wRate={g['weighted_legal_rate']*100:6.2f}%  aRate={g['avg_legal_rate']*100:6.2f}%  aPlies={g['avg_plies_llm']:5.2f}  aLatency={g['avg_latency_ms']:7.1f}ms  W/D/L={g['wins']}/{g['draws']}/{g['losses']}")

    # Per-model color impact (delta white - black)
    by_model: Dict[str, Dict[str, Dict]] = defaultdict(dict)
    for (model, color), g in groups.items():
        by_model[model][color] = g

    print('\nColor impact per model (white - black, weighted legal rate):')
    rows = []
    for model, colors in by_model.items():
        w = colors.get('white')
        b = colors.get('black')
        if not w or not b:
            continue
        delta = w['weighted_legal_rate'] - b['weighted_legal_rate']
        rows.append((model, delta, w['weighted_legal_rate'], b['weighted_legal_rate']))
    if rows:
        rows.sort(key=lambda x: abs(x[1]), reverse=True)
        for model, delta, w_rate, b_rate in rows:
            print(f"- {model:16s} Δ={delta*100:+6.2f}pp  white={w_rate*100:6.2f}%  black={b_rate*100:6.2f}%")
    else:
        print('(Need both white and black runs per model to compare)')

    # Overall best by selected metric
    best_model_color, best_stats = sorted_groups[0]
    print(f"\nTop group by {args.sort_by}: {best_model_color[0]} ({best_model_color[1]}) with weighted legal rate {best_stats['weighted_legal_rate']*100:.2f}%")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
