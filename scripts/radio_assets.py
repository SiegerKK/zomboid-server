#!/usr/bin/env python3
"""Deterministic source+sound pack builder for the opt-in SiegerRadio client.

No runtime uploads. Adding audio updates a catalog, Lua clip allowlists and
sound scripts; clients must receive a new mod version before playback.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import wave

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'story/radio/catalog.json'
CLIENT=ROOT/'mods/SiegerRadio/42/media/lua/client/SiegerRadioClient.lua'
SERVER=ROOT/'story/runtime/SiegerStoryRadio.lua'
SCRIPTS=ROOT/'mods/SiegerRadio/42/media/scripts/SiegerRadio_Sounds.txt'
AUDIO_DIR=ROOT/'mods/SiegerRadio/42/media/sound/SiegerRadio'
CLIP=re.compile(r'[a-z][a-z0-9_]{2,39}\Z')
BEGIN='    -- BEGIN RADIO CATALOG\n'
END='    -- END RADIO CATALOG\n'


def fail(msg):
    raise ValueError(msg)


def load():
    catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
    if catalog.get('schema')!=1 or catalog.get('pack_version')!='sr17-v1':
        fail('Unsupported radio catalog')
    clips=catalog.get('clips')
    if not isinstance(clips,dict) or len(clips)>32 or not clips:
        fail('Radio catalog must contain 1..32 clips')
    for id,info in clips.items():
        if not CLIP.fullmatch(id) or info.get('sound')!='SiegerRadio_'+ ''.join(n.capitalize() for n in id.split('_')):
            fail(f'Clip has unexpected generated name: {id}')
        if not 100<=info.get('duration_ms',0)<=60000:
            fail('Clip duration outside 0.1..60 seconds')
        if type(info.get('enabled')) is not bool:
            fail('Clip enabled must be bool')
    return catalog


def write_registry(content:str,entries:str):
    begin=content.find(BEGIN)
    if begin<0 or content.find(BEGIN,begin+1)>=0:
        fail('Cannot find unique auto catalog BEGIN')
    end=content.find(END,begin+len(BEGIN))
    if end<0 or content.find(END,end+len(END))>=0:
        fail('Cannot find unique auto catalog END')
    return content[:begin+len(BEGIN)]+entries+content[end:]


def render(catalog):
    clips=catalog['clips']
    server=''.join('    '+id+'={sound="'+d['sound']+'",duration='+str(d['duration_ms'])+'},\n'
                   for id,d in sorted(clips.items()))
    client=''.join('    '+id+'="'+d['sound']+'",\n'
                   for id,d in sorted(clips.items()))
    scripts='module Base\n{\n'
    for id,d in sorted(clips.items()):
        scripts+=('    sound '+d['sound']+'\n    {\n'
                  '        category = Item,\n'
                  '        clip\n        {\n'
                  '            file = media/sound/SiegerRadio/'+id+'.wav,\n'
                  '            volume = 0.45,\n'
                  '            distanceMax = 20,\n'
                  '        }\n    }\n')
    scripts+='}\n'
    return {
        SERVER:write_registry(SERVER.read_text(encoding='utf-8'),server),
        CLIENT:write_registry(CLIENT.read_text(encoding='utf-8'),client),
        SCRIPTS:scripts
    }


def check():
    data=load()
    expected=render(data)
    for path,content in expected.items():
        if path.read_text(encoding='utf-8')!=content:
            fail(f'Generated radio catalog out of sync: {path.relative_to(ROOT)}')
    for id,info in data['clips'].items():
        filename=AUDIO_DIR/(id+'.wav')
        if not filename.is_file() or filename.stat().st_size>5*1024*1024:
            fail(f'Radio audio file missing/too large: {id}')
        with wave.open(str(filename),'rb') as src:
            if src.getnchannels()!=1 or src.getsampwidth()!=2 or src.getframerate()!=22050:
                fail(f'Invalid PCM format for {id}: require mono 22050 Hz 16-bit')
            ms=round(src.getnframes()*1000/src.getframerate())
            if ms!=info['duration_ms']:
                fail(f'Catalog duration mismatch: {id} expected {info["duration_ms"]}, got {ms}')
    print(f'PASS: {len(data["clips"])} client audio assets match generated server/client allowlists')


def add(args):
    if not args.yes:
        print('READ-ONLY: would add registered audio',args.clip,'from',args.source)
        return
    data=load()
    ident=args.clip
    if not CLIP.fullmatch(ident) or ident in data['clips'] or len(data['clips'])>=32:
        fail('Clip ID invalid, duplicate, or exceeds 32 slots')
    purpose=args.purpose
    if not 12<=len(purpose)<=280 or any(c in purpose for c in '\n\r\t'):
        fail('Clip needs 12..280 character purpose')
    source=Path(args.source).resolve()
    if not source.is_file() or source.stat().st_size>100*1024*1024:
        fail('Input audio missing or >100 MiB')
    destination=AUDIO_DIR/(ident+'.wav')
    if destination.exists() or destination.is_symlink():
        fail('Audio asset already exists; no replacement in-place')
    fd,temp=tempfile.mkstemp(suffix='.wav',prefix='.sr17-',dir=AUDIO_DIR)
    os.close(fd)
    try:
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',
             '-i',str(source),'-vn','-ac','1','-ar','22050','-c:a','pcm_s16le',temp]
        done=subprocess.run(cmd,capture_output=True,text=True,timeout=120,check=False)
        if done.returncode!=0:
            fail('FFmpeg conversion failed: '+done.stderr[-240:])
        if os.stat(temp).st_size>5*1024*1024:
            fail('Encoded clip too large (limit 5 MiB)')
        with wave.open(temp,'rb') as audio:
            duration=round(audio.getnframes()*1000/audio.getframerate())
        if not 100<=duration<=60000:
            fail('Clip duration must be 0.1..60 seconds')
        data['clips'][ident]={
            'sound':'SiegerRadio_'+''.join(p.capitalize() for p in ident.split('_')),
            'duration_ms':duration,'enabled':True,'purpose':purpose}
        expected=render(data)
        os.replace(temp,destination)
        CATALOG.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        for path,text in expected.items():
            path.write_text(text,encoding='utf-8')
        check()
        print('Created asset',destination.relative_to(ROOT))
        print('IMPORTANT: install updated client pack on every client before using clip',ident)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    cp=sub.add_parser('check');cp.set_defaults(handler=lambda _:check())
    cp=sub.add_parser('add')
    cp.add_argument('--clip',required=True)
    cp.add_argument('--source',required=True)
    cp.add_argument('--purpose',required=True)
    cp.add_argument('--yes',action='store_true')
    cp.set_defaults(handler=add)
    args=parser.parse_args()
    try:
        args.handler(args)
    except (OSError,ValueError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
        parser.exit(2,'Radio assets: '+str(exc)+'\n')


if __name__=='__main__':
    main()
