#!/usr/bin/env python3
"""Read-only inventory of every original Smokey's window; create exact CLI plan.

Input must be a FRESH complete v3 scan with windows category; this tool
does not guess whether glass is intact or whether existing boards remain.
Commands are printed WITHOUT --yes to prevent accidental application.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from pathlib import Path

# All 32 windows seen in the owner's original 2026-10-17 101x101x5 survey.
# Note this list is historical. A missing/moved selector stops the planner.
WINDOWS = (
(10616,9215,0,2,"fixtures_windows_01_56"),
(10626,9215,0,1,"walls_commercial_01_80"),
(10626,9217,0,1,"walls_commercial_01_80"),
(10626,9219,0,1,"walls_commercial_01_80"),
(10626,9221,0,1,"walls_commercial_01_80"),
(10624,9223,0,2,"walls_commercial_01_80"),
(10626,9223,0,1,"walls_commercial_01_80"),
(10616,9224,0,1,"walls_commercial_01_80"),
(10624,9226,0,1,"walls_commercial_01_80"),
(10626,9226,0,1,"walls_commercial_01_80"),
(10616,9228,0,1,"walls_commercial_01_80"),
(10628,9228,0,1,"walls_commercial_01_80"),
(10616,9229,0,1,"walls_commercial_01_80"),
(10628,9229,0,1,"walls_commercial_01_80"),
(10628,9231,0,1,"walls_commercial_01_80"),
(10628,9232,0,1,"walls_commercial_01_80"),
(10616,9233,0,1,"walls_commercial_01_80"),
(10616,9214,1,1,"walls_commercial_01_80"),
(10626,9215,1,1,"walls_commercial_01_80"),
(10626,9217,1,1,"walls_commercial_01_80"),
(10616,9219,1,1,"walls_commercial_01_80"),
(10626,9219,1,1,"walls_commercial_01_80"),
(10616,9220,1,1,"walls_commercial_01_80"),
(10626,9221,1,1,"walls_commercial_01_80"),
(10616,9225,1,1,"walls_commercial_01_80"),
(10616,9228,1,2,"fixtures_windows_01_0"),
(10627,9228,1,2,"fixtures_windows_01_0"),
(10616,9231,1,2,"fixtures_windows_01_0"),
(10627,9233,1,2,"fixtures_windows_01_0"),
(10617,9235,1,1,"fixtures_windows_01_1"),
(10620,9235,1,1,"fixtures_windows_01_1"),
(10623,9235,1,1,"fixtures_windows_01_1"),
)
assert len(set(WINDOWS)) == len(WINDOWS) == 32

def fail(message):
    raise ValueError(message)


def plan(data:dict):
    if data.get("status")!="complete":
        fail("Survey must be complete")
    meta,summary=data["meta"],data["summary"]
    if meta.get("side") not in (25,51,101) or not (meta.get("min_z",99)<=0 and meta.get("max_z",-99)>=1):
        fail("Survey must cover both floors Z=0,1 and adequate bounds")
    if "windows" not in str(meta.get("modes","")).split(","):
        fail("Fresh v3 scan with explicit windows state required")
    if summary.get("truncated") or summary.get("errors")!=0:
        fail("Survey was truncated/partial")
    windows={}
    squares=set()
    for row in data["records"]:
        if row.get("kind")=="object" and row.get("class")=="IsoWindow":
            key=(row["x"],row["y"],row["z"],row["object_index"],row["sprite"])
            windows[key]=row
        if row.get("kind")=="square" and row.get("loaded"):
            squares.add((row["x"],row["y"],row["z"]))
    desired=[]; covered=[]
    for key in WINDOWS:
        x,y,z,idx,sprite=key
        if (x,y,z) not in squares:
            fail(f"Required Smokey's window tile not loaded {key}")
        w=windows.get(key)
        if not w:
            fail(f"Original window selector missing/changed {key}; re-scan and review")
        flags=("window_smashed","window_glass_removed",
               "window_barricaded_same","window_barricaded_opposite","window_open")
        if any(type(w.get(k)) is not bool for k in flags):
            fail(f"Missing validated current state for window {key}")
        if w["window_barricaded_same"] or w["window_barricaded_opposite"]:
            covered.append((key,"existing_barricade"))
            continue
        if w["window_smashed"] or w["window_glass_removed"]:
            covered.append((key,"already_broken"))
            continue
        if w["window_open"]:
            fail(f"Window is open; cannot safely stage barricade without player review: {key}")
        h=zlib.crc32(f"{x}:{y}:{z}:{idx}".encode("ascii"))
        mode="smash" if h%7==0 else "barricade"
        boards=h%4+1
        stem=f"smokeys_w_{x}_{y}_z{z}"
        cmd=(f"sudo pz story apply-once story_test --key {stem} "
             f"--type {'window' if mode=='smash' else 'barricade'} "
             f"--x {x} --y {y} --z {z} "
             f"--target-index {idx} --target-sprite {sprite} ")
        if mode=="smash":
            cmd+="--allow-environment"
        else:
            cmd+=f"--planks {boards} --allow-barricades"
        desired.append({"x":x,"y":y,"z":z,"mode":mode,"boards":boards if mode=="barricade" else 0,
                        "key":stem,"cmd_preview":cmd})
    return {"total_original_windows":len(WINDOWS),"already_safe":len(covered),
            "operations_to_apply":len(desired),"covered":covered,"operations":desired,
            "warning":"Commands are preview only. Add --yes only one-by-one after live-status COMPLETE."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scan",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        src=args.scan
        if not src.is_file() or src.stat().st_size>32*1024*1024:
            fail("Full trusted v3 scan JSON missing or oversized")
        data=json.loads(src.read_text(encoding="utf-8"))
        result=plan(data)
        if args.output.exists() or args.output.is_symlink():
            fail("Destination exists or is symlink")
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                               encoding="utf-8")
        print(f"Historical windows: {len(WINDOWS)}; already safe: {result['already_safe']}; "
              f"pending: {result['operations_to_apply']}")
        for action in result["operations"]:
            print(action["cmd_preview"])
        print("PREVIEW ONLY — no changes to the server. Add --yes only after review.")
    except (ValueError,OSError,json.JSONDecodeError) as ex:
        p.exit(2,"Smokey's windows: "+str(ex)+"\n")

if __name__=="__main__":
    main()
