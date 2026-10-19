#!/usr/bin/env python3
"""Offline same-date clock edit for the pinned B42.21 GMTM v249 save only."""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import tarfile
import tempfile

import scanctl
import backupctl

IMAGE = 'ghcr.io/meshi-team/project-zomboid-server@sha256:45c602cb07a1f4b228eefcf92ed4480cf877c409dcd16f0aaa53432063dd3b56'
RELATIVE = Path('data/Saves/Multiplayer/SiegerZomboid/map_t.bin')

def decode(body):
    if len(body) < 64 or len(body) > 1048576 or body[:4] != b'GMTM':
        raise ValueError('Unsupported/truncated GameTime save')
    version, = struct.unpack_from('>i', body, 4)
    if version != 249:
        raise ValueError('Only audited GameTime save version 249 is supported')
    last, current, day, month, year = struct.unpack_from('>ffiii', body, 20)
    if not all(math.isfinite(v) and 0 <= v < 24 for v in (last, current)):
        raise ValueError('Invalid saved clock')
    date = datetime.date(year, month + 1, day + 1)
    if not 1800 <= year <= 2500:
        raise ValueError('Invalid saved year')
    return {'date': date.isoformat(), 'time_hours': current,
            'last_time_hours': last, 'save_version': version}

def changed(body, clock):
    if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock):
        raise ValueError('Use HH:MM in 00:00..23:59')
    before = decode(body)
    hour, minute = map(int, clock.split(':'))
    value = hour + minute / 60
    # GameTime.save(DataOutputStream): GMTM, version, multiplier, nights,
    # targetZombies, lastTimeOfDay, timeOfDay, day, month, year, opaque tail.
    output = body[:20] + struct.pack('>ff', value, value) + body[28:]
    after = decode(output)
    assert before['date'] == after['date']
    assert output[:20] == body[:20] and output[28:] == body[28:]
    return output, before, after

def state(world, stopped=True):
    if world != 'story_test' or scanctl.active_world() != world:
        raise ValueError('Only selected story_test is supported')
    info = json.loads(subprocess.run(['docker', 'inspect', 'zomboid-server'],
        check=True, capture_output=True, text=True, timeout=15).stdout)[0]
    if stopped and (info['State']['Running'] or info['State']['ExitCode'] != 0):
        raise ValueError('Cleanly stop the game through pz before editing the clock')
    if info['Config']['Image'] != IMAGE:
        raise ValueError('Game image differs from the audited pinned B42.21 image')
    slot = scanctl.slot(world)
    mounts = {m['Destination']: Path(m['Source']).resolve() for m in info['Mounts']}
    if mounts.get('/root/Zomboid') != (slot / 'data').resolve():
        raise ValueError('World mount mismatch')
    path = slot / RELATIVE
    for part in (slot, *[slot.joinpath(*RELATIVE.parts[:i]) for i in range(1, len(RELATIVE.parts)+1)]):
        if part.is_symlink():
            raise ValueError('Symlink in clock save path')
    return info, path

def apply(world, clock, yes=False):
    info, path = state(world)
    with backupctl.regular(path) as stream:
        metadata = os.fstat(stream.fileno())
        if metadata.st_nlink != 1:
            raise ValueError('Hard-linked save refused')
        body = stream.read(1048577)
    output, before, after = changed(body, clock)
    result = {'world': world, 'before': before, 'after': after, 'applied': False,
              'scope': 'same-date clock only; no elapsed-time simulation'}
    if not yes:
        print(json.dumps(result, indent=2))
        return
    verification = backupctl.report(backupctl.ROOT, world)['verified_latest']
    backup = Path(verification['archive'])
    finished = datetime.datetime.fromisoformat(info['State']['FinishedAt'].replace('Z', '+00:00')).timestamp()
    age = datetime.datetime.now(datetime.timezone.utc).timestamp() - backup.stat().st_mtime
    if age > 1800 or backup.stat().st_mtime < finished:
        raise ValueError('Fresh cold backup after latest stop required (<=30 minutes)')
    with tarfile.open(backup, 'r:gz') as archive:
        member = archive.getmember(str(RELATIVE))
        if not member.isfile() or member.size != len(body):
            raise ValueError('Cold backup does not contain the exact clock file')
        with archive.extractfile(member) as stream:
            if stream.read(1048577) != body:
                raise ValueError('Saved clock differs from verified cold backup')
    if path.read_bytes() != body:
        raise ValueError('Clock file changed during preflight')
    temp = None
    try:
        fd, temp = tempfile.mkstemp(prefix='.clock-', dir=path.parent)
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), stat.S_IMODE(metadata.st_mode))
            os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        temp = None
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp is not None:
            os.unlink(temp)
    if path.read_bytes() != output:
        raise ValueError('Clock write verification failed; leave game stopped for investigation')
    result.update(applied=True, backup_sha256=verification['sha256'],
        original_sha256=hashlib.sha256(body).hexdigest(),
        updated_sha256=hashlib.sha256(output).hexdigest())
    print(json.dumps(result, indent=2))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('world')
    parser.add_argument('time', nargs='?', help='HH:MM, same calendar date')
    parser.add_argument('--show', action='store_true', help='Read persisted clock, not a live JVM snapshot')
    parser.add_argument('--yes', action='store_true')
    args = parser.parse_args()
    try:
        if args.show:
            if args.time or args.yes:
                raise ValueError('--show cannot edit the clock')
            _, path = state(args.world, stopped=False)
            with backupctl.regular(path) as stream:
                data = decode(stream.read(1048577))
            print(json.dumps(dict(data, source='persisted map_t.bin; use pz save-live before checking'), indent=2))
        else:
            if args.time is None:
                raise ValueError('Specify HH:MM or --show')
            apply(args.world, args.time, args.yes)
    except (ValueError, OSError, KeyError, subprocess.SubprocessError, tarfile.TarError) as error:
        parser.exit(2, 'Story clock: ' + str(error) + '\n')

if __name__ == '__main__':
    main()
