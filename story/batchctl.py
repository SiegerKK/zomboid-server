#!/usr/bin/env python3
"""Reviewed, root-only batch editor for the selected running Story world.

One JSON file may describe vehicle, online-player, container and ground edits.
Dry-run by default; live requests are typed, not executable Lua. No item-type
allowlist or test-world-only gate. Partial game-world edits cannot be rolled
back automatically, so the server acknowledges them explicitly.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import secrets
from pathlib import Path
import scanctl

REQ="SiegerStoryBatchRequest.txt"
RES="SiegerStoryBatchResult.txt"
ITEM=re.compile(r"[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*\Z")
FLUID=re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
NAME=re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}\Z")
ID=re.compile(r"[0-9a-f]{32}\Z")
HASH=re.compile(r"[0-9a-f]{64}\Z")
MAX_INPUT=512*1024
MAX_ACTIONS=4096

def fail(message): raise ValueError(message)

def keys(value,required,optional=()):
    if not isinstance(value,dict) or set(value)!=(set(required)|set(value).intersection(optional)):
        fail("Missing or unexpected JSON keys")
    if not set(required).issubset(value):fail("Missing JSON action fields")

def ident(value,pattern=NAME):
    if not isinstance(value,str) or not pattern.fullmatch(value):
        fail("Invalid exact identifier")
    return value

def number(value,minimum,maximum,integral=False):
    if type(value) not in (float,int) or value!=value or not minimum<=value<=maximum:
        fail("Value outside supported game range")
    if integral and (type(value) is not int):fail("Expected integer value")
    return str(value) if integral else format(value,".8g")

def tile(value):
    if not isinstance(value,list) or len(value)!=3:fail("Tile must be [x,y,z]")
    return [number(value[0],0,200000,True),number(value[1],0,200000,True),
            number(value[2],-2,32,True)]

def row(*parts):
    if len(parts)!=12 or not all(isinstance(v,str) and v and
            not any(c in v for c in "\t\r\n") for v in parts):
        fail("Malformed action row")
    content="\t".join(parts)
    if len(content)>400:fail("Action row too long")
    return content

def compile_plan(doc,world):
    keys(doc,{"schema","world","actions"})
    if doc["schema"]!=1 or doc["world"]!=world:fail("Plan world/schema mismatch")
    groups=doc["actions"]
    if not isinstance(groups,list) or not groups:fail("Plan needs at least one group")
    result=[]
    for group in groups:
        if not isinstance(group,dict):fail("Invalid target group")
        kind=group.get("target")
        if kind=="vehicle":
            keys(group,{"target","id","script","at","changes"})
            target=number(group["id"],1,2147483647,True)
            script=ident(group["script"],ITEM)
            coords=tile(group["at"]);selector="-"
        elif kind=="player":
            keys(group,{"target","username","changes"})
            target=ident(group["username"],scanctl.USERNAME)
            script="-";coords=["-"]*3;selector="-"
        elif kind=="container":
            keys(group,{"target","at","object_index","container_index",
                        "container_type","changes"},("source",))
            target=number(group["object_index"],0,2147483647,True)
            script=ident(group["container_type"])
            coords=tile(group["at"])
            location=group.get("source","square")
            if location not in ("square","static"):fail("Invalid container collection")
            selector=number(group["container_index"],0,2147483647,True)+(
                "q" if location=="square" else "s")
        elif kind=="corpse":
            keys(group,{"target","at","static_index","changes"})
            target=number(group["static_index"],0,2147483647,True)
            script="IsoDeadBody";coords=tile(group["at"]);selector="-"
        elif kind=="ground":
            keys(group,{"target","at","changes"})
            target=script=selector="-";coords=tile(group["at"])
        else:fail("Unsupported target kind")
        changes=group["changes"]
        if not isinstance(changes,list) or not changes:fail("Empty changes")
        for change in changes:
            if not isinstance(change,dict):fail("Invalid change")
            op=change.get("op")
            key=extra=expected="-"
            value="0"
            selected=selector
            if kind=="corpse":
                keys(change,{"op"})
                if op!="remove" or len(changes)!=1:
                    fail("Corpse target requires exactly one remove operation")
                value="1"
            elif op in ("condition","fuel","battery"):
                if kind!="vehicle":fail("Vehicle state requires exact vehicle")
                keys(change,{"op","expect","value"},("part",))
                selected=ident(change.get("part",{"condition":"Engine",
                                  "fuel":"GasTank","battery":"Battery"}[op]))
                upper=1 if op=="battery" else (100 if op=="condition" else 1000000)
                is_integer=op=="condition"
                value=number(change["value"],0,upper,is_integer)
                expected=number(change["expect"],0,upper,is_integer)
            elif op=="heal":
                keys(change,{"op"})
                if kind!="player":fail("Heal only targets player")
            elif op=="stat":
                keys(change,{"op","name","value"})
                if kind!="player" or change["name"] not in (
                    "hunger","thirst","fatigue","stress"):
                    fail("Unsupported player stat")
                key=change["name"]
                value=number(change["value"],0,1)
            elif op in ("add","remove"):
                required={"op","item","count"}|({"part"} if kind=="vehicle" else set())
                optional={"offset"} if kind=="ground" and op=="add" else (
                    {"world_index"} if kind=="ground" and op=="remove" else (
                    {"fluid","amount_l"} if kind=="container" and op=="add" else set()))
                keys(change,required,optional)
                key=ident(change["item"],ITEM)
                value=number(change["count"],1,2147483647,True)
                if kind=="vehicle":selected=ident(change["part"])
                if kind=="container" and op=="add":
                    has_fluid="fluid" in change
                    if has_fluid!=("amount_l" in change):
                        fail("Filled item needs fluid and amount_l together")
                    if has_fluid:
                        expected=ident(change["fluid"],FLUID)
                        extra=number(change["amount_l"],0.01,1000)
                if kind=="ground" and op=="add":
                    offset=change.get("offset",[0.5,0.5,0])
                    if not isinstance(offset,list) or len(offset)!=3:
                        fail("Ground offset must have three components")
                    extra=",".join(number(v,0,1) for v in offset)
                elif kind=="ground" and "world_index" in change:
                    selected=number(change["world_index"],0,2147483647,True)
                    if change["count"]!=1:fail("Indexed ground removal requires count=1")
            else:fail("Unsupported batch operation")
            result.append(row(kind,target,script,*coords,selected,op,key,
                              value,expected,extra))
            if len(result)>MAX_ACTIONS:fail("Batch exceeds transport action count")
    return result

def paths(world):
    base=scanctl.lua_dir(world)
    return base/REQ,base/RES

def previous(world):
    req,_=paths(world)
    if not req.is_file():return None
    if req.is_symlink() or req.stat().st_size>MAX_INPUT*2:
        fail("Unsafe prior batch request")
    head=req.open(encoding="ascii").readline().strip().split("\t")
    if len(head)!=5 or head[0]!="v1" or not ID.fullmatch(head[1]) or \
            head[2]!=world or not HASH.fullmatch(head[3]) or \
            not head[4].isdigit():fail("Malformed previous batch")
    return {"id":head[1],"hash":head[3],"count":int(head[4])}

def receipt(world,wanted):
    _,res=paths(world)
    if not res.is_file():return {"status":"pending"}
    if res.is_symlink() or res.stat().st_size>512:fail("Unsafe batch receipt")
    raw=res.read_text("ascii")
    if not raw.endswith("\n"):return {"status":"pending"}
    cells=raw.rstrip("\n").split("\t")
    if len(cells)!=8 or cells[0]!="v1" or not ID.fullmatch(cells[1]) or \
            cells[2]!=world or not HASH.fullmatch(cells[3]) or \
            cells[4] not in ("complete","error") or not cells[5].isdigit() \
            or not cells[6].isdigit() or not NAME.fullmatch(cells[7]):
        fail("Invalid batch receipt")
    if cells[1]!=wanted["id"]:return {"status":"pending"}
    if cells[3]!=wanted["hash"] or int(cells[6])!=wanted["count"] or \
            int(cells[5])>int(cells[6]):fail("Receipt does not match request")
    return {"status":cells[4],"applied":int(cells[5]),"total":int(cells[6]),
            "request_id":cells[1],"sha256":cells[3],"reason":cells[7]}

def load(path,world):
    source=Path(path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_INPUT:
        fail("Missing/unsafe plan JSON")
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:fail("Duplicate JSON key: "+k)
            result[k]=v
        return result
    return compile_plan(json.loads(source.read_text("utf-8"),
                                   object_pairs_hook=unique),world)

def execute(args):
    rows=load(args.file,args.world)
    data="\n".join(rows)+"\n"
    digest=hashlib.sha256(data.encode("ascii")).hexdigest()
    print(json.dumps({"world":args.world,"actions":len(rows),
        "sha256":digest,"commands":rows},indent=2))
    if not args.yes:
        print("PREVIEW ONLY: no world modification")
        return
    scanctl.assert_module_ready(args.world,"SiegerStoryBatch")
    old=previous(args.world)
    if old:
        result=receipt(args.world,old)
        if result["status"]=="pending":fail("Prior batch pending")
        if result["status"]=="error" and not args.acknowledge_failed:
            fail("Prior batch may have partially applied; review before retry")
    rid=secrets.token_hex(16)
    packet=f"v1\t{rid}\t{args.world}\t{digest}\t{len(rows)}\n"+data
    if len(packet)>MAX_INPUT*2:fail("Packet exceeds private file transport")
    req,_=paths(args.world)
    scanctl.atomic_request(req,packet)
    print("QUEUED",rid,"(not a confirmed game change)")
    print("Poll: sudo pz story batch status",args.world)

def status(args):
    old=previous(args.world)
    if not old:fail("No batch queued")
    result=receipt(args.world,old)
    print(json.dumps(result,indent=2))
    if result["status"]=="error":fail("Partial/failed batch; inspect world before retry")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    for command in ("preview","apply"):
        x=sub.add_parser(command)
        x.add_argument("world");x.add_argument("--file",required=True)
        if command=="apply":
            x.add_argument("--yes",action="store_true")
        else:
            x.set_defaults(yes=False)
        x.add_argument("--acknowledge-failed",action="store_true")
        x.set_defaults(handler=execute)
    x=sub.add_parser("status");x.add_argument("world");x.set_defaults(handler=status)
    args=p.parse_args()
    try:
        if args.command=="apply" and not args.yes:
            fail("--yes required for batch apply")
        args.handler(args)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as exc:
        p.exit(2,"Story batch: "+str(exc)+"\n")

if __name__=="__main__":main()
