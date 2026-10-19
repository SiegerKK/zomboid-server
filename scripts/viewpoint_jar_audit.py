#!/usr/bin/env python3
"""Read-only Viewpoint JAR reference audit (never executes/extracts/copies code).

Counts constant-pool method REFERENCES, not runtime GL invocations or leaks.
Requires the user's legitimately installed Viewpoint.jar. Stdlib only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import zipfile

MAX_JAR_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 96 * 1024 * 1024
MAX_CLASS_BYTES = 2 * 1024 * 1024
MAX_CLASSES = 10000
GL_PREFIX = "org/lwjgl/opengl/GL"
WATCH = {
    "glGenTextures", "glCreateTextures", "glDeleteTextures",
    "glTexStorage2D", "glTexStorage3D", "glTextureStorage2D",
    "glTextureStorage3D", "glTexImage2D", "glTexImage3D",
    "glGenBuffers", "glDeleteBuffers", "glBufferData", "glBufferStorage",
    "glGenFramebuffers", "glCreateFramebuffers", "glDeleteFramebuffers",
    "glGenVertexArrays", "glDeleteVertexArrays", "glMapBufferRange",
    "glUnmapBuffer", "glDispatchCompute", "glMemoryBarrier",
    "glCopyImageSubData", "glTexBufferRange",
}
ALIASES = ("viewpoint/mac41/Textures41", "viewpoint/mac41/Buffers41")


class ClassFormatError(ValueError):
    pass


def cp_method_references(data: bytes) -> list[tuple[str, str]]:
    """Metadata-only Java constant pool parser; no class loading or execution."""
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        raise ClassFormatError("not a Java class")
    pool_size = struct.unpack_from(">H", data, 8)[0]
    if pool_size < 2 or pool_size > 65000:
        raise ClassFormatError("invalid constant pool size")
    strings: dict[int, str] = {}
    classes: dict[int, int] = {}
    signatures: dict[int, tuple[int, int]] = {}
    method_refs: list[tuple[int, int]] = []
    offset, index = 10, 1

    def u2():
        nonlocal offset
        if offset + 2 > len(data):
            raise ClassFormatError("truncated constant pool")
        v = struct.unpack_from(">H", data, offset)[0]
        offset += 2
        return v

    def take(size: int):
        nonlocal offset
        if size < 0 or offset + size > len(data):
            raise ClassFormatError("truncated constant pool entry")
        part = data[offset:offset + size]
        offset += size
        return part

    while index < pool_size:
        tag = take(1)[0]
        if tag == 1:
            strings[index] = take(u2()).decode("utf-8", errors="replace")
        elif tag in (3, 4):
            take(4)
        elif tag in (5, 6):
            take(8)
            index += 1
        elif tag in (7, 8, 16, 19, 20):
            v = u2()
            if tag == 7:
                classes[index] = v
        elif tag in (9, 10, 11, 12, 17, 18):
            a, b = u2(), u2()
            if tag in (10, 11):
                method_refs.append((a, b))
            elif tag == 12:
                signatures[index] = (a, b)
        elif tag == 15:
            take(1)
            u2()
        else:
            raise ClassFormatError(f"unsupported class-pool tag {tag}")
        index += 1

    out = []
    for class_idx, sig_idx in method_refs:
        sig = signatures.get(sig_idx)
        owner_idx = classes.get(class_idx)
        if sig is None or owner_idx is None:
            raise ClassFormatError("dangling method/class constant pool reference")
        owner = strings.get(owner_idx)
        name = strings.get(sig[0])
        if owner is None or name is None:
            raise ClassFormatError("unresolved method/class name")
        if owner.startswith(GL_PREFIX) or owner in ALIASES:
            out.append((owner, name))
    return out


def sha256(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            dig.update(block)
    return dig.hexdigest()


def audit(path: Path, expected_sha256: str | None = None) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_JAR_BYTES:
        raise ValueError("supply a regular, safe-sized, non-symlink Viewpoint.jar")
    digest = sha256(path)
    if expected_sha256 and digest != expected_sha256.lower():
        raise ValueError("unexpected Viewpoint JAR SHA-256; no version-specific diagnosis")
    class_references: dict[str, Counter] = {}
    with zipfile.ZipFile(path, "r") as archive:
        entries = archive.infolist()
        if sum(item.file_size for item in entries) > MAX_TOTAL_BYTES:
            raise ValueError("JAR exceeds metadata audit limits")
        classes = [item for item in entries if item.filename.endswith(".class")]
        if len(classes) > MAX_CLASSES or not classes:
            raise ValueError("unexpected class count")
        if len({item.filename for item in classes}) != len(classes):
            raise ValueError("duplicate class names")
        for item in classes:
            if item.file_size > MAX_CLASS_BYTES:
                raise ValueError("oversized class")
            if not item.filename.startswith("viewpoint/"):
                continue
            class_name = item.filename[:-6].replace("/", ".")
            refs = cp_method_references(archive.read(item))
            watched = Counter(name for owner, name in refs
                              if name in WATCH or name.startswith("glUniform")
                              or name.startswith("glProgramUniform"))
            if watched:
                class_references[class_name] = watched
    priority = ("glTexStorage3D", "glTextureStorage3D", "glTexImage3D",
                "glGenTextures", "glCreateTextures", "glGenBuffers",
                "glBufferData", "glBufferStorage", "glCreateFramebuffers",
                "glGenFramebuffers")
    candidate = []
    for name, methods in class_references.items():
        suspect = sum(methods[k] for k in priority)
        candidate.append({"class": name, "allocation_api_refs": suspect,
                          "method_refs": dict(sorted(methods.items()))})
    candidate.sort(key=lambda x: (-x["allocation_api_refs"], x["class"]))
    return {
        "viewpoint_jar_sha256": digest,
        "class_count": len(classes),
        "classes_with_gl_references": len(candidate),
        "candidates": candidate[:50],
        "limitations": [
            "Only constant-pool method references, NOT dynamic call counts.",
            "No allocation sizes, per-frame rates or leak conclusions.",
            "No Viewpoint code, bytecode, shaders or assets are extracted.",
            "Optimizations require a separate installed-JAR ABI review and GPU tests."
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jar", type=Path, help="locally installed Viewpoint.jar")
    parser.add_argument("--expect-sha256", type=str, help="optional full exact 64-digit pin")
    args = parser.parse_args()
    if args.expect_sha256 and (len(args.expect_sha256) != 64
                               or any(c not in "0123456789abcdefABCDEF"
                                      for c in args.expect_sha256)):
        parser.error("--expect-sha256 needs a full hexadecimal SHA-256")
    try:
        result = audit(args.jar, args.expect_sha256)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        parser.exit(2, f"Viewpoint read-only audit: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
