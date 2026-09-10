"""Make upload assets from the verified exports; never upload to a channel."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
from PIL import Image,ImageDraw
import chess
from .art import BG,EDGE,LIGHT,MINT,MUTED,ORANGE,PANEL,WHITE,Layout,arrow,avatar,board,paragraph,rr,text
from llmchess_lab.core import save

ROOT=Path('artifacts/episode-02')
DEST=Path('../Deliverables/GPT-Learning-02').resolve()

def covers(dest):
    g=json.loads(Path('evidence/episode-02/games/astra-self.json').read_text())
    fen=g['moves'][66]['fen_after']
    im=Image.new('RGB',(1280,720),BG);d=ImageDraw.Draw(im)
    text(d,(56,37),'GPT LEARNING  /  CHESS',25,MINT,True)
    text(d,(56,152),'GPT SAID',50,WHITE,True)
    text(d,(51,214),'CHECKMATE?',80,ORANGE,True)
    text(d,(56,328),'THE KING MOVED.',39,WHITE,True)
    avatar(im,56,454,146,1,True,dark=False)
    rr(d,(228,470,621,591),PANEL,18,EDGE,2)
    paragraph(d,(251,492),'One legal reply. Awkward.',345,38,WHITE,True,maxlines=2)
    L=Layout(False);L.bx=696;L.by=130;L.bs=504
    rr(d,(L.bx-20,L.by-20,L.bx+L.bs+20,L.by+L.bs+29),PANEL,22,EDGE,2)
    board(im,L,fen,highlights=[('e6',MINT)])
    arrow(im,L.square(chess.F5),L.square(chess.E6),MINT,width=11)
    im.save(dest/'thumbnail-1280x720.jpg',quality=96)
    im=Image.new('RGB',(1080,1920),BG);d=ImageDraw.Draw(im)
    text(d,(86,92),'GPT LEARNING  /  CHESS',34,MINT,True)
    text(d,(86,184),'CHECKMATE?',112,ORANGE,True)
    L=Layout(True);L.by=422
    rr(d,(L.bx-26,L.by-26,L.bx+L.bs+26,L.by+L.bs+29),PANEL,24,EDGE,2)
    board(im,L,fen,highlights=[('e6',MINT)])
    arrow(im,L.square(chess.F5),L.square(chess.E6),MINT,width=17)
    text(d,(86,1339),'THE KING MOVED.',69,WHITE,True)
    text(d,(86,1461),'Actual GPT chess game.',42,MUTED,True)
    avatar(im,86,1570,154,1,True,dark=True)
    paragraph(d,(279,1597),'One legal reply. Awkward.',605,53,WHITE,True,maxlines=2)
    im.save(dest/'cover-1080x1920.jpg',quality=96)

DESCRIPTION='''GPT announced checkmate. The king moved.

We gave GPT-6 Astra an accurate chessboard and a list of legal moves, then made it play real games. Against itself, it confidently called checkmate five White moves too soon. The queen could have finished immediately. The rook couldn't.

Watch the actual game, the escape square, and the move it missed. All model quotes are exact public replies; the narrator's jokes are separate.

00:00 Checkmate?
00:14 How we tested
00:29 Twelve tiny endgames
00:43 Stockfish, then self-play
01:19 A queen for a pawn
01:39 Check or checkmate?
01:59 Back to the real game
02:15 Check the board

Code, report and all seven games:
https://github.com/MarcoBetti1/llmchess/blob/main/docs/episode-02/REPORT.md
Raw requests and token usage:
https://github.com/MarcoBetti1/llmchess/tree/main/evidence/episode-02
Interactive prompt-graph playground:
https://github.com/MarcoBetti1/llm-chess-lite-2

Method: GPT-6 Astra, GPT-5.6 Sol and GPT-5.6 Luna; low reasoning; 2,048 total output tokens per response. FEN + text board + full move history + unranked legal list. No engine help for the models, no retries, no replacement moves. Model-specific input counts matched final API usage on all 239 calls. Reasoning tokens are included in output, never added twice.

All three models solved the 12 constructed three-piece endgames. Astra lost two games by checkmate against Stockfish 18 at 2,000 nodes per move, then finished the 39-move self-play game shown here. Four separately planned Sol/Luna engine games stopped at the output-token ceiling: protocol forfeits, not checkmate losses. Those games are in the report. No Elo estimate or broad model ranking is claimed.

The film shows an unplayed alternative, 34.Qxf4#, with a persistent label. Every other game move comes from the saved game. The 77-ply self-play game was the longest rules-completed game in the original three-game protocol.

Production disclosure: AI-generated narration and fictional character voices using OpenAI stock voices (Cedar, Fable, Onyx). Quoted comments are public model outputs, not hidden reasoning. Original procedural chess artwork, animation, music and effects. No real person's voice is imitated.

GPT Learning is an independent experiment project, not affiliated with OpenAI. This video uses API models, not the ChatGPT interface.
'''

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--covers-only',action='store_true');args=ap.parse_args()
    DEST.mkdir(parents=True,exist_ok=True);covers(DEST)
    if args.covers_only:return
    media=json.loads((ROOT/'media-audit.json').read_text())
    for result in media:
        path=ROOT/result['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==result['sha256']
        shutil.copy2(path,DEST/path.name)
    shutil.copy2(ROOT/'GPT-Learning-02.en.srt',DEST/'GPT-Learning-02.en.srt')
    (DEST/'upload-title.txt').write_text('GPT Announced Checkmate. The King Moved.\n')
    (DEST/'upload-description.txt').write_text(DESCRIPTION)
    for sub in ('evidence/episode-02','docs/episode-02'):
        shutil.copytree(sub,DEST/sub,dirs_exist_ok=True,ignore=shutil.ignore_patterns('budget.lock','__pycache__'))
    production=DEST/'production';production.mkdir(exist_ok=True)
    for name in ['screenplay.json','timeline.json','captions.json','script.md','content-audit.json','media-audit.json','speech-review.json','sound-design.json']:
        shutil.copy2(ROOT/name,production/name)
    shutil.copytree(ROOT/'speech',production/'speech',dirs_exist_ok=True)
    shutil.copytree(ROOT/'speech-qa',production/'speech-qa',dirs_exist_ok=True)
    shutil.copy2(ROOT/'production-budget/budget.json',production/'budget.json')
    for name in ['mix.wav','dialogue.wav']:
        shutil.copy2(ROOT/name,production/name)
    shutil.copytree('video/chess',production/'source',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    (DEST/'README.md').write_text('''# GPT Learning — Chess

**Ready to upload: 2 minutes 25 seconds.**

- `GPT-Learning-02-landscape.mp4`: 1920×1080 widescreen, H.264, 30 fps.
- `GPT-Learning-02-portrait.mp4`: separately composed 1080×1920 phone version, same complete story.
- `thumbnail-1280x720.jpg` and `cover-1080x1920.jpg`: upload artwork.
- `upload-title.txt` and `upload-description.txt`: suggested title, description, chapters, evidence links and voice disclosure.
- `GPT-Learning-02.en.srt`: optional subtitle file. Both films already have burned-in captions; avoid showing duplicate captions.
- [Report](docs/episode-02/REPORT.md), [audit](evidence/episode-02/audit.json) and all seven PGNs/raw requests under `evidence/episode-02/`.
- `production/`: approved script, timeline, original audio, source, speech receipts and technical checks. This contains paid revisions as well as final selected clips; the timeline identifies the final edit.

The user handles channel creation and upload. No video was uploaded to YouTube. The film has stock AI-generated voices and original procedural visuals/music. All experimental model quotes are exact public comments.

Both exports passed full-stream decoding, frame-count/duration, caption and audio-level checks. Spending figures in the report are planning allowances, not an invoice. Every actual model input count matched provider usage.
''')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    save(DEST/'provenance.json',dict(repository='https://github.com/MarcoBetti1/llmchess',commit=commit,
        primary_experiment_commit='594970e',followup_protocol_commit='cac3938',media=media))
    manifest=[]
    for path in sorted(DEST.rglob('*')):
        if path.is_file() and path.name!='SHA256SUMS.txt':manifest.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(DEST)))
    (DEST/'SHA256SUMS.txt').write_text('\n'.join(manifest)+'\n')
    archive=DEST.parent/'GPT-Learning-02-upload-package.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(DEST.rglob('*')):
            if path.is_file():z.write(path,Path(DEST.name)/path.relative_to(DEST))
    print(DEST,flush=True);print(archive,flush=True)

if __name__=='__main__':main()
