#!/usr/bin/env python3
"""Read-only fresh-scan QA of Auto Shop's five outdoor windows.

The original pinned 51x51x5 survey identifies five WEST exterior windows
at x=10601. Two x=10605 windows face the workshop interior and are excluded.
This script never modifies the game or invents client availability.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

EXTERIOR=(
 (10601,9407,0,1,"walls_commercial_02_4"),
 (10601,9408,0,1,"walls_commercial_02_4"),
 (10601,9409,0,1,"walls_commercial_02_0"),
 (10601,9411,0,1,"walls_commercial_02_0"),
 (10601,9412,0,1,"walls_commercial_02_0"),
)
BROKEN_AFTER_BOARDS={(10601,9408,0),(10601,9412,0)}

def fail(msg):
    raise ValueError(msg)

def verify(snapshot, phase):
    if snapshot.get("status")!="complete" or snapshot["summary"].get("truncated") is not False or snapshot["summary"].get("errors")!=0:
        fail("Full recent scan must be complete, untruncated, no errors")
    meta=snapshot.get("meta",{})
    modes=set(str(meta.get("modes","")).split(","))
    if not {"squares","windows"}.issubset(modes):
        fail("Must scan windows AND loaded squares using modern v3 scan")
    sq={(r.get("x"),r.get("y"),r.get("z")):r
        for r in snapshot["records"] if r.get("kind")=="square"}
    objs={(r.get("x"),r.get("y"),r.get("z"),r.get("object_index"),r.get("sprite")):r
        for r in snapshot["records"]
        if r.get("kind")=="object" and r.get("class")=="IsoWindow"}
    result=[]
    for x,y,z,index,sprite in EXTERIOR:
        here=sq.get((x,y,z))
        outside=sq.get((x-1,y,z))
        if not here or not here.get("loaded") or here.get("room")!="office":
            fail(f"Office window tile absent/changed {(x,y,z)}")
        if not outside or not outside.get("loaded") or outside.get("room")!="":
            fail(f"Outside-west neighbour not loaded or no longer outdoor {(x,y,z)}")
        row=objs.get((x,y,z,index,sprite))
        if row is None:fail(f"Historic IsoWindow index/sprite changed {(x,y,z,index,sprite)}")
        keys=("window_open","window_smashed","window_glass_removed",
              "window_barricaded_same","window_barricaded_opposite")
        if any(type(row.get(k)) is not bool for k in keys):
            fail(f"Missing fresh window state {(x,y,z)}")
        if row["window_open"]:
            fail(f"Open window requires manual review before editing {(x,y,z)}")
        boarded=row["window_barricaded_same"] or row["window_barricaded_opposite"]
        damaged=row["window_smashed"] or row["window_glass_removed"]
        if phase=="pre_board" and boarded:
            state="already_boarded"
        elif phase=="pre_board":
            state="must_board"
        elif phase=="pre_breach":
            if not boarded:
                fail(f"No barricade yet, cannot damage boarded glass {(x,y,z)}")
            if (x,y,z) in BROKEN_AFTER_BOARDS:
                if damaged:fail(f"Glass already damaged; do not replay {(x,y,z)}")
                state="ready_for_explicit_breach"
            else:
                state="boarded_leave_intact"
        else:
            if not boarded:fail(f"Missing planks after work {(x,y,z)}")
            if (x,y,z) in BROKEN_AFTER_BOARDS and not damaged:
                fail(f"Staged glass breach missing from window {(x,y,z)}")
            state="verified"
        result.append({"x":x,"y":y,"z":z,"sprite":sprite,
                       "object_index":index,"boarded":boarded,
                       "glass_damaged":damaged,"status":state})
    return {"total_external_windows":5,"excluded_internal_window_positions":
        [[10605,9407,0],[10605,9412,0]],"phase":phase,"windows":result}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scan",type=Path,required=True)
    p.add_argument("--phase",choices=("pre_board","pre_breach","verify"),default="pre_board")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    try:
        if not a.scan.is_file() or a.scan.is_symlink() or a.scan.stat().st_size>32*1024*1024:
            fail("Unsafe scan file")
        data=json.loads(a.scan.read_text(encoding="utf-8"))
        result=verify(data,a.phase)
        text=json.dumps(result,ensure_ascii=False,indent=2)
        print(text)
        if a.output:
            if a.output.exists() or a.output.is_symlink() or not a.output.parent.is_dir():
                fail("Refusing unsafe output destination")
            a.output.write_text(text+"\n",encoding="utf-8")
    except (ValueError,OSError,json.JSONDecodeError,KeyError) as e:
        p.exit(2,"Auto Shop windows: "+str(e)+"\n")

if __name__=="__main__":
    main()
