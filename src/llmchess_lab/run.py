"""Run the fixed episode-02 protocol, resuming only already recorded moves."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import chess
import chess.engine
import chess.pgn
from dotenv import load_dotenv
from .core import MODELS, Player, BudgetStop, save, identity
from llmchess_simple.referee import Referee

ROOT=Path(__file__).resolve().parents[2]

def make_cases():
    rng=random.Random(9009);cases=[];seen=set()
    for ptype in (chess.QUEEN,chess.ROOK):
        found=0
        while found<6:
            wk,bk,p=rng.sample(range(64),3)
            b=chess.Board(None);b.set_piece_at(wk,chess.Piece(chess.KING,True));b.set_piece_at(bk,chess.Piece(chess.KING,False));b.set_piece_at(p,chess.Piece(ptype,True));b.turn=True
            if not b.is_valid() or b.is_game_over() or b.fen() in seen:continue
            mates=[]
            for mv in b.legal_moves:
                c=b.copy();c.push(mv)
                if c.is_checkmate():mates.append(mv.uci())
            if not 1<=len(mates)<=3:continue
            if found%2:
                b=b.mirror();mates=[]
                for mv in b.legal_moves:
                    c=b.copy();c.push(mv)
                    if c.is_checkmate():mates.append(mv.uci())
            seen.add(b.fen());found+=1
            cases.append(dict(id=f'{chess.piece_name(ptype)}-{found:02}',fen=b.fen(),mate_moves=sorted(mates)))
    return cases

def protocol(out):
    cases=make_cases();save(out/'cases.json',cases)
    manifest=dict(protocol='episode-02-v1',date='2026-09-09',cases_sha256=identity(cases),models=list(MODELS),
        reasoning_effort='low',max_output_tokens=2048,prompt='FEN + ASCII + history + alphabetically sorted legal UCI moves',
        puzzle_repeats=1,puzzle_outcome='Returned move gives immediate rules checkmate, exhaustively verified',
        repair_policy='None; malformed/illegal/incomplete outputs reported as separate failures; no automatic retries',
        games=[dict(id='astra-white',white='gpt-6-astra',black='stockfish'),
               dict(id='astra-black',white='stockfish',black='gpt-6-astra'),
               dict(id='astra-self',white='gpt-6-astra',black='gpt-6-astra')],
        engine=dict(name='Stockfish 18',nodes_per_move=2000,Threads=1,Hash=16,skill_level=20,
                    limit_strength=False,opening_book=False,tablebases=False),
        engine_analysis_nodes=100000,game_max_plies=240,
        rules='Automatic draw claim when available, including intended move; no resignations; caps are unfinished, not draws',
        game_order='astra-white, astra-black, astra-self; shared $17 cap; $3 reserved for production',
        film_selection='Longest rules-completed game; ties use protocol order. Report all games, no Elo estimate.',
        pricing_verified='2026-09-09',prices_per_million=MODELS,
        sources=['https://developers.openai.com/api/docs/models/gpt-6-astra',
                 'https://developers.openai.com/api/docs/models/gpt-5.6-sol',
                 'https://developers.openai.com/api/docs/models/gpt-5.6-luna'])
    save(out/'protocol.json',manifest);return manifest

def puzzles(player,out):
    cases=json.loads((out/'cases.json').read_text());rows=[]
    for case in cases:
        for model in MODELS:
            b=chess.Board(case['fen']);key='puzzle-'+case['id']+'-'+model
            r=player.play(model,b,key);p=r['parsed'];mate=p['legal'] and p['move'] in case['mate_moves']
            rows.append(dict(case=case['id'],model=model,legal=p['legal'],mate=mate,move=p.get('move'),failure=p['failure'],request=key))
            save(out/'puzzle-results.json',rows)

def game(player,out,cfg,engine_path):
    dest=out/'games';dest.mkdir(exist_ok=True);path=dest/(cfg['id']+'.json')
    if path.exists() and json.loads(path.read_text()).get('finished'):return
    manifest=json.loads((out/'protocol.json').read_text())
    ref=Referee();ref.set_headers(event='GPT Learning episode 02',white=cfg['white'],black=cfg['black'],round_=cfg['id'])
    game_data=dict(**cfg,moves=[],finished=False,engine=None)
    engine=chess.engine.SimpleEngine.popen_uci(engine_path)
    engine.configure({'Threads':1,'Hash':16,'Skill Level':20,'UCI_LimitStrength':False})
    game_data['engine']=dict(id=engine.id,options=manifest['engine'],binary_sha256=hashlib.sha256(Path(engine_path).read_bytes()).hexdigest())
    old=json.loads(path.read_text()) if path.exists() else None
    termination=None
    try:
        while len(ref.board.move_stack)<manifest['game_max_plies']:
            b=ref.board;outcome=b.outcome(claim_draw=True)
            if outcome:
                termination=outcome.termination.name.lower();ref.set_result(outcome.result(),termination);break
            ply=len(b.move_stack)+1;who=cfg['white'] if b.turn else cfg['black'];before=b.fen()
            if old and ply<=len(old['moves']):
                record=old['moves'][ply-1]
                if record['fen_before']!=before:raise RuntimeError('Recorded game state mismatch')
                move=chess.Move.from_uci(record['uci'])
            elif who=='stockfish':
                engine.configure({'Clear Hash':None})
                result=engine.play(b,chess.engine.Limit(nodes=2000),game=cfg['id'])
                move=result.move;record=dict(ply=ply,actor=who,uci=move.uci(),comment=None,request=None)
            else:
                try:r=player.play(who,b,cfg['id']+f'-ply-{ply:03}')
                except BudgetStop:
                    termination='budget_cap';break
                p=r['parsed']
                if not p['legal']:
                    termination=p['failure'];game_data['failed_request']=r['key']
                    # A malformed reply is a protocol forfeit, not a rules checkmate.
                    ref.set_result('0-1' if b.turn else '1-0','protocol_forfeit_'+termination);break
                move=chess.Move.from_uci(p['move']);record=dict(ply=ply,actor=who,uci=p['move'],comment=p['comment'],request=r['key'])
            if move not in b.legal_moves:raise RuntimeError('Illegal move reached referee')
            san=ref.engine_apply(move);record.update(san=san,fen_before=before,fen_after=ref.board.fen())
            game_data['moves'].append(record);save(path,game_data)
            (dest/(cfg['id']+'.pgn')).write_text(ref.pgn()+'\n')
        if termination is None:
            outcome=ref.board.outcome(claim_draw=True)
            if outcome:termination=outcome.termination.name.lower();ref.set_result(outcome.result(),termination)
            else:termination='ply_cap'
        game_data.update(finished=True,termination=termination,result=ref.status(),plies=len(game_data['moves']),final_fen=ref.board.fen(),rules_completed=ref.board.outcome(claim_draw=True) is not None)
        save(path,game_data);(dest/(cfg['id']+'.pgn')).write_text(ref.pgn()+'\n')
        print('GAME',cfg['id'],ref.status(),termination,len(game_data['moves']),flush=True)
    finally:engine.quit()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','puzzles','games']);ap.add_argument('--env-file');ap.add_argument('--out',default='evidence/episode-02');ap.add_argument('--engine',default=shutil.which('stockfish'));a=ap.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    if a.action=='prepare':protocol(out);print('Prepared 12 cases and fixed protocol; no API calls');return
    if a.env_file:load_dotenv(a.env_file)
    else:load_dotenv(ROOT/'.env')
    player=Player(out,'17')
    if a.action=='puzzles':puzzles(player,out)
    else:
        manifest=json.loads((out/'protocol.json').read_text())
        for cfg in manifest['games']:game(player,out,cfg,a.engine)

if __name__=='__main__':main()
