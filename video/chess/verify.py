"""Offline checks connecting the edit to its evidence and final media streams."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import chess
from llmchess_lab.core import save
from .art import Layout, measure, wrap

ROOT=Path('artifacts/episode-02')
EVIDENCE=Path('evidence/episode-02')

def content():
    timeline=json.loads((ROOT/'timeline.json').read_text())
    captions=json.loads((ROOT/'captions.json').read_text())
    game=json.loads((EVIDENCE/'games/astra-self.json').read_text())
    expected=json.loads((ROOT/'screenplay.json').read_text())
    assert len(timeline)==len(expected)==21
    elapsed=0;coverage=[];quotes=[]
    for shot,script in zip(timeline,expected):
        assert all(shot[k]==v for k,v in script.items())
        assert abs(shot['start']-elapsed)<1e-7
        assert shot['voice_offset']+shot['speech_duration']<shot['duration']
        elapsed+=shot['duration']
        if shot.get('quote'):
            record=game['moves'][shot['ply']-1]
            assert shot['narration']==shot['quote']==record['comment']
            quotes.append(dict(shot=shot['id'],request=record['request'],text=record['comment']))
        if shot['id']<'11_opening':continue
        if shot['kind']=='montage':coverage.extend(range(shot['start_ply'],shot['end_ply']+1))
        elif shot['kind'] in ('move','escape_demo','mate_demo'):coverage.append(shot['ply'])
    assert coverage==list(range(1,78))
    assert elapsed<180
    previous=0
    for cue in captions:
        assert previous<=cue['start']<cue['end']<=elapsed
        previous=cue['end']
        for portrait in (False,True):
            layout=Layout(portrait);size=43 if portrait else 38
            lines=wrap(cue['text'],780 if portrait else 1560,size,True)
            assert len(lines)<=2
            assert max(measure(line,size,True) for line in lines)<layout.w-180
            assert layout.caption_y+len(lines)*size*1.3+25<layout.h-12
    before=chess.Board(game['moves'][66]['fen_before'])
    actual=before.copy();actual.push_uci(game['moves'][66]['uci'])
    assert actual.is_check() and not actual.is_checkmate()
    assert [m.uci() for m in actual.legal_moves]==['f5e6']
    alternative=before.copy();alternative.push_uci('h6f4')
    assert alternative.is_checkmate() and alternative.piece_at(chess.E4)==chess.Piece(chess.ROOK,chess.WHITE)
    assert chess.E4 in alternative.attackers(chess.WHITE,chess.E6)
    final=chess.Board(game['final_fen']);assert final.is_checkmate()
    assert all(chess.A7 in final.attackers(chess.WHITE,sq) for sq in (chess.C7,chess.D7,chess.E7))
    budget=json.loads((ROOT/'production-budget/budget.json').read_text())
    production=sum(Decimal(x['bound_usd']) for x in budget['entries'].values())
    assert production<=Decimal('3') and all(x['status']=='received' for x in budget['entries'].values())
    experiment=Decimal(json.loads((EVIDENCE/'audit.json').read_text())['experiment_cost_bound_usd'])
    assert production+experiment<=Decimal('20')
    result=dict(duration_seconds=elapsed,shots=len(timeline),captions=len(captions),
        main_game_plies_in_order=coverage,exact_voiced_model_quotes=quotes,
        false_mate=dict(actual='Rxf4+',legal_replies=['Ke6']),
        unplayed_alternative=dict(move='Qxf4#',legal_replies=0,persistently_labeled=True),
        final_mate=dict(move='39.Rf8#',legal_replies=0),
        production_allowance_usd=str(production),experiment_cost_bound_usd=str(experiment),
        total_planning_allowance_usd=str(production+experiment),
        speech_qa='Per-clip transcription reviewed; numeric formatting and Sol/Saul, one/won homophones accepted. Captions use the script.',
        limitation='Cost figures are conservative planning allowances, not an account invoice.')
    save(ROOT/'content-audit.json',result);return result

def media():
    timeline=json.loads((ROOT/'timeline.json').read_text());duration=sum(s['duration'] for s in timeline);results=[]
    for mode,dimensions in [('landscape',(1920,1080)),('portrait',(1080,1920))]:
        file=ROOT/f'GPT-Learning-02-{mode}.mp4'
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(file)]))
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
        assert (video['width'],video['height'])==dimensions and video['r_frame_rate']=='30/1'
        assert int(video['nb_frames'])==round(duration*30)
        assert abs(float(probe['format']['duration'])-duration)<.06
        assert video['codec_name']=='h264' and video['pix_fmt']=='yuv420p'
        assert audio['codec_name']=='aac' and audio['channels']==2 and audio['sample_rate']=='48000'
        subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(file),'-f','null','-'],check=True)
        raw=subprocess.run(['ffmpeg','-hide_banner','-i',str(file),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-vn','-f','null','-'],capture_output=True,text=True,check=True).stderr
        loudness=json.JSONDecoder().raw_decode(raw[raw.rfind('{'):])[0]
        assert -17<=float(loudness['input_i'])<=-15 and float(loudness['input_tp'])<=-1
        result=dict(file=file.name,sha256=hashlib.sha256(file.read_bytes()).hexdigest(),bytes=file.stat().st_size,
                    width=dimensions[0],height=dimensions[1],frames=int(video['nb_frames']),fps=30,
                    duration_seconds=float(probe['format']['duration']),full_decode='passed',loudness=loudness)
        results.append(result);print(mode,'verified',flush=True)
    save(ROOT/'media-audit.json',results);return results

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--media',action='store_true');args=ap.parse_args()
    print(json.dumps(media() if args.media else content(),indent=2))

if __name__=='__main__':main()
