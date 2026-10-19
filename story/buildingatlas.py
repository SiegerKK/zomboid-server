#!/usr/bin/env python3
"""On-demand universal PZ building metadata atlas, independent of named towns.

All geometry is in PROJECT ZOMBOID tile coordinates (not WGS84). Buildings
and room rectangles are map metadata, NOT a census of player constructions.
Optional loaded-chunk presence is observational, not traversable/loaded tile
area. Nothing forces a chunk or zombie to load.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
import scanctl

REQUEST="SiegerAdminAtlasRequest.txt"
ACK="SiegerAdminAtlasResult.txt"
PREFIX="SiegerAdminAtlas-"
ID=re.compile(r"[0-9a-f]{32}\Z")
WORLD=re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
BID=re.compile(r"b[0-9]+\Z")
ROOM=re.compile(r"b[0-9]+_r[0-9]+\Z")
INT=re.compile(r"-?[0-9]+\Z")
HEX=re.compile(r"(?:[0-9a-f]{2})*\Z")
MAX_INPUT=192
MAX_OUTPUT=128*1024*1024
MAX_LINE=1600

def fail(msg):raise ValueError(msg)

def integer(v,minimum,maximum):
    if not INT.fullmatch(str(v)):fail("Expected decimal integer")
    num=int(v)
    if num<minimum or num>maximum:fail("Coordinate or count outside supported API range")
    return num

def bounds_arg(value):
    chunks=value.split(",")
    if len(chunks)!=4:fail("Use --bbox x0,y0,x1,y1 (exclusive upper bounds)")
    a,b,c,d=(integer(i,-100000,1000000) for i in chunks)
    if a>=c or b>=d:fail("Bounding box must have positive area")
    return (a,b,c,d)

def floor_arg(value):
    parts=value.split(":")
    if len(parts)!=2:fail("Use --floors MIN:MAX")
    lo,hi=(integer(v,-16,32) for v in parts)
    if lo>hi:fail("Floors must be ascending")
    return lo,hi

def rect(cells):
    if len(cells)!=4:fail("Incorrect rectangle column count")
    x0,y0,x1,y1=(integer(t,-100000,1000000) for t in cells)
    if x1<=x0 or y1<=y0:fail("Invalid rectangle")
    return [x0,y0,x1,y1]

def intersect(a,b):
    return a[0]<b[2] and a[2]>b[0] and a[1]<b[3] and a[3]>b[1]

def clip(a,b):
    x0=max(a[0],b[0]);y0=max(a[1],b[1])
    x1=min(a[2],b[2]);y1=min(a[3],b[3])
    return [x0,y0,x1,y1] if x0<x1 and y0<y1 else None

def decode(value):
    if value=="-":return None
    if not HEX.fullmatch(value):fail("Invalid hex metadata label")
    return bytes.fromhex(value).decode("utf-8")

def paths(world):
    folder=scanctl.lua_dir(world)
    return folder/REQUEST,folder/ACK

def request(world):
    req,_=paths(world)
    if not req.is_file():return None
    if req.is_symlink() or req.stat().st_size>MAX_INPUT:fail("Unsafe Atlas request")
    v=req.read_text("ascii").strip().split("\t")
    if len(v)!=12 or v[0]!="v1" or not ID.fullmatch(v[1]) or v[2]!=world or v[11]!="end":
        fail("Malformed previous Atlas request")
    bbox=rect(v[3:7])
    z0,z1=integer(v[7],-16,32),integer(v[8],-16,32)
    if z0>z1:fail("Atlas floors inverted")
    limit=integer(v[9],1,1000000)
    expiry=integer(v[10],1,9999999999999)
    return {"id":v[1],"world":world,"bbox":bbox,"floors":[z0,z1],
            "max_rows":limit,"expires_ms":expiry}

def receipt(world,meta):
    _,ack=paths(world)
    if not ack.is_file():return {"status":"pending"}
    if ack.is_symlink() or ack.stat().st_size>512:fail("Unsafe Atlas ACK")
    raw=ack.read_text("ascii")
    if not raw.endswith("\n"):return {"status":"pending"}
    v=raw.rstrip("\n").split("\t")
    if len(v)!=11 or v[0]!="v1" or not ID.fullmatch(v[1]) or v[2]!=world \
       or v[3] not in ("complete","error") or \
       not all(INT.fullmatch(n) for n in v[4:9]) or \
       v[9]!=PREFIX+v[1]+".txt" or v[10] not in ("meta_buildings","review_server_logs"):
        fail("Malformed Atlas ACK")
    if v[1]!=meta["id"]:return {"status":"pending"}
    return {"status":v[3],"request_id":v[1],"buildings":int(v[4]),
            "rooms":int(v[5]),"rectangles":int(v[6]),"loaded_chunks":int(v[7]),
            "rows":int(v[8]),"filename":v[9],"reason":v[10]}

def read_atlas(path,meta=None):
    """Verify EXACT footer/framing and every rectangle before exporting."""
    file=Path(path)
    if not file.is_file() or file.is_symlink() or file.stat().st_size>MAX_OUTPUT:
        fail("Unsafe/missing/oversized Atlas data")
    buildings={};rooms={};chunks=set();seen=0;header=None;footer=None
    with file.open("r",encoding="utf-8",newline="") as f:
        for line in f:
            if len(line)>MAX_LINE or not line.endswith("\n"):
                fail("Malformed/truncated Atlas row")
            fields=line.rstrip("\n").split("\t")
            if header is None:
                if len(fields)!=11 or fields[0]!="v1" or not ID.fullmatch(fields[1]) \
                        or not WORLD.fullmatch(fields[2]) or fields[9] not in ("chunk_presence","unknown"):
                    fail("Invalid Atlas header")
                bbox=rect(fields[3:7])
                floors=[integer(fields[7],-16,32),integer(fields[8],-16,32)]
                if floors[0]>floors[1]:fail("Atlas floors inverted")
                header={"schema":1,"id":fields[1],"world":fields[2],
                        "bbox":bbox,"floors":floors,"coverage_mode":fields[9],
                        "meta_buildings_scanned":integer(fields[10],0,2147483647),
                        "coordinate_system":"PZ tile coordinates; NOT geographic lon/lat"}
                if meta and (meta["id"]!=header["id"] or meta["world"]!=header["world"]
                        or meta["bbox"]!=bbox or meta["floors"]!=floors):
                    fail("Atlas does not match the exact queued request")
                continue
            if footer is not None:fail("Records after Atlas end")
            if fields[0]=="end":
                if len(fields)!=6 or not all(INT.fullmatch(n) for n in fields[1:]):
                    fail("Invalid Atlas footer")
                footer=[int(n) for n in fields[1:]]
                continue
            seen+=1
            if fields[0]=="b":
                if len(fields)!=7 or not BID.fullmatch(fields[1]) or fields[1] in buildings:
                    fail("Duplicate or invalid building ID")
                b=rect(fields[2:6])
                if not intersect(b,header["bbox"]):fail("Building outside query")
                buildings[fields[1]]={"id":fields[1],"bbox":b,
                    "map_id":decode(fields[6]),"rooms":[]}
            elif fields[0]=="r":
                if len(fields)!=9 or fields[1] not in buildings or not ROOM.fullmatch(fields[2]):
                    fail("Room references unknown building")
                z=integer(fields[3],-16,32)
                b=rect(fields[4:8])
                if not header["floors"][0]<=z<=header["floors"][1] or \
                        not intersect(b,header["bbox"]):
                    fail("Room outside queried rectangle/floors")
                # Every room polygon must be within the associated building bbox.
                container=buildings[fields[1]]["bbox"]
                if not (container[0]<=b[0]<b[2]<=container[2] and
                        container[1]<=b[1]<b[3]<=container[3]):
                    fail("Room rectangle outside parent building")
                room={"id":fields[2],"z":z,"bbox":b,"name":decode(fields[8]) or ""}
                buildings[fields[1]]["rooms"].append(room)
                rooms[(fields[1],fields[2])]=True
            elif fields[0]=="c":
                if len(fields)!=3 or header["coverage_mode"]!="chunk_presence":
                    fail("Unexpected chunk coverage row")
                cx,cy=integer(fields[1],-100000,100000),integer(fields[2],-100000,100000)
                key=(cx,cy)
                if key in chunks or not intersect([cx*10,cy*10,cx*10+10,cy*10+10],header["bbox"]):
                    fail("Duplicate/out-of-range loaded chunk")
                chunks.add(key)
            else:fail("Unexpected Atlas record")
            if meta and seen>meta["max_rows"]:fail("Atlas exceeded requested records")
    if header is None or footer is None:fail("Atlas incomplete: missing header or footer")
    if footer!=[seen,len(buildings),len(rooms),
                sum(len(b["rooms"]) for b in buildings.values()),len(chunks)]:
        fail("Atlas footer counts do not reconcile")
    if len(buildings)>header["meta_buildings_scanned"]:fail("Impossible metagrid building count")
    header.update({"buildings":list(buildings.values()),
                   "loaded_chunks":[list(c) for c in sorted(chunks)],
                   "counts":{"buildings":len(buildings),"rooms":len(rooms),
                             "room_rectangles":footer[3],"loaded_chunks":len(chunks),
                             "rows":seen}})
    return header

def safe_export(path,body):
    target=Path(path)
    if target.is_symlink() or not target.parent.is_dir() or \
       target.resolve().is_relative_to(scanctl.REPO.resolve()):
        fail("Private export must be a NEW file outside source repository")
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(body,stream,ensure_ascii=False,indent=2,allow_nan=False)
            stream.write("\n")
    except BaseException:
        target.unlink(missing_ok=True)
        raise

def polygon(box):
    x0,y0,x1,y1=box
    return {"type":"Polygon","coordinates":[
        [[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]]]}

def geojson(atlas):
    features=[]
    for b in atlas["buildings"]:
        features.append({"type":"Feature","geometry":polygon(b["bbox"]),
            "properties":{"kind":"building_bbox","building_id":b["id"],
                          "map_id":b["map_id"],"accuracy":"bounding_box_only"}})
        for room in b["rooms"]:
            features.append({"type":"Feature","geometry":polygon(room["bbox"]),
                "properties":{"kind":"room_rect","building_id":b["id"],
                    "room_id":room["id"],"name":room["name"],"z":room["z"],
                    "accuracy":"metagrid_room_rectangle"}})
    return {"type":"FeatureCollection",
            "pz_coordinate_system":"local tiles (NOT WGS84)",
            "world":atlas["world"],"bbox":atlas["bbox"],"features":features}

def capture(args):
    world=args.world
    scanctl.slot(world)
    if not WORLD.fullmatch(world):fail("Invalid world name")
    bbox=bounds_arg(args.bbox)
    zmin,zmax=floor_arg(args.floors)
    limit=integer(args.max_rows,1,1000000)
    print(json.dumps({"world":world,"bbox":bbox,"floors":[zmin,zmax],
        "max_records":limit,"source":"all map metadata buildings, not loaded square objects",
        "chunk_presence":"approximate coverage, not navigable tiles"}))
    if not args.yes:
        print("PREVIEW: No request queued. Use --yes to capture once.")
        return
    scanctl.assert_module_ready(world,"SiegerAdminBuildingAtlas")
    old=request(world)
    if old:
        state=receipt(world,old)
        if state["status"]=="pending":fail("Previous Atlas request pending")
        if state["status"]=="error" and not args.acknowledge_failed:
            fail("Last Atlas collection failed; review server logs first")
    rid=secrets.token_hex(16)
    expires=int(time.time()*1000)+30000
    packet="\t".join(["v1",rid,world,*(str(v) for v in bbox),
            str(zmin),str(zmax),str(limit),str(expires),"end"])+"\n"
    req,_=paths(world)
    scanctl.atomic_request(req,packet)
    print("QUEUED",rid,"; check: sudo pz story atlas status",world)

def status(args):
    old=request(args.world)
    if not old:fail("No Atlas request")
    a=receipt(args.world,old)
    print(json.dumps(a,indent=2))
    return a

def export(args):
    old=request(args.world)
    if not old:fail("No Atlas request")
    a=receipt(args.world,old)
    if a["status"]!="complete":fail("Atlas not complete; no export")
    file=scanctl.lua_dir(args.world)/a["filename"]
    data=read_atlas(file,old)
    if (a["buildings"],a["rooms"],a["rectangles"],a["loaded_chunks"],a["rows"])!=(
        data["counts"]["buildings"],data["counts"]["rooms"],
        data["counts"]["room_rectangles"],data["counts"]["loaded_chunks"],
        data["counts"]["rows"]):
        fail("Atlas receipt and file disagree")
    safe_export(args.output,data)
    if args.geojson:safe_export(args.geojson,geojson(data))
    print("EXPORTED private Atlas",args.output,"buildings",data["counts"]["buildings"])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    x=sub.add_parser("capture")
    x.add_argument("world")
    x.add_argument("--bbox",required=True,help="x0,y0,x1,y1; upper bounds exclusive")
    x.add_argument("--floors",default="0:4",help="inclusive floor levels min:max")
    x.add_argument("--max-rows",type=int,default=250000)
    x.add_argument("--yes",action="store_true")
    x.add_argument("--acknowledge-failed",action="store_true")
    x.set_defaults(handler=capture)
    x=sub.add_parser("status");x.add_argument("world");x.set_defaults(handler=status)
    x=sub.add_parser("export");x.add_argument("world")
    x.add_argument("--output",required=True)
    x.add_argument("--geojson",help="Optional NEW GeoJSON-like file in PZ tiles")
    x.set_defaults(handler=export)
    x=p.parse_args()
    try:x.handler(x)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as e:
        p.exit(2,"Building atlas: "+str(e)+"\n")

if __name__=="__main__":main()
