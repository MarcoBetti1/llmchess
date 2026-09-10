"""Stock synthetic voices, original effects, and bounded per-clip speech QA."""
import argparse
import difflib
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import wave
import httpx
import numpy as np
from dotenv import load_dotenv
from llmchess_lab.core import Ledger,save,identity
from .art import wrap

ROOT=Path('artifacts/episode-02').resolve();RATE=48000
MODEL='gpt-4o-mini-tts-2025-12-15'
BASE='Read only the supplied script in English. Original animated chess film. No music or sound effects. Do not imitate any real person. '
DIRECTIONS={
 'cedar':BASE+'Warm, alert, conversational narrator. Sound like you are watching the game with a friend. Brisk at about 175 words per minute, but clearly articulate every sentence. Use genuine surprise, a little amusement and varied emphasis. No motivational speech or announcer voice. Short pauses at punctuation. Dry jokes, not a laugh track. Say GPT as separate letters.',
 'fable':BASE+'You play a self-assured chess enthusiast with a warm British accent. Confident, slightly theatrical, a touch of comic self-importance. Give the short sentence real intention and energy, not a monotone. Do not add or change any words. This is a stock fictional character, not a real person.',
 'onyx':BASE+'You play a composed chess enthusiast. Deep, warm, wry, quietly competitive. Confident short statements with natural lively emphasis. No robotic delivery. Do not add any words.'}

def duration(path):return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)]))

def speech(scene):
    cache=ROOT/'speech';cache.mkdir(parents=True,exist_ok=True)
    payload=dict(model=MODEL,voice=scene['voice'],input=scene['narration'],instructions=DIRECTIONS[scene['voice']]+scene.get('delivery',''),response_format='wav')
    key=identity(payload);wav=cache/(key+'.wav');receipt=cache/(key+'.json')
    if len(scene['narration'])>700:raise ValueError('Split long narration')
    ledger=Ledger(ROOT/'production-budget','3')
    if not wav.exists():
        ledger.reserve('tts-'+key,Decimal('.08'),dict(service='speech',model=MODEL))
        rec=dict(status='reserved',payload=payload,reserved_allowance_usd='.08');save(receipt,rec)
        with httpx.Client(timeout=180) as c:
            r=c.post('https://api.openai.com/v1/audio/speech',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},json=payload)
        if r.status_code!=200:raise RuntimeError(f'Speech HTTP {r.status_code}; reservation retained')
        wav.write_bytes(r.content)
        rec.update(status='received',request_id=r.headers.get('x-request-id'),sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content))
        save(receipt,rec);ledger.settle('tts-'+key,Decimal('.08'),dict(note='Conservative planning allowance; endpoint does not return token usage'))
    target=ROOT/(scene['id']+'.wav');target.write_bytes(wav.read_bytes());return target

def build_timeline(scenes):
    timeline=[];elapsed=0
    for s in scenes:
        dur=duration(speech(s)) if s['narration'] else 0
        length=math.ceil(max(s.get('minimum',0),dur+s.get('tail',.5)+.12)*30)/30
        timeline.append(s|dict(start=elapsed,duration=length,speech_duration=dur,voice_offset=.12))
        elapsed+=length;print(s['id'],round(length,2),flush=True)
    if elapsed>=180:raise ValueError(f'Film is {elapsed:.2f}s; shorten the script, never accelerate it to fit')
    save(ROOT/'timeline.json',timeline);return timeline

def wav(path,data):
    if data.ndim==1:data=np.column_stack([data,data])
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(RATE);f.writeframes((np.clip(data,-.999,.999)*32767).astype('<i2').tobytes())

def cue(kind,length=.25):
    t=np.arange(round(length*RATE))/RATE;rng=np.random.default_rng(2026)
    if kind=='move':return .08*np.sin(2*np.pi*(180*t-80*t*t))*np.exp(-t*30)+.012*rng.normal(size=len(t))*np.exp(-t*60)
    if kind=='capture':return .11*np.sin(2*np.pi*100*t)*np.exp(-t*24)+.026*rng.normal(size=len(t))*np.exp(-t*48)
    if kind=='check':return .06*(np.sin(2*np.pi*880*t)+.2*np.sin(2*np.pi*1320*t))*np.exp(-t*9)
    if kind=='rewind':return .025*rng.normal(size=len(t))*np.sin(np.pi*t/length)**2
    return .035*np.sin(2*np.pi*392*t)*np.exp(-t*7)

def mix(timeline):
    total=sum(s['duration'] for s in timeline);n=round(total*RATE);dialogue=np.zeros(n,dtype=np.float32);fx=np.zeros(n,dtype=np.float32);events=[]
    for s in timeline:
        if s['narration']:
            raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(ROOT/(s['id']+'.wav')),'-af','loudnorm=I=-18:TP=-3:LRA=8','-ar',str(RATE),'-ac','1','-f','f32le','-'])
            a=np.frombuffer(raw,dtype='<f4');i=round((s['start']+s['voice_offset'])*RATE);dialogue[i:i+len(a)]+=a[:n-i]
        for event in s.get('sounds',[]):
            at=s['start']+event['at']*s['duration'] if event.get('relative',False) else s['start']+event['at']
            sound=cue(event['kind'],event.get('length',.3));i=round(at*RATE);end=min(n,i+len(sound))
            if 0<=i<n:fx[i:end]+=sound[:end-i]
            events.append(dict(at=at,kind=event['kind']))
    # A restrained original pulse under montage scenes only; dialogue always dominates.
    for s in timeline:
        if not s.get('music'):continue
        start=s['start'];length=s['duration'];i=round(start*RATE);count=round(length*RATE);t=np.arange(count)/RATE
        bed=np.zeros(count)
        for beat in np.arange(0,length,.42):
            j=int(beat*RATE);lt=np.arange(count-j)/RATE
            hz=[146.832,174.614,195.998,220][int(beat/.42)%4]
            bed[j:]+=.008*np.sin(2*np.pi*hz*lt)*np.exp(-lt*7)
        bed*=np.minimum(t/.3,1)*np.minimum((length-t)/.5,1);fx[i:i+count]+=bed[:n-i]
    wav(ROOT/'dialogue.wav',dialogue)
    stereo=np.column_stack([dialogue+fx,dialogue+np.roll(fx,480)]);wav(ROOT/'premix.wav',stereo)
    statsraw=subprocess.run(['ffmpeg','-hide_banner','-i',str(ROOT/'premix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,check=True).stderr
    stats=json.JSONDecoder().raw_decode(statsraw[statsraw.rfind('{'):])[0]
    flt='loudnorm=I=-16:TP=-1.5:LRA=9:linear=true:'+':'.join(f'{a}={stats[b]}' for a,b in [('measured_I','input_i'),('measured_TP','input_tp'),('measured_LRA','input_lra'),('measured_thresh','input_thresh'),('offset','target_offset')])
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(ROOT/'premix.wav'),'-af',flt,'-ar',str(RATE),'-ac','2',str(ROOT/'mix.wav')],check=True)
    save(ROOT/'sound-design.json',dict(original_synthesis=True,events=events,pre_normalization=stats))

def transcribe(scene):
    path=ROOT/(scene['id']+'.wav');key=hashlib.sha256(path.read_bytes()).hexdigest();dest=ROOT/'speech-qa'/key;dest.mkdir(parents=True,exist_ok=True);out=dest/'transcript.json'
    ledger=Ledger(ROOT/'production-budget','3')
    if not out.exists():
        ledger.reserve('asr-'+key,Decimal('.01'),dict(service='speech_qa',model='whisper-1'))
        with path.open('rb') as f,httpx.Client(timeout=120) as c:
            r=c.post('https://api.openai.com/v1/audio/transcriptions',headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY']},
                data={'model':'whisper-1','response_format':'verbose_json','timestamp_granularities[]':'word','language':'en'},files={'file':(path.name,f,'audio/wav')})
        if r.status_code!=200:raise RuntimeError(f'Speech QA HTTP {r.status_code}; reservation retained')
        save(out,r.json());ledger.settle('asr-'+key,Decimal('.01'),dict(request_id=r.headers.get('x-request-id'),note='Conservative per-clip allowance'))
    return json.loads(out.read_text())

def display(s):
    for a,b in [('GPT six Astra','GPT-6 Astra'),('GPT five point six Sol','GPT-5.6 Sol'),('GPT five point six Luna','GPT-5.6 Luna'),('e six','e6')]:s=s.replace(a,b)
    return s

def align(timeline):
    cues=[];review=[];norm=lambda s:re.sub('[^a-z0-9]','',s.lower())
    for s in timeline:
        if not s['narration']:continue
        transcript=transcribe(s);heard=transcript.get('words',[]);expected=display(s['narration']).split();timed=[];diffs=[]
        matcher=difflib.SequenceMatcher(None,[norm(w['word']) for w in heard],[norm(x) for x in expected],autojunk=False)
        for kind,i,j,k,l in matcher.get_opcodes():
            if kind=='equal':timed.extend(dict(text=expected[b],start=heard[a]['start'],end=heard[a]['end']) for a,b in zip(range(i,j),range(k,l)))
            else:
                diffs.append(dict(heard=' '.join(w['word'] for w in heard[i:j]),script=' '.join(expected[k:l])))
                if k==l:continue
                start=heard[i]['start'] if i<len(heard) else max(0,s['speech_duration']-.3)
                end=heard[j-1]['end'] if j>i else min(start+.15*(l-k),s['speech_duration'])
                timed.extend(dict(text=expected[b],start=start+(b-k)*(end-start)/(l-k),end=start+(b-k+1)*(end-start)/(l-k)) for b in range(k,l))
        groups=[];group=[]
        for w in timed:
            if group and (len(' '.join(g['text'] for g in group))+len(w['text'])>58 or w['end']-group[0]['start']>3.4):groups.append(group);group=[]
            group.append(w)
            if w['text'].endswith(('.','?','!')) and len(group)>3:groups.append(group);group=[]
        if group:groups.append(group)
        offset=s['start']+s['voice_offset']
        for g in groups:
            txt=' '.join(w['text'] for w in g);lines=wrap(txt,780,43,True)
            assert len(lines)<=2,(txt,lines)
            start=offset+g[0]['start'];end=min(s['start']+s['duration']-.02,offset+max(g[-1]['end']+.10,g[0]['start']+.25))
            cues.append(dict(start=start,end=end,text=txt,lines=lines,shot=s['id']))
        review.append(dict(id=s['id'],script=s['narration'],heard=transcript['text'],differences=diffs))
        print('Speech checked',s['id'],transcript['text'],flush=True)
    for a,b in zip(cues,cues[1:]):a['end']=min(a['end'],b['start'])
    assert all(c['end']>c['start'] for c in cues)
    save(ROOT/'captions.json',cues);save(ROOT/'speech-review.json',review)
    def stamp(t):
        m=round(t*1000);return f'{m//3600000:02}:{m//60000%60:02}:{m//1000%60:02},{m%1000:03}'
    (ROOT/'GPT-Learning-02.en.srt').write_text('\n'.join(f'{i+1}\n{stamp(c["start"])} --> {stamp(c["end"])}\n'+ '\n'.join(c['lines'])+'\n' for i,c in enumerate(cues)))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--env-file',required=True);ap.add_argument('--qa-only',action='store_true');ap.add_argument('--speech-only',action='store_true');a=ap.parse_args();load_dotenv(a.env_file)
    if a.qa_only:align(json.loads((ROOT/'timeline.json').read_text()));return
    timeline=build_timeline(json.loads((ROOT/'screenplay.json').read_text()))
    if not a.speech_only:mix(timeline);align(timeline)
    print('Total seconds',sum(s['duration'] for s in timeline),flush=True)

if __name__=='__main__':main()
