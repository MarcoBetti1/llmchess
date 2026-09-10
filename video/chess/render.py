"""Native landscape and portrait exports with source-keyed scene caches."""
import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
import hashlib
import json
import math
from pathlib import Path
import subprocess
from .motion import frame
from .art import Layout

ROOT=Path('artifacts/episode-02').resolve();FPS=30

def render_scene(args):
    s,portrait,cues,signature=args;L=Layout(portrait);mode='portrait' if portrait else 'landscape'
    key=hashlib.sha256(json.dumps(dict(scene=s,cues=cues,source=signature,mode=mode),sort_keys=True).encode()).hexdigest()[:20]
    cache=ROOT/'frames-cache'/mode;cache.mkdir(parents=True,exist_ok=True);dest=cache/(s['id']+'-'+key+'.mp4')
    if dest.exists():return s['id'],str(dest)
    temp=dest.with_suffix('.part.mp4');count=round(s['duration']*FPS)
    proc=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{L.w}x{L.h}','-r',str(FPS),'-i','-',
        '-an','-c:v','libx264','-crf','17','-preset','veryfast','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(temp)],stdin=subprocess.PIPE)
    try:
        for i in range(count):proc.stdin.write(frame(s,i/FPS,portrait,cues).tobytes())
        proc.stdin.close()
        if proc.wait()!=0:raise RuntimeError('Scene encoder failed')
        temp.replace(dest)
    except Exception:
        proc.kill();proc.wait();raise
    return s['id'],str(dest)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['landscape','portrait','both'],default='both');ap.add_argument('--stills',action='store_true');a=ap.parse_args()
    timeline=json.loads((ROOT/'timeline.json').read_text());cues=json.loads((ROOT/'captions.json').read_text())
    total=sum(s['duration'] for s in timeline);assert total<180
    modes=[False,True] if a.mode=='both' else [a.mode=='portrait']
    # Include the evidence so stale logs cannot silently reuse an old scene.
    files=[Path(__file__),Path(__file__).with_name('art.py'),Path(__file__).with_name('motion.py')]+sorted(Path('evidence/episode-02').rglob('*.json'))
    signature=hashlib.sha256(b''.join(p.read_bytes() for p in files if p.name!='budget.json')).hexdigest()
    for portrait in modes:
        mode='portrait' if portrait else 'landscape';out=ROOT/'review'/mode;out.mkdir(parents=True,exist_ok=True)
        for s in timeline:
            frame(s,min(s['duration']-.01,s['duration']*.68),portrait,cues).save(out/(s['id']+'.jpg'),quality=93)
        if a.stills:continue
        jobs=[(s,portrait,[c for c in cues if c['shot']==s['id']],signature) for s in timeline];paths={}
        with ProcessPoolExecutor(max_workers=2) as pool:
            for future in as_completed([pool.submit(render_scene,j) for j in jobs]):
                ident,path=future.result();paths[ident]=path;print('Rendered',mode,ident,flush=True)
        listing=ROOT/(mode+'-concat.txt');listing.write_text('\n'.join("file '"+paths[s['id']].replace("'","'\\''")+"'" for s in timeline)+'\n')
        final=ROOT/('GPT-Learning-02-'+mode+'.mp4')
        subprocess.run(['ffmpeg','-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-i',str(ROOT/'mix.wav'),'-map','0:v:0','-map','1:a:0',
                        '-c:v','copy','-c:a','aac','-b:a','256k','-ar','48000','-movflags','+faststart','-t',str(total),str(final)],check=True)
        print('EXPORTED',final,flush=True)

if __name__=='__main__':main()
