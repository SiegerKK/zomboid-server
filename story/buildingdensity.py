#!/usr/bin/env python3
"""Offline cross-map TLOU occupancy + density analysis.

Joins a verified Building Atlas export with either the existing full TLOU
roster or ONE completed ZombieDebug trace sample. Never sums frames as if
they were unique zombies. No changes to game state, spawns or tuning.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import json
import math
from pathlib import Path
import buildingatlas as atlas

MAX_INPUT=300*1024*1024

def fail(msg):raise ValueError(msg)

def load_json(path):
    p=Path(path)
    if not p.is_file() or p.is_symlink() or p.stat().st_size>MAX_INPUT:
        fail("Unsafe/missing/oversized input JSON")
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:fail("Duplicate JSON field: "+k)
            result[k]=v
        return result
    return json.loads(p.read_text("utf-8"),object_pairs_hook=unique,
                      parse_constant=lambda s:fail("Nonfinite JSON value"))

def finite(v):
    return type(v) in (float,int) and math.isfinite(v)

def source_roster(data,world,claim_world):
    # Legacy roster v3 has NO world name. Require an explicit operator assertion.
    if claim_world!=world:
        fail("Roster lacks world identity: give exact --source-world matching Atlas")
    if data.get("status")!="complete" or data.get("operation")!="roster":
        fail("Roster must be an exact complete snapshot")
    cover=data.get("coverage")
    zombies=data.get("zombies")
    if not isinstance(cover,dict) or not isinstance(zombies,list):
        fail("Missing TLOU roster coverage")
    n=cover.get("inspected")
    if type(n) is not int or type(cover.get("list_slots")) is not int or \
            type(cover.get("null_slots")) is not int or n!=len(zombies) \
            or n+cover["null_slots"]!=cover["list_slots"] or \
            cover.get("truncated") is not False:
        fail("TLOU roster is incomplete or contradictory")
    result=[]
    slots=set()
    for z in zombies:
        if not isinstance(z,dict) or not all(finite(z.get(k)) for k in ("x","y","z")) \
                or not isinstance(z.get("type"),str) or type(z.get("snapshot_index")) is not int:
            fail("Malformed TLOU roster zombie")
        if z["snapshot_index"] in slots:fail("Duplicate roster snapshot index")
        slots.add(z["snapshot_index"])
        result.append({"x":z["x"],"y":z["y"],"z":z["z"],"type":z["type"]})
    return result,{"format":"tlou_roster","scope":"all loaded server zombies",
                   "declared_world":claim_world,"world_identity":"manual_operator_assertion",
                   "expected_slots":cover["list_slots"],"inspected":n,
                   "null_slots":cover["null_slots"],"sample_sequence":1}

def source_trace(data,world,sample):
    if data.get("schema")!=1 or data.get("capture_complete") is not True or \
            data.get("terminal_status")!="complete":
        fail("Trace must be finished and complete; no silent partial statistics")
    records=data.get("records")
    rid=data.get("recording_id")
    if not isinstance(records,list) or not isinstance(rid,str) or \
            not atlas.ID.fullmatch(rid) or not records:
        fail("Malformed exported ZombieDebug recording")
    header=records[0]
    if header.get("kind")!="start" or header.get("world")!=world or \
            header.get("id")!=rid or header.get("schema")!=1:
        fail("ZombieDebug header world/schema mismatch")
    tail=records[-1]
    if tail.get("kind")!="end" or tail.get("status")!="complete" or \
            tail.get("id")!=rid or tail.get("samples",0)<1:
        fail("Missing completed terminal trace marker")
    snapshots={}
    current=None
    for row in records[1:-1]:
        if not isinstance(row,dict) or row.get("id")!=rid:fail("Trace ID mismatch")
        kind=row.get("kind")
        if kind=="sample":
            if current is not None or type(row.get("seq")) is not int \
                    or type(row.get("expected_slots")) is not int \
                    or row["seq"] in snapshots:
                fail("Invalid/duplicate trace sample")
            current={"seq":row["seq"],"expected":row["expected_slots"],
                     "zombies":[],"errors":0,"lost":0}
            snapshots[row["seq"]]=current
        elif kind=="zombie":
            if current is None or row.get("sample")!=current["seq"] \
                    or not all(finite(row.get(k))for k in("x","y","z")) \
                    or not isinstance(row.get("type"),str):
                fail("Malformed trace zombie")
            current["zombies"].append(row)
        elif kind=="entity_error":
            if current is None:fail("Out-of-sample trace error")
            current["errors"]+=1
        elif kind=="lost":
            if current is None:fail("Out-of-sample trace observation loss")
            current["lost"]+=1
        elif kind=="sample_end":
            if current is None or row.get("seq")!=current["seq"]:
                fail("Malformed trace sample_end")
            if type(row.get("null_slots")) is not int or \
                    type(row.get("inspected")) is not int or \
                    type(row.get("errors")) is not int or \
                    row.get("coverage_complete") is not True \
                    or row["errors"]!=current["errors"] or \
                    row["inspected"]!=len(current["zombies"]) or \
                    row["inspected"]+row["null_slots"]+row["errors"]!=current["expected"]:
                fail("Incomplete trace sample")
            current["null_slots"]=row["null_slots"]
            current=None
        else:fail("Unexpected trace record kind")
    if current is not None or len(snapshots)!=tail["samples"] \
            or any("null_slots" not in s for s in snapshots.values()):
        fail("Unclosed or missing trace samples")
    if sample=="last":key=max(snapshots)
    elif sample=="first":key=min(snapshots)
    else:
        try:key=int(sample)
        except ValueError:fail("Use first, last or an exact sample sequence")
    if key not in snapshots:fail("Requested trace frame not found")
    chosen=snapshots[key]
    if chosen["errors"] or len(chosen["zombies"])+chosen["null_slots"]!=chosen["expected"]:
        fail("Selected sample has incomplete coverage")
    result=[{"x":z["x"],"y":z["y"],"z":z["z"],"type":z["type"]}
            for z in chosen["zombies"]]
    return result,{"format":"zombie_debug_trace","scope":"all loaded server zombies in one frame",
                   "declared_world":world,"world_identity":"server_trace_header",
                   "recording_id":rid,"sample_sequence":key,
                   "expected_slots":chosen["expected"],"inspected":len(result),
                   "null_slots":chosen["null_slots"],
                   "available_samples":len(snapshots)}

def union_area(rectangles):
    """Exact tile-area union of axis-aligned integer map room rectangles."""
    if not rectangles:return 0
    xs=sorted({x for r in rectangles for x in (r[0],r[2])})
    total=0
    for left,right in zip(xs,xs[1:]):
        intervals=sorted((r[1],r[3]) for r in rectangles if r[0]<right and r[2]>left)
        if not intervals:continue
        sy,ey=intervals[0]
        height=0
        for y0,y1 in intervals[1:]:
            if y0<=ey:ey=max(ey,y1)
            else:height+=ey-sy;sy,ey=y0,y1
        height+=ey-sy
        total+=(right-left)*height
    return total

def summarize(mapdata,zombies,origin,grid_size):
    if mapdata.get("schema")!=1 or not isinstance(mapdata.get("buildings"),list) \
            or not isinstance(mapdata.get("loaded_chunks"),list):
        fail("Invalid exported Atlas schema")
    bbox=atlas.rect(mapdata["bbox"])
    floor0,floor1=mapdata["floors"]
    if not -16<=floor0<=floor1<=32:fail("Invalid Atlas floor range")
    if type(grid_size) is not int or not 1<=grid_size<=200:
        fail("Grid size must be 1..200 cells")
    # Index only actual room rectangles, not building bounding boxes.
    index=defaultdict(list)
    building={}
    room_hits=Counter()
    for b in mapdata["buildings"]:
        ident=b["id"]
        if ident in building:fail("Duplicate atlas building")
        building[ident]={"building_id":ident,"bbox":b["bbox"],
            "rooms":len(set(r["id"]for r in b["rooms"])),
            "room_rectangles":len(b["rooms"]),"indoor_tiles_by_floor":{},
            "observed":0,"by_type":Counter()}
        per_floor=defaultdict(list)
        for r in b["rooms"]:
            coords=atlas.clip(r["bbox"],bbox)
            if coords is None:continue
            level=r["z"]
            per_floor[level].append(coords)
            ix0,iy0=math.floor(coords[0]/grid_size),math.floor(coords[1]/grid_size)
            ix1,iy1=math.floor((coords[2]-1)/grid_size),math.floor((coords[3]-1)/grid_size)
            for ix in range(ix0,ix1+1):
                for iy in range(iy0,iy1+1):
                    index[(level,ix,iy)].append((ident,r["id"],coords))
        for z,rectangles in per_floor.items():
            building[ident]["indoor_tiles_by_floor"][str(z)]=union_area(rectangles)
    grid=defaultdict(Counter)
    accepted=0;matched=0;unknown=0;ambiguous=0;outside=0;other_floor=0
    total_types=Counter()
    for z in zombies:
        x,y,level=z["x"],z["y"],math.floor(z["z"])
        if not all(finite(v) for v in(x,y,z["z"])) or not isinstance(z["type"],str):
            fail("Malformed zombie coordinates/type")
        if not bbox[0]<=x<bbox[2] or not bbox[1]<=y<bbox[3]:
            outside+=1;continue
        if not floor0<=level<=floor1:
            other_floor+=1;continue
        kind=z["type"];total_types[kind]+=1
        accepted+=1
        ix,iy=math.floor(x/grid_size),math.floor(y/grid_size)
        grid[(ix,iy)][kind]+=1
        candidates={(bid,rid) for bid,rid,r in index.get((level,ix,iy),())
                    if r[0]<=x<r[2] and r[1]<=y<r[3]}
        by_buildings=sorted({bid for bid,_ in candidates})
        if candidates:
            matched+=1
            if len(by_buildings)>1:ambiguous+=1
            # Choose one deterministic owner to avoid inflating counts.
            bid=by_buildings[0]
            building[bid]["observed"]+=1
            building[bid]["by_type"][kind]+=1
            same=sorted(rid for b,rid in candidates if b==bid)
            room_hits[(bid,same[0])]+=1
        if kind=="unknown":unknown+=1
    chunkset=set()
    if mapdata.get("coverage_mode")=="chunk_presence":
        for item in mapdata["loaded_chunks"]:
            if not isinstance(item,list) or len(item)!=2 or \
                    any(type(v) is not int for v in item):
                fail("Invalid loaded-chunk metadata")
            chunkset.add(tuple(item))
    elif mapdata.get("coverage_mode")!="unknown":
        fail("Unknown Atlas coverage semantics")
    # Pre-aggregate chunk area by grid cell. Never rescan every loaded
    # chunk for every cell (that would be O(chunks * grid_cells)).
    ix0,iy0=math.floor(bbox[0]/grid_size),math.floor(bbox[1]/grid_size)
    ix1,iy1=math.floor((bbox[2]-1)/grid_size),math.floor((bbox[3]-1)/grid_size)
    cell_count=(ix1-ix0+1)*(iy1-iy0+1)
    if cell_count>500000:
        fail("Grid would exceed 500000 output cells; choose a coarser --grid-size")
    loaded_by_grid=defaultdict(int)
    covered=0 if mapdata["coverage_mode"]=="chunk_presence" else None
    if covered is not None:
        for cx,cy in chunkset:
            chunk=atlas.clip(bbox,[cx*10,cy*10,cx*10+10,cy*10+10])
            if not chunk:continue
            covered+=(chunk[2]-chunk[0])*(chunk[3]-chunk[1])
            for gx in range(math.floor(chunk[0]/grid_size),math.floor((chunk[2]-1)/grid_size)+1):
                for gy in range(math.floor(chunk[1]/grid_size),math.floor((chunk[3]-1)/grid_size)+1):
                    block=[gx*grid_size,gy*grid_size,(gx+1)*grid_size,(gy+1)*grid_size]
                    part=atlas.clip(chunk,block)
                    if part:
                        loaded_by_grid[(gx,gy)]+=(part[2]-part[0])*(part[3]-part[1])
    cells=[]
    for ix in range(ix0,ix1+1):
        for iy in range(iy0,iy1+1):
            counts=grid.get((ix,iy),Counter())
            b=[ix*grid_size,iy*grid_size,(ix+1)*grid_size,(iy+1)*grid_size]
            region=atlas.clip(b,bbox)
            if not region:fail("Grid cell escaped Atlas bounds")
            area=(region[2]-region[0])*(region[3]-region[1])
            load=loaded_by_grid[(ix,iy)] if covered is not None else None
            observed=sum(counts.values())
            cells.append({"grid":[ix,iy],"bbox":region,"observed":observed,
                "by_type":dict(counts),"horizontal_tile_area":area,
                "loaded_chunk_tile_estimate":load,
                "per_1000_horizontal_tiles":round(1000*observed/area,3),
                "per_1000_loaded_chunk_tiles_estimate":(
                    round(1000*observed/load,3) if load else None)})
    building_rows=[]
    for ident,b in sorted(building.items()):
        b["by_type"]=dict(b["by_type"])
        b["rooms_with_observed_zombies"]=sum(
            1 for (building_id,_),count in room_hits.items()
            if building_id==ident and count)
        building_rows.append(b)
    return {
        "schema":1,"world":mapdata["world"],"bbox":bbox,"floors":[floor0,floor1],
        "source":origin,
        "measure":"one loaded-zombie census frame, NOT persistent map population",
        "coverage":{
            "building_geometry":"static metagrid only; excludes player construction",
            "loaded_chunk_area":"chunk presence is not loaded/walkable square coverage",
            "loaded_chunk_horizontal_tiles_estimate":covered,
            "region_horizontal_tiles":(bbox[2]-bbox[0])*(bbox[3]-bbox[1]),
            "z_levels_collapsed_in_grid":True
        },
        "counts":{"observed_in_bounds":accepted,
                  "observed_outside_bounds":outside,
                  "observed_other_levels":other_floor,
                  "observed_unknown_type":unknown,
                  "matched_to_room_footprint":matched,
                  "unmatched_or_outdoor":accepted-matched,
                  "ambiguous_building_matches":ambiguous,
                  "metadata_buildings":len(building),
                  "observed_occupied_buildings":sum(b["observed"]>0 for b in building.values()),
                  "by_type":dict(total_types)},
        "grid_size":grid_size,"grids":cells,"buildings":building_rows,
        "warnings":["Missing loaded zombies in a region does not prove the area is empty.",
          "Loaded chunk presence is only a horizontal coverage proxy, never a navigability measurement.",
          "Room rectangles identify metadata interior; they do not encode walls, doors, sightlines or accessibility.",
          "No encounter/pursuit rate or TLOU danger is inferred from a single census."]
    }

def geojson(analysis):
    features=[]
    for g in analysis["grids"]:
        features.append({"type":"Feature","geometry":atlas.polygon(g["bbox"]),
            "properties":{"kind":"infected_grid","observed":g["observed"],
                "by_type":g["by_type"],"per_1000_loaded_chunk_tiles_estimate":
                    g["per_1000_loaded_chunk_tiles_estimate"]}})
    return {"type":"FeatureCollection","world":analysis["world"],
            "pz_coordinate_system":"local game tiles, NOT WGS84",
            "features":features}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--atlas",required=True,help="Complete private Building Atlas JSON")
    sel=p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--roster",help="Private TLOU roster JSON; requires --source-world")
    sel.add_argument("--trace",help="Full ZombieDebug report JSON, not per-zombie analysis")
    p.add_argument("--source-world",help="Explicit world assertion for legacy roster without world ID")
    p.add_argument("--sample",default="last",help="Trace sample: first, last, or integer")
    p.add_argument("--grid-size",type=int,default=25)
    p.add_argument("--output",required=True)
    p.add_argument("--geojson",help="Optional NEW tile-coordinate GeoJSON-like grid")
    args=p.parse_args()
    try:
        mapdata=load_json(args.atlas)
        if not atlas.WORLD.fullmatch(mapdata.get("world","")):
            fail("Atlas has no valid source world")
        if args.trace:observed,origin=source_trace(load_json(args.trace),mapdata["world"],args.sample)
        else:observed,origin=source_roster(load_json(args.roster),mapdata["world"],args.source_world)
        report=summarize(mapdata,observed,origin,args.grid_size)
        atlas.safe_export(args.output,report)
        if args.geojson:atlas.safe_export(args.geojson,geojson(report))
        print("ANALYZED",report["world"],"observed",report["counts"]["observed_in_bounds"],
              "buildings",report["counts"]["metadata_buildings"],
              "output",args.output)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as ex:
        p.exit(2,"Building density: "+str(ex)+"\n")

if __name__=="__main__":main()
