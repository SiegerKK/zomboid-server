#!/usr/bin/env python3
"""Explicit same-slot cold restore, called under the pz lifecycle lock.

Never stops/starts a game or deletes the replaced slot. No caller shell/Lua.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import stat
import subprocess
import tarfile
import tempfile

STORE = Path(os.environ.get('PZ_STORY_STORE_ROOT', '/srv/zomboid'))
WORLD = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}')
ARCHIVE = re.compile(r'world-[A-Za-z0-9_-]+\.tar\.gz')
ROOT_FILES = {'profile', 'mods.env', 'deployment.txt', 'preset', 'server-rules.env'}
MAX_BYTES = 64 * 1024**3
MAX_MEMBERS = 1000000


def fail(message):
    raise ValueError(message)


def real_path(path):
    path = Path(path)
    for part in [path, *path.parents]:
        if part.is_symlink():
            fail('Symlink path refused')
    return path


def regular(path):
    fd = os.open(real_path(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        fail('Expected regular file')
    return os.fdopen(fd, 'rb')


def read_spec(path, world):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail('Duplicate request key')
            result[key] = value
        return result
    with regular(path) as stream:
        raw = stream.read(8193)
    if len(raw) > 8192:
        fail('Oversized restore request')
    doc = json.loads(raw, object_pairs_hook=unique)
    if (not isinstance(doc, dict) or set(doc) != {'schema', 'world', 'archive', 'sha256'}
            or type(doc['schema']) is not int or doc['schema'] != 1
            or doc['world'] != world
            or not isinstance(doc['archive'], str) or not ARCHIVE.fullmatch(doc['archive'])
            or not isinstance(doc['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', doc['sha256'])):
        fail('Invalid restore identity; exact world, archive basename and SHA-256 required')
    return doc


def stopped(world):
    if real_path(STORE / 'manager' / 'active-world').read_text().strip() != world:
        fail('Only the selected world may be restored')
    result = subprocess.run(['docker', 'inspect', 'zomboid-server'], check=True,
                            capture_output=True, text=True, timeout=20)
    rows = json.loads(result.stdout)
    if len(rows) != 1:
        fail('Unknown container state')
    state = rows[0]['State']
    if state.get('Status') not in ('exited', 'created') or state.get('Running') is not False:
        fail('Stop the game before restoring; never disconnects players automatically')
    if state.get('ExitCode') != 0 or state.get('OOMKilled'):
        fail('Unclean game exit; inspect before restoring')
    mounts = [m for m in rows[0].get('Mounts', []) if m.get('Destination') == '/root/Zomboid']
    if len(mounts) != 1 or mounts[0].get('Source') != str(STORE / 'worlds' / world / 'data'):
        fail('Container save mount does not match target world')


def members(archive):
    seen, total, result = set(), 0, []
    for member in archive:
        name = member.name.rstrip('/')
        parts = PurePosixPath(name).parts
        if (not name or name.startswith('/') or '\\' in name or '\x00' in name
                or any(p in ('..', '.') for p in name.split('/'))
                or str(PurePosixPath(name)) != name
                or len(name) > 512
                or name in seen or not (member.isdir() or member.isfile())
                or member.issparse() or not parts
                or parts[0] not in ROOT_FILES | {'data', 'story'}
                or (parts[0] in ROOT_FILES and (len(parts) != 1 or not member.isfile() or member.size > 1024**2))):
            fail('Unsafe archive member')
        seen.add(name)
        total += member.size
        if len(seen) > MAX_MEMBERS or total > MAX_BYTES:
            fail('Restore resource budget exceeded')
        result.append(member)
    for required in ('profile', 'mods.env', 'deployment.txt', 'data'):
        if required not in seen:
            fail('Incomplete manager archive')
    return result, total


def restore(world, request, yes=False):
    if not WORLD.fullmatch(world):
        fail('Invalid world name')
    spec = read_spec(request, world)
    current = real_path(STORE / 'worlds' / world)
    if not current.is_dir() or not real_path(current / 'data').is_dir():
        fail('Existing target slot required')
    path = real_path(STORE / 'backups' / 'worlds' / world / spec['archive'])
    with regular(Path(str(path) + '.sha256')) as sidecar:
        fields = sidecar.read(4097).decode('ascii').strip().split()
    if fields != [spec['sha256'], path.name]:
        fail('Checksum sidecar does not match explicit request')
    with regular(path) as stream:
        before = os.fstat(stream.fileno())
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != spec['sha256']:
            fail('Archive checksum mismatch')
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode='r:gz') as archive:
            entries, total = members(archive)
            for filename in ('profile', 'mods.env'):
                with archive.extractfile(filename) as source, regular(current / filename) as existing:
                    if source.read() != existing.read():
                        fail('Archived mod profile differs; review before restoring')
            report = dict(world=world, archive=path.name, sha256=digest,
                          members=len(entries), payload_bytes=total, mode='preview',
                          preserves_current=True, game_started=False)
            if not yes:
                return report
            if os.geteuid() != 0:
                fail('Apply requires the protected pz broker')
            stopped(world)
            if shutil.disk_usage(current.parent).free < total + 64 * 1024**2:
                fail('Insufficient disk for restore while preserving current data')
            preserved_root = real_path(STORE / 'checkpoint-preserved')
            if preserved_root.exists() and preserved_root.stat().st_dev != current.parent.stat().st_dev:
                fail('Preserved slots must share the worlds filesystem')
            preserved_root.mkdir(mode=0o700, exist_ok=True)
            temp = Path(tempfile.mkdtemp(prefix='.checkpoint-', dir=current.parent))
            # Fully validate archive paths before extraction; never restore links,
            # ownership, executable bits or devices from archive metadata.
            try:
                for member in entries:
                    dest = temp / member.name
                    if member.isdir():
                        dest.mkdir(mode=0o700, parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        with archive.extractfile(member) as source, dest.open('xb') as output:
                            shutil.copyfileobj(source, output)
                            output.flush()
                            os.fsync(output.fileno())
                        dest.chmod(0o600)
                if not (temp / 'data').is_dir():
                    fail('Archive data root is not a directory')
                after = os.fstat(stream.fileno())
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    fail('Archive changed while restoring')
                stopped(world)  # Recheck immediately before rename under pz lock.
                preserved = preserved_root / (world + '-' + secrets.token_hex(12))
                # Move the entire slot: saves AND setup/native ledgers are coherent.
                os.rename(current, preserved)
                try:
                    os.rename(temp, current)
                except BaseException:
                    os.rename(preserved, current)
                    raise
                report.update(mode='restored', preserved_slot=str(preserved))
                return report
            finally:
                if temp.exists():
                    shutil.rmtree(temp)  # Only our private, never-active extraction.


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('world')
    parser.add_argument('--file', required=True, help='JSON: schema, world, archive basename, sha256')
    parser.add_argument('--yes', action='store_true')
    args = parser.parse_args()
    print(json.dumps(restore(args.world, args.file, args.yes), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError, KeyError) as error:
        raise SystemExit('checkpoint-restore: ' + str(error))
