#!/usr/bin/env python3
"""Typed root-only Story player operations; never executes arbitrary Lua.

API is deliberately narrow; health updates are experimental in multiplayer.
Player reports may be sensitive: stay on the local root-owned game host.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
from pathlib import Path

import scanctl

REQUEST = "SiegerStoryPlayerRequest.txt"
RESPONSE = "SiegerStoryPlayerResult.txt"
TYPES = {
    "Base.Bandage", "Base.Disinfectant", "Base.RippedSheets",
    "Base.Notebook", "Base.Plank", "Base.Hammer",
    "Base.Screwdriver", "Base.WaterBottleFull",
}
TOKEN = re.compile(r"SiegerStory:[A-Za-z0-9_:.-]{6,160}\Z")
OPERATIONS = {"inspect", "grant", "remove-tagged", "heal"}
MAX_RESPONSE = 64 * 1024


def fail(message: str):
    raise ValueError(message)


def paths(world: str) -> tuple[Path, Path]:
    return (scanctl.lua_dir(world) / REQUEST, scanctl.lua_dir(world) / RESPONSE)


def read_request(world: str):
    req, _ = paths(world)
    if not req.is_file():
        return None
    if req.is_symlink() or req.stat().st_size > 256:
        fail("Unsafe or oversized previous player request")
    match = re.fullmatch(
        r"v1\t([0-9a-f]{32})\t([A-Za-z0-9_][A-Za-z0-9_.-]{0,30})"
        r"\t([A-Za-z0-9_][A-Za-z0-9_.-]{0,30})"
        r"\t(inspect|grant|remove-tagged|heal)\t([A-Za-z0-9_:.-]{1,180})\t([0-9])\n?",
        req.read_text(encoding="ascii"),
    )
    if not match or match[2] != world:
        fail("Unrecognized previous player request; manual review required")
    return {"id": match[1], "world": match[2], "player": match[3],
            "action": match[4], "arg": match[5], "count": int(match[6])}


def read_response(world: str, wanted_id: str | None = None):
    _, path = paths(world)
    if not path.is_file():
        return {"status": "pending"}
    if path.is_symlink() or path.stat().st_size > MAX_RESPONSE:
        fail("Unsafe or oversized player response")
    raw = path.read_text(encoding="utf-8")
    if not raw.endswith("\n"):
        return {"status": "pending"}
    lines = raw.splitlines()
    if not lines:
        return {"status": "pending"}
    head = lines[0].split("\t")
    if len(head) != 7 or head[0] != "v1" or not re.fullmatch(r"[0-9a-f]{32}", head[1]):
        fail("Invalid player response header")
    if wanted_id and head[1] != wanted_id:
        return {"status": "pending"}
    if head[2] != world or head[4] not in OPERATIONS or head[5] not in ("complete", "error"):
        fail("Unexpected response world, operation, or status")
    if lines[-1] != "end":
        return {"status": "pending"}
    if len(lines) > 300:
        fail("Too many player response rows")
    fields: dict[str, str] = {}
    items: list[dict] = []
    for raw_line in lines[1:-1]:
        row = raw_line.split("\t")
        if len(row) == 3 and row[0] == "field":
            if row[1] in fields or not re.fullmatch(r"[a-z_]{1,64}", row[1]):
                fail("Invalid or repeated player field")
            fields[row[1]] = row[2]
        elif len(row) == 4 and row[0] == "item":
            if not row[1].isdigit() or not re.fullmatch(r"[A-Za-z0-9_]+\.[A-Za-z0-9_]+", row[2]):
                fail("Invalid player item row")
            items.append({"slot": int(row[1]), "type": row[2],
                          "story_token": row[3] if row[3] != "-" else None})
        else:
            fail("Invalid player response row")
    return {"status": head[5], "request_id": head[1], "world": world,
            "player": head[3], "operation": head[4], "message": head[6],
            "fields": fields, "items": items}


def assert_ready(world: str):
    scanctl.assert_ready(world)
    mounts = scanctl.docker_mounts()
    if not scanctl.packaged_runtime(mounts,world) and "/pzomboid-server/media/lua/server/SiegerStoryPlayerControl.lua" not in mounts:
        fail("New Story player runtime not mounted; controlled restart required")


def command(args):
    world = args.world
    scanctl.slot(world)
    if world != "story_test":
        fail("Player mutation/report currently restricted to story_test")
    if not scanctl.USERNAME.fullmatch(args.player):
        fail("Specify exact online game account login")
    if not args.yes:
        fail("--yes required for root player request")
    assert_ready(world)
    previous = read_request(world)
    if previous:
        prior = read_response(world, previous["id"])
        if prior["status"] == "pending":
            fail("Previous player request still pending; inspect player-status first")
        if prior["status"] == "error" and not args.acknowledge_failed:
            fail("Previous player request failed; verify game state and pass --acknowledge-failed")
    kind = args.operation
    arg, count = "-", 0
    if kind == "grant":
        arg = args.item
        count = args.count
        if arg not in TYPES or not 1 <= count <= 5:
            fail("Only allowlisted items (1..5) may be granted")
    elif kind == "remove-tagged":
        arg, count = args.token, 1
        if not TOKEN.fullmatch(arg):
            fail("Only one exact Story-owned token is removable")
    elif kind == "heal" and not args.experimental_health:
        fail("Health synchronization is experimental; --experimental-health required")
    elif kind not in OPERATIONS:
        fail("Unsupported player command")
    rid = secrets.token_hex(16)
    request = f"v1\t{rid}\t{world}\t{args.player}\t{kind}\t{arg}\t{count}\n"
    req, _ = paths(world)
    scanctl.atomic_request(req, request)
    print("Player request queued:", kind, "for", args.player)
    print("Request ID:", rid)
    print(f"Poll: sudo pz story player-status {world}")
    print("Do not queue another operation until the previous result is terminal.")


def status(args):
    scanctl.slot(args.world)
    current = read_request(args.world)
    if not current:
        fail("No player operation issued")
    data = read_response(args.world, current["id"])
    if data["status"] == "pending":
        print("Player request pending:", current["id"], current["action"])
        return
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if data["status"] != "complete":
        fail("Server rejected the player operation; examine private server logs")
    if args.output:
        target = Path(args.output)
        if target.resolve().is_relative_to(scanctl.REPO):
            fail("Private player data cannot be exported inside repo")
        if target.exists() or target.is_symlink() or not target.parent.is_dir():
            fail("Unsafe destination or file exists")
        fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("Saved private report:", target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("world")
    common.add_argument("player")
    common.add_argument("--yes", action="store_true")
    common.add_argument("--acknowledge-failed", action="store_true",
                        help="Confirm manual review of previous failed/partial mutation")
    for cmd, op in (("player-inspect", "inspect"), ("player-grant", "grant"),
                    ("player-remove-tagged", "remove-tagged"), ("player-heal", "heal")):
        p = sub.add_parser(cmd, parents=[common])
        p.set_defaults(handler=command, operation=op)
        if op == "grant":
            p.add_argument("--item", required=True, choices=sorted(TYPES))
            p.add_argument("--count", type=int, default=1)
        if op == "remove-tagged":
            p.add_argument("--token", required=True)
        if op == "heal":
            p.add_argument("--experimental-health", action="store_true")
    p = sub.add_parser("player-status")
    p.add_argument("world")
    p.add_argument("--output")
    p.set_defaults(handler=status)
    args = parser.parse_args()
    try:
        args.handler(args)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.exit(2, "Story player: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
