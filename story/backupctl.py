#!/usr/bin/env python3
"""Private, read-only manager backup metadata; never extract archive contents."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tarfile
import time

ROOT = Path('/srv/zomboid/backups')

def regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Expected regular backup file')
        return os.fdopen(fd, 'rb')
    except BaseException:
        os.close(fd)
        raise

def report(root, world=None):
    if world is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,47}', world):
        raise ValueError('Invalid world name')
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Backup root must be a real directory')
    rows = []
    skipped = 0
    seen = set()
    allocated = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        safe = []
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                skipped += 1
            else:
                safe.append(name)
        dirs[:] = safe
        for name in files:
            path = Path(directory) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                skipped += 1
                continue
            key = (info.st_dev, info.st_ino)
            if key not in seen:
                allocated += info.st_blocks * 512
                seen.add(key)
            rows.append((path, info.st_size, info.st_mtime_ns))
            if len(rows) > 100000:
                raise ValueError('Too many backup files; report refused')
    groups = {}
    for path, size, _ in rows:
        if path.name.endswith('.tar.gz'):
            group = str(path.parent.relative_to(root))
            item = groups.setdefault(group, {'archives': 0, 'bytes': 0})
            item['archives'] += 1
            item['bytes'] += size
    result = {'scope': str(root), 'files': len(rows),
              'archives': sum(g['archives'] for g in groups.values()),
              'logical_bytes': sum(row[1] for row in rows),
              'allocated_bytes': allocated, 'skipped_unsafe_entries': skipped,
              'groups': groups}
    if world is not None:
        candidates = [r for r in rows if r[0].parent == root / 'worlds' / world
                      and re.fullmatch(r'world-[A-Za-z0-9_-]+\.tar\.gz', r[0].name)]
        if not candidates:
            raise ValueError('No manager archive for this world')
        path, size, _ = max(candidates, key=lambda r: (r[2], r[0].name))
        begin = time.monotonic()
        with regular(Path(str(path) + '.sha256')) as stream:
            fields = stream.read(4097).decode('ascii').strip().split()
        if len(fields) != 2 or fields[1] != path.name or not re.fullmatch('[0-9a-f]{64}', fields[0]):
            raise ValueError('Invalid checksum sidecar')
        with regular(path) as stream:
            before = os.fstat(stream.fileno())
            digest = hashlib.sha256()
            while block := stream.read(8 * 1024 * 1024):
                digest.update(block)
            if digest.hexdigest() != fields[0]:
                raise ValueError('Backup checksum mismatch')
            stream.seek(0)
            members = payload = 0
            with tarfile.open(fileobj=stream, mode='r|gz') as archive:
                for member in archive:
                    members += 1
                    if member.isfile():
                        payload += member.size
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('Archive changed during verification')
        result['verified_latest'] = {'world': world, 'archive': str(path), 'bytes': size,
            'sha256': digest.hexdigest(), 'sha256_match': True, 'tar_readable': True,
            'members': members, 'regular_payload_bytes': payload,
            'verification_seconds': round(time.monotonic() - begin, 4)}
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-latest', metavar='WORLD')
    args = parser.parse_args()
    print(json.dumps(report(ROOT, args.verify_latest), indent=2))

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, tarfile.TarError, EOFError) as error:
        raise SystemExit('backup-info: ' + str(error))
