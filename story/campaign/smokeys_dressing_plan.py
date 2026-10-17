#!/usr/bin/env python3
"""Read-only suggested relocation of Story-owned floor clutter onto real tabletops.

Requires a NEW v3 scan with tagged ground items and table_surface=true.
Prints per-item --allow-relocate PREVIEW commands, never executes them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SKIP_ACTIONS={"house_rules","shop_run_original","public_closed","dont_take_books","last_board"}
MAX_RECOMMENDED=80


def fail(msg):
    raise ValueError(msg)


def suggest(data):
    if data.get("status")!="complete" or data["summary"].get("errors")!=0 or data["summary"].get("truncated"):
        fail("Require untruncated, error-free current scan")
    meta=data.get("meta",{})
    if not {"ground","objects"}.issubset(set(str(meta.get("modes","")).split(","))):
        fail("scan-area --include ground,objects,squares,... required")
    rows=data["records"]
    support={}
    for r in rows:
        if (r.get("kind")=="object" and r.get("table_surface") is True
            and r.get("class")=="IsoObject" and r.get("sprite")
            and type(r.get("surface_offset_no_table")) in (int,float)
            and 0<r["surface_offset_no_table"]/96<=0.90
            and 10615<=r["x"]<=10628 and 9212<=r["y"]<=9235 and r["z"] in (0,1)):
            support.setdefault(r["z"],[]).append(r)
    if not support:
        fail("No furniture with measured getSurfaceOffsetNoTable in the new v3 scan")
    pending=[]
    seats={}
    for r in rows:
        if (r.get("kind")!="ground_item" or r.get("story_kind")!="item"
                or r.get("story_quest","").startswith("smokeys_bar_") is False
                or r.get("story_action") in SKIP_ACTIONS
                or not 10615<=r["x"]<=10628 or not 9212<=r["y"]<=9235
                or r["z"] not in (0,1) or not r.get("story_token")):
            continue
        nearest=[]
        for t in support.get(r["z"],[]):
            dx=abs(r["x"]-t["x"]);dy=abs(r["y"]-t["y"])
            if max(dx,dy)<=5:
                slot=(t["x"],t["y"],t["z"],t["object_index"])
                if seats.get(slot,0)>=3:continue
                nearest.append((dx+dy,seats.get(slot,0),t))
        if not nearest:continue
        nearest.sort(key=lambda p:(p[0],p[1],p[2]["x"],p[2]["y"]))
        target=nearest[0][2]
        slot=(target["x"],target["y"],target["z"],target["object_index"])
        seats[slot]=seats.get(slot,0)+1
        key=hashlib.sha256(r["story_token"].encode("utf-8")).hexdigest()
        ox=round(0.15+(int(key[0:3],16)%65)/100,2)
        oy=round(0.15+(int(key[3:6],16)%65)/100,2)
        angle=int(key[6:10],16)%360
        height=round(target["surface_offset_no_table"]/96,3)
        action_key="reposition_"+key[:18]
        cmd=(f"sudo pz story apply-once story_test --key {action_key} "
          f"--type relocate --x {r['x']} --y {r['y']} --z {r['z']} "
          f"--token {r['story_token']} "
          f"--to-x {target['x']} --to-y {target['y']} --to-z {target['z']} "
          f"--offset-x {ox:.2f} --offset-y {oy:.2f} --height {height:.3f} --angle {angle} "
          f"--support-index {target['object_index']} "
          f"--support-sprite {target['sprite']} --allow-relocate")
        pending.append({"source":(r["x"],r["y"],r["z"]),
            "target":(target["x"],target["y"],target["z"]),
            "token":r["story_token"],"item_type":r.get("full_type",""),
            "pose":{"x":ox,"y":oy,"z":height,"angle":angle},
            "support":{"index":target["object_index"],"sprite":target["sprite"],
                       "surface_offset_no_table":target["surface_offset_no_table"]},
            "preview":cmd})
        if len(pending)>=MAX_RECOMMENDED:break
    return {"recommendations":pending,"count":len(pending),
            "warning":"Read-only suggestions based on measured B42 surface_offset_no_table /96. "
                      "Revalidate exact target selector and client placement before any --yes."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scan",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    try:
        if not a.scan.is_file() or a.scan.stat().st_size>32*1024*1024:fail("Scan missing/oversized")
        data=json.loads(a.scan.read_text(encoding="utf-8"))
        result=suggest(data)
        if a.output.exists() or a.output.is_symlink():fail("Refuse overwrite/symlink")
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",
                            encoding="utf-8")
        print(f"Natural display: {result['count']} proposed moves (READ ONLY)")
        for item in result["recommendations"]:print(item["preview"])
    except (ValueError,OSError,json.JSONDecodeError) as e:
        p.exit(2,"Smokey's dressing: "+str(e)+"\n")

if __name__=="__main__":
    main()
