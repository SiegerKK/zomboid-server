#!/usr/bin/env python3
"""Build or verify/install a versioned SiegerRadio client ZIP; audio stays outside Git."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile
import radio_assets as assets

ROOT = Path(__file__).resolve().parents[1]
PREFIX = 'SiegerRadio/'
MAX_TOTAL = 1024 * 1024 * 1024


def expected():
    files = {}
    for path in (ROOT / 'mods/SiegerRadio').rglob('*'):
        if path.is_file() and not path.is_symlink():
            name = PREFIX + path.relative_to(ROOT / 'mods/SiegerRadio').as_posix()
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    # External WAVs may be absent in a clean checkout; their reviewed SHA is mandatory.
    for ident, entry in assets.load()['clips'].items():
        files[PREFIX + '42/media/sound/SiegerRadio/' + ident + '.wav'] = entry['sha256']
    return files


def verify(path):
    wanted = expected()
    with zipfile.ZipFile(path) as z:
        entries = z.infolist()
        if len(entries) != len(wanted) or len({x.filename for x in entries}) != len(entries):
            raise ValueError('Pack has missing, extra or duplicate members')
        if sum(x.file_size for x in entries) > MAX_TOTAL:
            raise ValueError('Pack exceeds 1 GiB uncompressed')
        for entry in entries:
            name = entry.filename
            rel = PurePosixPath(name)
            if rel.is_absolute() or '..' in rel.parts or '\\' in name or name not in wanted:
                raise ValueError('Unexpected pack member')
            if entry.file_size > assets.MAX_WAV_BYTES:
                raise ValueError('Pack member exceeds reviewed size limit')
            if hashlib.sha256(z.read(entry)).hexdigest() != wanted[name]:
                raise ValueError('Pack file hash mismatch: ' + name)
    return wanted


def build(output):
    assets.check()
    if output.exists():
        raise ValueError('Output exists; never overwrite a versioned pack')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(output, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for name in sorted(expected()):
                z.write(ROOT / 'mods' / name, name)
        verify(output)
    except BaseException:
        if output.exists(): output.unlink()
        raise
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    Path(str(output)+'.sha256').write_text(digest+'  '+output.name+'\n')
    print('PACK:', output, 'SHA256:', digest)


def install(path, destination, audio_only):
    wanted = verify(path)  # validate every byte before any destination mutation
    if destination.exists():
        raise ValueError('Install destination must be new; existing mod is never replaced automatically')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.siegerradio-', dir=destination.parent) as folder:
        stage = Path(folder) / 'mod'
        stage.mkdir()
        with zipfile.ZipFile(path) as z:
            for name in wanted:
                if audio_only and not name.endswith('.wav'): continue
                target = stage / PurePosixPath(name).relative_to('SiegerRadio')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name)); target.chmod(0o644)
        stage.rename(destination)
    print('INSTALLED:', destination, 'version:', assets.catalog_version(assets.load()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('build'); p.add_argument('--output', type=Path, required=True)
    p = subs.add_parser('verify'); p.add_argument('archive', type=Path)
    p = subs.add_parser('install'); p.add_argument('archive', type=Path)
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--audio-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'build': build(args.output)
        elif args.command == 'verify':
            files = verify(args.archive); print('PASS:', len(files), 'pack file hashes match reviewed code/catalog')
        else: install(args.archive, args.destination, args.audio_only)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(2, 'Radio pack: '+str(exc)+'\n')


if __name__ == '__main__': main()
