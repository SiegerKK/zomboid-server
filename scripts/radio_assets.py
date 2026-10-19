#!/usr/bin/env python3
"""Deterministic source+sound pack builder for the opt-in SiegerRadio client.

No runtime uploads. Adding audio updates a catalog, Lua clip allowlists and
sound scripts; clients must receive a new mod version before playback.
"""
from __future__ import annotations

import argparse
import hashlib
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
STATION=ROOT/'mods/SiegerRadio/42/media/lua/server/SiegerRadioStation.lua'
SCRIPTS=ROOT/'mods/SiegerRadio/42/media/scripts/SiegerRadio_Sounds.txt'
AUDIO_DIR=ROOT/'mods/SiegerRadio/42/media/sound/SiegerRadio'
CLIP=re.compile(r'[a-z][a-z0-9_]{2,39}\Z')
BEGIN='    -- BEGIN RADIO CATALOG\n'
END='    -- END RADIO CATALOG\n'
PLAY_BEGIN='    -- BEGIN RADIO PLAYLIST\n'
PLAY_END='    -- END RADIO PLAYLIST\n'
MAX_CLIPS=64
MAX_TRACK_MS=720000
MAX_WAV_BYTES=32*1024*1024


def fail(msg):
    raise ValueError(msg)


def load():
    catalog=json.loads(CATALOG.read_text(encoding='utf-8'))
    if catalog.get('schema')!=1 or catalog.get('pack_version')!='sr17-v1':
        fail('Unsupported radio catalog')
    if type(catalog.get('runtime_revision',0)) is not int or not 0<=catalog.get('runtime_revision',0)<=999:
        fail('Invalid runtime revision')
    clips=catalog.get('clips')
    if not isinstance(clips,dict) or len(clips)>MAX_CLIPS or not clips:
        fail('Radio catalog must contain 1..64 clips')
    for id,info in clips.items():
        if not CLIP.fullmatch(id) or info.get('sound')!='SiegerRadio_'+ ''.join(n.capitalize() for n in id.split('_')):
            fail(f'Clip has unexpected generated name: {id}')
        if not 100<=info.get('duration_ms',0)<=MAX_TRACK_MS:
            fail('Clip duration outside 0.1..720 seconds')
        if type(info.get('channels',1)) is not int or info.get('channels',1) not in (1,2):
            fail(f'Clip channels must be explicit mono/stereo PCM: {id}')
        if type(info.get('enabled')) is not bool:
            fail('Clip enabled must be bool')
        if not re.fullmatch(r'[0-9a-f]{64}', info.get('sha256','')):
            fail('Clip lacks immutable SHA-256')
    playlist=catalog.get('playlist',[])
    if not isinstance(playlist,list) or len(playlist)>MAX_CLIPS or len(set(playlist))!=len(playlist):
        fail('Station playlist invalid or contains duplicate IDs')
    for track in playlist:
        if track not in clips or not clips[track]['enabled'] or clips[track]['duration_ms']<5000:
            fail('Station only accepts enabled registered tracks of at least 5 seconds')
    return catalog


def write_registry(content:str,entries:str):
    begin=content.find(BEGIN)
    if begin<0 or content.find(BEGIN,begin+1)>=0:
        fail('Cannot find unique auto catalog BEGIN')
    end=content.find(END,begin+len(BEGIN))
    if end<0 or content.find(END,end+len(END))>=0:
        fail('Cannot find unique auto catalog END')
    return content[:begin+len(BEGIN)]+entries+content[end:]


def write_playlist(content:str,entries:str):
    a=content.find(PLAY_BEGIN)
    b=content.find(PLAY_END,a+len(PLAY_BEGIN))
    if a<0 or b<0 or content.find(PLAY_BEGIN,a+1)>=0 or content.find(PLAY_END,b+1)>=0:
        fail('Station playlist markers missing or duplicated')
    return content[:a+len(PLAY_BEGIN)]+entries+content[b:]


def catalog_version(catalog):
    payload=catalog['clips'] if not catalog.get('playlist') else {
        'clips':catalog['clips'],'playlist':catalog['playlist']}
    if catalog.get('runtime_revision',0):
        payload={'catalog':payload,'runtime_revision':catalog['runtime_revision']}
    canonical=json.dumps(payload,ensure_ascii=True,sort_keys=True,
                         separators=(',',':')).encode('utf-8')
    return catalog['pack_version']+'-'+hashlib.sha256(canonical).hexdigest()[:12]


def render(catalog):
    clips=catalog['clips']
    server=''.join('    '+id+'={sound="'+d['sound']+'",duration='+str(d['duration_ms'])+'},\n'
                   for id,d in sorted(clips.items()))
    client=''.join('    '+id+'="'+d['sound']+'",\n'
                   for id,d in sorted(clips.items()))
    station=''.join('    {id="'+track+'",duration='+str(clips[track]['duration_ms'])+'},\n'
                    for track in catalog.get('playlist',[]))
    scripts='module Base\n{\n'
    for id,d in sorted(clips.items()):
        # The 41 songs are streamed by native FMOD; never register GameSounds
        # for them (or other long clips) that might trigger eager WAV loading.
        if id in catalog.get('playlist',[]) or d['duration_ms']>60000:
            continue
        scripts+=('    sound '+d['sound']+'\n    {\n'
                  '        category = Item,\n'
                  '        clip\n        {\n'
                  '            file = media/sound/SiegerRadio/'+id+'.wav,\n'
                  '            volume = 0.45,\n'
                  '            distanceMax = 20,\n'
                  '        }\n    }\n')
    # Only SHORT, registered cues get a 30-tile vehicle GameSound.
    # Full songs remain FMOD CREATESTREAM and cannot be sent as CUE.
    for id,d in sorted(clips.items()):
        if d['duration_ms']<=60000:
            scripts+=('    sound '+d['sound']+'_Vehicle\n    {\n'
                      '        category = Item,\n'
                      '        clip\n        {\n'
                      '            file = media/sound/SiegerRadio/'+id+'.wav,\n'
                      '            volume = 0.45,\n'
                      '            distanceMax = 30,\n'
                      '        }\n    }\n')
    scripts+='}\n'
    version=catalog_version(catalog)
    def set_version(content):
        found=re.findall(r'local VERSION ?= ?"[^"]+"',content)
        if len(found)!=1:fail('Radio script must have one VERSION declaration')
        return content.replace(found[0],'local VERSION="'+version+'"')
    outputs = {
        SERVER:set_version(write_registry(SERVER.read_text(encoding='utf-8'),server)),
        CLIENT:set_version(write_registry(CLIENT.read_text(encoding='utf-8'),client)),
        STATION:set_version(write_playlist(STATION.read_text(encoding='utf-8'),station)),
        SCRIPTS:scripts,
        ROOT/'mods/SiegerRadio/42/media/radio/catalog.json':
            json.dumps(catalog,ensure_ascii=False,indent=2)+'\n'
    }

    # Identical public server Lua ships to clients for B42 checksum enumeration.
    for name in ['SiegerStoryDirector','SiegerStoryAreaScan','SiegerStoryPlayerControl',
                 'SiegerStoryBarControl','SiegerStoryRadio',
                 'SiegerStoryVehicleControl','SiegerStoryBatch','SiegerStoryCharacter','SiegerStoryOps',
                 'SiegerStoryTLOUDiagnostics']:
        source=ROOT/'story/runtime'/(name+'.lua')
        outputs[ROOT/'mods/SiegerRadio/42/media/lua/server'/(name+'.lua')]=outputs.get(source,source.read_text())
    outputs[ROOT/'mods/SiegerRadio/42/media/lua/server/SiegerRuntimeAudit.lua']=(
        'if isClient and isClient() then return end\n'+(ROOT/'scripts/runtime-tlou-audit.lua').read_text())
    return outputs


def check(*, allow_missing_external=False):
    data=load()
    expected=render(data)
    for path,content in expected.items():
        if path.read_text(encoding='utf-8')!=content:
            fail(f'Generated radio catalog out of sync: {path.relative_to(ROOT)}')
    missing=0
    for id,info in data['clips'].items():
        filename=AUDIO_DIR/(id+'.wav')
        if not filename.exists() and allow_missing_external and info.get('external_asset') is True:
            missing+=1
            print(f'EXTERNAL NOT PRESENT: {id} (PCM bytes not checked)')
            continue
        if not filename.is_file() or filename.is_symlink() or filename.stat().st_size>MAX_WAV_BYTES:
            fail(f'Radio audio file missing/too large: {id}')
        if hashlib.sha256(filename.read_bytes()).hexdigest()!=info['sha256']:
            fail(f'Clip byte hash differs from reviewed client catalog: {id}')
        with wave.open(str(filename),'rb') as src:
            if (src.getnchannels()!=info.get('channels',1) or
                    src.getsampwidth()!=2 or src.getframerate()!=22050):
                fail(f'Invalid PCM format for {id}: require catalog-defined 1/2 channels, 22050 Hz, 16-bit')
            ms=round(src.getnframes()*1000/src.getframerate())
            if ms!=info['duration_ms']:
                fail(f'Catalog duration mismatch: {id} expected {info["duration_ms"]}, got {ms}')
    print(f'PASS: generated registries match; {len(data["clips"])-missing} PCM assets verified; {missing} external assets NOT checked')


def add(args):
    if not args.yes:
        print('READ-ONLY: would add registered audio',args.clip,'from',args.source)
        return
    data=load()
    ident=args.clip
    if not CLIP.fullmatch(ident) or ident in data['clips'] or len(data['clips'])>=MAX_CLIPS:
        fail('Clip ID invalid, duplicate, or exceeds 64 slots')
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
             '-i',str(source),'-vn','-ac','2' if args.music else '1','-ar','22050','-c:a','pcm_s16le',temp]
        done=subprocess.run(cmd,capture_output=True,text=True,timeout=120,check=False)
        if done.returncode!=0:
            fail('FFmpeg conversion failed: '+done.stderr[-240:])
        if os.stat(temp).st_size>MAX_WAV_BYTES:
            fail('Encoded clip too large (limit 32 MiB)')
        with wave.open(temp,'rb') as audio:
            duration=round(audio.getnframes()*1000/audio.getframerate())
        if not 100<=duration<=MAX_TRACK_MS:
            fail('Clip duration must be 0.1..720 seconds')
        if args.music and duration<5000:
            fail('Playlist songs must be at least five seconds')
        data['clips'][ident]={
            'sound':'SiegerRadio_'+''.join(p.capitalize() for p in ident.split('_')),
            'duration_ms':duration,'enabled':True,'purpose':purpose,
            'sha256':hashlib.sha256(Path(temp).read_bytes()).hexdigest(),
            'channels':2 if args.music else 1}
        if args.music:
            data.setdefault('playlist',[]).append(ident)
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
    cp=sub.add_parser('check')
    cp.add_argument('--allow-missing-external',action='store_true',
                    help='CI metadata only: allow explicitly external music WAVs to be absent; never for deployment')
    cp.set_defaults(handler=lambda a:check(allow_missing_external=a.allow_missing_external))
    cp=sub.add_parser('add')
    cp.add_argument('--clip',required=True)
    cp.add_argument('--source',required=True)
    cp.add_argument('--purpose',required=True)
    cp.add_argument('--music',action='store_true',help='Add to the sequential shuffled station rotation')
    cp.add_argument('--yes',action='store_true')
    cp.set_defaults(handler=add)
    args=parser.parse_args()
    try:
        args.handler(args)
    except (OSError,ValueError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
        parser.exit(2,'Radio assets: '+str(exc)+'\n')


if __name__=='__main__':
    main()
