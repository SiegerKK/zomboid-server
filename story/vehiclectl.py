#!/usr/bin/env python3
"""Explicit, root-only operations on one already-loaded story_test vehicle.

Dry-run by default. Operations are executed asynchronously by a server-owned
Lua handler; success requires inspecting its exact request result. Repeated
or ambiguous failed writes must be reviewed manually before proceeding.
"""
from __future__ import annotations
import argparse
import json
import re
import secrets
from pathlib import Path
import scanctl

REQUEST="SiegerStoryVehicleRequest.txt"
RESULT="SiegerStoryVehicleResult.txt"
ALLOWED_ITEMS={"Base.Bandage","Base.WaterBottle","Base.CigaretteSingle",
    "Base.Pen","Base.Pencil","Base.Lighter","Base.Paperclip",
    "Base.Notebook","Base.Hammer","Base.Screwdriver"}
OPERATIONS={"inspect","condition","fuel","battery","add","remove"}
IDENT=re.compile(r"[A-Za-z0-9_]{1,50}\Z")
SCRIPT=re.compile(r"Base\.[A-Za-z0-9_]{1,80}\Z")
WIRE=re.compile(r"v1\t([0-9a-f]{32})\tstory_test\t"
    r"(inspect|condition|fuel|battery|add|remove)\t"
    r"([0-9]{1,10})\t(Base\.[A-Za-z0-9_]{1,80})\t"
    r"([0-9]{1,6})\t([0-9]{1,6})\t([0-9]{1,2})\t"
    r"([A-Za-z0-9_\-]{1,50})\t([A-Za-z0-9_.\-]{1,80})\t"
    r"([0-9.]{1,12})\n?\Z")
ANSWER=re.compile(r"v1\t([0-9a-f]{32})\tstory_test\t"
    r"(inspect|condition|fuel|battery|add|remove)\t(complete|error)\t"
    r"([A-Za-z0-9_.:\-]{1,100})\t([A-Za-z0-9_.:\-]{1,100})\n?\Z")

def fail(reason):
    raise ValueError(reason)

def paths(world):
    base=scanctl.lua_dir(world)
    return base/REQUEST,base/RESULT

def prior_request(world):
    req,_=paths(world)
    if not req.exists():return None
    if req.is_symlink() or req.stat().st_size>400:fail("Unsafe prior vehicle request")
    m=WIRE.fullmatch(req.read_text("ascii"))
    if not m:fail("Malformed prior vehicle request: manual review required")
    return {"id":m[1],"operation":m[2]}

def response(world,rid):
    _,f=paths(world)
    if not f.exists():return {"status":"pending"}
    if f.is_symlink() or f.stat().st_size>400:fail("Unsafe vehicle response")
    m=ANSWER.fullmatch(f.read_text("ascii"))
    if not m:fail("Malformed vehicle result: manual review required")
    if m[1]!=rid:return {"status":"pending"}
    return {"request_id":m[1],"operation":m[2],"status":m[3],
            "reason":m[4],"detail":m[5]}

def ready(world):
    if world!="story_test":fail("Only story_test is authorized")
    scanctl.assert_module_ready(world,"SiegerStoryVehicleControl")

def run(a):
    if a.world!="story_test":fail("Only story_test")
    scanctl.slot(a.world)
    if not SCRIPT.fullmatch(a.script):fail("Exact Base.<script> required")
    if not 1<=a.id<=2147483647:fail("Invalid vehicle ID")
    if any(not 0<=v<=limit for v,limit in ((a.x,200000),(a.y,200000),(a.z,32))):
        fail("Exact scanned position required")
    key,old,new="-","-", "0"
    if a.operation=="condition":
        key=a.part
        if not 0<=a.expect<=100 or not 0<=a.value<=100:fail("Condition must be 0..100")
        old,new=str(a.expect),str(a.value)
    elif a.operation in ("fuel","battery"):
        key="GasTank" if a.operation=="fuel" else "Battery"
        limit=1000 if a.operation=="fuel" else 1
        if any(not 0<=v<=limit for v in (a.expect,a.value)):
            fail("Fluid/charge amount outside allowed range")
        old,new=str(a.expect),str(a.value)
    elif a.operation in ("add","remove"):
        key=a.part
        if a.item not in ALLOWED_ITEMS or not 1<=a.count<=5:
            fail("Only allowlisted item and count 1..5")
        old,new=a.item,str(a.count)
    if key!="-" and not IDENT.fullmatch(key):fail("Invalid part ID")
    payload=(f"v1\t{{id}}\tstory_test\t{a.operation}\t{a.id}\t{a.script}"
        f"\t{a.x}\t{a.y}\t{a.z}\t{key}\t{old}\t{new}\n")
    print("Vehicle operation preview:",a.operation,"id",a.id,a.script,
          "at",a.x,a.y,a.z,"part",key,"expected",old,"value",new)
    if not a.yes:
        print("READ-ONLY PREVIEW. Pass --yes to queue a server-side request.")
        return
    ready(a.world)
    prior=prior_request(a.world)
    if prior:
        result=response(a.world,prior["id"])
        if result["status"]=="pending":fail("Previous request pending; use status")
        if result["status"]=="error":
            fail("Previous failed/partial request: manual game-state review required")
    request_id=secrets.token_hex(16)
    req,_=paths(a.world)
    scanctl.atomic_request(req,payload.format(id=request_id))
    print("QUEUED request",request_id,"; poll: sudo pz story vehicle status story_test")
    print("A queued write is not confirmation of actual server/client synchronization.")

def status(a):
    scanctl.slot(a.world)
    if a.world!="story_test":fail("Only story_test")
    prior=prior_request(a.world)
    if not prior:fail("No prior vehicle request")
    data=response(a.world,prior["id"])
    print(json.dumps(data,ensure_ascii=False,indent=2))
    if data["status"]=="error":fail("Server rejected or partially executed write; inspect logs")

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="operation",required=True)
    for name in ("inspect","condition","fuel","battery","add","remove"):
        s=sub.add_parser(name)
        s.add_argument("world")
        s.add_argument("--id",required=True,type=int)
        s.add_argument("--script",required=True)
        s.add_argument("--x",required=True,type=int)
        s.add_argument("--y",required=True,type=int)
        s.add_argument("--z",required=True,type=int)
        s.add_argument("--part",required=name in ("condition","add","remove"))
        s.add_argument("--expect",type=float)
        s.add_argument("--value",type=float)
        s.add_argument("--item")
        s.add_argument("--count",type=int,default=1)
        s.add_argument("--yes",action="store_true")
        s.set_defaults(handler=run)
    s=sub.add_parser("status");s.add_argument("world");s.set_defaults(handler=status)
    a=parser.parse_args()
    if a.operation=="condition":
        if a.expect is None or a.value is None or not a.expect.is_integer() or not a.value.is_integer():
            parser.error("Condition requires exact integer --expect and --value")
        a.expect=int(a.expect);a.value=int(a.value)
    if a.operation in ("fuel","battery") and (a.expect is None or a.value is None):
        parser.error("Fluid/charge requires --expect and --value")
    if a.operation in ("add","remove") and not a.item:
        parser.error("Container operation requires --item")
    try:a.handler(a)
    except (ValueError,OSError,UnicodeError) as error:parser.exit(2,"Story vehicle: "+str(error)+"\n")

if __name__=="__main__":main()
