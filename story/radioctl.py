#!/usr/bin/env python3
"""Guarded, parameterised Story radio operations for one running story_test.

No arbitrary Lua, uploads, remote audio URLs, player inventory or world edits.
A command without --yes is a read-only preview. Native radio text uses the
engine's broadcast path; audio cues require opt-in client-side SiegerRadio.
"""
from __future__ import annotations

import argparse
import hashlib
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import secrets

import scanctl

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'story' / 'radio' / 'catalog.json'
REQUEST = 'SiegerStoryRadioRequest.txt'
RESPONSE = 'SiegerStoryRadioResult.txt'
VERSION = 'v1'
ID = re.compile(r'[0-9a-f]{32}\Z')
CLIP = re.compile(r'[a-z][a-z0-9_]{2,39}\Z')
MAX_TEXT_BYTES = 480
MAX_PACKET = 2500
MAX_RESPONSE = 320
STATION_REQ = 'SiegerRadioStationRequest.txt'
STATION_RESP = 'SiegerRadioStationResult.txt'
STATION_STATE = 'SiegerRadioStationState.txt'


def fail(reason: str):
    raise ValueError(reason)


def catalog() -> dict:
    raw = CATALOG.read_bytes()
    if len(raw) > 64 * 1024:
        fail('Radio catalog exceeds 64 KiB')
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('schema') != 1:
        fail('Radio catalog has unexpected schema')
    if data.get('pack_version') != 'sr17-v1':
        fail('Radio client pack version has not been reviewed')
    if type(data.get('runtime_revision',0)) is not int or not 0<=data.get('runtime_revision',0)<=999:
        fail('Invalid runtime revision')
    clips = data.get('clips')
    if not isinstance(clips, dict) or not clips or len(clips) > 64:
        fail('Invalid clip allowlist')
    for key, entry in clips.items():
        if not CLIP.fullmatch(key) or not isinstance(entry, dict):
            fail('Invalid catalog clip key')
        if (not re.fullmatch(r'SiegerRadio_[A-Za-z0-9_]{3,64}', entry.get('sound', ''))
                or type(entry.get('duration_ms')) is not int
                or not 100 <= entry['duration_ms'] <= 720000
                or type(entry.get('enabled')) is not bool):
            fail('Invalid clip definition')
    playlist=data.get('playlist',[])
    if (not isinstance(playlist,list) or len(playlist)>64 or
            len(set(playlist))!=len(playlist)):
        fail('Invalid or duplicate station playlist')
    for clip in playlist:
        if clip not in clips or not clips[clip]['enabled'] or clips[clip]['duration_ms']<5000:
            fail('Station playlist needs enabled registered music longer than 5 seconds')
    return data


def catalog_version(data:dict)->str:
    payload=data['clips'] if not data.get('playlist') else {
        'clips':data['clips'],'playlist':data['playlist']}
    if data.get('runtime_revision',0):
        payload={'catalog':payload,'runtime_revision':data['runtime_revision']}
    payload=json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':'))
    return data['pack_version']+'-'+hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]


def freq_khz(value: str) -> int:
    """PZ radio channel integer in kHz, input MHz with one decimal place."""
    if not re.fullmatch(r'\d{2,3}\.\d', value):
        fail('Use MHz to one decimal place, e.g. 101.3')
    try:
        exact = Decimal(value) * Decimal(1000)
    except InvalidOperation:
        fail('Invalid radio frequency')
    freq = int(exact)
    if not 88000 <= freq <= 108000 or freq % 100:
        fail('Radio frequency must be 88.0..108.0 MHz in 0.1 MHz steps')
    return freq


def position(raw: str) -> tuple[int, int]:
    if not re.fullmatch(r'\d{1,5},\d{1,5}', raw):
        fail('--source must be X,Y integers')
    x, y = map(int, raw.split(','))
    if x > 40000 or y > 40000:
        fail('Radio source outside world bounds')
    return x, y


def paths(world: str) -> tuple[Path, Path]:
    folder = scanctl.lua_dir(world)
    return folder / REQUEST, folder / RESPONSE


def read_request(world: str) -> dict | None:
    req, _ = paths(world)
    if not req.is_file():
        return None
    if req.is_symlink() or req.stat().st_size > MAX_PACKET:
        fail('Unsafe previous radio request file')
    raw = req.read_text(encoding='ascii').rstrip('\n')
    parts = raw.split('\t')
    if (len(parts) != 11 or parts[0] != 'v1' or not ID.fullmatch(parts[1])
            or parts[2] != world or parts[3] not in ('text', 'audio')
            or not all(re.fullmatch(r'\d{1,6}', p) for p in parts[4:8])
            or parts[8] not in ('radio', 'tuned', 'global')
            or not parts[9] or len(parts[9]) > 1500
            or not parts[10].isdigit()):
        fail('Unrecognized previous radio request; operator review required')
    return {'id': parts[1], 'operation': parts[3], 'frequency': int(parts[4])}


def read_response(world: str, request_id: str) -> dict:
    _, resp = paths(world)
    if not resp.is_file():
        return {'status': 'pending'}
    if resp.is_symlink() or resp.stat().st_size > MAX_RESPONSE:
        fail('Unsafe radio response file')
    raw = resp.read_text(encoding='ascii')
    if not raw.endswith('\n'):
        return {'status': 'pending'}
    parts = raw.rstrip('\n').split('\t')
    if (len(parts) != 8 or parts[0] != 'v1' or not ID.fullmatch(parts[1])
            or parts[2] != world or parts[3] not in ('text', 'audio')
            or parts[4] not in ('complete', 'error')
            or not parts[5].isdigit() or not parts[6].isdigit()
            or not re.fullmatch(r'[a-z_]{3,80}', parts[7])):
        fail('Malformed radio response file')
    if parts[1] != request_id:
        return {'status': 'pending'}
    return {'status': parts[4], 'request_id': parts[1], 'operation': parts[3],
            'frequency_khz': int(parts[5]), 'clients_dispatched': int(parts[6]),
            'reason': parts[7]}


def assert_ready(world: str):
    if world != 'story_test':
        fail('Only story_test may receive Story radio controls')
    scanctl.assert_module_ready(world,"SiegerStoryRadio")
    mounts=scanctl.docker_mounts()
    if not scanctl.packaged_runtime(mounts,world) and '/pzomboid-server/media/lua/server/SiegerStoryRadio.lua' not in mounts:
        fail('Story radio runtime mount absent; controlled same-world restart required')


def action_packet(args: argparse.Namespace) -> tuple[str, dict]:
    frequency = freq_khz(args.frequency)
    source_x, source_y = position(args.source)
    signal = args.signal_strength
    if type(signal) is not int or not 100 <= signal <= 500000:
        fail('Signal strength must be 100..500000')
    if args.command == 'text':
        message = args.text
        if (not isinstance(message, str) or not message.strip()
                or any(c in message for c in '\r\n\x00\t')):
            fail('Radio text must be nonempty and single-line, without control bytes')
        encoded = message.encode('utf-8')
        if len(encoded) > MAX_TEXT_BYTES:
            fail('Radio text exceeds 480 UTF-8 bytes')
        mode, scope, payload, duration = 'text', 'radio', encoded.hex(), 0
    elif args.command == 'audio':
        clip = args.clip
        registry = catalog()
        entry = registry['clips'].get(clip)
        if not entry or not entry['enabled']:
            fail('Unregistered/disabled audio clip (see radio clips)')
        if clip in registry.get('playlist', []) or entry['duration_ms'] > 60000:
            fail('Music tracks or long clips must use the FM station, not audio CUE')
        if not args.allow_audio:
            fail('Explicit --allow-audio required for playback')
        if args.scope == 'global' and not args.allow_global:
            fail('Global playback requires explicit --allow-global')
        mode, scope, payload, duration = 'audio', args.scope, clip, entry['duration_ms']
    else:
        fail('Unsupported radio operation')
    return ('\t'.join(['v1', 'ID_PLACEHOLDER', args.world, mode,
                       str(frequency), str(source_x), str(source_y), str(signal),
                       scope, payload, str(duration)]) + '\n',
            {'world': args.world, 'kind': mode, 'frequency_mhz': args.frequency,
             'source': [source_x, source_y], 'signal_strength': signal,
             'scope': scope, 'text': args.text if mode == 'text' else None,
             'clip': payload if mode == 'audio' else None,
             'duration_ms': duration,
             'client_pack_required': mode == 'audio'})


def transmit(args: argparse.Namespace):
    packet, preview = action_packet(args)
    if not args.yes:
        print('READ-ONLY radio preview; no broadcast queued.')
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        print('Repeat with --yes to queue one controlled transmission.')
        return
    assert_ready(args.world)
    old = read_request(args.world)
    if old:
        state = read_response(args.world, old['id'])
        if state['status'] == 'pending':
            fail('Previous radio request is pending; do not overwrite it')
        if state['status'] == 'error' and not args.acknowledge_failed:
            fail('Previous radio request failed; manually check logs, then --acknowledge-failed')
    ident = secrets.token_hex(16)
    packet = packet.replace('ID_PLACEHOLDER', ident, 1)
    if len(packet) > MAX_PACKET:
        fail('Radio request too large')
    req, _ = paths(args.world)
    scanctl.atomic_request(req, packet)
    print('QUEUED:', preview['kind'], preview['frequency_mhz'], 'MHz', 'request_id:', ident)
    print('Check: sudo pz story radio status', args.world)
    print('Server dispatch does not prove radio reception or audio playback on clients.')


def status(args: argparse.Namespace):
    if args.world != 'story_test':
        fail('Only story_test')
    previous = read_request(args.world)
    if not previous:
        fail('No radio requests in this world')
    state = read_response(args.world, previous['id'])
    print(json.dumps(state, ensure_ascii=False, indent=2))
    if state['status'] == 'error':
        fail('Radio transmission failed; inspect server logs and attempt guard')


def clips(args: argparse.Namespace):
    if args.world != 'story_test':
        fail('Only story_test')
    data = catalog()
    print(json.dumps(data, ensure_ascii=False, indent=2))


def station_status(args):
    if args.world!='story_test':fail('Radio station limited to story_test')
    folder=scanctl.lua_dir(args.world)
    state,previous=folder/STATION_STATE,folder/STATION_RESP
    if state.is_symlink() or previous.is_symlink():fail('Station status symlink refused')
    mode='off'
    if state.is_file():
        if state.stat().st_size>32:fail('Station state oversized')
        raw=state.read_text('ascii').strip()
        if raw not in ('v1\ton','v1\toff'):fail('Malformed station state')
        mode='on' if raw=='v1\ton' else 'off'
    result={'world':args.world,'station_mode':mode,'playlist':catalog()['playlist']}
    if previous.is_file():
        if previous.stat().st_size>200:fail('Station response oversized')
        fields=previous.read_text('ascii').strip().split('\t')
        if len(fields)==5 and fields[0]=='v1' and ID.fullmatch(fields[1]) and fields[2] in ('start','stop') and fields[3] in ('complete','error'):
            result['last_command']={'id':fields[1],'mode':fields[2],'status':fields[3]}
    print(json.dumps(result,ensure_ascii=False,indent=2))


def station_control(args):
    if args.world!='story_test':fail('Only story_test supports SiegerRadio')
    data=catalog()
    if args.station_command=='start' and len(data['playlist'])<2:
        fail('Add at least two songs with radio_assets.py add --music before starting')
    version=catalog_version(data)
    if not args.yes:
        print('READ-ONLY: would',args.station_command,'NORTHBOUND FM 101.2; songs:',len(data['playlist']))
        print('No commands queued; add --yes after installing the matching client pack.')
        return
    assert_ready(args.world)
    if not scanctl.packaged_runtime(scanctl.docker_mounts(),args.world):
        fail('Station server module not mounted; approved story_test restart required')
    folder=scanctl.lua_dir(args.world)
    request,response=folder/STATION_REQ,folder/STATION_RESP
    if request.is_symlink() or response.is_symlink():fail('Station protocol symlink refused')
    if request.is_file():
        if request.stat().st_size>150:fail('Previous station request oversized')
        old=request.read_text('ascii').strip().split('\t')
        if len(old)!=5 or old[0]!='v1' or not ID.fullmatch(old[1]):
            fail('Malformed old station request')
        if not response.is_file() or response.stat().st_size>200:
            fail('Previous station command pending')
        reply=response.read_text('ascii').strip().split('\t')
        if len(reply)!=5 or reply[1]!=old[1] or reply[3] not in ('complete','error'):
            fail('Previous station request still pending')
    rid=secrets.token_hex(16)
    scanctl.atomic_request(request,'\t'.join(['v1',rid,'story_test',args.station_command,version])+'\n')
    print('QUEUED:',args.station_command,'request_id:',rid)
    print('Check: sudo pz story radio station status story_test')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    base = argparse.ArgumentParser(add_help=False)
    base.add_argument('world')
    base.add_argument('--frequency', required=True, help='MHz, e.g. 101.3')
    base.add_argument('--source', required=True, help='Radio source X,Y')
    base.add_argument('--signal-strength', type=int, default=100000)
    base.add_argument('--yes', action='store_true', help='Actual send, default preview only')
    base.add_argument('--acknowledge-failed', action='store_true',
                      help='After manual review of failed previous request')
    p = subs.add_parser('text', parents=[base])
    p.add_argument('--text', required=True)
    p.set_defaults(handler=transmit)
    p = subs.add_parser('audio', parents=[base])
    p.add_argument('--clip', required=True, help='Registered audio catalog clip ID')
    p.add_argument('--scope', choices=('tuned', 'global'), default='tuned')
    p.add_argument('--allow-audio', action='store_true')
    p.add_argument('--allow-global', action='store_true')
    p.set_defaults(handler=transmit)
    p = subs.add_parser('status')
    p.add_argument('world')
    p.set_defaults(handler=status)
    p = subs.add_parser('clips')
    p.add_argument('world')
    p.set_defaults(handler=clips)
    station = subs.add_parser('station',help='Nonrepeating shuffle station')
    commands=station.add_subparsers(dest='station_command',required=True)
    for operation in ('start','stop'):
        q=commands.add_parser(operation)
        q.add_argument('world')
        q.add_argument('--yes',action='store_true')
        q.set_defaults(handler=station_control)
    q=commands.add_parser('status')
    q.add_argument('world')
    q.set_defaults(handler=station_status)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as error:
        parser.exit(2, 'SiegerRadio: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
