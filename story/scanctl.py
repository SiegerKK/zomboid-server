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
SCAN_MODES = {"squares", "objects", "containers", "items", "ground",
              "actors", "corpses", "vehicles", "windows", "blood"}
DEFAULT_MODES = ",".join(sorted(SCAN_MODES))


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


def packaged_runtime(mounts, world):
    return (mounts.get("/root/Zomboid/mods/SiegerAdmin") == (REPO/"mods/SiegerAdmin").resolve()
            and mounts.get("/root/Zomboid/Lua/SiegerStoryBundle.txt") == (slot(world)/"story/bundle.lua").resolve())


def assert_ready(world: str):
    if active_world() != world:
        die(f"Active world is not {world}; do not scan another world's data")
    mounts = docker_mounts()
    expected = (slot(world) / "data").resolve()
    if mounts.get("/root/Zomboid") != expected:
        die(f"Container /root/Zomboid mount does not match {expected}")
    if not packaged_runtime(mounts,world) and "/pzomboid-server/media/lua/server/SiegerStoryAreaScan.lua" not in mounts:
        die("Story AreaScan runtime is not mounted: install and restart the test world first")
    if not packaged_runtime(mounts,world) and "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua" not in mounts:
        die("Story Director runtime is not mounted")
    if not (slot(world) / "story" / "bundle.lua").is_file():
        die("Story bundle is disabled for this world")


def assert_module_ready(world: str, name: str):
    """Require the exact reviewed runtime through either supported overlay."""
    if not re.fullmatch(r"(?:SiegerStory[A-Za-z]+|SiegerAdminClock|SiegerAdminZombieDebug)", name):
        die("Invalid Story runtime name")
    assert_ready(world)
    mounts = docker_mounts()
    source = REPO / "story/runtime" / (name + ".lua")
    if not source.is_file() or source.is_symlink():
        die("Reviewed Story runtime missing or unsafe")
    if packaged_runtime(mounts, world):
        pack = "SiegerRadio" if name == "SiegerStoryRadio" else "SiegerAdmin"
        if mounts.get("/root/Zomboid/mods/" + pack) != (REPO / "mods" / pack).resolve():
            die("Required local mod pack is not mounted")
        packaged = REPO / "mods" / pack / "42/media/lua/server" / (name + ".lua")
        if (not packaged.is_file() or packaged.is_symlink()
                or packaged.read_bytes() != source.read_bytes()):
            die("Packaged Story runtime differs from reviewed source")
        return
    destination = "/pzomboid-server/media/lua/server/" + name + ".lua"
    if mounts.get(destination) != source.resolve():
        die("Story runtime not mounted from reviewed source; controlled deployment required")


def parse_req(world: str):
    path = request_path(world)
    if not path.is_file():
        return None
    if path.is_symlink():
        die("Request file is a symlink")
    if path.stat().st_size > 256:
        die("Request file exceeds 256 bytes")
    raw = path.read_text(encoding="ascii").rstrip("\n")
    legacy = re.fullmatch(
        r"(v[12])\t([0-9a-f]{32})\t([A-Za-z0-9_][A-Za-z0-9_.-]{0,30})\t(25|51|101)\t5",
        raw
    )
    if legacy:
        if legacy[1] == "v1" and legacy[4] != "25":
            die("Legacy v1 scan must use side=25")
        return {"id": legacy[2], "username": legacy[3],
                "side": int(legacy[4]), "levels": 5, "version": legacy[1]}
    modern = re.fullmatch(
        r"v3\t([0-9a-f]{32})\t([A-Za-z0-9_][A-Za-z0-9_.-]{0,30})"
        r"\t(-|[0-9]{1,5})\t(-|[0-9]{1,5})"
        r"\t([1-9]|[1-4][0-9]|50)\t(-?[0-9]{1,2})\t(-?[0-9]{1,2})"
        r"\t([a-z,]{3,150})", raw
    )
    if not modern:
        die("Invalid scan request file format; request not modified")
    modes = modern[8].split(",")
    if (len(modes) != len(set(modes)) or set(modes) - SCAN_MODES
            or ("blood" in modes and "squares" not in modes)
            or ("items" in modes and "containers" not in modes)):
        die("Invalid scan mode combination")
    radius = int(modern[5])
    zmin, zmax = int(modern[6]), int(modern[7])
    if not -2 <= zmin <= zmax <= 16 or zmax - zmin >= 5:
        die("Invalid floor range")
    if (modern[3] == "-") != (modern[4] == "-"):
        die("Center coordinates must both be '-' or both integers")
    return {"id": modern[1], "username": modern[2], "version": "v3",
            "side": radius * 2 + 1, "levels": zmax-zmin+1,
            "radius": radius, "min_z": zmin, "max_z": zmax,
            "center_x": None if modern[3] == "-" else int(modern[3]),
            "center_y": None if modern[4] == "-" else int(modern[4]),
            "modes": modes}


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
                if kind not in ("object", "container", "container_item", "ground_item", "static_object", "square", "quest_zombie", "quest_corpse",
                                "vehicle", "vehicle_part", "vehicle_container", "vehicle_item"):
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
        expected_levels = request["levels"] if request else meta.get("levels")
        if (type(expected_side) is not int or not 3 <= expected_side <= 101
                or expected_side % 2 != 1 or type(expected_levels) is not int
                or not 1 <= expected_levels <= 5 or
                summary["requested_squares"] != expected_side * expected_side * expected_levels):
            die("Unexpected requested scan volume")
        if meta.get("side") != expected_side or meta.get("levels") != expected_levels:
            die("Incorrect scan dimensions in metadata")
        if request and request["version"] in ("v2", "v3") and (
                request["version"] == "v2" or "vehicles" in request.get("modes", [])):
            if summary.get("vehicle_snapshot") not in ("complete", "incomplete"):
                die("Vehicle survey status missing from modern scan")
            if summary["status"] == "complete" and summary["vehicle_snapshot"] != "complete":
                die("Report claims complete although vehicle pass was not completed")
        vehicle_counters = ("vehicles", "vehicle_parts", "vehicle_containers", "vehicle_items")
        if "vehicles" in summary:
            if any(type(summary.get(k)) is not int or summary[k] < 0 for k in vehicle_counters):
                die("Malformed vehicle census counters")
            if (summary["vehicles"] != sum(row["kind"] == "vehicle" for row in records)
                    or summary["vehicle_parts"] != sum(row["kind"] == "vehicle_part" for row in records)
                    or summary["vehicle_containers"] != sum(row["kind"] == "vehicle_container" for row in records)
                    or summary["vehicle_items"] != sum(row["kind"] == "vehicle_item" for row in records)):
                if summary["status"] == "complete":
                    die("Vehicle row/counter mismatch")
        if summary["loaded_squares"] + summary["unloaded_squares"] != summary["scanned_squares"]:
            die("Loaded/missing counts differ from scanned squares")
        if summary["scanned_squares"] > summary["requested_squares"]:
            die("Scan exceeds approved volume")
        if summary["status"] == "complete" and summary["scanned_squares"] != expected_side * expected_side * expected_levels:
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
    modern = getattr(args, "modern", False)
    if modern:
        radius = args.radius
        if not 1 <= radius <= 50:
            die("Radius must be 1..50 cells")
        if not -2 <= args.z_min <= args.z_max <= 16 or args.z_max-args.z_min >= 5:
            die("Floor range must contain 1..5 levels within -2..16")
        side = 2 * radius + 1
        modes = args.include.split(",")
        if (not modes or len(modes) != len(set(modes)) or set(modes)-SCAN_MODES
                or ("blood" in modes and "squares" not in modes)
                or ("items" in modes and "containers" not in modes)):
            die("Invalid --include categories or dependencies")
        if args.center is None:
            center_x = center_y = "-"
        else:
            center = args.center.split(",")
            if len(center) != 2 or not all(re.fullmatch(r"[0-9]{1,5}", n) for n in center):
                die("--center must be X,Y")
            center_x, center_y = (int(x) for x in center)
            if not (0 <= center_x <= 40000 and 0 <= center_y <= 40000):
                die("Center must be inside world bounds")
    else:
        side = getattr(args, "side", 25)
        if side not in ALLOWED_SIDES:
            die("Area must be 25, 51 or 101 cells wide")
    previous = parse_req(world)
    if previous:
        result = read_response(world, previous["id"])
        if result is None or result["status"] == "pending":
            die("Previous request is pending; do not overwrite an in-progress scan")
    new_id = secrets.token_hex(16)
    version = "v3" if modern else ("v1" if side == 25 else "v2")
    if modern:
        content = (f"v3\t{new_id}\t{args.username}\t{center_x}\t{center_y}"
                   f"\t{radius}\t{args.z_min}\t{args.z_max}\t{','.join(modes)}\n")
        levels = args.z_max-args.z_min+1
    else:
        content = f"{version}\t{new_id}\t{args.username}\t{side}\t{LEVELS}\n"
        levels = LEVELS
    atomic_request(request_path(world), content)
    print(f"Requested {side}x{side}x{levels} scan around {args.username} in {world}.")
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
    print(f"Vehicles={summary.get('vehicles', 0)}, parts={summary.get('vehicle_parts', 0)}, "
          f"car containers={summary.get('vehicle_containers', 0)}, "
          f"car inventory items={summary.get('vehicle_items', 0)}, "
          f"vehicle snapshot={summary.get('vehicle_snapshot', 'not_requested')}")
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
    child = sub.add_parser("scan-area",
                           help="Parameterised read-only scan of loaded squares (v3)")
    child.add_argument("world")
    child.add_argument("--player", dest="username", required=True,
                       help="Online game login anchoring this survey")
    child.add_argument("--center", default=None, help="X,Y; default current player position")
    child.add_argument("--radius", type=int, required=True, help="1..50 square radius")
    child.add_argument("--z-min", type=int, required=True)
    child.add_argument("--z-max", type=int, required=True)
    child.add_argument("--include", default=DEFAULT_MODES,
                       help="comma-separated squares,objects,containers,items,ground,actors,corpses,vehicles,windows,blood")
    child.add_argument("--yes", action="store_true")
    child.set_defaults(handler=scan, modern=True)
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
