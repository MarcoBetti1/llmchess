import argparse, json, logging, statistics, time, os, sys
from datetime import datetime

# Ensure project root added
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.llmchess_simple.game import GameRunner, GameConfig
from src.llmchess_simple.engine_opponent import EngineOpponent
from src.llmchess_simple.random_opponent import RandomOpponent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=5)
    ap.add_argument('--model', default='gpt-5')
    ap.add_argument('--depth', type=int, default=6)
    ap.add_argument('--movetime', type=int, default=None, help='Engine movetime ms (overrides depth)')
    ap.add_argument('--max-plies', type=int, default=240)
    ap.add_argument('--pgn-tail', type=int, default=20)
    ap.add_argument('--out-jsonl', default=None, help='Path to write per-game metrics as JSONL')
    ap.add_argument('--log-level', default='INFO')
    ap.add_argument('--verbose-llm', action='store_true')
    ap.add_argument('--opponent', choices=['engine','random'], default='engine')
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    log = logging.getLogger('run_many')

    jsonl_f = open(args.out_jsonl, 'a', encoding='utf-8') if args.out_jsonl else None
    all_metrics = []
    t_start = time.time()

    for i in range(args.games):
        log.info('Starting game %d/%d (opp=%s)', i+1, args.games, args.opponent)
        if args.opponent == 'random':
            opp = RandomOpponent()
        else:
            opp = EngineOpponent(depth=args.depth, movetime_ms=args.movetime)
        cfg = GameConfig(max_plies=args.max_plies, pgn_tail_plies=args.pgn_tail, verbose_llm=args.verbose_llm)
        runner = GameRunner(model=args.model, opponent=opp, cfg=cfg)
        res = runner.play()
        m = runner.summary()
        m['game_index'] = i
        all_metrics.append(m)
        print(f"[Game {i+1}] result={res} reason={m['termination_reason']} plies={m['plies_total']}")
        if jsonl_f:
            jsonl_f.write(json.dumps(m) + '\n')
            jsonl_f.flush()
        opp.close()

    if jsonl_f:
        jsonl_f.close()

    # Aggregate
    results = [m['result'] for m in all_metrics]
    w = results.count('1-0'); l = results.count('0-1'); d = results.count('1/2-1/2')
    legal_rates = [m['llm_legal_rate'] for m in all_metrics if 'llm_legal_rate' in m]
    avg_legal = statistics.mean(legal_rates) if legal_rates else 0
    avg_plies = statistics.mean([m['plies_total'] for m in all_metrics]) if all_metrics else 0
    avg_latency = statistics.mean([m['latency_ms_avg'] for m in all_metrics if 'latency_ms_avg' in m]) if all_metrics else 0

    print('\nSummary:')
    print(f"Games: {len(all_metrics)}  W={w} D={d} L={l}")
    print(f"Avg plies: {avg_plies:.1f}")
    print(f"Avg legal rate: {avg_legal*100:.2f}%")
    print(f"Avg LLM latency (ms): {avg_latency:.1f}")
    print(f"Wall time: {time.time()-t_start:.1f}s")

if __name__ == '__main__':
    main()
