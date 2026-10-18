#!/usr/bin/env python3
"""Build and byte-verify a deterministic, Lua-only Viewpoint Lite client ZIP.

No Viewpoint JAR, ZombieBuddy, game assets, user data or music is packaged.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "mods/SiegerViewpointLite"
PREFIX = "SiegerViewpointLite"
ALLOWED = {
    "42/mod.info",
    "42/media/lua/client/SiegerViewpointLite.lua",
}
MAX_FILE = 128 * 1024


def expected() -> dict[str, bytes]:
    if not MOD.is_dir() or MOD.is_symlink():
        raise ValueError("client addon directory missing/unsafe")
    actual = {p.relative_to(MOD).as_posix() for p in MOD.rglob("*") if p.is_file()}
    if actual != ALLOWED:
        raise ValueError(f"unexpected Viewpoint Lite files: {sorted(actual ^ ALLOWED)}")
    result = {}
    for rel in sorted(ALLOWED):
        path = MOD / rel
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
            raise ValueError("missing, linked or oversized addon source: " + rel)
        result[PREFIX + "/" + rel] = path.read_bytes()
    return result


def verify(path: Path) -> str:
    want = expected()
    if not path.is_file() or path.is_symlink():
        raise ValueError("no regular archive to verify")
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != len(want) or len({m.filename for m in members}) != len(members):
            raise ValueError("missing/extra/duplicate archive member")
        for item in members:
            rel = PurePosixPath(item.filename)
            if rel.is_absolute() or ".." in rel.parts or item.filename not in want:
                raise ValueError("unsafe/unexpected archive path")
            if item.file_size > MAX_FILE or archive.read(item) != want[item.filename]:
                raise ValueError("archive differs from source: " + item.filename)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(path: Path) -> str:
    want = expected()
    if path.exists() or path.is_symlink() or path.resolve().is_relative_to(MOD.resolve()):
        raise ValueError("output must be a new archive outside source tree")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(path, mode="x") as archive:
            for name, data in sorted(want.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 10, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
        return verify(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="mode", required=True)
    b = sub.add_parser("build")
    b.add_argument("--output", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("archive", type=Path)
    args = cli.parse_args()
    try:
        if args.mode == "build":
            digest = build(args.output)
            print(f"EXPERIMENTAL VIEWPOINT LITE ZIP: {args.output} SHA256: {digest}")
        else:
            digest = verify(args.archive)
            print(f"PASS Viewpoint Lite source-identical ZIP SHA256: {digest}")
    except (OSError, ValueError, zipfile.BadZipFile) as err:
        cli.exit(2, "Viewpoint Lite pack: " + str(err) + "\n")


if __name__ == "__main__":
    main()
