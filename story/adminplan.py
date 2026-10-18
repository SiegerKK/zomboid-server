#!/usr/bin/env python3
"""Root-only, preview-first batch editing of the ACTIVE PZ world.

One JSON plan can edit vehicles, players, world containers and ground objects.
No item allowlist, test-world gate, 5-item limit, or forced unoccupied vehicle.
Requests are literal typed lines, never executable Lua. Server preflights the
entire plan before writing anything. Once mutation begins it is NOT atomic:
a crash/failed sync can leave a partial write and must never be auto-replayed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
import scanctl

REQUEST="SiegerStoryAdminRequest.txt"
RESULT="SiegerStoryAdminResult.txt"
TYPE=re.compile(r"[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*\Z")
IDENT=re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}\Z")
DIGEST=re.compile(r"[0-9a-f]{64}\Z")
RID=re.compile(r"[0-9a-f]{32}\Z")
OPS={"condition","fuel","battery","add","remove","heal","stat"}
FIELDS={"schema","world","actions"}
# Resource/format constraints, NOT arbitrary item-type or per-operation caps.
MAX_PLAN_BYTES=512*1024
MAX_LINES=4096
MAX_PACKET_BYTES=1024*1024
MAX_COUNT=2147483647

def fail(message): raise ValueError(message)

def exact_keys(obj,required,optional=frozenset()):
    if not isinstance(obj,dict) or not required<=obj.keys() or obj.keys()-(required|optional):
        fail("Unrecognized/missing manifest keys: expected "+", ".join(sorted(required|optional)))

def number(value, minimum, maximum):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or \
            not minimum<=value<=maximum or value!=value:
        fail("Numeric value outside engine bounds")
    return format(value,".9g")

def integer(value,minimum=0,maximum=MAX_COUNT):
    if type(value) is not int or not minimum<=value<=maximum:
        fail("Expected integral value in supported engine range")
    return str(value)

def label(value,pattern=IDENT):
    if not isinstance(value,str) or not pattern.fullmatch(value):fail("Invalid identifier")
    return value

def coord(value):
    if not isinstance(value,list) or len(value)!=3:
        fail("Required exact [x,y,z] tile coordinates")
    return [integer(value[0],0,200000),integer(value[1],0,200000),
            integer(value[2],0,32)]

def pos(value):
    if not isinstance(value,list) or len(value)!=3:fail("Required [dx,dy,dz] on tile")
    return ",".join(number(x,0,1) for x in value)

def format_row(parts):
    if len(parts)!=13 or any(not isinstance(v,str) or not v or \
            "\t" in v or "\n" in v or "\r" in v for v in parts):
        fail("Invalid typed admin plan row")
    row="\t".join(parts)
    if len(row)>350:fail("Admin action row exceeds format budget")
    return row

def compile_plan(value,world):
    exact_keys(value,{"schema","world","actions"})
    if value["schema"]!=1 or value["world"]!=world:
        fail("JSON schema or target world mismatch")
    groups=value["actions"]
    if not isinstance(groups,list) or not groups:fail("At least one edit group required")
    rows=[]
    for group in groups:
        if not isinstance(group,dict):fail("Invalid edit group")
        kind=group.get("target")
        if kind=="vehicle":
            exact_keys(group,{"target","id","script","at","changes"})
            identity=integer(group["id"],1)
            script=label(group["script"],TYPE)
            xyz=coord(group["at"])
            selector="-"
        elif kind=="player":
            exact_keys(group,{"target","username","changes"})
            identity=label(group["username"],scanctl.USERNAME)
            script="-";xyz=["-"]*3;selector="-"
        elif kind=="container":
            exact_keys(group,{"target","at","object_index","container_index",
                              "container_type","changes"},{"source"})
            identity=integer(group["object_index"])
            script=label(group["container_type"])
            xyz=coord(group["at"])
            selector=integer(group["container_index"])
            if group.get("source","square") not in ("square","static"):
                fail("Unknown container source")
            # The object collection (square or static) is resolved by engine.
            selector=selector+("s" if group.get("source","square")=="static" else "q")
        elif kind=="ground":
            exact_keys(group,{"target","at","changes"})
            identity="-";script="-";xyz=coord(group["at"]);selector="-"
        else:fail("Unsupported edit target")
        changes=group["changes"]
        if not isinstance(changes,list) or not changes:fail("Empty batch edit group")
        for change in changes:
            if not isinstance(change,dict):fail("Invalid edit")
            op=change.get("op")
            if op in ("condition","fuel","battery"):
                if kind!="vehicle":fail("Part/charge edits require vehicle")
                exact_keys(change,{"op","value","expect"}, {"part"})
                part=label(change.get("part",{"condition":"Engine","fuel":"GasTank",
                                               "battery":"Battery"}[op]))
                if op=="battery":
                    amount=number(change["value"],0,1)
                    expect=number(change["expect"],0,1)
                else:
                    limit=100 if op=="condition" else 1000000
                    amount=number(change["value"],0,limit)
                    expect=number(change["expect"],0,limit)
                    if op=="condition":
                        integer(change["value"],0,100);integer(change["expect"],0,100)
                row=[ "a",kind,identity,script,*xyz,part,op,"-",amount,expect,"-" ]
            elif op=="heal":
                if kind!="player":fail("Heal requires player")
                exact_keys(change,{"op"})
                row=["a",kind,identity,script,*xyz,selector,op,"-","0","-","-"]
            elif op=="stat":
                if kind!="player":fail("Player stat requires player")
                exact_keys(change,{"op","name","value"})
                metric=change["name"]
                if metric not in ("hunger","thirst","fatigue","stress"):
                    fail("Unsupported stat: only stock Health/Stats properties")
                row=["a",kind,identity,script,*xyz,selector,op,metric,
                     number(change["value"],0,1),"-","-"]
            elif op in ("add","remove"):
                if kind not in ("vehicle","player","container","ground"):
                    fail("Invalid item target")
                optional={"offset"} if kind=="ground" and op=="add" else (
                    {"world_index"} if kind=="ground" and op=="remove" else set())
                required={"op","item","count"}
                if kind=="vehicle":required.add("part")
                exact_keys(change,required,optional)
                item=label(change["item"],TYPE)
                count=integer(change["count"],1)
                local_selector=label(change["part"]) if kind=="vehicle" else selector
                extra="-"
                if kind=="ground" and op=="add":
                    extra=pos(change.get("offset",[0.5,0.5,0]))
                if kind=="ground" and op=="remove" and "world_index" in change:
                    local_selector=integer(change["world_index"])
                    if change["count"]!=1:
                        fail("Indexed ground removal targets exactly one object")
                row=["a",kind,identity,script,*xyz,local_selector,op,item,count,"-",extra]
            else:fail("Unsupported edit operation")
            rows.append(format_row(row))
            if len(rows)>MAX_LINES:
                fail("Batch exceeds supported request-file transport size")
    return rows

def read_plan(path,world):
    file=Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size>MAX_PLAN_BYTES:
        fail("Missing, symlinked or oversized JSON plan")
    raw=file.read_text(encoding="utf-8")
    # reject duplicate JSON keys instead of silently overriding crucial IDs
    def unique(pairs):
        result={}
        for key,val in pairs:
            if key in result:fail("Duplicate JSON key: "+key)
            result[key]=val
        return result
    return compile_plan(json.loads(raw,object_pairs_hook=unique),world)

def paths(world):
    location=scanctl.lua_dir(world)
    return location/REQUEST,location/RESULT

def prior(world):
    req,_=paths(world)
    if not req.exists():return None
    if req.is_symlink() or req.stat().st_size>MAX_PACKET_BYTES:
        fail("Unsafe previous request file")
    with req.open(encoding="ascii") as f:
        parts=f.readline().rstrip("\n").split("\t")
    if len(parts)!=5 or parts[0]!="v2" or not RID.fullmatch(parts[1]) or \
            parts[2]!=world or not DIGEST.fullmatch(parts[3]) or \
            not parts[4].isdigit():
        fail("Previous request malformed: do not overwrite")
    return {"id":parts[1],"hash":parts[3],"count":int(parts[4])}

def response(world,current):
    _,res=paths(world)
    if not res.exists():return {"status":"pending"}
    if res.is_symlink() or res.stat().st_size>512:fail("Unsafe batch result")
    raw=res.read_text("ascii")
    if not raw.endswith("\n"):return {"status":"pending"}
    parts=raw.strip("\n").split("\t")
    if len(parts)!=8 or parts[0]!="v2" or not RID.fullmatch(parts[1]) or \
            parts[2]!=world or not DIGEST.fullmatch(parts[3]) or \
            parts[4] not in ("complete","error") or not parts[5].isdigit() \
            or not parts[6].isdigit() or not IDENT.fullmatch(parts[7]):
        fail("Invalid batch ACK")
    if parts[1]!=current["id"]:return {"status":"pending"}
    if parts[3]!=current["hash"] or int(parts[6])!=current["count"] or \
            int(parts[5])>current["count"]:
        fail("ACK not for the exact requested plan")
    return {"status":parts[4],"request_id":parts[1],"sha256":parts[3],
            "applied":int(parts[5]),"requested":int(parts[6]),"detail":parts[7],
            "caution":"Server ACK does not prove client replication or save persistence."}

def check_world(world):
    if not scanctl.WORLD.fullmatch(world):fail("Invalid world")
    # Works on any selected, running Story-enabled world, not only story_test.
    scanctl.assert_module_ready(world,"SiegerStoryAdmin")

def preview(args):
    rows=read_plan(args.file,args.world)
    payload="\n".join(rows)+"\n"
    digest=hashlib.sha256(payload.encode("ascii")).hexdigest()
    print(json.dumps({"world":args.world,"operations":len(rows),
        "sha256":digest,"rows":rows},ensure_ascii=False,indent=2))
    if not args.yes:
        print("PREVIEW ONLY: no world mutations, requests, or spawning.")
        return
    if os.geteuid()!=0:fail("Batch writes require root (sudo pz story admin-plan ...)")
    check_world(args.world)
    old=prior(args.world)
    if old:
        state=response(args.world,old)
        if state["status"]=="pending":fail("Previous request still pending")
        if state["status"]=="error" and not args.acknowledge_failed:
            fail("Previous batch failed/partly applied; manual review required")
    rid=secrets.token_hex(16)
    content=f"v2\t{rid}\t{args.world}\t{digest}\t{len(rows)}\n"+payload
    if len(content.encode("ascii"))>MAX_PACKET_BYTES:
        fail("Batch request exceeds safe transport file size")
    req,_=paths(args.world)
    scanctl.atomic_request(req,content)
    print("QUEUED batch",rid,"sha256",digest)
    print("Check: sudo pz story admin-plan status",args.world)
    print("One request; all actions are preflighted before write, but no rollback after partial failure.")

def status(args):
    old=prior(args.world)
    if not old:fail("No admin batch requested")
    data=response(args.world,old)
    print(json.dumps(data,ensure_ascii=False,indent=2))
    if data["status"]=="error":
        fail("Batch failed or partially applied; do not replay before inspecting game/server logs")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    for cmd in ("preview","apply"):
        x=sub.add_parser(cmd)
        x.add_argument("world");x.add_argument("--file",required=True)
        x.add_argument("--acknowledge-failed",action="store_true")
        x.set_defaults(handler=preview,yes=cmd=="apply")
        if cmd=="apply":
            x.add_argument("--yes",action="store_true",required=True)
    x=sub.add_parser("status");x.add_argument("world");x.set_defaults(handler=status)
    args=p.parse_args()
    try:
        if args.command=="apply" and not args.yes:
            fail("--yes required to queue a world mutation")
        args.handler(args)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as ex:
        p.exit(2,"Story admin batch: "+str(ex)+"\n")

if __name__=="__main__":
    main()
