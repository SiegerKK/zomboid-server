#!/usr/bin/env python3
"""Exact read-only TLOU registry and full loaded-zombie census, on demand.

The census visits every slot in the dedicated server's loaded zombie list
once. No sample cap, background metrics, client commands or forced chunk
loading; one O(N) scan may briefly occupy a server tick for a large N.
"""
from __future__ import annotations
import argparse
import json
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

def fail(message):
    raise ValueError(message)

def paths(world):
    folder=scanctl.lua_dir(world)
    return folder/REQUEST,folder/RESPONSE

def previous(world):
    path,_=paths(world)
    if not path.is_file():return None
    if path.is_symlink() or path.stat().st_size>120:
        fail("Unsafe previous TLOU census request")
    m=REQ.fullmatch(path.read_text("ascii"))
    if not m:fail("Malformed previous TLOU request; manual review required")
    return {"id":m[1],"operation":m[2]}

def read_result(world,request_id):
    _,path=paths(world)
    if not path.is_file():return {"status":"pending"}
    if path.is_symlink() or path.stat().st_size>MAX_BYTES:
        fail("Unsafe or oversized TLOU result")
    raw=path.read_text("utf-8")
    if not raw.endswith("\n"):return {"status":"pending"}
    lines=raw.splitlines()
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

def ready(world):
    if world!="story_test":fail("Only story_test")
    scanctl.assert_module_ready(world,"SiegerStoryTLOUDiagnostics")

def run(a):
    if a.world!="story_test":fail("Only story_test")
    scanctl.slot(a.world)
    print("PREVIEW read-only TLOU",a.command,"in",a.world)
    if a.command=="census":
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
    scanctl.atomic_request(req,f"v2\t{rid}\tstory_test\t{a.command}\n")
    print("QUEUED read-only",a.command,"request",rid)
    print("Poll: sudo pz story tlou result story_test")

def result(a):
    if a.world!="story_test":fail("Only story_test")
    scanctl.slot(a.world)
    prior=previous(a.world)
    if not prior:fail("No TLOU request queued")
    data=read_result(a.world,prior["id"])
    print(json.dumps(data,ensure_ascii=False,indent=2))
    if data["status"]=="error":
        fail("TLOU snapshot failed; review server logs")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    subs=p.add_subparsers(dest="command",required=True)
    for kind in ("registry","census"):
        q=subs.add_parser(kind)
        q.add_argument("world")
        q.add_argument("--yes",action="store_true")
        q.add_argument("--acknowledge-failed",action="store_true")
        q.set_defaults(handler=run)
    q=subs.add_parser("result")
    q.add_argument("world")
    q.set_defaults(handler=result)
    a=p.parse_args()
    try:a.handler(a)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as e:
        p.exit(2,"Story TLOU: "+str(e)+"\n")

if __name__=="__main__":main()
