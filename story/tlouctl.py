#!/usr/bin/env python3
"""Exact read-only TLOU registry and full loaded-zombie census, on demand.

The census visits every slot in the dedicated server's loaded zombie list
once. No sample cap, background metrics, client commands or forced chunk
loading; one O(N) scan may briefly occupy a server tick for a large N.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import re
import secrets
import scanctl

REQUEST="SiegerStoryTLOURequest.txt"
RESPONSE="SiegerStoryTLOUResult.txt"
TYPES=("TLOU_Runner","TLOU_Stalker","TLOU_Clicker","TLOU_Bloater")
SETTINGS=("VanillaSpawn","RunnerSpawnWeight","StalkerSpawnWeight",
    "ClickerSpawnWeight","BloaterSpawn","HideIndoors","OnlyUnexplored","WanderAtNight")
REQ=re.compile(r"v2\t([0-9a-f]{32})\tstory_test\t(registry|census)\n?\Z")
IDENT=re.compile(r"[0-9a-f]{32}\Z")
INTEGER=re.compile(r"[0-9]+\Z")
SCALAR=re.compile(r"-|true|false|not_registered|[0-9]{1,12}(?:\.[0-9]{1,8})?\Z")
DECIMAL=re.compile(r"-|[0-9]{1,12}(?:\.[0-9]{1,8})?\Z")
MAX_BYTES=8192
ROSTER_MAX_BYTES=32*1024*1024
USER=re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,39}\Z")
ROSTER_REQ=re.compile(r"v3\t([0-9a-f]{32})\tstory_test\troster\t([A-Za-z0-9_][A-Za-z0-9_.-]{0,39})\n?\Z")

def fail(message):
    raise ValueError(message)

def paths(world):
    folder=scanctl.lua_dir(world)
    return folder/REQUEST,folder/RESPONSE

def previous(world):
    path,_=paths(world)
    if not path.is_file():return None
    if path.is_symlink() or path.stat().st_size>220:
        fail("Unsafe previous TLOU census request")
    raw=path.read_text("ascii")
    roster=ROSTER_REQ.fullmatch(raw)
    if roster:return {"id":roster[1],"operation":"roster","player":roster[2]}
    m=REQ.fullmatch(raw)
    if not m:fail("Malformed previous TLOU request; manual review required")
    return {"id":m[1],"operation":m[2]}

def read_result(world,request_id):
    _,path=paths(world)
    if not path.is_file():return {"status":"pending"}
    if path.is_symlink() or path.stat().st_size>ROSTER_MAX_BYTES:
        fail("Unsafe or oversized TLOU result")
    raw=path.read_text("utf-8")
    if not raw.endswith("\n"):return {"status":"pending"}
    lines=raw.splitlines()
    if lines and lines[0].startswith("v3\t"):
        return read_roster(lines,world,request_id)
    if len(raw.encode("utf-8"))>MAX_BYTES:fail("Oversized legacy TLOU response")
    if len(lines)<2 or len(lines)>22 or lines[-1]!="end":
        fail("Invalid TLOU response envelope")
    h=lines[0].split("\t")
    if len(h)!=7 or h[0]!="v2" or not IDENT.fullmatch(h[1]) or \
            h[2]!="story_test" or h[3] not in ("registry","census") or \
            h[4] not in ("complete","error") or \
            h[5] not in ("server_registry","complete_loaded_census","review_server_logs") or \
            not INTEGER.fullmatch(h[6]):
        fail("Invalid TLOU response header")
    if h[1]!=request_id:return {"status":"pending"}
    if not previous(world) or previous(world)["operation"]!=h[3]:
        fail("Response operation differs from exact request")
    count=int(h[6])
    if count!=len(lines)-2 or (h[4]=="error" and count!=0) or \
            (h[4]=="complete" and count!=(13 if h[3]=="registry" else 20)):
        fail("TLOU snapshot row count mismatch")
    if h[4]=="complete" and h[5]!=("server_registry" if h[3]=="registry"
                                                    else "complete_loaded_census"):
        fail("Unexpected success reason")
    result={"status":h[4],"operation":h[3],"request_id":h[1],
        "reason":h[5],"framework":None,"registry":{},"sandbox":{},
        "census":None,"by_type":{},
        "scope":"currently_loaded_server_zombie_list_only"}
    for line in lines[1:-1]:
        row=line.split("\t")
        if row[0]=="framework":
            if len(row)!=3 or result["framework"] is not None or \
                    row[1] not in ("available","unavailable") or row[2] not in ("yes","no"):
                fail("Invalid Forge availability")
            result["framework"]={"registry":row[1],"cached_type_data":row[2]}
        elif row[0]=="ztype":
            if len(row)!=8 or row[1] not in TYPES or row[1] in result["registry"] or \
                    not all(SCALAR.fullmatch(v) for v in row[2:]):
                fail("Invalid Forge ZType")
            result["registry"][row[1]]={"weight":row[2],"hp":row[3],
                "walktype":row[4],"hearing":row[5],"sight":row[6],
                "on_tick_callbacks":row[7]}
        elif row[0]=="setting":
            if len(row)!=3 or row[1] not in SETTINGS or row[1] in result["sandbox"] \
                    or not SCALAR.fullmatch(row[2]):
                fail("Invalid TLOU sandbox setting")
            result["sandbox"][row[1]]=row[2]
        elif row[0]=="census":
            if h[3]!="census" or len(row)!=8 or result["census"] is not None \
                    or not all(INTEGER.fullmatch(x) for x in row[1:6]) \
                    or (row[6]!="-" and not INTEGER.fullmatch(row[6])) \
                    or row[7]!="loaded_list_only":
                fail("Invalid full census metadata")
            n,seen,skipped,bad,not_ready=map(int,row[1:6])
            if seen+skipped!=n or bad>seen or not_ready>seen:
                fail("Invalid full census totals")
            result["census"]={"list_slots":n,"inspected":seen,
                "null_slots":skipped,"classification_errors":bad,
                "uninitialized_outfit_ids":not_ready,
                "elapsed_ms":None if row[6]=="-" else int(row[6]),
                "coverage":"all_loaded_list_entries",
                "truncated":False}
        elif row[0]=="observed":
            if h[3]!="census" or len(row)!=9 or \
                    row[1] not in (*TYPES,"other","unknown") or \
                    row[1] in result["by_type"] or \
                    not all(INTEGER.fullmatch(x) for x in (row[2],row[3],
                        row[5],row[6],row[7],row[8])) or \
                    not DECIMAL.fullmatch(row[4]):
                fail("Invalid infected type metrics")
            n,health_count,moving,moving_known,target,target_known=(
                int(row[2]),int(row[3]),int(row[5]),int(row[6]),int(row[7]),int(row[8]))
            if health_count>n or moving>moving_known or moving_known>n \
                    or target>target_known or target_known>n:
                fail("Contradictory infected type metrics")
            result["by_type"][row[1]]={"count":n,
                "health_samples":health_count,
                "mean_health":None if row[4]=="-" else float(row[4]),
                "moving":moving,"moving_samples":moving_known,
                "targeting":target,"targeting_samples":target_known}
        else:
            fail("Unexpected TLOU result row")
    if result["status"]=="complete":
        if result["framework"] is None or \
                set(result["registry"])!=set(TYPES) or \
                set(result["sandbox"])!=set(SETTINGS):
            fail("Incomplete TLOU registry")
        if h[3]=="census":
            if result["census"] is None or \
                    set(result["by_type"])!=set((*TYPES,"other","unknown")) \
                    or sum(row["count"] for row in result["by_type"].values())!=result["census"]["inspected"]:
                fail("Full zombie census does not reconcile")
        elif result["census"] is not None or result["by_type"]:
            fail("Unexpected census data in registry-only operation")
    return result

def read_roster(lines,world,rid):
    if len(lines)<2 or lines[-1]!="end":fail("Incomplete roster envelope")
    h=lines[0].split("\t")
    if len(h)!=8 or h[0]!="v3" or not IDENT.fullmatch(h[1]) or h[2]!=world or h[3]!="roster" or h[4] not in ("complete","error") or not INTEGER.fullmatch(h[6]) or not USER.fullmatch(h[7]):
        fail("Invalid roster header")
    if h[1]!=rid:return {"status":"pending"}
    prior=previous(world)
    if not prior or prior.get("operation")!="roster" or prior.get("player")!=h[7]:fail("Roster target mismatch")
    if int(h[6])!=len(lines)-2:fail("Roster row count mismatch")
    if h[4]=="error":
        if h[5]!="review_server_logs" or h[6]!="0":fail("Malformed roster error")
        return {"status":"error","operation":"roster","request_id":rid,"reason":h[5]}
    if h[5]!="complete_loaded_roster" or len(lines)<4:fail("Invalid roster success")
    def numeric(s):
        if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]{1,6})?",s):fail("Invalid roster number")
        value=float(s)
        if not math.isfinite(value) or abs(value)>3000000:fail("Invalid roster coordinate")
        return value
    origin=lines[1].split("\t");cov=lines[2].split("\t")
    if len(origin)!=5 or origin[:2]!=["origin",h[7]]:fail("Invalid roster origin")
    px,py,pz=map(numeric,origin[2:])
    if len(cov)!=5 or cov[0]!="coverage" or cov[4]!="loaded_list_only" or not all(INTEGER.fullmatch(v) for v in cov[1:4]):fail("Invalid roster coverage")
    total,seen,skipped=map(int,cov[1:4])
    if seen+skipped!=total or seen!=len(lines)-4:fail("Roster coverage mismatch")
    zombies=[];slots=set()
    for line in lines[3:-1]:
        r=line.split("\t")
        if len(r)!=9 or r[0]!="zombie" or not INTEGER.fullmatch(r[1]) or (r[2]!="-" and not INTEGER.fullmatch(r[2])) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,96}",r[3]):fail("Invalid roster zombie")
        slot=int(r[1])
        if slot>=total or slot in slots:fail("Duplicate/out-of-range roster slot")
        slots.add(slot)
        x,y,z,distance,dz=map(numeric,r[4:])
        if distance<0 or abs(distance-math.hypot(x-px,y-py))>.00001 or abs(dz-(z-pz))>.00001:fail("Roster distance mismatch")
        online=None if r[2]=="-" else int(r[2])
        if online is not None and online>2147483647:fail("Invalid online ID")
        zombies.append({"snapshot_index":slot,"online_id":online,"type":r[3],"x":x,"y":y,"z":z,"distance_tiles_2d":distance,"floor_delta":dz})
    zombies.sort(key=lambda z:(z["distance_tiles_2d"],z["snapshot_index"]))
    return {"status":"complete","operation":"roster","request_id":rid,"player":h[7],
        "origin":{"x":px,"y":py,"z":pz},"coverage":{"list_slots":total,"inspected":seen,"null_slots":skipped,"truncated":False},
        "scope":"currently_loaded_server_zombie_list_only","identity":"snapshot_index is local to this snapshot; online_id is session-local and may be unavailable/reused",
        "type_source":"existing Forge cache only; unknown is not proof of vanilla type", "zombies":zombies}

def ready(world):
    if world!="story_test":fail("Only story_test")
    scanctl.assert_module_ready(world,"SiegerStoryTLOUDiagnostics")

def run(a):
    if a.world!="story_test":fail("Only story_test")
    scanctl.slot(a.world)
    if a.command=="roster" and not USER.fullmatch(getattr(a,"player","") or ""):
        fail("Exact player login required")
    print("PREVIEW read-only TLOU",a.command,"in",a.world)
    if a.command in ("census","roster"):
        print("Will count EVERY currently loaded server zombie in ONE pass.")
        print("A large population may temporarily lengthen one game tick.")
    if not a.yes:
        print("No request queued. Add --yes to run once.")
        return
    ready(a.world)
    prior=previous(a.world)
    if prior:
        result=read_result(a.world,prior["id"])
        if result["status"]=="pending":fail("Previous TLOU request still pending")
        if result["status"]=="error" and not a.acknowledge_failed:
            fail("Prior TLOU census failed; check logs and --acknowledge-failed")
    rid=secrets.token_hex(16)
    req,_=paths(a.world)
    payload=(f"v3\t{rid}\tstory_test\troster\t{a.player}\n" if a.command=="roster" else f"v2\t{rid}\tstory_test\t{a.command}\n")
    scanctl.atomic_request(req,payload)
    print("QUEUED read-only",a.command,"request",rid)
    print("Poll: sudo pz story tlou result story_test")

def result(a):
    if a.world!="story_test":fail("Only story_test")
    scanctl.slot(a.world)
    prior=previous(a.world)
    if not prior:fail("No TLOU request queued")
    data=read_result(a.world,prior["id"])
    body=json.dumps(data,ensure_ascii=False,indent=2)+"\n"
    output=getattr(a,"output",None)
    if output:
        if data["status"]!="complete":fail("Cannot export an incomplete snapshot")
        fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:stream.write(body)
    print(body,end="")
    if data["status"]=="error":
        fail("TLOU snapshot failed; review server logs")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    subs=p.add_subparsers(dest="command",required=True)
    for kind in ("registry","census","roster"):
        q=subs.add_parser(kind)
        q.add_argument("world")
        if kind=="roster":q.add_argument("--player",required=True)
        q.add_argument("--yes",action="store_true")
        q.add_argument("--acknowledge-failed",action="store_true")
        q.set_defaults(handler=run)
    q=subs.add_parser("result")
    q.add_argument("world")
    q.add_argument("--output",help="New private JSON file (0600); refuses existing paths")
    q.set_defaults(handler=result)
    a=p.parse_args()
    try:a.handler(a)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as e:
        p.exit(2,"Story TLOU: "+str(e)+"\n")

if __name__=="__main__":main()
