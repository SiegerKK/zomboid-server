#!/usr/bin/env python3
"""Low-impact on-demand TLOU zombie statistics for a story_test server.

Read-only. Registry is a constant-size inspection; nearby infected sampling
checks <=512 loaded zombies, 16 per OnTick. It does not profile CPU time
attributable to a specific mod. Use the existing pz story profile separately
to inspect the entire Docker game container.
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
REQ=re.compile(r"v1\t([0-9a-f]{32})\tstory_test\t(registry|sample)\t"
    r"(-|[A-Za-z0-9_][A-Za-z0-9_.-]{0,30})\t([0-9]{1,2})\t([0-9]{1,3})\n?\Z")
ID=re.compile(r"[0-9a-f]{32}\Z")
NONNEG=re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,3})?\Z")
SCALAR=re.compile(r"-|true|false|[0-9]{1,6}(?:\.[0-9]{1,3})?\Z")
MAX_BYTES=8192
MAX_ROWS=32

def fail(message):
    raise ValueError(message)

def paths(world):
    folder=scanctl.lua_dir(world)
    return folder/REQUEST,folder/RESPONSE

def previous(world):
    req,_=paths(world)
    if not req.is_file():return None
    if req.is_symlink() or req.stat().st_size>220:
        fail("Unsafe previous TLOU request")
    m=REQ.fullmatch(req.read_text("ascii"))
    if not m:fail("Malformed previous TLOU request; manual inspection required")
    return {"id":m[1],"operation":m[2],"username":m[3],
            "radius":int(m[4]),"limit":int(m[5])}

def parse(world,requested):
    _,res=paths(world)
    if not res.is_file():return {"status":"pending"}
    if res.is_symlink() or res.stat().st_size>MAX_BYTES:
        fail("Unsafe/oversized TLOU snapshot result")
    data=res.read_text("utf-8")
    if not data.endswith("\n"):return {"status":"pending"}
    lines=data.splitlines()
    if len(lines)<2 or len(lines)>MAX_ROWS+2 or lines[-1]!="end":
        fail("Invalid TLOU response size/footer")
    head=lines[0].split("\t")
    if len(head)!=7 or head[0]!="v1" or not ID.fullmatch(head[1]) \
            or head[2]!="story_test" or head[3] not in ("registry","sample") \
            or head[4] not in ("complete","error") \
            or head[5] not in ("server_registry","sampled_loaded_only","review_server_logs") \
            or not head[6].isdigit():
        fail("Invalid TLOU response header")
    if head[1]!=requested:return {"status":"pending"}
    if len(lines)-2!=int(head[6]) or int(head[6])>MAX_ROWS:
        fail("Inconsistent TLOU response row count")
    original=previous(world)
    if not original or original["id"]!=head[1] or original["operation"]!=head[3]:
        fail("TLOU response does not match requested operation")
    if (head[4]=="error" and len(lines)!=2) \
            or (head[4]=="complete" and len(lines)<2+13):
        fail("Incomplete or invalid TLOU result")
    result={"status":head[4],"request_id":head[1],"operation":head[3],
        "reason":head[5],"registry":{},"sandbox":{},"observed":{},
        "sample":None,"activity":None}
    gotFramework=False
    for raw in lines[1:-1]:
        row=raw.split("\t")
        if row[0]=="framework":
            if len(row)!=3 or gotFramework or row[1] not in ("available","unavailable") \
                    or row[2] not in ("yes","no"):
                fail("Invalid Zomboid Forge availability marker")
            gotFramework=True
            result["framework"]={"registry":row[1],"type_api":row[2]}
        elif row[0]=="ztype":
            if len(row)!=8 or row[1] not in TYPES or row[1] in result["registry"] \
                    or not all(SCALAR.fullmatch(x) or x=="not_registered" for x in row[2:]):
                fail("Invalid TLOU ZType row")
            result["registry"][row[1]]={"weight":row[2],"hp":row[3],
                "walktype":row[4],"hearing":row[5],"sight":row[6],
                "on_tick_callbacks":row[7]}
        elif row[0]=="setting":
            if len(row)!=3 or row[1] not in SETTINGS or row[1] in result["sandbox"] \
                    or not SCALAR.fullmatch(row[2]):
                fail("Invalid sandbox setting")
            result["sandbox"][row[1]]=row[2]
        elif row[0]=="observed":
            if len(row)!=3 or row[1] not in (*TYPES,"other","unknown") \
                    or row[1] in result["observed"] or not row[2].isdigit():
                fail("Invalid observed infected row")
            result["observed"][row[1]]=int(row[2])
        elif row[0]=="sample":
            if len(row)!=9 or result["sample"] is not None \
                    or not scanctl.USERNAME.fullmatch(row[1]) \
                    or not all(v.isdigit() for v in row[2:]):
                fail("Invalid sample metadata")
            values=list(map(int,row[2:]))
            if not (1<=values[0]<=30 and 0<=values[2]<=512
                    and values[2]<=values[1]<=10000 and
                    0<=values[3]<=values[2] and 0<=values[4]<=64
                    and values[5]==16 and values[6]<=values[3]):
                fail("Impossible sample budget/count")
            if row[1]!=original["username"] or values[0]!=original["radius"] \
                    or values[2]>original["limit"]:
                fail("Sample does not match requested player/budget")
            result["sample"]={"player":row[1],"radius":values[0],
                "loaded_list":values[1],"inspected":values[2],
                "within_radius":values[3],"processing_ticks":values[4],
                "per_tick_limit":values[5],"classification_errors":values[6],
                "partial":values[2]<values[1]}
        elif row[0]=="activity":
            if len(row)!=7 or result["activity"] is not None \
                    or not row[1].isdigit() or \
                    not (row[2]=="-" or NONNEG.fullmatch(row[2])) \
                    or not all(x.isdigit() for x in row[3:]):
                fail("Invalid zombie activity metrics")
            result["activity"]={"health_samples":int(row[1]),
                "mean_health":None if row[2]=="-" else float(row[2]),
                "moving_count":int(row[3]),"moving_samples":int(row[4]),
                "targeting_count":int(row[5]),"targeting_samples":int(row[6])}
        else:
            fail("Unknown TLOU diagnostics row")
    if head[4]=="complete":
        if not gotFramework or set(result["registry"])!=set(TYPES) \
                or set(result["sandbox"])!=set(SETTINGS):
            fail("Incomplete TLOU registry/sandbox output")
        if head[3]=="registry" and (result["sample"] is not None or
                result["observed"] or result["activity"] is not None):
            fail("Unexpected samples in registry request")
        if head[3]=="sample":
            sample=result["sample"]
            if sample is None or result["activity"] is None \
                    or set(result["observed"])!=set((*TYPES,"other","unknown")) \
                    or sum(result["observed"].values())!=sample["within_radius"]:
                fail("Incomplete or contradictory infected sample")
            act=result["activity"]
            if any(act[k]>sample["within_radius"] for k in
                   ("health_samples","moving_samples","targeting_samples")) \
                    or act["moving_count"]>act["moving_samples"] \
                    or act["targeting_count"]>act["targeting_samples"]:
                fail("Impossible TLOU activity totals")
    return result

def ensure_ready(world):
    if world!="story_test":fail("Only story_test is authorized")
    scanctl.assert_ready(world)
    expected=(scanctl.REPO/"story/runtime/SiegerStoryTLOUDiagnostics.lua").resolve()
    mounted=scanctl.docker_mounts().get(
        "/pzomboid-server/media/lua/server/SiegerStoryTLOUDiagnostics.lua")
    if mounted!=expected:
        fail("TLOU diagnostics runtime missing; a controlled restart is required")

def queue(args):
    if args.world!="story_test":fail("Only story_test")
    scanctl.slot(args.world)
    username,radius,limit="-",0,0
    if args.operation=="sample":
        username,radius,limit=args.player,args.radius,args.limit
        if not scanctl.USERNAME.fullmatch(username) or not 1<=radius<=30 \
                or not 16<=limit<=512:
            fail("Exact player, radius 1..30 and limit 16..512 required")
    print("PREVIEW read-only TLOU",args.operation,"world",args.world,
          "player",username,"radius",radius,"sample limit",limit)
    if not args.yes:
        print("No request queued. Add --yes for a one-shot snapshot.")
        return
    ensure_ready(args.world)
    old=previous(args.world)
    if old:
        result=parse(args.world,old["id"])
        if result["status"]=="pending":
            fail("Previous TLOU request pending; wait for result")
        if result["status"]=="error" and not args.acknowledge_failed:
            fail("Previous TLOU error; inspect logs and add --acknowledge-failed")
    rid=secrets.token_hex(16)
    packet=f"v1\t{rid}\tstory_test\t{args.operation}\t{username}\t{radius}\t{limit}\n"
    req,_=paths(args.world)
    scanctl.atomic_request(req,packet)
    print("QUEUED read-only request",rid)
    print("Poll: sudo pz story tlou result story_test")

def show(args):
    if args.world!="story_test":fail("Only story_test")
    scanctl.slot(args.world)
    old=previous(args.world)
    if not old:fail("No previous TLOU request")
    data=parse(args.world,old["id"])
    print(json.dumps(data,ensure_ascii=False,indent=2))
    if data["status"]=="error":
        fail("TLOU snapshot failed; inspect server logs")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    for mode in ("registry","sample"):
        cmd=sub.add_parser(mode)
        cmd.add_argument("world")
        if mode=="sample":
            cmd.add_argument("--player",required=True)
            cmd.add_argument("--radius",type=int,default=20)
            cmd.add_argument("--limit",type=int,default=256)
        cmd.add_argument("--yes",action="store_true")
        cmd.add_argument("--acknowledge-failed",action="store_true")
        cmd.set_defaults(handler=queue,operation=mode)
    cmd=sub.add_parser("result")
    cmd.add_argument("world")
    cmd.set_defaults(handler=show)
    a=p.parse_args()
    try:a.handler(a)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as err:
        p.exit(2,"Story TLOU: "+str(err)+"\n")

if __name__=="__main__":main()
