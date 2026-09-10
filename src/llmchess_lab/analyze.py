"""Replay evidence, verify results, and add independent local engine analysis."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import shutil
import chess
import chess.engine
import chess.pgn
from .core import SYSTEM, bound_cost, identity, parse_reply, prompt, save


def audit(root):
    manifest=json.loads((root/'protocol.json').read_text());cases=json.loads((root/'cases.json').read_text())
    assert identity(cases)==manifest['cases_sha256']
    source=json.loads((root/'source-identity.json').read_text())
    for path,digest in source.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,('Experiment source changed',path)
    for case in cases:
        board=chess.Board(case['fen']);assert board.is_valid()
        mates=[]
        for move in board.legal_moves:
            after=board.copy();after.push(move)
            if after.is_checkmate():mates.append(move.uci())
        assert sorted(mates)==case['mate_moves']
    receipts=sorted((root/'requests').glob('*.json'));total=Decimal(0);usage=Counter();failures=[];models=Counter();per_model={};used=[]
    budget=json.loads((root/'budget.json').read_text());deltas=Counter()
    for file in receipts:
        r=json.loads(file.read_text());assert r['status']=='received',file
        assert identity(r['payload'])==r['payload_sha256']
        assert r['returned_model']==r['payload']['model']
        assert r['usage']==r['raw']['usage']
        assert r['payload']['instructions']==SYSTEM
        assert r['payload']['reasoning']=={'effort':manifest['reasoning_effort']}
        assert r['payload']['max_output_tokens']==manifest['max_output_tokens']
        assert r['usage']['total_tokens']==r['usage']['input_tokens']+r['usage']['output_tokens']
        assert r['parsed']==parse_reply(r['text'],chess.Board(r['fen'])) or r['provider_status']!='completed'
        cost=bound_cost(r['returned_model'],r['usage']['input_tokens'],r['usage']['output_tokens'])
        assert cost==Decimal(r['cost_bound_usd'])==Decimal(budget['entries'][r['key']]['bound_usd'])
        total+=cost;models[r['returned_model']]+=1
        stats=per_model.setdefault(r['returned_model'],Counter())
        for k in ('input_tokens','output_tokens'):stats[k]+=r['usage'][k]
        stats['reasoning_tokens_included_in_output']+=r['usage'].get('output_tokens_details',{}).get('reasoning_tokens',0)
        stats['cost_bound_usd']+=cost
        for k in ('input_tokens','output_tokens'):usage[k]+=r['usage'][k]
        usage['reasoning_tokens_included_in_output']+=r['usage'].get('output_tokens_details',{}).get('reasoning_tokens',0)
        usage['cached_input_tokens']+=r['usage'].get('input_tokens_details',{}).get('cached_tokens',0)
        deltas[r['input_count_delta']]+=1
        if not r['parsed']['legal']:failures.append(r['key'])
    assert len(budget['entries'])==len(receipts)
    assert total==sum(Decimal(v['bound_usd']) for v in budget['entries'].values())
    assert total<=Decimal(budget['cap_usd'])
    assert all(v['status']=='received' for v in budget['entries'].values())
    puzzles=json.loads((root/'puzzle-results.json').read_text());scores={}
    assert len(puzzles)==len(cases)*len(manifest['models'])
    for model in manifest['models']:
        rows=[r for r in puzzles if r['model']==model]
        assert {r['case'] for r in rows}=={c['id'] for c in cases}
        scores[model]=dict(attempts=len(rows),legal=sum(r['legal'] for r in rows),mate_in_one=sum(r['mate'] for r in rows))
        for row in rows:
            c=next(c for c in cases if c['id']==row['case']);rec=json.loads((root/'requests'/(row['request']+'.json')).read_text())
            b=chess.Board(c['fen']);p=rec['parsed'];mate=False
            assert rec['payload']['input']==prompt(b);used.append(row['request'])
            if p['legal']:b.push_uci(p['move']);mate=b.is_checkmate()
            assert mate==row['mate'] and p['legal']==row['legal']
    games=[]
    planned=manifest['games']+json.loads((root/'followup-protocol.json').read_text())['games']
    assert {p.stem for p in (root/'games').glob('*.json') if not p.name.endswith('-analysis.json')}=={g['id'] for g in planned}
    for path in sorted((root/'games').glob('*.json')):
        if path.name.endswith('-analysis.json'):continue
        g=json.loads(path.read_text());b=chess.Board()
        cfg=next(c for c in planned if c['id']==g['id'])
        assert g['finished'] and all(g[k]==cfg[k] for k in ('white','black'))
        for r in g['moves']:
            assert b.fen()==r['fen_before']
            m=chess.Move.from_uci(r['uci']);assert m in b.legal_moves and b.san(m)==r['san']
            if r['request']:
                req=json.loads((root/'requests'/(r['request']+'.json')).read_text())
                assert req['parsed']['move']==r['uci'] and req['parsed']['comment']==r['comment'] and req['fen']==b.fen()
                assert req['payload']['input']==prompt(b);used.append(r['request'])
            b.push(m);assert b.fen()==r['fen_after']
        if g.get('finished'):
            assert g['final_fen']==b.fen() and g['plies']==len(b.move_stack)
            outcome=b.outcome(claim_draw=True)
            if g['rules_completed']:assert outcome and outcome.result()==g['result']
            else:
                assert outcome is None and g['termination']=='provider_incomplete'
                req=json.loads((root/'requests'/(g['failed_request']+'.json')).read_text());used.append(g['failed_request'])
                assert req['fen']==b.fen() and req['payload']['input']==prompt(b)
                assert req['provider_status']=='incomplete' and req['raw']['incomplete_details']['reason']=='max_output_tokens'
                assert req['usage']['output_tokens']==manifest['max_output_tokens']
                assert g['result']==('0-1' if b.turn else '1-0')
            pgn=chess.pgn.read_game(io.StringIO(path.with_suffix('.pgn').read_text()))
            assert pgn.end().board().fen()==b.fen() and pgn.headers['Result']==g['result']
        games.append({k:g.get(k) for k in ('id','white','black','plies','result','termination','rules_completed','finished')})
    assert Counter(used)==Counter(p.stem for p in receipts),'Unaccounted or duplicated request'
    for stats in per_model.values():stats['cost_bound_usd']=str(stats['cost_bound_usd'])
    result=dict(requests=len(receipts),requests_by_model=dict(models),usage_by_model=per_model,experiment_cost_bound_usd=str(total),
        token_usage=dict(usage),official_input_count_deltas=dict(deltas),failures=failures,puzzles=scores,games=games)
    save(root/'audit.json',result);return result

def analyze_game(root,path,engine):
    g=json.loads(path.read_text());dest=path.with_name(path.stem+'-analysis.json')
    if not g.get('finished'):return
    if dest.exists():return
    b=chess.Board();rows=[]
    for i in range(len(g['moves'])+1):
        engine.configure({'Clear Hash':None})
        info=engine.analyse(b,chess.engine.Limit(nodes=100000))
        score=info['score'].white();pv=info.get('pv',[])
        rows.append(dict(after_ply=i,fen=b.fen(),score_cp=score.score(),mate=score.mate(),
                         score_for_graph=score.score(mate_score=10000),nodes=info.get('nodes'),depth=info.get('depth'),pv=[m.uci() for m in pv]))
        if i<len(g['moves']):b.push_uci(g['moves'][i]['uci'])
    losses=[]
    for i,move in enumerate(g['moves']):
        delta=(rows[i]['score_for_graph']-rows[i+1]['score_for_graph'])*(1 if i%2==0 else -1)
        finite=rows[i]['mate'] is None and rows[i+1]['mate'] is None
        losses.append(dict(ply=i+1,san=move['san'],actor=move['actor'],cp_loss_estimate=max(0,delta) if finite else None,
                           mate_before=rows[i]['mate'],mate_after=rows[i+1]['mate'],comment=move['comment']))
    save(dest,dict(engine=engine.id,nodes_per_position=100000,rows=rows,largest_cp_losses=sorted([x for x in losses if x['cp_loss_estimate'] is not None],key=lambda x:-x['cp_loss_estimate'])[:12],
                   mate_transitions=[x for x in losses if x['cp_loss_estimate'] is None]))
    print('Analyzed',g['id'],'positions',len(rows),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default='evidence/episode-02');ap.add_argument('--engine-analysis',action='store_true');a=ap.parse_args();root=Path(a.root)
    if a.engine_analysis:
        engine=chess.engine.SimpleEngine.popen_uci(shutil.which('stockfish'));engine.configure({'Threads':1,'Hash':16})
        try:
            for p in sorted((root/'games').glob('*.json')):
                if not p.name.endswith('-analysis.json'):analyze_game(root,p,engine)
        finally:engine.quit()
    else:print(json.dumps(audit(root),indent=2))

if __name__=='__main__':main()
