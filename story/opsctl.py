#!/usr/bin/env python3
"""Root-only bounded read-only snapshots of online players and nearby danger.

The game server handles requests on its OnTick event; this never calls RCON or
mutates the world. The operator reads a matching terminal ACK separately.
"""
from __future__ import annotations
import argparse
import json
import re
import secrets
from pathlib import Path

import scanctl

REQUEST="SiegerStoryOpsRequest.txt"
RESPONSE="SiegerStoryOpsResult.txt"
ID=re.compile(r"[0-9a-f]{32}\Z")
USER=scanctl.USERNAME
REQUEST_PATTERN=re.compile(
    r"v1\t([0-9a-f]{32})\tstory_test\t(players|nearby)\t"
    r"([A-Za-z0-9_][A-Za-z0-9_.-]{0,30}|-)\t([0-9]{1,2})\n?\Z")
COORD=re.compile(r"-?[0-9]{1,6}\.[0-9]\Z")
INT=re.compile(r"0|[1-9][0-9]{0,6}\Z")
DECIMAL=re.compile(r"0|[1-9][0-9]{0,5}\.[0-9]\Z")

def fail(message):
    raise ValueError(message)

def paths(world: str):
    base=scanctl.lua_dir(world)
    return base/REQUEST,base/RESPONSE

def request(world: str):
    path,_=paths(world)
    if not path.is_file():
        return None
    if path.is_symlink() or path.stat().st_size>200:
        fail("Unsafe previous ops request")
    match=REQUEST_PATTERN.fullmatch(path.read_text("ascii"))
    if not match:fail("Invalid previous ops request; manual inspection required")
    return {"id":match[1],"operation":match[2],"player":match[3],
            "radius":int(match[4])}

def result(world: str, wanted_id: str):
    _,file=paths(world)
    if not file.is_file():
        return {"status":"pending"}
    if file.is_symlink() or file.stat().st_size>16384:
        fail("Unsafe or oversized ops result")
    raw=file.read_text("utf-8")
    if not raw.endswith("\n"):
        return {"status":"pending"}
    lines=raw.splitlines()
    if len(lines)<2 or len(lines)>67:
        fail("Unexpected snapshot row count")
    header=lines[0].split("\t")
    if len(header)!=7 or header[0]!="v1" or not ID.fullmatch(header[1]) or \
            header[2]!="story_test" or header[3] not in ("players","nearby") or \
            header[4] not in ("complete","error") or \
            header[5] not in ("server_snapshot","review_server_logs") or \
            not INT.fullmatch(header[6]) or lines[-1]!="end":
        fail("Malformed ops result header/footer")
    if header[1]!=wanted_id:
        return {"status":"pending"}
    count=int(header[6])
    if count!=len(lines)-2 or count>64:
        fail("Inconsistent snapshot count")
    if header[4]=="error" and count:
        fail("Failed snapshot may not contain data rows")
    if header[3]=="nearby" and header[4]=="complete" and count!=1:
        fail("A successful nearby snapshot needs exactly one row")
    rows=[]
    seen=set()
    for line in lines[1:-1]:
        row=line.split("\t")
        if header[3]=="players":
            if len(row)!=6 or row[0]!="player" or not USER.fullmatch(row[1]) \
                    or not all(COORD.fullmatch(n) for n in row[2:5]) \
                    or (row[5]!="-" and (not INT.fullmatch(row[5]) or int(row[5])<1)):
                fail("Invalid online player record")
            if row[1] in seen:fail("Duplicate player in census")
            seen.add(row[1])
            rows.append({"username":row[1],"x":float(row[2]),"y":float(row[3]),
                         "z":float(row[4]),
                         "vehicle_id":None if row[5]=="-" else int(row[5])})
        else:
            if len(row)!=9 or row[0]!="nearby" or not USER.fullmatch(row[1]) \
                    or not all(INT.fullmatch(n) for n in [row[2],row[3],
                        row[5],row[6],row[7],row[8]]) \
                    or (row[4]!="-" and not DECIMAL.fullmatch(row[4])):
                fail("Invalid nearby summary")
            if not 1<=int(row[2])<=20 or int(row[7])>int(row[8]):
                fail("Invalid nearby radius/coverage")
            rows.append({"username":row[1],"radius":int(row[2]),
                         "loaded_zombies":int(row[3]),
                         "nearest_zombie_tiles":None if row[4]=="-" else float(row[4]),
                         "loaded_vehicles":int(row[5]),
                         "other_online_players":int(row[6]),
                         "loaded_tiles":int(row[7]),"survey_tiles":int(row[8])})
    return {"status":header[4],"request_id":header[1],"operation":header[3],
            "reason":header[5],"data":rows,
            "scope":"loaded_entities_and_current_online_players_only"}

def ready(world):
    if world!="story_test":fail("Only story_test is authorized")
    scanctl.assert_ready(world)
    path="/pzomboid-server/media/lua/server/SiegerStoryOps.lua"
    expected=(scanctl.REPO/"story/runtime/SiegerStoryOps.lua").resolve()
    if scanctl.docker_mounts().get(path)!=expected:
        fail("Story Ops runtime is not mounted; controlled deployment required")

def queue(args):
    if args.world!="story_test":fail("Only story_test is supported")
    scanctl.slot(args.world)
    kind=args.operation
    user="-"
    radius=0
    if kind=="nearby":
        user=args.player
        radius=args.radius
        if not USER.fullmatch(user) or not 1<=radius<=20:
            fail("Exact player login and radius 1..20 required")
    print("PREVIEW read-only",kind,"world",args.world,
          "player",user,"radius",radius,"(loaded entities only)")
    if not args.yes:
        print("No request queued. Add --yes to request a snapshot.")
        return
    ready(args.world)
    prior=request(args.world)
    if prior:
        old=result(args.world,prior["id"])
        if old["status"]=="pending":
            fail("Prior snapshot pending; poll result before another request")
        if old["status"]=="error" and not args.acknowledge_failed:
            fail("Prior server snapshot failed; inspect logs and pass --acknowledge-failed")
    rid=secrets.token_hex(16)
    body=f"v1\t{rid}\tstory_test\t{kind}\t{user}\t{radius}\n"
    req,_=paths(args.world)
    scanctl.atomic_request(req,body)
    print("Read-only snapshot queued:",rid)
    print("Poll: sudo pz story ops result story_test")

def show(args):
    if args.world!="story_test":fail("Only story_test is supported")
    scanctl.slot(args.world)
    prior=request(args.world)
    if not prior:fail("No prior ops snapshot request")
    data=result(args.world,prior["id"])
    print(json.dumps(data,ensure_ascii=False,indent=2))
    if data["status"]=="error":
        fail("Game rejected the census. Inspect private logs before retry")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("players","nearby"):
        cmd=sub.add_parser(name)
        cmd.add_argument("world")
        if name=="nearby":
            cmd.add_argument("--player",required=True)
            cmd.add_argument("--radius",required=True,type=int)
        cmd.add_argument("--yes",action="store_true")
        cmd.add_argument("--acknowledge-failed",action="store_true")
        cmd.set_defaults(operation=name,handler=queue)
    cmd=sub.add_parser("result")
    cmd.add_argument("world")
    cmd.set_defaults(handler=show)
    args=parser.parse_args()
    try:args.handler(args)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as e:
        parser.exit(2,"Story ops: "+str(e)+"\n")

if __name__=="__main__":
    main()
