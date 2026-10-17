#!/usr/bin/env python3
"""Read-only quest provenance audit for an existing Project Zomboid world.

Only server-owned, validated Story ledger records are considered.
This is an event log, not a real-time entity tracking service: a zombie may
die/despawn without an observable OnZombieDead, and an item may be moved/used.
"""
from __future__ import annotations
import argparse
import json
import os
import re
from pathlib import Path

STORE = Path(os.environ.get("PZ_STORY_STORE_ROOT", "/srv/zomboid")).resolve()
WORLD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
NAME = re.compile(r"[a-z][a-z0-9_-]{2,63}\Z")
MAX_BYTES = 8 * 1024 * 1024
FILE = "SiegerStoryQuestEvents.txt"


def audit(world: str, quest: str) -> dict:
    if not WORLD.fullmatch(world) or not NAME.fullmatch(quest):
        raise ValueError("Invalid world/quest identifier")
    folder = STORE / "worlds" / world
    if not (folder / "profile").is_file() or not (folder / "data").is_dir():
        raise ValueError("Unknown world")
    ledger = folder / "data" / "Lua" / FILE
    if ledger.is_symlink():
        raise ValueError("Quest ledger may not be a symlink")
    seen: dict[str, dict] = {}
    counts = {"item_spawns": 0, "corpse_spawns": 0, "infected_spawns": 0,
              "barricade_spawns": 0, "radio_spawns": 0, "vehicle_spawns": 0, "window_edits": 0, "blood_edits": 0,
              "infected_deaths": 0, "item_moves": 0, "duplicate_rows": 0}
    if ledger.is_file():
        if ledger.stat().st_size > MAX_BYTES:
            raise ValueError("Quest ledger too large; inspect privately")
        with ledger.open("r", encoding="utf-8") as stream:
            for i, line in enumerate(stream, 1):
                if i > 50000:
                    raise ValueError("Too many quest ledger rows")
                f = line.rstrip("\n").split("\t")
                if len(f) != 10 or f[0] != "v1" or f[1] not in ("spawn", "dead", "edit", "move"):
                    raise ValueError(f"Malformed quest ledger row {i}")
                _, event, scene, action, token, kind, x, y, z, online_id = f
                if not NAME.fullmatch(scene) or not NAME.fullmatch(action):
                    raise ValueError(f"Invalid scene/action in row {i}")
                if kind not in ("item", "infected", "corpse", "barricade", "radio", "vehicle", "window", "blood") or not token.startswith(
                        f"SiegerStory:{scene}:{action}:"):
                    raise ValueError(f"Invalid ownership token in row {i}")
                if len(token) > 220:
                    raise ValueError(f"Oversized ownership token in row {i}")
                try:
                    xyz = [int(x), int(y), int(z)]
                    int(online_id)
                except ValueError as err:
                    raise ValueError(f"Bad coordinate/ID in row {i}") from err
                if scene != quest:
                    continue
                if (event == "move" and kind != "item") or (event == "dead" and kind != "infected") or (
                    event == "edit" and kind not in ("window", "blood")) or (
                    event == "spawn" and kind in ("window", "blood")):
                    raise ValueError(f"Invalid quest event kind at row {i}")
                if event == "move":
                    if token in seen and seen[token]["kind"]=="item":
                        seen[token]["last_xyz"]=xyz
                        counts["item_moves"]+=1
                    else:
                        counts["duplicate_rows"]+=1
                elif event in ("spawn", "edit"):
                    if token in seen:
                        counts["duplicate_rows"] += 1
                    else:
                        seen[token] = {"kind": kind, "action": action, "last_xyz": xyz,
                                       "dead_reported": False}
                        counter = {
                            "item": "item_spawns", "infected": "infected_spawns",
                            "corpse": "corpse_spawns", "barricade": "barricade_spawns",
                            "radio": "radio_spawns",
                            "vehicle": "vehicle_spawns",
                            "window": "window_edits", "blood": "blood_edits"
                        }[kind]
                        counts[counter] += 1
                elif token in seen and seen[token]["kind"] == "infected" and not seen[token]["dead_reported"]:
                    seen[token]["dead_reported"] = True
                    seen[token]["last_xyz"] = xyz
                    counts["infected_deaths"] += 1
                else:
                    counts["duplicate_rows"] += 1
    counts["infected_without_reported_death"] = (
        counts["infected_spawns"] - counts["infected_deaths"])
    return {"world": world, "quest": quest, "counts": counts,
            "events_seen": len(seen),
            "warning": "Event ledger only: bodies may be removed/decay, zombies despawn and items move."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("world")
    p.add_argument("quest")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        data = audit(args.world, args.quest)
    except (OSError, UnicodeError, ValueError) as exc:
        p.exit(2, "Quest status: " + str(exc) + "\n")
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"Quest {data['quest']} in {data['world']} (server event ledger):")
    for key, value in data["counts"].items():
        print(f"  {key}: {value}")
    print(data["warning"])


if __name__ == "__main__":
    main()
