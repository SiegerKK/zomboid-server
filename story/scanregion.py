#!/usr/bin/env python3
"""Plan and reconcile arbitrarily large loaded-square surveys safely.

A region is tiled into disjoint <=101x101 coverage clips. Every tile uses the
ALREADY TESTED v3 scan-area server API; this utility neither increases work per
game tick nor loads chunks. Run each command while the exact player is online
near the tile's centre, export a fresh full JSON, then merge verified results.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import re
import scanctl

VERSION="sieger-private-mosaic-area-survey-v1"
PLAN="sieger-private-area-scan-plan-v1"
TILE=101
MAX_SOURCE_BYTES=64*1024*1024
MAX_MANIFEST_BYTES=4*1024*1024
MAX_MERGED_BYTES=768*1024*1024
RID=re.compile(r"[0-9a-f]{32}\Z")
BASENAME=re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,96}\.json\Z")
CATEGORIES={"squares","objects","containers","items","ground","actors",
            "corpses","vehicles","windows","blood"}

def fail(msg):raise ValueError(msg)

def json_file(path,maximum):
    f=Path(path)
    if not f.is_file() or f.is_symlink() or f.stat().st_size>maximum:
        fail("Unsafe/missing/oversized source file: "+str(f))
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:fail("Duplicate JSON key: "+k)
            result[k]=v
        return result
    return json.loads(f.read_text("utf-8"),object_pairs_hook=unique,
        parse_constant=lambda s:fail("JSON non-finite value "+s))

def destination(path):
    p=Path(path)
    if p.is_symlink() or p.exists() or not p.parent.is_dir() or \
       p.resolve().is_relative_to(scanctl.REPO.resolve()):
        fail("Output must be a NEW private file outside the repository")
    return p

def save_new(path,body):
    out=destination(path)
    fd=os.open(out,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(body,stream,ensure_ascii=False,allow_nan=False,
                      separators=(",",":"))
            stream.write("\n")
    except BaseException:
        out.unlink(missing_ok=True)
        raise

def bbox_parse(raw):
    try:a=list(map(int,raw.split(",")))
    except ValueError:fail("Use --bbox x0,y0,x1,y1")
    if len(a)!=4 or not 0<=a[0]<a[2]<=40001 or \
       not 0<=a[1]<a[3]<=40001:
        fail("Bbox must have positive area within the map: [x0,y0,x1,y1)")
    return a

def modes_parse(raw):
    modes=raw.split(",")
    if len(modes)!=len(set(modes)) or not set(modes)<=CATEGORIES or \
       "squares" not in modes or "items" in modes and "containers" not in modes or \
       "blood" in modes and "squares" not in modes:
        fail("Invalid scan modes: squares are mandatory; items need containers")
    return modes

def construct_tiles(box):
    x0,y0,x1,y1=box
    # Edge areas are deliberately clipped to prevent cross-frame object-index
    # collisions, while the engine still scans its safe fixed 101x101 window.
    tiles=[]
    for y in range(y0,y1,TILE):
        for x in range(x0,x1,TILE):
            xmax,ymax=min(x+TILE,x1),min(y+TILE,y1)
            cx,cy=min(x+50,40000),min(y+50,40000)
            if not cx-50<=x<xmax<=cx+51 or not cy-50<=y<ymax<=cy+51:
                fail("Tile centre cannot cover map boundary")
            n=len(tiles)+1
            tiles.append({"index":n,"clip_bbox":[x,y,xmax,ymax],
                          "center":[cx,cy],
                          "source":f"tile-{n:03d}.json"})
    return tiles

def build_plan(world,player,bbox,zmin,zmax,modes):
    if not scanctl.WORLD.fullmatch(world) or not scanctl.USERNAME.fullmatch(player):
        fail("Invalid world/player")
    if not -2<=zmin<=zmax<=16 or zmax-zmin>=5:
        fail("Requested floors must span 1..5 levels in -2..16")
    modes=modes_parse(modes)
    tiles=construct_tiles(bbox)
    if len(tiles)>64:fail("More than 64 tiles; split the huge region into smaller mosaics")
    return {"schema":PLAN,"world":world,"player":player,
            "bbox_exclusive":bbox,"floors":[zmin,zmax],"modes":modes,
            "tile_side":TILE,"tiles":tiles,
            "observation":"Independent read-only server scans; NOT simultaneous",
            "caveats":["Every tile requires online player within 100 squares of scan centre",
                       "Teleportation is a separate explicit administrator operation",
                       "No scan generates unloaded chunks, zombie population or buildings",
                       "Later scans can observe later world state"]}

def exact_plan(raw):
    if not isinstance(raw,dict) or raw.get("schema")!=PLAN:
        fail("Not a v1 mosaic plan")
    keys={"schema","world","player","bbox_exclusive","floors","modes",
          "tile_side","tiles","observation","caveats"}
    if set(raw)!=keys or raw["tile_side"]!=TILE:
        fail("Malformed tiled plan envelope")
    box=raw["bbox_exclusive"]
    if not isinstance(box,list) or len(box)!=4 or any(type(k)is not int for k in box):
        fail("Plan has invalid bounding box")
    bbox=bbox_parse(",".join(map(str,box)))
    z=raw["floors"]
    if not isinstance(z,list) or len(z)!=2 or any(type(k)is not int for k in z):
        fail("Plan floor range invalid")
    modes=raw["modes"]
    if not isinstance(modes,list) or any(not isinstance(x,str) for x in modes):
        fail("Plan scan modes invalid")
    trusted=build_plan(raw["world"],raw["player"],bbox,*z,",".join(modes))
    if raw!=trusted:fail("Plan modified or its tile coverage is inconsistent")
    return trusted

def scanned_tile(src,expected,plan):
    if not isinstance(src,dict) or src.get("status")!="complete":
        fail("Incomplete source tile: "+str(expected["index"]))
    meta,summary,records=(src.get(key) for key in ("meta","summary","records"))
    if not isinstance(meta,dict) or not isinstance(summary,dict) or \
       not isinstance(records,list):
        fail("Source missing meta/summary/records")
    rid=meta.get("request_id")
    if not isinstance(rid,str) or not RID.fullmatch(rid):
        fail("Invalid source request ID")
    if meta.get("player")!=plan["player"] or \
       [meta.get("center_x"),meta.get("center_y")]!=expected["center"] or \
       meta.get("side")!=TILE or \
       (meta.get("min_z"),meta.get("max_z"))!=tuple(plan["floors"]) or \
       meta.get("levels")!=plan["floors"][1]-plan["floors"][0]+1 or \
       meta.get("snapshot_mode")!="incremental" or \
       set(str(meta.get("modes","")).split(","))!=set(plan["modes"]):
        fail("Source tile mode, centre, player or floor differs")
    count=TILE*TILE*(plan["floors"][1]-plan["floors"][0]+1)
    for key,value in {"requested_squares":count,
                      "scanned_squares":count,
                      "truncated":False,"errors":0}.items():
        if type(summary.get(key)) is not type(value) or summary[key]!=value:
            fail("Incomplete or truncated tile: "+str(expected["index"]))
    if summary.get("kind")!="summary" or summary.get("status")!="complete" or \
       summary.get("loaded_squares",0)+summary.get("unloaded_squares",0)!=count or \
       summary.get("records")!=len(records):
        fail("Source footer not consistent with tile records")
    if "vehicles" in plan["modes"] and summary.get("vehicle_snapshot")!="complete":
        fail("Vehicle pass incomplete in tile")
    lo,hi=expected["clip_bbox"][:2],expected["clip_bbox"][2:]
    seen={};accepted=[];by_kind=Counter()
    for row in records:
        if not isinstance(row,dict) or not isinstance(row.get("kind"),str):
            fail("Invalid source record type")
        x,y,z=row.get("x"),row.get("y"),row.get("z")
        if any(type(v)is not int for v in (x,y,z)):
            fail("Missing or noninteger record coordinate")
        if not (lo[0]<=x<hi[0] and lo[1]<=y<hi[1]
                and plan["floors"][0]<=z<=plan["floors"][1]):
            continue
        p=(x,y,z)
        if row["kind"]=="square":
            if p in seen or type(row.get("loaded"))is not bool:
                fail("Duplicate/incomplete loaded-square coverage")
            seen[p]=row["loaded"]
        accepted.append(row)
        by_kind[row["kind"]]+=1
    x0,y0,x1,y1=expected["clip_bbox"]
    need=(x1-x0)*(y1-y0)*(plan["floors"][1]-plan["floors"][0]+1)
    if len(seen)!=need:fail("Clipped tile lacks one square record per coordinate")
    for row in accepted:
        if row["kind"]!="square":
            owner=(row["x"],row["y"],row["z"])
            if owner not in seen:
                fail("Entity from source lacks corresponding square coverage")
            if not seen[owner]:
                fail("Entity reported on explicitly unloaded square")
    return {"request_id":rid,"meta":meta,"summary":summary,
            "rows":accepted,"counts":dict(by_kind)}

def merge(plan,manifest):
    bbox=plan["bbox_exclusive"];z0,z1=plan["floors"]
    seenids=set();record_kinds=Counter();results=[]
    source_at={}
    loaded_by_level=Counter();unloaded_by_level=Counter()
    source_summary=[]
    base=manifest.parent
    for tile in plan["tiles"]:
        source=tile["source"]
        if not BASENAME.fullmatch(source) or "/" in source or "\\" in source:
            fail("Unsafe tile source basename")
        parsed=json_file(base/source,MAX_SOURCE_BYTES)
        verified=scanned_tile(parsed,tile,plan)
        rid=verified["request_id"]
        if rid in seenids:fail("Reused request ID across tiles")
        seenids.add(rid)
        source_summary.append({"index":tile["index"],"file":source,
            "request_id":rid,"clip_bbox":tile["clip_bbox"],
            "source_center":tile["center"],
            "records_inside_clip":len(verified["rows"]),
            "note":"Different capture time from other tiles"})
        for row in verified["rows"]:
            z=row["z"];key=(row["x"],row["y"],z)
            if row["kind"]=="square":
                if key in source_at:fail("Mosaic tiles overlap on square")
                source_at[key]=rid
                if row["loaded"]:loaded_by_level[str(z)]+=1
                else:unloaded_by_level[str(z)]+=1
            record_kinds[row["kind"]]+=1
            results.append(row)
    area=(bbox[2]-bbox[0])*(bbox[3]-bbox[1])
    total=area*(z1-z0+1)
    if len(source_at)!=total:fail("Merged area contains missing or overlapping squares")
    result={
        "schema":VERSION,"world":plan["world"],
        "bbox_exclusive":bbox,"width":bbox[2]-bbox[0],
        "height":bbox[3]-bbox[1],"floors":[z0,z1],
        "snapshot_mode":"multiple_sequential_loaded_square_scans_not_simultaneous",
        "source_policy":"Disjoint spatial clips; each square and its associated objects from ONE verified source",
        "sources":source_summary,
        "cell_source_request_ids":{f"{x},{y},{z}":v for (x,y,z),v in source_at.items()},
        "summary":{
           "visited_cells":total,"all_requested_coordinates_visited":True,
           "source_errors":0,"source_truncated":False,
           "floor_coverage":{
               str(z):{"loaded":loaded_by_level[str(z)],
                       "unloaded_or_nonexistent":unloaded_by_level[str(z)]}
               for z in range(z0,z1+1)},
           "record_kinds":dict(record_kinds),
           "source_count":len(source_summary)},
        "limitations":["Not simultaneous; different sectors may reflect different states",
            "Unloaded/absent is not free or accessible terrain",
            "No automatic migration of buildings or zombie population",
            "Distinct scans may move the same vehicle/person; cross-time unique entity count is not guaranteed"],
        "records":results,
    }
    if len(json.dumps(result,ensure_ascii=False).encode("utf-8"))>MAX_MERGED_BYTES:
        fail("Merged output exceeds 768 MiB; split the export")
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    plan=sub.add_parser("plan")
    plan.add_argument("world")
    plan.add_argument("--player",required=True)
    plan.add_argument("--bbox",required=True)
    plan.add_argument("--z-min",type=int,default=0)
    plan.add_argument("--z-max",type=int,default=1)
    plan.add_argument("--include",default="squares,objects,vehicles,windows")
    plan.add_argument("--output",required=True)
    collect=sub.add_parser("merge")
    collect.add_argument("--manifest",required=True)
    collect.add_argument("--output",required=True)
    args=p.parse_args()
    try:
        if args.command=="plan":
            manifest=build_plan(args.world,args.player,bbox_parse(args.bbox),
                                args.z_min,args.z_max,args.include)
            save_new(args.output,manifest)
            print(f"PLANNED {len(manifest['tiles'])} independent 101x101 scans")
            for tile in manifest["tiles"]:
                x,y=tile["center"]
                print(f"  {tile['index']:03d}: centre {x},{y}; "+
                      f"clip={tile['clip_bbox']} -> {tile['source']}")
                print(f"     sudo pz story teleport {args.world} {args.player} {x} {y} 0 --yes")
                print(f"     sudo pz story scan-area {args.world} "+
                      f"--player {args.player} --center {x},{y} "+
                      f"--radius 50 --z-min {args.z_min} --z-max {args.z_max} "+
                      f"--include {args.include} --yes")
                print(f"     sudo pz story scan-report {args.world} "+
                      f"--output {Path(args.output).parent/tile['source']}")
            print("Wait for loaded chunks and scan-status COMPLETE between tiles. "+
                  "NO automatic teleport or scan was performed.")
        else:
            manifest=Path(args.manifest)
            plan_data=exact_plan(json_file(manifest,MAX_MANIFEST_BYTES))
            result=merge(plan_data,manifest)
            save_new(args.output,result)
            print(f"MERGED {len(plan_data['tiles'])} complete scans across "+
                  f"{result['summary']['visited_cells']} unique square positions")
            print("WARNING: successive scans are NOT a single world instant.")
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as e:
        p.exit(2,"Story scan-region: "+str(e)+"\n")

if __name__=="__main__":main()
