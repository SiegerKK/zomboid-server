#!/usr/bin/env python3
"""Safe Story Director live editing sessions for one running PZ world.

"Commit" means a verified second *cold world backup* and a session ledger;
it is not a Git commit. At no point do we accept arbitrary Lua from a user.
The root-only Bash pz CLI orchestrates begin/commit with short maintenance
windows. Between those windows this CLI exchanges bounded data with the Lua
server runtime using the world's private Lua directory.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

from storyctl import read_scene, resolve_scene

STORE = Path(os.environ.get("PZ_STORY_STORE_ROOT", "/srv/zomboid")).resolve()
WORLD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
ID_RE = re.compile(r"^[0-9a-f]{32}$")
ACTION_RE = re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*$")
SPRITE_RE = re.compile(r"^[A-Za-z0-9_]{3,90}$")
REQUEST = "SiegerStoryLiveRequest.txt"
RESPONSE = "SiegerStoryLiveResult.txt"
MAX_SCENE_ACTIONS = 32
MAX_REQUEST_BYTES = 128 * 1024


def fail(message):
    raise ValueError(message)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def slot(world):
    if not WORLD_RE.fullmatch(world):
        fail("Invalid world name")
    path = STORE / "worlds" / world
    if not (path / "data").is_dir() or not (path / "profile").is_file():
        fail(f"Unknown world: {world}")
    return path


def story_dir(world):
    return slot(world) / "story" / "live"


def state_file(world):
    return story_dir(world) / "session.json"


def lua_dir(world):
    return slot(world) / "data" / "Lua"


def atomic_write(path, text, *, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        fail("Refusing symlink: " + str(path))
    if exclusive and path.exists():
        fail("Output already exists: " + str(path))
    tmp = path.parent / ("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    with tmp.open("x", encoding="utf-8") as stream:
        os.chmod(tmp, 0o600)
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def read_session(world):
    path = state_file(world)
    if not path.is_file() or path.is_symlink():
        fail(f"No Story live session for {world}; run pz story live-begin first")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("world") != world:
        fail("Invalid live session state")
    if data.get("status") not in ("open", "committed"):
        fail("Unsupported session status")
    return data


def save_session(world, data):
    atomic_write(state_file(world), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def checksum_backup(world, candidate):
    path = Path(candidate).resolve(strict=True)
    root = (STORE / "backups" / "worlds" / world).resolve(strict=True)
    if not path.is_relative_to(root) or not path.name.startswith("world-") or path.suffixes[-2:] != [".tar", ".gz"]:
        fail("Backup must be manager-created under the selected world's backup directory")
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        fail("Backup has no trusted checksum")
    match = re.fullmatch(r"([a-f0-9]{64})\s\s([A-Za-z0-9_.-]+)\s*", sidecar.read_text("ascii"))
    if not match or match[2] != path.name:
        fail("Backup sidecar does not match archive")
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    if sha.hexdigest() != match[1]:
        fail("Backup checksum mismatch")
    return str(path), match[1]


def running_world(world):
    active = STORE / "manager" / "active-world"
    if not active.is_file() or active.read_text(encoding="utf-8").strip() != world:
        fail("The active Docker world differs from the requested live session")
    call = subprocess.run(
        ["docker", "inspect", "--format", "{{json .}}", "zomboid-server"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    if call.returncode:
        fail("Docker inspection failed; fail closed")
    info = json.loads(call.stdout)
    if info.get("State", {}).get("Running") is not True:
        fail("Game container is not running")
    mounts = {m["Destination"]: Path(m["Source"]).resolve() for m in info.get("Mounts", [])}
    if mounts.get("/root/Zomboid") != (slot(world) / "data").resolve():
        fail("Docker save mount doesn't match selected world")
    if "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua" not in mounts:
        fail("Story Director server runtime not mounted; activate Story on next controlled restart")
    if "/pzomboid-server/media/lua/server/ZZ_SiegerStoryScenes.lua" not in mounts:
        fail("Story bundle not mounted")
    return True


def encode_text(value):
    if not isinstance(value, str):
        fail("Only strings may be hex encoded")
    return value.encode("utf-8").hex()


def encode_action(action):
    ident, kind, pos = action["id"], action["type"], action["at"]
    if kind == "corpse":
        if not ACTION_RE.fullmatch(ident):
            fail("Invalid corpse action ID")
        if (action.get("room") != "bathroom" or action.get("ground_item") != "Base.Revolver"
                or type(action.get("blood")) is not int or not 0 <= action["blood"] <= 3
                or not SPRITE_RE.fullmatch(action.get("floor_sprite", ""))):
            fail("Corpse action contains unapproved parameters")
        return "\t".join(["corpse", ident, str(pos["x"]), str(pos["y"]),
                          str(pos["z"]), "-", "-1", "-", "-", action["room"],
                          action["floor_sprite"], str(action["blood"]), action["ground_item"]])
    if kind == "infected":
        if action.get("subtype") != "vanilla" or action.get("count") != 1:
            fail("Only a single vanilla zombie per live action is allowed")
        pos = action["at"]
        return "\t".join(["infected", action["id"], str(pos["x"]), str(pos["y"]),
                          str(pos["z"]), "-", "-1", "-", "-", "vanilla", "1"])
    if kind not in ("note", "loot"):
        fail(f"Live adapter for {kind} is not implemented")
    if not ACTION_RE.fullmatch(ident):
        fail("Unsupported action id")
    place = action["placement"]
    selector = action.get("selector")
    fields = [kind, ident, str(pos["x"]), str(pos["y"]), str(pos["z"]), place,
              str(selector["object_index"]) if selector else "-1",
              selector["sprite"] if selector else "-",
              selector["class"] if selector else "-"]
    if kind == "note":
        fields += [encode_text(action["title"]), str(len(action["pages"])),
                   ":".join(encode_text(x) for x in action["pages"])]
    else:
        fields.append(";".join(entry["type"] + "=" + str(entry["count"])
                               for entry in action["items"]))
    line = "\t".join(fields)
    if "\n" in line or "\r" in line:
        fail("Control characters in wire data")
    return line


def response_for(world, wanted_id):
    path = lua_dir(world) / RESPONSE
    if not path.is_file():
        return {"status": "pending"}
    if path.is_symlink() or path.stat().st_size > 128 * 1024:
        fail("Unsafe live response file")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return {"status": "pending"}
    first = lines[0].split("\t")
    if len(first) != 6 or first[:2] != ["v1", wanted_id] or first[2] != world:
        return {"status": "pending"}
    if not first[5].isdigit() or not 1 <= int(first[5]) <= MAX_SCENE_ACTIONS:
        fail("Invalid live response action count")
    statuses = {}
    summary = None
    for row_index, line in enumerate(lines[1:], start=1):
        fields = line.split("\t")
        if len(fields) == 4 and fields[0] == "action":
            _, ident, status, reason_hex = fields
            if not ACTION_RE.fullmatch(ident) or status not in ("applied", "already", "pending", "error"):
                fail("Invalid server action result")
            try:
                reason = bytes.fromhex(reason_hex).decode("utf-8")
            except (ValueError, UnicodeError) as exc:
                fail(f"Malformed action reason: {exc}")
            if ident in statuses:
                fail("Duplicate server action result")
            statuses[ident] = {"status": status, "reason": reason[:400]}
        elif len(fields) == 6 and fields[0] == "end":
            _, ident, status, applied, pending, failed = fields
            if ident != wanted_id or status not in ("pending", "complete", "failed"):
                fail("Invalid live response trailer")
            if any(not x.isdigit() for x in (applied, pending, failed)):
                fail("Invalid live response counts")
            if row_index != len(lines) - 1:
                fail("Trailing data after live response trailer")
            summary = {"status": status, "applied": int(applied),
                       "pending": int(pending), "failed": int(failed)}
            break
        else:
            fail("Unexpected live response row")
    if summary is None:
        return {"status": "pending"}
    if len(statuses) != int(first[5]):
        fail("Live result action count mismatch")
    expected = {"applied": sum(v["status"] in ("applied", "already") for v in statuses.values()),
                "pending": sum(v["status"] == "pending" for v in statuses.values()),
                "failed": sum(v["status"] == "error" for v in statuses.values())}
    if any(summary[k] != v for k, v in expected.items()):
        fail("Live response counters disagree with actions")
    expected_status = "failed" if expected["failed"] else ("pending" if expected["pending"] else "complete")
    if summary["status"] != expected_status:
        fail("Live response status disagrees with actions")
    return {"status": summary["status"], "result": summary,
            "actions": statuses, "scene_id": first[3], "sha256": first[4]}


def last_job(world, data, *, record=False):
    job = data.get("pending_job")
    if not job:
        return None
    response = response_for(world, job["request_id"])
    if response["status"] == "pending":
        return response
    if response["scene_id"] != job["scene_id"] or response["sha256"] != job["sha256"]:
        fail("Server confirmation doesn't match requested scene hash")
    if set(response["actions"]) != set(job["action_ids"]):
        fail("Server response action IDs differ from reviewed scene")
    if response["status"] == "complete" and any(
            v["status"] not in ("applied", "already") for v in response["actions"].values()):
        fail("Server complete acknowledgment contains incomplete actions")
    if record:
        if response["status"] != "complete":
            job["last_error"] = response
        else:
            data.setdefault("applied_scenes", []).append({
                "scene_id": job["scene_id"],
                "request_id": job["request_id"],
                "sha256": job["sha256"],
                "actions": response["actions"],
                "completed_at": now()
            })
            data["pending_job"] = None
        save_session(world, data)
    return response


def clear_queue(args):
    """Quarantine prior live request/response files while server is stopped.

    This avoids replaying an already-committed scene after the next cold
    checkpoint restart. Source files stay inside the same per-world directory.
    """
    slot(args.world)
    state = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", "zomboid-server"],
        capture_output=True, text=True, check=False, timeout=15)
    if state.returncode == 0 and state.stdout.strip() != "false":
        fail("Refuse queue reset while the game might be running")
    if state.returncode != 0:
        fail("Docker inspection failed: cannot prove server is stopped")
    folder = story_dir(args.world) / "io_archive"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    for basename in (REQUEST, RESPONSE):
        source = lua_dir(args.world) / basename
        if source.is_symlink():
            fail("Refuse symlinked Story live request/response")
        if source.exists():
            target = folder / (secrets.token_hex(16) + "-" + basename)
            source.rename(target)
            target.chmod(0o600)
    print("Quarantined previous in-world live queue files before restart")


def check_new(args):
    slot(args.world)
    if state_file(args.world).exists() and read_session(args.world)["status"] == "open":
        fail("An open Story live session already exists in this world")
    print("No open Story live session. Brief stopped-server backup can proceed.")


def begin_record(args):
    world = args.world
    slot(world)
    archive, sha = checksum_backup(world, args.backup)
    path = state_file(world)
    if path.exists():
        old = read_session(world)
        if old["status"] == "open":
            fail("An open live session already exists; finish/recover it before starting another")
        history = story_dir(world) / ("session-" + old["session_id"] + ".json")
        atomic_write(history, json.dumps(old, ensure_ascii=False, indent=2) + "\n", exclusive=True)
    sid = secrets.token_hex(16)
    data = {"schema": 1, "session_id": sid, "world": world, "status": "open",
            "started_at": now(), "baseline": {"path": archive, "sha256": sha},
            "applied_scenes": [], "pending_job": None, "post_backup": None}
    save_session(world, data)
    print("Story live session started:", sid)
    print("Baseline cold backup:", archive)
    print("Game may now remain RUNNING while reviewed scenes are applied.")


def apply_live(args):
    world = args.world
    data = read_session(world)
    if data["status"] != "open":
        fail("Session already committed; begin another verified backup session")
    if not args.yes:
        fail("--yes required for a live world mutation")
    running_world(world)
    if data.get("pending_job"):
        ack = last_job(world, data, record=True)
        if ack["status"] != "complete":
            fail("Previous job has not fully completed. Check live-status.")
    scene, counts = read_scene(resolve_scene(args.scene), ready=True,
                               allow_infected=getattr(args, "allow_infected", False),
                               allow_corpses=getattr(args, "allow_corpses", False))
    if scene["world"] != world or not scene["enabled"]:
        fail("Scene world mismatch or scene disabled")
    enabled = [a for a in scene["actions"] if a.get("enabled", True)]
    if not 1 <= len(enabled) <= MAX_SCENE_ACTIONS:
        fail("Live scene must have 1..32 enabled actions")
    if any(a["type"] not in ("note", "loot", "infected", "corpse") for a in enabled):
        fail("Unsupported live action: only notes, loot, opt-in vanilla infected/corpse")
    if any(a["type"] == "infected" for a in enabled) and not getattr(args, "allow_infected", False):
        fail("Vanilla infected require explicit --allow-infected")
    if any(a["type"] == "corpse" for a in enabled) and not getattr(args, "allow_corpses", False):
        fail("Corpse actions require explicit --allow-corpses")
    if any(s["scene_id"] == scene["id"] for s in data["applied_scenes"]):
        fail("Scene already applied in this session; use a unique scene ID")
    if (slot(world) / "story" / "scenes" / (scene["id"] + ".json")).exists():
        fail("Scene is already staged as an older startup scenario; choose a fresh scene ID")
    lines = [encode_action(a) for a in enabled]
    raw = "\n".join(lines) + "\n"
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    rid = secrets.token_hex(16)
    header = f"v1\t{rid}\t{world}\t{scene['id']}\t{sha}\t{len(enabled)}\n"
    packet = header + raw
    if len(packet.encode("utf-8")) > MAX_REQUEST_BYTES:
        fail("Scene exceeds 128 KiB live request limit")
    folder = story_dir(world) / "scenes"
    source = resolve_scene(args.scene)
    target = folder / (scene["id"] + ".json")
    if target.exists():
        fail("Scene already staged in this world's live session")
    atomic_write(target, json.dumps(scene, ensure_ascii=False, indent=2) + "\n", exclusive=True)
    # Store first: if we crash before publishing the request, operator may
    # re-issue pending request after reviewing the ledger, not silently skip.
    data["pending_job"] = {
        "request_id": rid, "scene_id": scene["id"], "sha256": sha,
        "action_ids": [a["id"] for a in enabled], "requested_at": now()
    }
    save_session(world, data)
    atomic_write(lua_dir(world) / REQUEST, packet)
    print("Queued live scene:", scene["id"], "request:", rid)
    print("Game stays online. Do NOT commit until live-status confirms complete.")
    print("Check: sudo pz story live-status", world)


def status(args):
    data = read_session(args.world)
    print("World:", args.world, "session:", data["session_id"],
          "status:", data["status"], "started:", data["started_at"])
    print("Cold baseline:", data["baseline"]["path"])
    print("Applied scenes:", len(data.get("applied_scenes", [])))
    if data.get("pending_job"):
        job = data["pending_job"]
        response = last_job(args.world, data, record=True)
        print("Last requested scene:", job["scene_id"],
              "request:", job["request_id"],
              "response:", response["status"])
        for aid, detail in response.get("actions", {}).items():
            print(" ", aid, detail["status"], detail["reason"][:100])
        if response["status"] == "complete":
            print("All actions acknowledged by the server. Re-run to show updated session.")
    if data["status"] == "committed":
        print("Commit world backup:", data["post_backup"]["path"])


def pre_commit(args):
    data = read_session(args.world)
    if data["status"] != "open":
        fail("Session not open")
    if data.get("pending_job"):
        response = last_job(args.world, data, record=True)
        if response["status"] != "complete":
            fail("Incomplete or failed scene: cannot commit; restore baseline to a NEW world to roll back")
    if not data.get("applied_scenes"):
        fail("No completed live scenes to commit")
    running_world(args.world)
    print("Ready for final cold backup. Completed scenes:", len(data["applied_scenes"]))


def commit_record(args):
    world = args.world
    data = read_session(world)
    if data["status"] != "open":
        fail("Session is not open")
    if data.get("pending_job"):
        fail("Cannot commit with outstanding jobs")
    if not data.get("applied_scenes"):
        fail("Nothing has been applied")
    archive, sha = checksum_backup(world, args.backup)
    if archive == data["baseline"]["path"]:
        fail("Commit archive must differ from baseline archive")
    data["status"] = "committed"
    data["committed_at"] = now()
    data["post_backup"] = {"path": archive, "sha256": sha}
    # World backups contain the game save as it was *before* the ledger
    # changed to committed. Store a root-only sidecar as an immutable
    # provenance record next to the archive, without modifying the save.
    evidence = Path(archive + ".story-commit.json")
    atomic_write(evidence, json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                 exclusive=True)
    save_session(world, data)
    print("COMMITTED LIVE STORY SESSION", data["session_id"])
    print("BEFORE:", data["baseline"]["path"])
    print("AFTER :", archive)
    print("Scene approvals saved; this is a WORLD checkpoint, not a Git commit.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    parser = sub.add_parser("check-new")
    parser.add_argument("world")
    parser.set_defaults(handler=check_new)
    parser = sub.add_parser("clear-queue")
    parser.add_argument("world")
    parser.set_defaults(handler=clear_queue)
    for action in ("begin-record", "commit-record"):
        parser = sub.add_parser(action)
        parser.add_argument("world")
        parser.add_argument("--backup", required=True)
        parser.set_defaults(handler=begin_record if action == "begin-record" else commit_record)
    parser = sub.add_parser("apply-live")
    parser.add_argument("world")
    parser.add_argument("scene")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--allow-infected", action="store_true",
                        help="Explicit opt-in for one-by-one vanilla zombie spawns")
    parser.add_argument("--allow-corpses", action="store_true",
                        help="Explicit opt-in for surveyed bathroom corpse and revolver scene")
    parser.set_defaults(handler=apply_live)
    for action in ("live-status", "pre-commit"):
        parser = sub.add_parser(action)
        parser.add_argument("world")
        parser.set_defaults(handler=status if action == "live-status" else pre_commit)
    args = ap.parse_args()
    try:
        args.handler(args)
    except (ValueError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        ap.exit(2, "Story live: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
