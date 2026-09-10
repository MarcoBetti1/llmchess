"""Final chess film: an actual false-mate claim, then the game that produced it."""
import argparse
import json
from pathlib import Path
from llmchess_lab.core import save

EVIDENCE=Path('evidence/episode-02');OUT=Path('artifacts/episode-02')

def game(name):return json.loads((EVIDENCE/'games'/(name+'.json')).read_text())
def move(name,ply):return game(name)['moves'][ply-1]

def shot(id,kind,title,narration,voice='cedar',tail=.5,minimum=0,**extra):
    return dict(id=id,kind=kind,title=title,narration=narration,voice=voice,tail=tail,minimum=minimum,**extra)

def opening():
    quote=move('astra-self',67)['comment'];reply=move('astra-self',68)['comment']
    assert quote=='Capture the rook and deliver checkmate.'
    return [
        shot('01_plan','position','CHECKMATE?',"GPT just announced checkmate.",game='astra-self',ply=67,before=True,minimum=2.5,label='Astra vs Astra · move 34',speaker='ASTRA / WHITE',chapter='ACTUAL GAME',sounds=[]),
        shot('02_quote','move','ASTRA SAYS: CHECKMATE',quote,voice='fable',game='astra-self',ply=67,quote=quote,speaker='ASTRA / WHITE',tail=.65,label='Actual model reply · voiced',chapter='ACTUAL GAME',sounds=[dict(kind='capture',at=.75)]),
        shot('03_escape','move','ONE LEGAL REPLY',reply,voice='onyx',game='astra-self',ply=68,quote=reply,speaker='ASTRA / BLACK',tail=.55,label='Same game · next move',chapter='ACTUAL GAME',sounds=[dict(kind='move',at=.8)]),
        shot('04_question','question','CHECKMATE. EVENTUALLY?',"The king can still move. Let's see how we got here.",game='astra-self',ply=68,minimum=4.2,tail=.5,music=True),
        shot('05_method','method','OUR CHESS TEST',"Each turn: the exact board, and a list of legal moves. No chess engine. One answer. No retries.",game='astra-self',ply=67,before=True,minimum=8.6,chapter='HOW WE TESTED'),
        shot('06_tokens','method_tokens','SAVE EVERY MOVE',"We save the replies and count tokens using OpenAI's own numbers.",game='astra-self',ply=67,before=True,minimum=4.5,chapter='HOW WE TESTED'),
        shot('07_puzzle','puzzle','FIRST: FIND MATE',"We started with twelve tiny endgames. We didn't tell the models that checkmate was available.",case='queen-01',minimum=6.5,label='White to move · choose the best move',chapter='TEST 1 / ENDGAMES'),
        shot('08_results','results','12 OUT OF 12. EACH.',"Astra, Sol, and Luna all found a mating move in every position. Good. Now play a whole game.",case='queen-01',minimum=7.5,chapter='TEST 1 / ENDGAMES',music=True),
    ]

def final():
    primary=[game(g['id']) for g in json.loads((EVIDENCE/'protocol.json').read_text())['games']]
    assert all(g['finished'] for g in primary)
    chosen=max([g for g in primary if g['rules_completed']],key=lambda g:g['plies'])
    assert chosen['id']=='astra-self' and chosen['plies']==77 and chosen['result']=='1-0'
    assert game('astra-white')['termination']==game('astra-black')['termination']=='checkmate'
    scenes=opening()+[
      shot('09_engine','match_results','THEN: STOCKFISH',"Astra lost both games against Stockfish. We gave the engine a small search budget: two thousand nodes per move.",game='astra-white',rows=[dict(label='Astra as White',result='Checkmated · move 31'),dict(label='Astra as Black',result='Checkmated · move 30')],minimum=8,chapter='TEST 2 / FULL GAMES'),
      shot('10_self','position','ASTRA VS ASTRA',"Then we made Astra play itself. Finally, an opponent with matching credentials.",game='astra-self',ply=1,before=True,speaker='ASTRA / WHITE',label='Independent requests · same model and settings',minimum=5.7,chapter='GAME 3 / ASTRA PLAYS BOTH SIDES',music=True),
      shot('11_opening','montage','A PERFECTLY NORMAL OPENING',"Both sides castle. White attacks the center; Black goes after the king.",game='astra-self',start_ply=1,end_ply=20,minimum=9,match_label='Astra plays both sides',chapter='MOVES 1–10 / TIME-LAPSE',music=True),
      shot('12_middle','montage','THEN BLACK SEES A PAWN',"A few trades later, Black reaches for a pawn.",game='astra-self',start_ply=21,end_ply=53,minimum=13,match_label='Astra plays both sides',chapter='MOVES 11–27 / TIME-LAPSE',music=True),
      shot('13_pawn','move','BLACK’S PLAN',move('astra-self',54)['comment'],voice='onyx',game='astra-self',ply=54,quote=move('astra-self',54)['comment'],speaker='ASTRA / BLACK',label='Move 27 · actual model reply',chapter='THE QUEEN TRADE',minimum=4.2,delivery=" Clearly articulate 'win a pawn' as three separate words. Emphasize pawn, then pause briefly.",sounds=[dict(kind='capture',at=.75)]),
      shot('14_queen','move','WHITE TAKES THE QUEEN',"Black won a pawn. White won a queen. Excellent trade... for White.",game='astra-self',ply=55,speaker='ASTRA / WHITE',label='Move 28 · pawn captures queen',chapter='THE QUEEN TRADE',minimum=5.7,values=True,sounds=[dict(kind='capture',at=.75)]),
      shot('15_attack','montage','CAN WHITE FINISH?',"White has enough pieces to win. But watch the move it calls checkmate.",game='astra-self',start_ply=56,end_ply=66,minimum=8,match_label='White has queen, rook and knight',chapter='MOVES 28–33 / TIME-LAPSE',music=True),
      shot('16_rejoin','move','BACK TO THE OPENING',"Rook takes rook. Check. We're back at the opening of the video.",game='astra-self',ply=67,speaker='ASTRA / WHITE',label='Move 34 · replay of our opening',chapter='CHECK OR CHECKMATE?',minimum=4.8,sounds=[dict(kind='capture',at=.75)]),
      shot('17_rule','escape_demo','ONE ESCAPE IS ENOUGH',"Checkmate means check with no legal reply. This position has one: king to e six.",game='astra-self',ply=68,minimum=6.7,chapter='CHECK OR CHECKMATE?',sounds=[dict(kind='move',at=.7,relative=True)]),
      shot('17b_alternative','alternative','THE MATE IT MISSED',"The queen could take instead. Then the rook stays here, covering e six. That's mate.",game='astra-self',ply=67,alternative='h6f4',minimum=8.4,chapter='LEGAL ALTERNATIVE / NEVER PLAYED'),
      shot('18_chase','montage','FIVE WHITE MOVES LATER…',"Back in the game, the king runs across the board.",game='astra-self',start_ply=69,end_ply=76,minimum=7.3,match_label='Every move shown is from the log',chapter='MOVES 35–38 / TIME-LAPSE',music=True),
      shot('19_real_mate','mate_demo','THIS TIME: CHECKMATE',"The rook gives check. The queen covers the escape squares. Black has no legal move left.",game='astra-self',ply=77,minimum=8.3,tail=.8,chapter='MOVE 39 / VERIFIED MATE',sounds=[dict(kind='move',at=.7),dict(kind='check',at=6.8,length=.7)]),
      shot('20_close','end','CHECK THE BOARD.',"Astra finished a thirty-nine-move game against itself. Its confident commentary wasn't always right. Check the board. Code and every game are linked.",game='astra-self',takeaway='Real moves.\nSometimes imaginary checkmate.',minimum=9.6,tail=1.4,chapter='SMALL TESTS / THESE SETTINGS',music=True),
    ]
    for s in scenes:
        if s['kind']=='montage':
            s['sounds']=[dict(kind='move',at=t) for t in [1.0,2.5,4,5.5] if t<s['minimum']]
    return scenes

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--opening',action='store_true');a=ap.parse_args();scenes=opening() if a.opening else final()
    save(OUT/'screenplay.json',scenes)
    (OUT/'script.md').write_text('\n\n'.join(f'**{s["id"]} · {s["title"]}**\n\n{s["narration"]}' for s in scenes)+'\n')
    print('Script words',sum(len(s['narration'].split()) for s in scenes),'shots',len(scenes))

if __name__=='__main__':main()
