#!/usr/bin/env python3
"""Story Director CLI: strictly validate JSON scenes and stage per-world Lua.

Runs under the existing root-owned Bash 'pz' manager lock. No arbitrary Lua,
RCON exposure, background daemon, third-party Python modules or network calls.
Applying never restarts a game or writes to a game save/chunk directly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(os.environ.get("PZ_STORY_REPO_ROOT", Path(__file__).resolve().parents[1])).resolve()
STORE = Path(os.environ.get("PZ_STORY_STORE_ROOT", "/srv/zomboid")).resolve()
WORLD_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
SCENE_ID = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
ITEM_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$")
SPRITE = re.compile(r"^[A-Za-z0-9_]{3,90}$")
SCENE_FOLDER = REPO / "story" / "scenes"
MAX_SCENE_BYTES = 128 * 1024
MAX_ACTIONS = 100


def fail(message: str):
    raise ValueError(message)


def require_keys(value: dict, allowed: set[str], context: str):
    extra = sorted(set(value) - allowed)
    if extra:
        fail(f"{context}: unexpected keys: {', '.join(extra)}")


def name(value: str, kind: str):
    pattern = WORLD_NAME if kind == "world" else SCENE_ID
    if not isinstance(value, str) or not pattern.fullmatch(value):
        fail(f"Invalid {kind} name: {value!r}")
    return value


def point(raw, *, ready: bool):
    if not isinstance(raw, dict):
        fail("Position 'at' must be an object {x,y,z}")
    require_keys(raw, {"x", "y", "z"}, "Position")
    if set(raw) != {"x", "y", "z"}:
        fail("Position must contain exactly x, y, z")
    if (raw["x"] is None or raw["y"] is None) and not ready:
        if raw["x"] is not None or raw["y"] is not None:
            fail("Draft location needs both x and y absent, or both concrete")
        if type(raw["z"]) is not int or not (-2 <= raw["z"] <= 16):
            fail("Invalid z level")
        return None
    for coord, minimum, maximum in (("x", 0, 40000), ("y", 0, 40000), ("z", -2, 16)):
        if type(raw[coord]) is not int or not (minimum <= raw[coord] <= maximum):
            fail(f"Coordinate {coord} must be an integer within {minimum}..{maximum}")
    return [raw["x"], raw["y"], raw["z"]]


def selector(raw):
    if not isinstance(raw, dict):
        fail("Container/window selector must be {object_index,sprite}")
    require_keys(raw, {"object_index", "sprite", "class"}, "Selector")
    if set(raw) != {"object_index", "sprite", "class"}:
        fail("Selector requires object_index, sprite and class (no fuzzy matching)")
    i, sprite, cls = raw["object_index"], raw["sprite"], raw["class"]
    if type(i) is not int or not 0 <= i <= 255:
        fail("Selector object_index must be 0..255")
    if not isinstance(sprite, str) or not SPRITE.fullmatch(sprite):
        fail("Selector must specify an exact nonempty sprite name")
    if cls not in ("IsoObject", "IsoWindow", "IsoDoor", "IsoThumpable"):
        fail("Selector class is not allowlisted")
    return raw


def item_type(raw):
    if not isinstance(raw, str) or not ITEM_ID.fullmatch(raw):
        fail(f"Invalid item type: {raw!r}")
    return raw


def check_action(action: dict, *, ready: bool, allow_barricades: bool):
    if not isinstance(action, dict):
        fail("Each action must be an object")
    kind = action.get("type")
    common = {"id", "type", "at", "enabled"}
    if kind == "note":
        allowed = common | {"title", "pages", "placement", "selector"}
    elif kind == "loot":
        allowed = common | {"items", "placement", "selector"}
    elif kind == "barricade":
        allowed = common | {"selector", "planks"}
    elif kind in ("infected", "decor", "construction"):
        allowed = common | {"subtype", "count", "sprite", "description"}
    else:
        fail(f"Unsupported action type: {kind!r}")
    require_keys(action, allowed, f"Action {action.get('id')}")
    ident = action.get("id")
    if not isinstance(ident, str) or not SCENE_ID.fullmatch(ident):
        fail(f"Invalid action id {ident!r}")
    enabled = action.get("enabled", True)
    if type(enabled) is not bool:
        fail(f"{ident}: enabled must be a boolean")
    coords = point(action.get("at"), ready=ready and enabled)
    if ready and enabled and coords is None:
        fail(f"{ident}: missing actual game coordinates")
    if kind == "note":
        title = action.get("title")
        pages = action.get("pages")
        if not isinstance(title, str) or not 1 <= len(title) <= 120:
            fail(f"{ident}: note title must have 1..120 characters")
        if (not isinstance(pages, list) or not 1 <= len(pages) <= 8
                or any(not isinstance(p, str) or not 1 <= len(p) <= 2000 for p in pages)):
            fail(f"{ident}: pages must be 1..8 nonempty strings, <=2000 characters")
    if kind == "loot":
        items = action.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 25:
            fail(f"{ident}: loot must have 1..25 item entries")
        for item in items:
            if not isinstance(item, dict):
                fail(f"{ident}: each loot entry must be an object")
            require_keys(item, {"type", "count"}, "Loot entry")
            item_type(item.get("type"))
            if type(item.get("count")) is not int or not 1 <= item["count"] <= 20:
                fail(f"{ident}: item counts must be 1..20")
    if kind in ("note", "loot"):
        place = action.get("placement")
        if place not in ("ground", "container"):
            fail(f"{ident}: placement must be ground or container")
        if place == "container":
            sel = selector(action.get("selector"))
            if sel["class"] != "IsoObject":
                fail(f"{ident}: containers must use selector class IsoObject")
        elif "selector" in action:
            fail(f"{ident}: ground placement cannot specify a selector")
    if kind == "barricade":
        sel = selector(action.get("selector"))
        if sel["class"] not in ("IsoWindow", "IsoDoor", "IsoThumpable"):
            fail(f"{ident}: barricade target must be a window, door or thumpable")
        if type(action.get("planks")) is not int or not 1 <= action["planks"] <= 4:
            fail(f"{ident}: barricade planks must be 1..4")
        if ready and enabled and not allow_barricades:
            fail(f"{ident}: barricade requires explicit --allow-barricades after B42 test")
    if kind in ("infected", "decor", "construction") and enabled and ready:
        fail(f"{ident}: {kind} adapter not yet validated for Build 42.21 dedicated MP. Disable action until tested.")
    if kind in ("infected", "decor", "construction") and not ready:
        if kind == "infected":
            if action.get("subtype") not in ("TLOU_Runner", "TLOU_Stalker", "TLOU_Clicker"):
                fail(f"{ident}: unknown TLOU subtype")
            if type(action.get("count")) is not int or not 1 <= action["count"] <= 20:
                fail(f"{ident}: count must be 1..20")
        if kind == "decor" and "sprite" in action and (
                not isinstance(action["sprite"], str) or not SPRITE.fullmatch(action["sprite"])):
            fail(f"{ident}: invalid sprite")
    return enabled, coords


def resolve_scene(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_file():
        return candidate
    filename = value if value.endswith(".json") else value + ".json"
    other = SCENE_FOLDER / filename
    if other.is_file():
        return other
    fail(f"Scene file not found: {value}")


def read_scene(file: Path, *, ready: bool = False, allow_barricades: bool = False):
    file = file.resolve(strict=True)
    if not file.is_relative_to(SCENE_FOLDER.resolve()):
        fail("Scenes must be stored inside repository story/scenes/")
    if not file.is_file() or file.stat().st_size > MAX_SCENE_BYTES:
        fail("Scene must be a regular file <=128 KiB")
    try:
        scene = json.loads(file.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        fail(f"Scene JSON could not be parsed: {error}")
    if not isinstance(scene, dict):
        fail("Scene must be a JSON object")
    require_keys(scene, {"schema", "id", "world", "title", "enabled", "actions"}, "Scene")
    if scene.get("schema") != 1:
        fail("Scene schema must be 1")
    name(scene.get("id"), "scene")
    if file.name != scene["id"] + ".json":
        fail("Scene source file name must equal its declared id")
    name(scene.get("world"), "world")
    if not isinstance(scene.get("title"), str) or not 1 <= len(scene["title"]) <= 160:
        fail("Scene title must have 1..160 characters")
    if type(scene.get("enabled")) is not bool:
        fail("Scene enabled must be boolean")
    actions = scene.get("actions")
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        fail(f"Scene must contain 1..{MAX_ACTIONS} actions")
    ids = set()
    missing = 0
    active = 0
    for action in actions:
        enabled, coords = check_action(
            action, ready=ready and scene["enabled"], allow_barricades=allow_barricades)
        if action["id"] in ids:
            fail(f"Duplicate action ID: {action['id']}")
        ids.add(action["id"])
        if enabled:
            active += 1
            if coords is None:
                missing += 1
    if ready and not scene["enabled"]:
        fail("Draft scene is disabled. Explicitly set enabled=true after mapping.")
    if ready and active == 0:
        fail("No enabled actions to apply")
    if ready and missing:
        fail(f"{missing} action(s) still missing coordinates")
    return scene, {"active": active, "unmapped": missing, "total": len(actions)}


def lua_string(value: str) -> str:
    pieces = []
    for byte in value.encode("utf-8"):
        if 32 <= byte < 127 and byte not in (34, 92):
            pieces.append(chr(byte))
        else:
            pieces.append("\\%03d" % byte)
    return '"' + "".join(pieces) + '"'


def lua_literal(value, depth=0):
    if depth > 16:
        fail("Scene nesting too deep")
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return lua_string(value)
    if type(value) is int:
        return str(value)
    if isinstance(value, list):
        return "{" + ",".join(lua_literal(x, depth + 1) for x in value) + "}"
    if isinstance(value, dict):
        for k in value:
            if not IDENT_FOR_LUA.fullmatch(k):
                fail(f"Invalid Lua table key: {k}")
        return "{" + ",".join(k + "=" + lua_literal(v, depth + 1)
                              for k, v in sorted(value.items())) + "}"
    fail(f"Unsupported data type for Lua conversion: {type(value).__name__}")


IDENT_FOR_LUA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_bundle(world: str, folder: Path):
    scenes_dir = folder / "scenes"
    all_scenes = []
    enabled_barricades = False
    for scene_file in (sorted(scenes_dir.glob("*.json")) if scenes_dir.is_dir() else []):
        if scene_file.is_symlink():
            fail("World scene files may not be symlinks")
        scene = json.loads(scene_file.read_text(encoding="utf-8"))
        if scene.get("world") != world:
            fail(f"Stored scene world does not match {world}: {scene_file.name}")
        if not scene.get("enabled"):
            continue
        # Scene has already undergone strict validation at apply time.
        # Validate again with the same per-scene barricade approval flag.
        approved = (folder / "barricades-approved.json")
        approved_ids = json.loads(approved.read_text()) if approved.exists() else []
        allow = scene["id"] in approved_ids
        source = SCENE_FOLDER / f"{scene['id']}.json"
        if source.exists():
            checked, _ = read_scene(source, ready=True, allow_barricades=allow)
            if checked != scene:
                fail(f"Stored scene changed since source review: {scene['id']}")
        else:
            fail(f"Missing exact Git-reviewed source scene: {source}")
        enabled_barricades = enabled_barricades or allow
        all_scenes.append({
            "id": scene["id"], "title": scene["title"],
            "actions": [a for a in scene["actions"] if a.get("enabled", True)]
        })
    inspectors = []
    f = folder / "inspect.json"
    if f.exists():
        inspectors = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(inspectors, list) or len(inspectors) > 25:
            fail("Invalid inspection coordinates list")
        for entry in inspectors:
            point(entry, ready=True)
    out = {"schema": 1, "world": world, "scenes": all_scenes, "inspect": inspectors}
    compiled = "-- GENERATED by storyctl.py. Do not edit; source of truth is JSON.\n" \
               + "SiegerStoryScenes = " + lua_literal(out) + "\n"
    return compiled, out


def save_atomic(file: Path, text: str, mode: int = 0o600):
    file.parent.mkdir(parents=True, exist_ok=True)
    tmp = file.with_name("." + file.name + "." + str(os.getpid()) + ".tmp")
    with open(tmp, "x", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(tmp, mode)
    os.replace(tmp, file)


def ensure_stopped():
    check = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "zomboid-server"],
        text=True, capture_output=True, check=False,
    )
    if check.returncode == 0 and check.stdout.strip() == "true":
        fail("Game container is running. Agree a maintenance window and sudo pz stop first.")


def world_folder(value):
    name(value, "world")
    w = STORE / "worlds" / value
    if not (w / "data").is_dir() or not (w / "profile").is_file():
        fail(f"Unknown/unfinished world slot: {value}")
    return w


def recent_verified_backup(world: str):
    folder = STORE / "backups" / "worlds" / world
    files = sorted(folder.glob("world-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    for archive in files:
        sidecar = Path(str(archive) + ".sha256")
        if not sidecar.is_file():
            continue
        if time.time() - archive.stat().st_mtime > 4 * 3600:
            continue
        rows = sidecar.read_text().strip().split(maxsplit=1)
        if len(rows) != 2 or rows[1] != archive.name:
            continue
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
        if digest.hexdigest() == rows[0]:
            return archive
    fail(f"No verified cold backup newer than 4 hours for {world}; use sudo pz save {world} first.")


def command_validate(args):
    scene, stat = read_scene(resolve_scene(args.scene))
    print(json.dumps({"id": scene["id"], "world": scene["world"], "enabled": scene["enabled"],
                      "status": "draft" if not scene["enabled"] or stat["unmapped"] else "mapped",
                      **stat}, ensure_ascii=False, indent=2))


def command_preview(args):
    scene, stat = read_scene(Path(args.scene))
    print(f"Scene {scene['id']} for {scene['world']}: {scene['title']}")
    print(f"Status: {'DRAFT, not deployable' if not scene['enabled'] else 'mapping review'}")
    print(f"Actions: {stat['total']}, enabled: {stat['active']}, missing coordinates: {stat['unmapped']}")
    for action in scene["actions"]:
        print(" -", action["id"], action["type"], action["at"],
              "(disabled)" if not action.get("enabled", True) else "")
    print("Offline preview does NOT confirm map objects. Run inspector and check the game before applying.")


def command_apply(args):
    scene, stat = read_scene(resolve_scene(args.scene), ready=True, allow_barricades=args.allow_barricades)
    if scene["world"] != args.world:
        fail("Scene world and requested slot differ")
    world = world_folder(args.world)
    ensure_stopped()
    if not args.yes:
        fail("Explicit --yes required; applying changes future game-world state.")
    backup = recent_verified_backup(args.world)
    story = world / "story"
    dst = story / "scenes" / (scene["id"] + ".json")
    if dst.exists():
        fail("Scene already staged in this world; no silent edit/reapply. Restore a backup into a new slot.")
    if dst.is_symlink():
        fail("Refusing symlink scene target")
    print("Verified cold backup:", backup)
    save_atomic(dst, json.dumps(scene, ensure_ascii=False, indent=2) + "\n")
    try:
        if args.allow_barricades:
            approvals = story / "barricades-approved.json"
            previous = json.loads(approvals.read_text()) if approvals.exists() else []
            if scene["id"] not in previous:
                previous.append(scene["id"])
            save_atomic(approvals, json.dumps(sorted(previous)) + "\n")
        lua, data = build_bundle(args.world, story)
        save_atomic(story / "bundle.lua", lua)
        print(f"Staged {scene['id']} in {args.world}: {stat['active']} action(s).")
        print("Server remains STOPPED. Start the world manually, inspect logs, visit its coordinates.")
        print("Rollback means restoring a previous cold backup to a NEW slot, not deleting player-built objects.")
    except Exception:
        dst.unlink(missing_ok=True)
        raise


def command_inspect(args):
    world = world_folder(args.world)
    ensure_stopped()
    if not args.yes:
        fail("Explicit --yes required to install read-only inspection probe")
    entry = {"x": args.x, "y": args.y, "z": args.z}
    point(entry, ready=True)
    story = world / "story"
    f = story / "inspect.json"
    entries = json.loads(f.read_text()) if f.exists() else []
    if entry not in entries:
        if len(entries) >= 25:
            fail("At most 25 pending inspected coordinates")
        entries.append(entry)
    save_atomic(f, json.dumps(entries, indent=2) + "\n")
    lua, data = build_bundle(args.world, story)
    save_atomic(story / "bundle.lua", lua)
    print(f"Read-only probe staged for ({args.x},{args.y},{args.z}) in {args.world}.")
    print("Requires a game restart and a player/chunk load. Look for STORY_INSPECT in server logs.")
    print("Existing staged scenes will also run when their chunks load; inspect on a disposable copy first.")


def command_status(args):
    world = world_folder(args.world)
    story = world / "story"
    if not (story / "bundle.lua").exists():
        print(f"{args.world}: no active Story Director bundle")
        return
    _, data = build_bundle(args.world, story)
    print(json.dumps({
        "world": args.world,
        "staged_scenes": [s["id"] for s in data["scenes"]],
        "inspections": data["inspect"],
        "bundle_sha256": hashlib.sha256((story / "bundle.lua").read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    for cmd in ("validate", "preview"):
        s = sub.add_parser(cmd)
        s.add_argument("scene")
        s.set_defaults(handler=command_validate if cmd == "validate" else command_preview)
    s = sub.add_parser("apply")
    s.add_argument("world")
    s.add_argument("scene")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--allow-barricades", action="store_true")
    s.set_defaults(handler=command_apply)
    s = sub.add_parser("inspect")
    s.add_argument("world")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.add_argument("z", type=int)
    s.add_argument("--yes", action="store_true")
    s.set_defaults(handler=command_inspect)
    s = sub.add_parser("status")
    s.add_argument("world")
    s.set_defaults(handler=command_status)
    args = p.parse_args()
    try:
        args.handler(args)
    except (ValueError, OSError, json.JSONDecodeError) as err:
        p.exit(2, "Story Director: " + str(err) + "\n")


if __name__ == "__main__":
    main()
