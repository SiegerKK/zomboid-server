#!/usr/bin/env python3
"""Prepare reviewed 3D stereo PCM from the OWNER'S ORIGINAL radiomusic.zip.

Staging-only: never overwrite a running mod, live catalog, original mono PCM,
player data, or existing output. Start with --track north_track_38 to A/B one
song before converting the complete 41-track library.
"""
from __future__ import annotations
import argparse
from array import array
import math
import sys
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import wave
import zipfile

import radio_assets as assets

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'story/radio/owner-tracklist.json'
MAX_SOURCE=100*1024*1024
MAX_ARCHIVE_UNPACKED=3*1024*1024*1024
SOURCE_EXTENSIONS={'.wav','.mp3','.ogg','.mp4','.m4a','.aac','.webm','.flac'}

def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def fail(message:str):
    raise ValueError(message)

def reviewed_manifest()->dict:
    data=json.loads(MANIFEST.read_text(encoding='utf-8'))
    tracks=data.get('tracks')
    if (not isinstance(tracks,list) or len(tracks)!=41
        or len({row['id'] for row in tracks})!=41):
        fail('Expected exactly 41 reviewed source tracks')
    if len({row['source_sha256'] for row in tracks})!=41:
        fail('Duplicate source hashes in owner manifest')
    return data

def source_files(archive:Path, wanted:dict, output:Path)->dict:
    """Match ZIP bytes to immutable owner manifest by SHA, NOT filenames."""
    found={}
    seen_total=0
    with zipfile.ZipFile(archive) as source:
        infos=source.infolist()
        if len(infos)>256:fail('Owner archive has unexpected member count')
        for info in infos:
            if info.is_dir():continue
            member=PurePosixPath(info.filename)
            if (member.is_absolute() or '..' in member.parts or '\\' in info.filename
                or (info.external_attr>>16)&0o170000==0o120000):
                fail('Unsafe ZIP member')
            if info.file_size>MAX_SOURCE:fail('Oversized ZIP source member')
            seen_total+=info.file_size
            if seen_total>MAX_ARCHIVE_UNPACKED:fail('Archive expands above 3 GiB')
            ext=member.suffix.lower()
            if ext not in SOURCE_EXTENSIONS:continue
            # Archive SHA is checked before this, but every source must also
            # match the exact track digest. Never use untrusted ZIP paths.
            sha=hashlib.sha256()
            with source.open(info) as stream:
                with tempfile.TemporaryFile() as scratch:
                    for piece in iter(lambda:stream.read(1024*1024),b''):
                        sha.update(piece)
                        scratch.write(piece)
                    ident=wanted.get(sha.hexdigest())
                    if ident is not None:
                        if ident in found:fail('Duplicate matching original source')
                        dest=output/(ident+ext)
                        scratch.seek(0)
                        with dest.open('xb') as disk:shutil.copyfileobj(scratch,disk)
                        found[ident]=dest
    if len(found)!=len(wanted):
        fail('Archive source SHA mismatch, or one or more selected tracks absent')
    return found

def source_channels(path:Path)->int:
    result=subprocess.run(['ffprobe','-v','error','-select_streams','a:0',
        '-show_entries','stream=channels','-of','default=noprint_wrappers=1:nokey=1',
        str(path)],capture_output=True,text=True,timeout=40,check=False)
    if result.returncode!=0 or not result.stdout.strip().isdigit():
        fail('Cannot inspect original source channel layout: '+path.name)
    return int(result.stdout.strip())

def stereo_evidence(path:Path)->dict:
    """Bounded full PCM inspection: reject duplicated mono or a silent side.

    Channel count alone does not prove stereo. Keep only one 64K-frame block
    in memory; report actual differences/energy without touching samples.
    """
    count=different=left_energy=right_energy=side_energy=cross=0
    with wave.open(str(path),'rb') as wav:
        if wav.getnchannels()!=2 or wav.getsampwidth()!=2:
            fail('No independent stereo pair')
        while block:=wav.readframes(65536):
            samples=array('h',block)
            if sys.byteorder!='little':samples.byteswap()
            for i in range(0,len(samples),2):
                l,r=samples[i],samples[i+1]
                count+=1;different+=l!=r
                left_energy+=l*l;right_energy+=r*r
                side_energy+=(l-r)*(l-r);cross+=l*r
    if not count or not different or not left_energy or not right_energy:
        fail('PCM has no independent stereo pair (duplicated mono or silent side)')
    return {'frames':count,'different_channel_frames':different,
            'left_rms':math.sqrt(left_energy/count),
            'right_rms':math.sqrt(right_energy/count),
            'side_rms':math.sqrt(side_energy/count),
            'normalized_cross_energy':cross/math.sqrt(left_energy*right_energy)}

def to_stereo(source:Path,dest:Path,old_duration_ms:int)->tuple[str,int,int]:
    if source_channels(source)!=2:
        fail('Original source has no independent stereo pair: '+source.name)
    run=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin',
        '-xerror','-i',str(source),'-map','0:a:0','-vn','-sn','-ac','2',
        '-ar','22050','-c:a','pcm_s16le','-y',str(dest)],
        capture_output=True,text=True,timeout=180,check=False)
    if run.returncode!=0:
        fail('FFmpeg rejected original stereo: '+source.name+' '+run.stderr[-300:])
    if (not dest.is_file() or dest.is_symlink()
        or dest.stat().st_size>assets.MAX_WAV_BYTES):
        fail('Stereo PCM is missing/too large: '+dest.name)
    with wave.open(str(dest),'rb') as wav:
        if wav.getnchannels()!=2 or wav.getsampwidth()!=2 or wav.getframerate()!=22050:
            fail('Stereo PCM does not match approved FMOD format')
        duration_ms=round(wav.getnframes()*1000/wav.getframerate())
    if abs(duration_ms-old_duration_ms)>150:
        fail('Unexpected stereo/mono duration delta: '+dest.name)
    stereo_evidence(dest)
    return digest(dest),duration_ms,dest.stat().st_size

def prepare(archive:Path,output:Path,track_ids:list[str],apply:bool=False):
    catalog=assets.load()
    owner=reviewed_manifest()
    reviewed={row['id']:row for row in owner['tracks']}
    if not track_ids or len(track_ids)!=len(set(track_ids)):
        fail('Choose at least one distinct reviewed track')
    if any(ident not in reviewed or ident not in catalog['playlist'] for ident in track_ids):
        fail('Only 41 registered owner music IDs are permitted')
    if not archive.is_file() or archive.is_symlink():
        fail('Use your own existing radiomusic.zip (no network/download)')
    if digest(archive)!=owner['archive_sha256']:
        fail('Original music archive does not match the pinned owner SHA-256')
    if output.exists() or output.is_symlink():
        fail('Never overwrite an existing staging directory')
    original_digest=digest(assets.CATALOG)
    if not apply:
        print('READ-ONLY: would prepare',len(track_ids),
              'original stereo tracks; source ZIP SHA-256 verified')
        print('Output:',output,'(use --yes to stage; live mod unchanged)')
        return
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.northbound-stereo-',dir=output.parent) as td:
        temp=Path(td)
        source_dir=temp/'sources';source_dir.mkdir()
        staging=temp/'staging';staging.mkdir()
        wavdir=staging/'pcm';wavdir.mkdir()
        lookup={reviewed[i]['source_sha256']:i for i in track_ids}
        originals=source_files(archive,lookup,source_dir)
        candidate=copy.deepcopy(catalog)
        summary=[]
        for ident in track_ids:
            source=originals[ident]
            wav=wavdir/(ident+'.wav')
            sha,ms,size=to_stereo(source,wav,catalog['clips'][ident]['duration_ms'])
            candidate['clips'][ident]['channels']=2
            candidate['clips'][ident]['sha256']=sha
            candidate['clips'][ident]['duration_ms']=ms
            summary.append({'id':ident,'source_sha256':reviewed[ident]['source_sha256'],
                            'stereo_sha256':sha,'duration_ms':ms,'bytes':size,
                            'stereo_evidence':stereo_evidence(wav)})
        (staging/'catalog.candidate.json').write_text(
            json.dumps(candidate,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        metadata={'source_catalog_sha256':original_digest,
                  'archive_sha256':owner['archive_sha256'],
                  'new_version':assets.catalog_version(candidate),
                  'selected_stereo_tracks':summary,
                  'status':'STAGED ONLY - no active data changed'}
        (staging/'review.json').write_text(
            json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        generated=staging/'generated'
        for original,contents in assets.render(candidate).items():
            dest=generated/original.relative_to(ROOT)
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_text(contents,encoding='utf-8')
        staging.rename(output)
    print('STAGED ONLY:',output)
    print('New catalog handshake:',assets.catalog_version(candidate))
    print('No active WAV, git file, running game, or world was modified.')

def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--archive',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    group=cli.add_mutually_exclusive_group(required=True)
    group.add_argument('--track',action='append',help='First A/B one owner track, e.g. north_track_38')
    group.add_argument('--all',action='store_true',help='Stage all originals for later listening acceptance; never installs')
    cli.add_argument('--yes',action='store_true',help='Create a new reviewed staging directory')
    args=cli.parse_args()
    try:
        reviewed=reviewed_manifest()
        tracks=[row['id'] for row in reviewed['tracks']] if args.all else args.track
        prepare(args.archive,args.output,tracks,args.yes)
    except (OSError,ValueError,zipfile.BadZipFile,subprocess.TimeoutExpired) as exc:
        cli.exit(2,'Stereo prepare: '+str(exc)+'\n')

if __name__=='__main__':main()
