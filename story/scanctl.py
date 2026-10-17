#!/usr/bin/env python3
"""On-demand, read-only scan of loaded Build 42 map cells around one online player.

No external service. The pz manager enforces root/operation lock; this CLI
also verifies active world, Docker mount identity and Story runtime mount.
The exchange uses the game's built-in Lua/ file I/O.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

STORE = Path(os.environ.get("PZ_STORY_STORE_ROOT", "/srv/zomboid")).resolve()
REPO = Path(__file__).resolve().parents[1]
WORLD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
USERNAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,30}$")
REQ_NAME = "SiegerStoryScanRequest.txt"
RESP_NAME = "SiegerStoryScanResult.txt"  # B42 writer extension allowlist
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_LINES = 140005
SIDE = 25
LEVELS = 5
ALLOWED_SIDES = {25, 51, 101}


def die(message: str):
    raise ValueError(message)


def slot(world: str) -> Path:
    if not WORLD.fullmatch(world):
        die("Invalid world name")
    path = STORE / "worlds" / world
    if not (path / "profile").is_file() or not (path / "data").is_dir():
        die(f"Unknown world slot: {world}")
    return path


def lua_dir(world: str) -> Path:
    return slot(world) / "data" / "Lua"


def request_path(world: str) -> Path:
    return lua_dir(world) / REQ_NAME


def response_path(world: str) -> Path:
    return lua_dir(world) / RESP_NAME


def active_world() -> str:
    path = STORE / "manager" / "active-world"
    if not path.is_file():
        die("No selected PZ world")
    value = path.read_text(encoding="utf-8").strip()
    if not WORLD.fullmatch(value):
        die("Invalid active world marker")
    return value


def docker_mounts():
    command = ["docker", "inspect", "--format", "{{json .}}", "zomboid-server"]
    call = subprocess.run(command, capture_output=True, text=True, check=False, timeout=15)
    if call.returncode:
        die("Cannot inspect Docker container; fail closed")
    try:
        info = json.loads(call.stdout)
    except json.JSONDecodeError as exc:
        die(f"Invalid Docker metadata: {exc}")
    if info.get("State", {}).get("Running") is not True:
        die("Game is not running")
    return {m["Destination"]: Path(m["Source"]).resolve()
            for m in info.get("Mounts", []) if "Destination" in m and "Source" in m}


def assert_ready(world: str):
    if active_world() != world:
        die(f"Active world is not {world}; do not scan another world's data")
    mounts = docker_mounts()
    expected = (slot(world) / "data").resolve()
    if mounts.get("/root/Zomboid") != expected:
        die(f"Container /root/Zomboid mount does not match {expected}")
    if "/pzomboid-server/media/lua/server/SiegerStoryAreaScan.lua" not in mounts:
        die("Story AreaScan runtime is not mounted: install and restart the test world first")
    if "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua" not in mounts:
        die("Story Director runtime is not mounted")
    if not (slot(world) / "story" / "bundle.lua").is_file():
        die("Story bundle is disabled for this world")


def parse_req(world: str):
    path = request_path(world)
    if not path.is_file():
        return None
    if path.is_symlink():
        die("Request file is a symlink")
    if path.stat().st_size > 128:
        die("Request file exceeds 128 bytes")
    match = re.fullmatch(
        r"(v[12])\t([0-9a-f]{32})\t([A-Za-z0-9_][A-Za-z0-9_.-]{0,30})\t(25|51|101)\t5\n?",
        path.read_text(encoding="ascii")
    )
    if not match or (match[1] == "v1" and match[4] != "25"):
        die("Invalid request file format; request not modified")
    return {"id": match[2], "username": match[3], "side": int(match[4]),
            "version": match[1]}


def read_response(world: str, requested_id: str | None = None):
    path = response_path(world)
    if not path.is_file():
        return None
    if path.is_symlink():
        die("Response file must not be a symlink")
    if path.stat().st_size > MAX_RESPONSE_BYTES:
        die("Area scan exceeds 32 MiB report safety limit")
    meta = None
    summary = None
    records = []
    with path.open(encoding="utf-8") as data:
        for line_index, raw in enumerate(data, 1):
            if line_index > MAX_LINES:
                die("Too many report lines")
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                if not raw.endswith("\n"):
                    return {"status": "pending"}
                die(f"Invalid JSONL at line {line_index}")
            if not isinstance(obj, dict):
                die(f"Non-object JSONL at line {line_index}")
            kind = obj.get("kind")
            if line_index == 1:
                if kind != "meta":
                    die("Report lacks meta header")
                meta = obj
                if requested_id is not None and meta.get("request_id") != requested_id:
                    return {"status": "pending"}
            elif kind == "summary":
                summary = obj
                if summary.get("request_id") != meta.get("request_id"):
                    die("Response request ID differs between header and footer")
                break
            else:
                if kind not in ("object", "container", "container_item", "ground_item", "static_object", "square", "quest_zombie"):
                    die(f"Unexpected row kind: {kind}")
                for axis in ("x", "y", "z"):
                    if not isinstance(obj.get(axis), int) or isinstance(obj[axis], bool):
                        die(f"Malformed {axis} at line {line_index}")
                records.append(obj)
    if meta is None or summary is None:
        return {"status": "pending"}
    if summary.get("status") not in ("complete", "partial", "error"):
        die("Invalid terminal scan status")
    request = parse_req(world)
    if request and meta.get("player") != request["username"]:
        die("Report player differs from requested exact username")
    if summary.get("status") == "complete" and (summary.get("truncated") is not False or summary.get("errors") != 0):
        die("Report claims complete despite errors or truncation")
    if "records" in summary and summary["records"] != len(records):
        die("Report record count differs from footer")
    if summary["status"] != "error":
        for key in ("requested_squares", "loaded_squares", "unloaded_squares", "scanned_squares", "records", "errors"):
            if type(summary.get(key)) is not int or summary[key] < 0:
                die(f"Invalid scan counter: {key}")
        expected_side = request["side"] if request else meta.get("side")
        if expected_side not in ALLOWED_SIDES or summary["requested_squares"] != expected_side * expected_side * LEVELS:
            die("Unexpected requested scan volume")
        if meta.get("side") != expected_side or meta.get("levels") != LEVELS:
            die("Incorrect scan dimensions in metadata")
        if summary["loaded_squares"] + summary["unloaded_squares"] != summary["scanned_squares"]:
            die("Loaded/missing counts differ from scanned squares")
        if summary["scanned_squares"] > summary["requested_squares"]:
            die("Scan exceeds approved volume")
        if summary["status"] == "complete" and summary["scanned_squares"] != expected_side * expected_side * LEVELS:
            die("Scan claims complete before visiting all candidates")
    return {"status": summary.get("status"), "meta": meta,
            "summary": summary, "records": records}


def atomic_request(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        die("Request file is a symlink")
    tmp = path.with_name("." + path.name + "." + secrets.token_hex(6) + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def scan(args):
    world = args.world
    slot(world)
    if not USERNAME.fullmatch(args.username):
        die("Use exact simple game login (letters/digits/_/./-), not display name")
    if not args.yes:
        die("Requires --yes; this snapshots loaded world information")
    assert_ready(world)
    side = getattr(args, "side", 25)
    if side not in ALLOWED_SIDES:
        die("Area must be 25, 51 or 101 cells wide")
    previous = parse_req(world)
    if previous:
        result = read_response(world, previous["id"])
        if result is None or result["status"] == "pending":
            die("Previous request is pending; do not overwrite an in-progress scan")
    new_id = secrets.token_hex(16)
    version = "v1" if side == 25 else "v2"
    atomic_request(request_path(world),
                   f"{version}\t{new_id}\t{args.username}\t{side}\t{LEVELS}\n")
    print(f"Requested {side}x{side}x{LEVELS} scan around {args.username} in {world}.")
    print(f"Request ID: {new_id}")
    print("Read-only one-shot; player must be connected. No chunks are force-loaded.")
    print(f"Wait a few seconds, then: sudo pz story scan-status {world}")
    print(f"Full JSON report: sudo pz story scan-report {world} --json")


def report_data(world: str):
    req = parse_req(world)
    if not req:
        die("No scan requested in this world")
    res = read_response(world, req["id"])
    if res is None or res["status"] == "pending":
        die(f"Scan {req['id']} is pending. Keep the player connected; check again in a few seconds.")
    return res


def summary_message(data, *, sample: int = 15):
    meta, summary = data["meta"], data["summary"]
    print(f"Scan {meta.get('request_id')} player={meta.get('player')} status={summary.get('status')}")
    print(f"Center=({meta.get('center_x')},{meta.get('center_y')},{meta.get('center_z')}), "
          f"area {meta.get('side')}x{meta.get('side')}x{meta.get('levels')}")
    print(f"Squares loaded={summary.get('loaded_squares')}/{summary.get('requested_squares')}, "
          f"unloaded={summary.get('unloaded_squares')}, errors={summary.get('errors')}")
    print(f"Objects={summary.get('objects')}, containers={summary.get('containers')}, "
          f"container items={summary.get('container_items')}, "
          f"ground items={summary.get('ground_items')}")
    print(f"Output truncated={summary.get('truncated')} (no hidden omissions).")
    if summary.get("reason"):
        print("Reason:", summary["reason"])
    containers = [x for x in data["records"] if x.get("kind") == "container"]
    for entry in containers[:sample]:
        print(f"  container @ ({entry['x']},{entry['y']},{entry['z']}) "
              f"obj #{entry.get('object_index')} subcontainer #{entry.get('container_index')}, "
              f"type={entry.get('container_type')}, items={entry.get('item_count')}")
    if len(containers) > sample:
        print(f"  ... {len(containers)-sample} more containers via scan-report --json")


def status(args):
    slot(args.world)
    data = report_data(args.world)
    if data is not None:
        summary_message(data)
        if data["status"] != "complete":
            die("Scan finished with " + str(data["status"]) + "; export for diagnosis, not a complete result")


def report(args):
    slot(args.world)
    data = report_data(args.world)
    if data is None:
        return
    if args.output:
        dst = Path(args.output)
        if dst.resolve().is_relative_to(REPO):
            die("Private scan exports must be outside the source repository")
        if dst.is_symlink() or dst.exists():
            die("Output file already exists; will not overwrite")
        if not dst.parent.is_dir():
            die("Output parent directory does not exist")
        fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(f"Saved full JSON: {dst} ({len(data['records'])} entities)")
    elif args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        summary_message(data, sample=25)
        print("Use --json or --output /var/tmp/area-scan.json for every item and position.")
    if data["status"] != "complete":
        die("Exported diagnostic report is " + str(data["status"]) + ", not complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    child = sub.add_parser("scan-player")
    child.add_argument("world")
    child.add_argument("username")
    child.add_argument("--yes", action="store_true")
    child.add_argument("--side", type=int, default=25,
                       choices=sorted(ALLOWED_SIDES), help="square side: 25, 51, 101")
    child.set_defaults(handler=scan)
    child = sub.add_parser("scan-status")
    child.add_argument("world")
    child.set_defaults(handler=status)
    child = sub.add_parser("scan-report")
    child.add_argument("world")
    child.add_argument("--json", action="store_true")
    child.add_argument("--output")
    child.set_defaults(handler=report)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (ValueError, OSError, subprocess.TimeoutExpired, UnicodeError,
            json.JSONDecodeError) as exc:
        parser.exit(2, "Story scan: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
