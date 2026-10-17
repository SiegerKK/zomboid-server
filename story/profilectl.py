#!/usr/bin/env python3
"""Sample Docker CPU/memory of existing world; not an isolated Story-mod profiler."""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import scanctl

SIZE = {"B": 1, "kB": 1000, "MB": 10**6, "GB": 10**9,
        "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}


def fail(message: str):
    raise ValueError(message)


def parse_size(raw: str) -> int:
    found = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{1,3})\s*", raw)
    if not found or found[2] not in SIZE:
        fail("Unrecognized Docker memory unit: " + raw[:80])
    return round(float(found[1]) * SIZE[found[2]])


def parse_stats(obj: dict):
    cp = obj.get("CPUPerc", "")
    mem = obj.get("MemUsage", "")
    if not isinstance(cp, str) or not cp.endswith("%"):
        fail("Docker CPU percentage not present")
    try:
        cpu = float(cp[:-1])
    except ValueError:
        fail("Invalid Docker CPU percentage")
    if cpu < 0 or cpu > 100000:
        fail("Implausible Docker CPU percentage")
    if not isinstance(mem, str) or "/" not in mem:
        fail("Docker memory usage is missing")
    left, right = mem.split("/", 1)
    used, limit = parse_size(left), parse_size(right)
    if used < 0 or limit < 1:
        fail("Invalid Docker memory numbers")
    return cpu, used, limit


def docker_sample() -> dict:
    proc = subprocess.run(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}", "zomboid-server"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if proc.returncode or not proc.stdout.strip():
        fail("Docker stats did not return a sample: " + proc.stderr[:200])
    row = json.loads(proc.stdout.splitlines()[0])
    cpu, used, limit = parse_stats(row)
    return {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cpu_percent": cpu, "memory_bytes": used, "limit_bytes": limit}


def profile(world: str, samples: int, interval: int) -> dict:
    scanctl.assert_ready(world)
    results = []
    for idx in range(samples):
        # Abort if the selected world changes or container is unavailable.
        if scanctl.active_world() != world:
            fail("Active world changed while profiling")
        sample = docker_sample()
        results.append(sample)
        print(f"[{idx+1}/{samples}] CPU={sample['cpu_percent']:.2f}% "
              f"RAM={sample['memory_bytes']/1024**3:.3f} GiB", flush=True)
        if idx + 1 < samples:
            time.sleep(interval)
    cpus = [r["cpu_percent"] for r in results]
    mems = [r["memory_bytes"] for r in results]
    return {"world": world, "source": "docker stats (entire game container)",
            "samples": samples, "interval_seconds": interval,
            "min_cpu_percent": min(cpus), "median_cpu_percent": statistics.median(cpus),
            "max_cpu_percent": max(cpus),
            "median_memory_mib": round(statistics.median(mems)/1024**2, 2),
            "max_memory_mib": round(max(mems)/1024**2, 2),
            "memory_limit_mib": round(results[-1]["limit_bytes"]/1024**2, 2),
            "data": results,
            "warning": "Container metrics include JVM/game/TLOU/other mods. "
                       "They do NOT isolate CPU or heap usage of Story Director."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("world")
    p.add_argument("--samples", type=int, default=12)
    p.add_argument("--interval", type=int, default=5)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    try:
        if args.world != "story_test":
            fail("Profiler scoped to story_test")
        if not 3 <= args.samples <= 120 or not 1 <= args.interval <= 60:
            fail("Samples 3..120, interval 1..60 s")
        result = profile(args.world, args.samples, args.interval)
        summary = {k: v for k, v in result.items() if k != "data"}
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if args.output:
            if (args.output.resolve().is_relative_to(scanctl.REPO) or
                    args.output.is_symlink() or args.output.exists()
                    or not args.output.parent.is_dir()):
                fail("Unsafe profile output destination")
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            print("Private profiler JSON:", args.output)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        p.exit(2, "Story profile: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
