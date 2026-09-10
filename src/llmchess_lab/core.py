"""Strict moves, provider token counts, and a durable dollar reservation ledger."""
from __future__ import annotations
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import re
import chess
import httpx

D = Decimal
MODELS = {
    'gpt-6-astra': {'input': '10', 'output': '50'},
    'gpt-5.6-sol': {'input': '4', 'output': '20'},
    'gpt-5.6-luna': {'input': '0.20', 'output': '1.20'},
}
SYSTEM = ('Play the best chess move for the side to move. You have no chess engine or tools. '
          'The board and legal move list are supplied accurately. Choose a move yourself. '
          'Return only a JSON object with exactly two keys: "move" (one legal UCI move) '
          'and "comment" (your brief intention, at most twelve words). Do not include analysis.')

class BudgetStop(RuntimeError): pass
class UncertainRequest(RuntimeError): pass

def save(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    with tmp.open('w') as f:
        json.dump(obj, f, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)

def identity(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True).encode()).hexdigest()

def parse_reply(raw, board):
    try:
        obj = json.loads(raw)
    except (ValueError,TypeError):
        return {'legal':False,'failure':'invalid_json','move':None,'comment':None}
    if (not isinstance(obj,dict) or set(obj) != {'move','comment'} or
        not isinstance(obj['move'],str) or not isinstance(obj['comment'],str)):
        return {'legal':False,'failure':'invalid_schema','move':None,'comment':None}
    uci = obj['move']
    if not re.fullmatch(r'[a-h][1-8][a-h][1-8][qrbn]?',uci):
        return dict(legal=False,failure='invalid_uci',**obj)
    mv=chess.Move.from_uci(uci)
    if mv not in board.legal_moves:
        return dict(legal=False,failure='illegal_move',**obj)
    return dict(legal=True,failure=None,san=board.san(mv),**obj)

def prompt(board):
    replay=board.root();history=[]
    for mv in board.move_stack:
        history.append(replay.san(mv));replay.push(mv)
    return (f'Side to move: {"White" if board.turn else "Black"}\nFEN: {board.fen()}\n'
            f'Board (rank 8 at top; uppercase White, lowercase Black; dot empty):\n{board}\n'
            f'Files left to right: a b c d e f g h\n'
            f'Moves from starting FEN {board.root().fen()}: {" ".join(history) or "(none)"}\n'
            f'Legal UCI moves (alphabetical, unranked): {", ".join(sorted(m.uci() for m in board.legal_moves))}\n'
            'Choose the best move. Return the JSON move and short comment.')

def bound_cost(model, inp, out):
    # 1.25x all input covers possible cache writes; no assumed cache discount.
    r=MODELS[model]
    return (D(inp)*D(r['input'])*D('1.25')+D(out)*D(r['output']))/D(1_000_000)

class Ledger:
    def __init__(self, root, cap='17'):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.cap=D(cap)
        self.path=self.root/'budget.json';self.lock_path=self.root/'budget.lock'
    def _load(self):
        if self.path.exists():
            d=json.loads(self.path.read_text())
            if D(d['cap_usd']) != self.cap:raise ValueError('Budget identity changed')
            return d
        return dict(cap_usd=str(self.cap),entries={})
    def reserve(self, key, amount, meta):
        with self.lock_path.open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX);d=self._load()
            if key in d['entries']:raise UncertainRequest('Existing reservation; never automatically retry')
            total=sum(D(x['bound_usd']) for x in d['entries'].values())
            if total+amount>self.cap:raise BudgetStop(f'Request would exceed ${self.cap} experiment cap')
            d['entries'][key]=dict(status='reserved',bound_usd=str(amount),**meta);save(self.path,d)
    def settle(self,key,amount,meta):
        with self.lock_path.open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX);d=self._load();e=d['entries'][key]
            if amount>D(e['bound_usd']):raise RuntimeError('Provider usage exceeded reservation')
            e.update(status='received',reserved_usd=e['bound_usd'],bound_usd=str(amount),**meta);save(self.path,d)
    def total(self):return sum(D(x['bound_usd']) for x in self._load()['entries'].values())

class Player:
    def __init__(self,root,cap='17',client=None):
        self.root=Path(root);self.ledger=Ledger(root,cap)
        self.client=client or httpx.Client(base_url='https://api.openai.com/v1/',
            headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},timeout=180)
    def play(self,model,board,key):
        body=dict(model=model,instructions=SYSTEM,input=prompt(board),reasoning={'effort':'low'},
                  max_output_tokens=2048,store=False,truncation='disabled',service_tier='default')
        fingerprint=identity(body)
        out=self.root/'requests'/(key+'.json')
        if out.exists():
            rec=json.loads(out.read_text())
            if rec['payload_sha256']!=fingerprint:raise RuntimeError('Request identity changed')
            if rec['status']!='received':raise UncertainRequest('Prior dispatch incomplete; inspect, do not retry')
            return rec
        count_body={k:v for k,v in body.items() if k in ('model','instructions','input','reasoning')}
        c=self.client.post('responses/input_tokens',json=count_body)
        if c.status_code!=200:raise RuntimeError(f'Input count HTTP {c.status_code}; no generation sent')
        n=c.json().get('input_tokens')
        if type(n) is not int or n<1:raise RuntimeError('Invalid official input count')
        amount=bound_cost(model,n,body['max_output_tokens'])
        self.ledger.reserve(key,amount,dict(model=model,payload_sha256=fingerprint))
        rec=dict(key=key,status='reserved',payload=body,payload_sha256=fingerprint,
                 fen=board.fen(),preflight=dict(input_tokens=n,source='OpenAI responses/input_tokens',
                 request_id=c.headers.get('x-request-id')),reserved_usd=str(amount))
        save(out,rec);t=time.time()
        try:r=self.client.post('responses',json=body)
        except httpx.HTTPError:
            raise UncertainRequest('Transport failed; reservation retained, no automatic retry') from None
        if r.status_code!=200:
            rec.update(status='http_error',http_status=r.status_code,request_id=r.headers.get('x-request-id'))
            save(out,rec);raise UncertainRequest(f'Generation HTTP {r.status_code}; reservation retained')
        raw=r.json();usage=raw.get('usage',{})
        # Persist the entire provider result before interpreting it.
        rec.update(raw=raw,latency_s=time.time()-t,request_id=r.headers.get('x-request-id'))
        save(out,rec)
        inp,outn=usage.get('input_tokens'),usage.get('output_tokens')
        if any(type(x) is not int or x<0 for x in (inp,outn)):raise UncertainRequest('Missing valid usage')
        actual_bound=bound_cost(model,inp,outn)
        text=''.join(c.get('text','') for i in raw.get('output',[]) if i.get('type')=='message'
                     for c in i.get('content',[]) if c.get('type')=='output_text')
        parsed=parse_reply(text,board)
        if raw.get('status')!='completed':parsed.update(legal=False,failure='provider_'+raw.get('status','unknown'))
        rec.update(status='received',text=text,parsed=parsed,usage=usage,returned_model=raw.get('model'),
                   provider_status=raw.get('status'),cost_bound_usd=str(actual_bound),input_count_delta=inp-n)
        self.ledger.settle(key,actual_bound,dict(usage=usage,returned_model=raw.get('model'),request_id=rec['request_id']))
        save(out,rec)
        print(key,parsed.get('san') or parsed['failure'],f'${self.ledger.total():.4f}',flush=True)
        return rec
