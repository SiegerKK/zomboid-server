#!/usr/bin/env python3
"""Offline preflight of Route 17 Story scene coordinates against trusted survey.

Never touches a game save. The SHA-256 and request-id pins prevent accidentally
using a scan from another world or a different site. The inventory is top-level
only; this audit proves selectors at survey time, NOT at live apply time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "story"))
from storyctl import read_scene, resolve_scene

SITES = {
    "bar": {
        "sha256": "16cd6b500428a88a85a6908ac774c5cfd0939ae448e21d5acdc9e038ecc144a1",
        "request_id": "17bbb7165cb0f05099b32ef32ace4488",
        "prefix": "smokeys_bar_",
        "side": 101, "center": (10622, 9221, 0),
        "allowed_x": (10610, 10629), "allowed_y": (9210, 9237),
        "known_rooms": {"restaurantdining", "restaurantkitchen", "bar", "hall", "bathroom",
                        "bedroom", "livingroom", "kitchen", "empty"},
    },
    "shop": {
        "sha256": "4b784e5d1ca94cf163ee3f0a184d000d538902201011e42b023b3da920b403cc",
        "request_id": "be026a6b6104218925e10603b9781e8d",
        "prefix": "smokeys_shop_",
        "side": 51, "center": (10609, 9407, 0),
        "allowed_x": (10600, 10613), "allowed_y": (9402, 9413),
        "known_rooms": {"mechanic", "office", "bathroom"},
    },
}


def verify(scene_names: list[str], site: str, snapshot: Path) -> dict:
    cfg = SITES[site]
    digest = hashlib.sha256()
    with snapshot.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != cfg["sha256"]:
        raise ValueError(f"{site}: scan SHA-256 differs from pinned trusted snapshot")
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    if data.get("status") != "complete":
        raise ValueError("Scan status is not complete")
    meta, summary = data.get("meta"), data.get("summary")
    if not isinstance(meta, dict) or not isinstance(summary, dict):
        raise ValueError("Malformed scan metadata")
    if meta.get("request_id") != cfg["request_id"] or summary.get("request_id") != cfg["request_id"]:
        raise ValueError("Scan request IDs differ")
    if meta.get("side") != cfg["side"] or (
            meta.get("center_x"), meta.get("center_y"), meta.get("center_z")) != cfg["center"]:
        raise ValueError("Unexpected scan location / dimensions")
    if summary.get("status") != "complete" or summary.get("errors") != 0 or summary.get("truncated"):
        raise ValueError("Incomplete, erroneous or truncated scan")
    if summary.get("scanned_squares") != cfg["side"] * cfg["side"] * 5:
        raise ValueError("Scan coverage count is inconsistent")
    squares, objects, containers = {}, {}, set()
    for row in data.get("records", []):
        k = (row.get("x"), row.get("y"), row.get("z"))
        if row.get("kind") == "square":
            if k in squares:
                raise ValueError(f"Duplicate square {k}")
            squares[k] = row
        elif row.get("kind") == "object":
            key = k + (row.get("object_index"),)
            if key in objects:
                raise ValueError(f"Duplicate object selector {key}")
            objects[key] = row
        elif row.get("kind") == "container" and row.get("source") == "square":
            containers.add(k + (row.get("object_index"), row.get("container_index")))
    if len(squares) != summary["scanned_squares"]:
        raise ValueError("Square record count disagrees with summary")
    seen_scenes = set()
    checked, counters = 0, Counter()
    scene_results = []
    for path_or_id in scene_names:
        file = resolve_scene(path_or_id)
        scene, stats = read_scene(file, ready=True, allow_infected=True)
        if scene["id"] in seen_scenes:
            raise ValueError("Duplicate scene ID in audit")
        seen_scenes.add(scene["id"])
        if scene["world"] != "story_test" or not scene["id"].startswith(cfg["prefix"]):
            raise ValueError(f"Scene does not belong to {site}: {scene['id']}")
        if stats["active"] > 32:
            raise ValueError("Live executor supports <=32 enabled actions per scene")
        for action in scene["actions"]:
            if not action.get("enabled", True):
                continue
            x, y, z = action["at"].values()
            x, y, z = action["at"]["x"], action["at"]["y"], action["at"]["z"]
            if not (cfg["allowed_x"][0] <= x <= cfg["allowed_x"][1]
                    and cfg["allowed_y"][0] <= y <= cfg["allowed_y"][1]
                    and z in (0, 1 if site == "bar" else 0)):
                raise ValueError(f"{scene['id']}:{action['id']}: outside protected site bounds")
            cell = squares.get((x, y, z))
            if not cell or cell.get("loaded") is not True:
                raise ValueError(f"{scene['id']}:{action['id']}: target cell not loaded")
            room = cell.get("room", "")
            if room not in cfg["known_rooms"]:
                if action["type"] == "infected" or action.get("placement") == "container":
                    raise ValueError(f"{scene['id']}:{action['id']}: unexpected room {room!r}")
                # Non-room ground cells in the yard are permitted only by manual review.
                counters["unnamed_ground_warning"] += 1
            if action.get("placement") == "container":
                selector = action["selector"]
                key = (x, y, z, selector["object_index"])
                obj = objects.get(key)
                if not obj or obj.get("sprite") != selector["sprite"] or obj.get("class") != selector["class"]:
                    raise ValueError(f"{scene['id']}:{action['id']}: selector mismatch {key}")
                if key + (0,) not in containers:
                    raise ValueError(f"{scene['id']}:{action['id']}: container #0 missing")
            if action["type"] == "infected" and (
                    action["subtype"] != "vanilla" or action["count"] != 1):
                raise ValueError("Unapproved infected action")
            counters[action["type"]] += 1
            if action["type"] == "loot":
                counters["item_instances"] += sum(entry["count"] for entry in action["items"])
            checked += 1
        scene_results.append({"scene": scene["id"], **stats})
    return {"site": site, "source_request": cfg["request_id"],
            "scene_count": len(seen_scenes), "checked_actions": checked,
            "counters": dict(counters), "scenes": scene_results,
            "warning": "Read-only survey audit. Recheck indexes in game before applying scenes."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True, choices=sorted(SITES))
    parser.add_argument("--scan", required=True, type=Path)
    parser.add_argument("scenes", nargs="+")
    args = parser.parse_args()
    try:
        result = verify(args.scenes, args.site, args.scan)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Route17 scan audit FAILED: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
