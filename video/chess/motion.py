"""Directed board animation. Every position and move resolves to recorded evidence."""
from functools import lru_cache
import json
import math
from pathlib import Path
from PIL import Image,ImageDraw
import chess
from .art import *

EVIDENCE=Path('evidence/episode-02')
@lru_cache(maxsize=16)
def game(name):return json.loads((EVIDENCE/'games'/(name+'.json')).read_text())
@lru_cache(maxsize=1)
def cases():return json.loads((EVIDENCE/'cases.json').read_text())
@lru_cache(maxsize=1)
def results():return json.loads((EVIDENCE/'puzzle-results.json').read_text())

def title(d,L,label):
    size=L.title_size
    while measure(label,size,True)>(816 if L.portrait else 1700):size-=1
    text(d,(86,L.title_y),label,size,WHITE,True)

def panel_label(d,L,label):
    if label:text(d,(L.px,L.py-54 if L.portrait else L.py-47),label,26,MUTED,True)

def actor_panel(im,L,s,t,quote=None):
    d=ImageDraw.Draw(im);px,py,pw=L.px,L.py,L.pw
    avatar(im,px,py,118 if L.portrait else 150,t,s['voice']!='cedar',s.get('speaker')=='STOCKFISH','BLACK' in s.get('speaker',''))
    offset=146 if L.portrait else 184
    speaker=s.get('speaker','ASTRA');text(d,(px+offset,py-2),speaker,32,MINT,True)
    if quote:
        paragraph(d,(px+offset,py+49),f'“{quote}”',pw-offset,37 if L.portrait else 42,WHITE,True,leading=1.3,maxlines=5)
    elif s['id']=='01_plan':
        paragraph(d,(px+offset,py+53),'Watch this rook.',pw-offset,49 if L.portrait else 67,WHITE,True,maxlines=2)
    elif s.get('ply'):
        m=game(s['game'])['moves'][s['ply']-1];big=m['san']
        text(d,(px+offset,py+45),big,88 if L.portrait else 104,WHITE,True)
        if not L.portrait:text(d,(px+offset,py+174),f'{(s["ply"]+1)//2}{"." if s["ply"]%2 else "..."} {big}',32,MUTED)

def explain_attack(im,L,s,t):
    # Only attack arrows that can be verified against the displayed board.
    d=ImageDraw.Draw(im);q=t/max(.1,s['duration'])
    if s.get('arrows'):
        for a in s['arrows']:
            arrow(im,L.square(chess.parse_square(a[0])),L.square(chess.parse_square(a[1])),a[2] if len(a)>2 else MINT,progress=ease((q-.2)*3))
    if s.get('note'):
        y=L.py+170 if L.portrait else L.py+360
        paragraph(d,(L.px,y),s['note'],L.pw,38 if L.portrait else 44,ORANGE,True,maxlines=3)

def frame(s,t,portrait=False,cues=()):
    L=Layout(portrait);im=background(portrait).copy();d=ImageDraw.Draw(im);title(d,L,s['title'])
    kind=s['kind'];q=max(0,min(1,t/s['duration']));gs=game(s['game']) if s.get('game') else None
    if kind in ('position','move','question','method','method_tokens','gamebeat','game_end'):
        m=gs['moves'][s.get('ply',1)-1]
        if kind=='move':
            # Specific cut timings keep the capture on the spoken reveal.
            onset=1.05 if s['id']=='03_take' else .18
            progress=ease((t-onset)/.72)
            board(im,L,m['fen_before'],m['uci'],progress)
        else:
            board(im,L,m['fen_before'] if s.get('before') else m['fen_after'],highlights=[(m['uci'][:2],ORANGE)] if s['id']=='01_plan' else [])
        if kind in ('position','move','gamebeat','game_end'):
            panel_label(d,L,s.get('label'))
            if s['id']=='10_self':
                for j,side in enumerate(['WHITE','BLACK']):
                    x=L.px+j*(L.pw/2+10);w=L.pw/2-10;y=L.py
                    rr(d,(x,y,x+w,y+(255 if portrait else 430)),PANEL,20,EDGE,2)
                    size=110 if portrait else 170
                    avatar(im,x+(w-size)/2,y+17,size,t,False,False,j==1)
                    text(d,(x+w/2,y+(137 if portrait else 219)),'ASTRA',38 if portrait else 52,WHITE,True,anchor='mt')
                    text(d,(x+w/2,y+(192 if portrait else 300)),side,30,MINT if j==0 else ORANGE,True,anchor='mt')
            else:actor_panel(im,L,s,t,s.get('quote'))
            explain_attack(im,L,s,t)
            if s.get('values'):
                py=L.py+(184 if portrait else 362)
                text(d,(L.px,py),'TYPICAL MATERIAL VALUES',24,MUTED,True)
                for j,(symbol,label) in enumerate([('P','1'),('q','~9')]):
                    x=L.px+j*290
                    spr=piece_sprite(symbol,69);im.paste(spr,(round(x),round(py+42)),spr)
                    text(d,(x+89,py+37),label,59,WHITE,True)
            if s['id']=='03_escape':
                before=chess.Board(m['fen_before'])
                assert before.is_check() and len(list(before.legal_moves))==1
                if t>1.2:
                    arrow(im,L.square(chess.F5),L.square(chess.E6),MINT,progress=ease((t-1.2)/.4))

            if s['id']=='03_take' and t>2:
                k=chess.Board(m['fen_after']).king(chess.BLACK);x,y=L.square(k)
                d.ellipse((x-37,y-37,x+37,y+37),outline=MINT,width=4)
                # The king's square never changes; compare adjacent logged positions.
                assert chess.Board(m['fen_before']).king(chess.BLACK)==k
                y2=L.py+185 if portrait else L.py+320
                text(d,(L.px,y2),'King moved: 0 squares',34,MINT,True)
        elif kind=='question':
            px,py,pw=L.px,L.py,L.pw
            paragraph(d,(px,py),'Can it play a whole game?',pw,57 if portrait else 72,WHITE,True,leading=1.15,maxlines=3)
            text(d,(px,py+170 if portrait else py+250),'12 puzzles / real games',32,MINT,True)
        elif kind=='method':
            px,py,pw=L.px,L.py,L.pw
            labels=['BOARD AS TEXT','LEGAL MOVE LIST','MODEL CHOOSES']
            for i,label in enumerate(labels):
                revealed=t>(.4+i*1.8);y=py+i*(77 if portrait else 136)
                rr(d,(px,y,px+pw,y+(62 if portrait else 106)),LIGHT if revealed else PANEL,14)
                color=BG if revealed else MUTED
                text(d,(px+20,y+(10 if portrait else 14)),f'{i+1}   {label}',34,color,True)
                if not portrait and revealed:
                    detail=['Board refreshed every turn','Alphabetical list, no rankings','One reply. No repair.'][i]
                    text(d,(px+64,y+61),detail,27,BG)
            text(d,(px,py+(250 if portrait else 452)),'Low reasoning / 2,048-token output cap',30,MINT,True)
        elif kind=='method_tokens':
            px,py,pw=L.px,L.py,L.pw;r=json.loads((EVIDENCE/'requests'/(m['request']+'.json')).read_text());u=r['usage']
            rr(d,(px,py,px+pw,py+(245 if portrait else 410)),PANEL,20,EDGE,2)
            text(d,(px+26,py+17),f'MOVE {(s["ply"]+1)//2} / SAVED REQUEST',28,MINT,True)
            text(d,(px+26,py+78),f'{u["input_tokens"]:,} input tokens',40,WHITE,True)
            text(d,(px+26,py+141),f'{u["output_tokens"]:,} output tokens',40,WHITE,True)
            if portrait:text(d,(px+26,py+206),'Output includes reasoning tokens',26,MUTED)
            if not portrait:
                text(d,(px+26,py+232),'Includes reasoning tokens',32,MUTED)
                text(d,(px+26,py+302),'Source: actual API usage',30,MINT,True)
    elif kind=='puzzle':
        c=next(c for c in cases() if c['id']==s['case']);b=chess.Board(c['fen']);mate=c['mate_moves'][0]
        show=t>s['duration']*.6
        board(im,L,c['fen'],mate if show else None,ease((t-s['duration']*.6)/.8))
        panel_label(d,L,s.get('label'))
        text(d,(L.px,L.py),'YOUR TURN' if not show else 'CHECKMATE',50,MINT,True)
        if not show:
            paragraph(d,(L.px,L.py+77),'One move ends it.',L.pw,45,WHITE,True)
            for i in range(3):d.ellipse((L.px+i*42,L.py+177,L.px+i*42+18,L.py+195),fill=MINT if t>(i+1)*.65 else EDGE)
        else:
            b.push_uci(mate);assert b.is_checkmate()
            text(d,(L.px,L.py+78),chess.Board(c['fen']).san(chess.Move.from_uci(mate)),92,WHITE,True)
            if not portrait:paragraph(d,(L.px,L.py+225),'The king is attacked. Every escape square is covered.',L.pw,40,WHITE)
            # Highlight attacked adjacent escape squares to explain mate directly.
            king=b.king(b.turn)
            for sq in chess.SquareSet(chess.BB_KING_ATTACKS[king]):
                if b.is_attacked_by(not b.turn,sq):
                    x,y=L.square(sq);d.ellipse((x-9,y-9,x+9,y+9),fill=RED)
    elif kind=='results':
        c=next(c for c in cases() if c['id']==s['case']);b=chess.Board(c['fen']);b.push_uci(c['mate_moves'][0]);board(im,L,b.fen())
        px,py,pw=L.px,L.py,L.pw
        for i,(model,label) in enumerate([('gpt-6-astra','GPT-6 Astra'),('gpt-5.6-sol','GPT-5.6 Sol'),('gpt-5.6-luna','GPT-5.6 Luna')]):
            yy=py+i*(79 if portrait else 135);rows=[r for r in results() if r['model']==model];score=sum(r['mate'] for r in rows)
            rr(d,(px,yy,px+pw,yy+(66 if portrait else 112)),PANEL,14,EDGE,2)
            text(d,(px+22,yy+10),label,36,WHITE,True)
            text(d,(px+pw-26,yy+5),f'{score}/12',43,MINT,True,anchor='rt')
            if not portrait:
                for j in range(12):rr(d,(px+24+j*61,yy+70,px+65+j*61,yy+83),MINT if t>.2+j*.09 else EDGE,4)
        if not portrait:paragraph(d,(px,py+450),'Constructed three-piece endgames.\nOne attempt per position.',pw,31,MUTED)
        else:paragraph(d,(px,py+246),'Three-piece endgames. One attempt per position.',pw,28,MUTED,maxlines=2)
    elif kind=='escape_demo':
        m=gs['moves'][s['ply']-1];b=chess.Board(m['fen_before'])
        legal=list(b.legal_moves)
        assert len(legal)==1 and legal[0].uci()==m['uci'] and b.is_check() and not b.is_checkmate()
        onset=s['duration']*.62;progress=ease((t-onset)/.7)
        board(im,L,m['fen_before'],m['uci'] if t>=onset else None,progress,highlights=[('e6',MINT)])
        arrow(im,L.square(chess.F5),L.square(chess.E6),MINT,progress=ease((t-2.8)/.65))
        text(d,(L.px,L.py),'LEGAL REPLIES TO THE CHECK',29,MUTED,True)
        text(d,(L.px,L.py+48),'1',126,MINT,True)
        text(d,(L.px+142,L.py+76),'King to e6',47,WHITE,True)
        if not portrait:paragraph(d,(L.px,L.py+267),'One escape keeps the game alive.',L.pw,44,WHITE,True)
    elif kind=='alternative':
        m=gs['moves'][s['ply']-1];b=chess.Board(m['fen_before']);alt=chess.Move.from_uci(s['alternative'])
        assert alt in b.legal_moves and alt.uci()!=m['uci']
        proof=b.copy();proof.push(alt);assert proof.is_checkmate()
        # A different frame color and persistent label identify the unplayed branch.
        d.rounded_rectangle((L.bx-26,L.by-26,L.bx+L.bs+26,L.by+L.bs+26),radius=24,outline=ORANGE,width=6)
        board(im,L,m['fen_before'],alt.uci(),ease((t-.3)/.9),highlights=[('e4',MINT),('e6',MINT)])
        if t>2.2:arrow(im,L.square(chess.E4),L.square(chess.E6),MINT,progress=ease((t-2.2)/.7))
        badge(d,L.px,L.py,'ALTERNATIVE / NOT PLAYED',ORANGE,27)
        text(d,(L.px,L.py+65),'Qxf4#',83,WHITE,True)
        paragraph(d,(L.px,L.py+184),'Rook stays on e4. Escape covered.',L.pw,36 if portrait else 44,WHITE,True,maxlines=2)
        if not portrait and t>4.2:text(d,(L.px,L.py+351),'Verified: zero legal replies',32,MINT,True)
    elif kind=='mate_demo':
        m=gs['moves'][s['ply']-1];b=chess.Board(m['fen_before']);b.push_uci(m['uci'])
        assert b.is_checkmate() and not list(b.legal_moves)
        board(im,L,m['fen_before'],m['uci'],ease((t-.15)/.65))
        if t>1:
            arrow(im,L.square(chess.F8),L.square(chess.D8),ORANGE,progress=ease((t-1)/.7))
        if t>2.5:
            arrow(im,L.square(chess.A7),L.square(chess.E7),MINT,progress=ease((t-2.5)/.7))
            for sq in [chess.C7,chess.D7,chess.E7]:
                x,y=L.square(sq);ss=L.bs/8
                d.rectangle((x-ss/2+4,y-ss/2+4,x+ss/2-4,y+ss/2-4),outline=MINT,width=4)
        text(d,(L.px,L.py),'LEGAL REPLIES',31,MUTED,True)
        if t>4.0:
            text(d,(L.px,L.py+47),'0',128,MINT,True)
            text(d,(L.px+155,L.py+72),'CHECKMATE',48,WHITE,True)
            text(d,(L.px,L.py+208),'White wins on move 39.',32,WHITE,True)
        else:
            paragraph(d,(L.px,L.py+66),'Rook checks. Queen blocks the escapes.',L.pw,45,WHITE,True,maxlines=3)
        if not portrait and t>4.0:text(d,(L.px,L.py+337),'Verified by the rules engine',31,MINT,True)
    elif kind=='montage':
        start=s['start_ply'];end=s['end_ply'];span=end-start+1
        # Hold the final position; speed is set by the edit, never by model latency.
        u=max(0,min(.999999,(t-.15)/max(.1,s['duration']-.7)));idx=min(span-1,int(u*span));local=u*span-idx
        ply=start+idx;m=gs['moves'][ply-1]
        board(im,L,m['fen_before'],m['uci'],ease(local/.72))
        px,py,pw=L.px,L.py,L.pw
        text(d,(px,py),'MOVE '+str((ply+1)//2),48,MINT,True)
        text(d,(px,py+72),m['san'],86,WHITE,True)
        label=s.get('match_label','Astra vs Stockfish')
        text(d,(px,py+190 if portrait else py+205),label,33,MUTED,True)
        if not portrait and m['comment']:
            text(d,(px,py+273),'MODEL COMMENT / UNVERIFIED',23,MUTED,True)
            paragraph(d,(px,py+310),m['comment'],pw,36,WHITE)
        # A clear, numbered progress track supports the fast game section.
        yy=L.py+272 if portrait else L.py+487
        rr(d,(px,yy,px+pw,yy+8),EDGE,4);rr(d,(px,yy,px+pw*(idx+1)/span,yy+8),MINT,4)
    elif kind=='match_results':
        m=gs['moves'][-1];board(im,L,m['fen_after'])
        px,py,pw=L.px,L.py,L.pw
        for i,row in enumerate(s['rows']):
            y=py+i*(85 if portrait else 155);text(d,(px,y),row['label'],31,MUTED,True)
            text(d,(px,y+38),row['result'],40,WHITE,True)
    elif kind=='end':
        m=gs['moves'][-1];board(im,L,m['fen_after']);px,py,pw=L.px,L.py,L.pw
        paragraph(d,(px,py),s['takeaway'],pw,45 if portrait else 61,WHITE,True,leading=1.2,maxlines=3)
        text(d,(px,py+235 if portrait else py+310),'Code + full games in the description',28,MINT,True)
        text(d,(px,py+(290 if portrait else 368)),'AI-generated voices / real game logs',25,MUTED)
    else:raise ValueError(kind)
    # A small chapter marker is consistent, never a new unexplained section.
    if s.get('chapter'):
        yy=279 if portrait else 22
        text(d,(86 if portrait else 620,yy),s['chapter'],25,MUTED,True)
    active=next((c for c in cues if c['start']<=s['start']+t<c['end']),None)
    if active:
        lines=wrap(active['text'],780 if portrait else 1560,43 if portrait else 38,True)
        captions(im,L,lines)
    return im
