#!/usr/bin/env python3
"""Stage linear EBU R128 matching of reviewed stereo WAVs; never overwrite sources.

Choose one common target with enough true-peak headroom for EVERY track.
No compressor/limiter/EQ, no channel remix, no trimming. Music stays local.
"""
import argparse,copy,hashlib,json,math,re,subprocess,wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import radio_assets as assets


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def measure(path):
    r=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-nostats','-threads','1',
        '-filter_threads','1','-i',str(path),'-af',
        'loudnorm=I=-18:TP=-1.5:LRA=20:print_format=json','-f','null','-'],
        capture_output=True,text=True,check=True,timeout=300)
    d=json.loads(re.findall(r'\{[^{}]*"input_i"[^{}]*\}',r.stderr,re.S)[-1])
    for k in ['input_i','input_tp']:
        if not math.isfinite(float(d[k])):raise ValueError('Unmeasurable/silent audio')
    return d


def common_target(rows,preferred=-18.0,peak=-1.5):
    # Extra 0.1 dB headroom for measurement/PCM rounding. Only constant gain.
    return math.floor(min([preferred]+[float(v['input_i'])+peak-float(v['input_tp']) for v in rows.values()])*10)/10-.1


def prepare(source,output,catalog,workers=2):
    source=source.resolve();output=output.resolve()
    if output.exists() or output.is_relative_to(source) or output.is_relative_to(assets.ROOT):raise ValueError('Use a NEW separate staging directory')
    playlist=catalog['playlist']
    if len(playlist)!=41:raise ValueError('Expected all 41 reviewed owner songs')
    for ident in playlist:
        p=source/(ident+'.wav')
        if p.is_symlink() or sha(p)!=catalog['clips'][ident]['sha256']:raise ValueError('Source hash mismatch: '+ident)
        with wave.open(str(p)) as w:
            if (w.getnchannels(),w.getsampwidth(),w.getframerate())!=(2,2,22050):raise ValueError('Expected stereo PCM22050/16bit')
    output.mkdir(parents=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        measured=dict(zip(playlist,pool.map(lambda ident:measure(source/(ident+'.wav')),playlist)))
    target=common_target(measured)
    if target < -30:raise ValueError('Excessive crest factor; review target rather than silently compress')
    def convert(ident):
        src=source/(ident+'.wav');dst=output/(ident+'.wav');before=measured[ident]
        gain=target-float(before['input_i'])
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-n',
            '-threads','1','-filter_threads','1','-i',str(src),'-map','0:a:0',
            '-af','volume='+format(gain,'.5f')+'dB:precision=double','-c:a','pcm_s16le',
            '-ar','22050','-ac','2',str(dst)],capture_output=True,check=True,timeout=300)
        with wave.open(str(src)) as a,wave.open(str(dst)) as b:
            if a.getparams()[:4]!=b.getparams()[:4]:raise ValueError('PCM shape/duration changed: '+ident)
        after=measure(dst)
        if abs(float(after['input_i'])-target)>.15 or float(after['input_tp'])> -1.35:raise ValueError('Loudness/peak check failed: '+ident)
        print(ident,'LUFS',before['input_i'],'->',after['input_i'],'gain_db',round(gain,3),flush=True)
        return ident,{'source_sha256':sha(src),'sha256':sha(dst),'gain_db':round(gain,4),
            'before_lufs':float(before['input_i']),'after_lufs':float(after['input_i']),
            'after_true_peak_dbtp':float(after['input_tp'])}
    with ThreadPoolExecutor(max_workers=workers) as pool:rows=dict(pool.map(convert,playlist))
    updated=copy.deepcopy(catalog);updated['runtime_revision']=catalog.get('runtime_revision',0)+1
    for ident,row in rows.items():updated['clips'][ident]['sha256']=row['sha256']
    report={'algorithm':'EBU R128 measured, constant per-track stereo gain only',
            'target_lufs':round(target,2),'true_peak_limit_dbtp':-1.5,'tracks':rows}
    (output/'loudness-report.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'catalog.json').write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--workers',type=int,choices=[1,2],default=2)
    a=p.parse_args()
    try:
        r=prepare(a.source,a.output,assets.load(),a.workers)
        print('STAGED 41 tracks, target LUFS',r['target_lufs'],'sources unchanged')
    except (ValueError,OSError,subprocess.SubprocessError) as e:p.exit(2,str(e)+'\n')
if __name__=='__main__':main()
