#!/usr/bin/env python3
"""Preview-first, staged, server-native construction for ANY Story-enabled map.

One request applies ONE named stage, containing reviewed object placements and
targeted removals. No arbitrary Lua, sprite code, chunk generation, or blind
replacement. The server preflights every operation before modifying the map.
Game-world changes are not atomic; partial failures require manual recovery.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, secrets, time
from pathlib import Path
import scanctl

REQ="SiegerAdminConstructionRequest.txt"
ACK="SiegerAdminConstructionResult.txt"
MAX_BYTES=2*1024*1024
MAX_ACTIONS=4096  # transport-frame size; not a world population/structure cap
IDENT=re.compile(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,63}\Z")
SPRITE=re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
ITEM=re.compile(r"[A-Za-z][A-Za-z0-9_]*\.[A-Za-z][A-Za-z0-9_]*\Z")
RID=re.compile(r"[0-9a-f]{32}\Z")
HASH=re.compile(r"[0-9a-f]{64}\Z")
PLACEMENTS={"wall","fence","door","window","floor","decor","generator"}
CLASSES={"IsoDoor","IsoWindow","IsoThumpable","IsoObject","IsoGenerator"}

def fail(message):raise ValueError(message)

def fields(obj,required,optional=()):
    if not isinstance(obj,dict) or not set(required)<=obj.keys() or \
       obj.keys()-set(required)-set(optional):
        fail("Unexpected or missing plan fields: "+repr(sorted(set(required)-set(obj))))

def name(value,pattern=IDENT):
    if not isinstance(value,str) or not pattern.fullmatch(value):
        fail("Invalid named object / sprite / settlement")
    return value

def number(v,low,high):
    if type(v) is not int or not low<=v<=high:
        fail("Expected integer in engine coordinate range")
    return v

def at(value):
    if not isinstance(value,list) or len(value)!=3:
        fail("Expected exact map tile [x,y,z]")
    return [str(number(value[0],-100000,1000000)),
            str(number(value[1],-100000,1000000)),
            str(number(value[2],-16,32))]

def row(values):
    if len(values)!=13 or any(not isinstance(s,str) or not s or "\t" in s or
                "\n" in s or "\r" in s or len(s)>128 for s in values):
        fail("Invalid construction transport row")
    return "\t".join(values)

def expand_actions(actions):
    """Compile explicitly requested straight wall/fence/floor/decor runs.

    An edge is a single N/W edge of one tile; skipped gate tiles remain
    untouched. A run is never a geometric fill or an implicit building.
    """
    if not isinstance(actions,list):fail("Stage actions must be an array")
    for action in actions:
        if not isinstance(action,dict):fail("Invalid action")
        if action.get("op")!="line":
            yield action
            continue
        fields(action,{"id","op","kind","start","end","sprite"},
               ("face","health","skip"))
        if action["kind"] not in {"wall","fence","floor","decor"}:
            fail("Line expansion supports wall/fence/floor/decor only")
        prefix=name(action["id"])
        if len(prefix)>55:fail("Line id is too long to add cell suffix")
        x0,y0,z0=map(int,at(action["start"]))
        x1,y1,z1=map(int,at(action["end"]))
        if z0!=z1 or (x0!=x1 and y0!=y1):
            fail("Line must be an axis-aligned single-floor run")
        stepX=(x1>x0)-(x1<x0)
        stepY=(y1>y0)-(y1<y0)
        distance=abs(x1-x0)+abs(y1-y0)+1
        if distance>MAX_ACTIONS:fail("One line cannot fit a single transport frame")
        removed=action.get("skip",[])
        if not isinstance(removed,list):fail("Line skip needs a coordinate list")
        skip={tuple(map(int,at(pos))) for pos in removed}
        if len(skip)!=len(removed):fail("Duplicate line gap")
        target={(x0+i*stepX,y0+i*stepY,z0) for i in range(distance)}
        if not skip<=target:fail("Line gap outside its endpoints")
        for i in range(distance):
            point=(x0+i*stepX,y0+i*stepY,z0)
            if point in skip:continue
            line={"id":f"{prefix}_{i:04d}","op":"place","kind":action["kind"],
                  "at":list(point),"sprite":action["sprite"]}
            if "face" in action:line["face"]=action["face"]
            if "health" in action:line["health"]=action["health"]
            yield line

def prepare(plan,world,stage):
    fields(plan,{"schema","world","settlement","stages"})
    if plan["schema"]!=1 or plan["world"]!=world:fail("Plan world/schema mismatch")
    settlement=name(plan["settlement"])
    stages=plan["stages"]
    if not isinstance(stages,list) or not stages:fail("Plan requires stages")
    selected=None
    stage_ids=set()
    for group in stages:
        fields(group,{"id","actions"},("requires","description"))
        ident=name(group["id"])
        if ident in stage_ids:fail("Duplicate construction stage")
        stage_ids.add(ident)
        if ident==stage:selected=group
    if selected is None:fail("Requested stage is not in the plan")
    requires=selected.get("requires",[])
    if not isinstance(requires,list) or len(requires)!=len(set(requires)) or \
       any(not isinstance(x,str) or not IDENT.fullmatch(x) or x==stage or
           x not in stage_ids for x in requires):
        fail("Invalid prerequisites")
    actions=list(expand_actions(selected["actions"]))
    if not actions:fail("Stage needs actions (line may not skip every cell)")
    results=[];ids=set();targets=set()
    existing=False
    placement_started=False
    for action in actions:
        if not isinstance(action,dict):fail("Invalid construction action")
        verb=action.get("op")
        ident=name(action.get("id"))
        if ident in ids:fail("Duplicate construction action id")
        ids.add(ident)
        coords=at(action.get("at"))
        kind=action.get("kind")
        sprite=other=health=expect=index="-"
        if verb=="place":
            placement_started=True
            fields(action,{"id","op","kind","at"},("face","sprite","open_sprite","item","health"))
            if kind not in PLACEMENTS:fail("Unsupported placed object type")
            face=action.get("face","-")
            if kind in ("wall","fence","door","window"):
                if face not in ("N","W"):fail("Wall/door/window face must be N or W")
            elif face!="-":
                fail("Unoriented object does not accept a face")
            if kind=="generator":
                if "sprite" in action or "open_sprite" in action:fail("Generator uses item, not sprite")
                sprite=name(action.get("item","Base.Generator"),ITEM)
                health=str(number(action.get("health",100),1,100))
            else:
                if "item" in action:fail("Only generator uses an inventory item")
                sprite=name(action.get("sprite"),SPRITE)
                if kind=="door":
                    other=name(action["open_sprite"],SPRITE) if "open_sprite" in action else "-"
                elif "open_sprite" in action:fail("Only doors accept open_sprite")
                health=str(number(action.get("health",350),1,100000)) \
                    if kind in ("wall","fence","door","floor") else "-"
        elif verb in ("remove_tag","remove_exact"):
            if placement_started:fail("All removals must precede placements within a stage")
            required={"id","op","kind","at","sprite"}
            optional={"face","target_tag"} if verb=="remove_tag" else {"face","index"}
            fields(action,required,optional)
            if kind not in CLASSES:fail("Exact removal needs a native object class")
            face=action.get("face","-")
            if face not in ("N","W","-"):fail("Bad expected object orientation")
            sprite=name(action["sprite"],SPRITE) if kind!="IsoGenerator" else \
                   name(action["sprite"],ITEM)
            if verb=="remove_tag":
                expect=action.get("target_tag")
                if not isinstance(expect,str) or len(expect)>190 or \
                   not re.fullmatch(r"[A-Za-z0-9_-]+:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+",expect):
                    fail("Tagged removal requires exact settlement:stage:action reference")
            else:
                existing=True
                if kind in ("IsoGenerator","IsoObject"):
                    fail("Unreviewed native generator/floor/decor deletion is not supported")
                index=str(number(action.get("index"),0,2147483647))
        else:fail("Unsupported construction verb")
        addr=(tuple(coords),face)
        # One object per face/square per stage. Door replacement can be an
        # explicit remove_exact followed by place in the same stage.
        if verb=="place":
            if addr in targets:fail("Overlapping stage placements on one face")
            targets.add(addr)
        results.append(row(["a",ident,verb,kind,*coords,face,sprite,other,
                            health,expect,index]))
        if len(results)>MAX_ACTIONS:fail("Transport request too large")
    wire="\n".join(results)+"\n"
    digest=hashlib.sha256(wire.encode("ascii")).hexdigest()
    return {"world":world,"settlement":settlement,"stage":name(stage),
            "actions":len(results),"rows":results,"digest":digest,
            "requires":sorted(requires),"allow_existing":existing,
            "description":selected.get("description","")}

def load(path,world,stage):
    file=Path(path)
    if file.is_symlink() or not file.is_file() or file.stat().st_size>MAX_BYTES:
        fail("Unsafe/missing/oversized construction plan")
    def unique(pairs):
        obj={}
        for k,v in pairs:
            if k in obj:fail("Duplicate JSON key: "+k)
            obj[k]=v
        return obj
    doc=json.loads(file.read_text(encoding="utf-8"),object_pairs_hook=unique,
                   parse_constant=lambda x:fail("Invalid JSON non-finite number"))
    return prepare(doc,world,stage)

def paths(world):
    directory=scanctl.lua_dir(world)
    return directory/REQ,directory/ACK

def previous(world):
    file,_=paths(world)
    if not file.is_file():return None
    if file.is_symlink() or file.stat().st_size>MAX_BYTES:fail("Unsafe prior request")
    with file.open("r",encoding="ascii") as stream:head=stream.readline()
    f=head.rstrip("\n").split("\t")
    if len(f)!=11 or f[0]!="v1" or not RID.fullmatch(f[1]) or \
       f[2]!=world or not IDENT.fullmatch(f[3]) or not IDENT.fullmatch(f[4]) or \
       not HASH.fullmatch(f[5]) or not f[6].isdigit() or \
       f[10]!="end":fail("Corrupted previous construction request")
    return {"id":f[1],"world":world,"settlement":f[3],"stage":f[4],
            "digest":f[5],"count":int(f[6])}

def receipt(world,prior):
    _,file=paths(world)
    if not file.is_file():return {"status":"pending"}
    if file.is_symlink() or file.stat().st_size>768:fail("Unsafe receipt")
    data=file.read_text("ascii")
    if not data.endswith("\n"):return {"status":"pending"}
    f=data.rstrip("\n").split("\t")
    if len(f)!=10 or f[0]!="v1" or not RID.fullmatch(f[1]) or \
       f[2]!=world or not IDENT.fullmatch(f[3]) or not IDENT.fullmatch(f[4]) or \
       not HASH.fullmatch(f[5]) or f[6] not in ("running","complete","error") or \
       not f[7].isdigit() or not f[8].isdigit() or \
       not IDENT.fullmatch(f[9]):fail("Invalid construction receipt")
    if f[1]!=prior["id"]:return {"status":"pending"}
    if (f[3],f[4],f[5],int(f[8]))!=(prior["settlement"],prior["stage"],
                                        prior["digest"],prior["count"]) or \
        int(f[7])>int(f[8]):
        fail("Receipt does not match exact world, stage or digest")
    return {"status":f[6],"request_id":f[1],"settlement":f[3],
            "stage":f[4],"sha256":f[5],"applied":int(f[7]),
            "total":int(f[8]),"detail":f[9]}

def preview(args):
    data=load(args.file,args.world,args.stage)
    print(json.dumps({k:v for k,v in data.items() if k!="rows"},indent=2,
                     ensure_ascii=False))
    for line in data["rows"]:print("  ",line)
    if args.survey:
        survey=Path(args.survey)
        if survey.is_symlink() or not survey.is_file() or survey.stat().st_size>50*1024*1024:
            fail("Unsafe/missing optional survey")
        snap=json.loads(survey.read_text("utf-8"))
        if snap.get("world",snap.get("meta",{}).get("world")) not in (None,args.world):
            fail("Survey world differs from selected world")
        squares={(r["x"],r["y"],r["z"]):r["loaded"]
            for r in snap.get("records",[]) if r.get("kind")=="square"}
        counters={"loaded_at_survey":0,"unloaded_or_nonexistent":0,"outside_survey":0}
        for line in data["rows"]:
            r=line.split("\t");address=tuple(map(int,r[4:7]))
            state=squares.get(address)
            key="outside_survey" if state is None else (
                "loaded_at_survey" if state else "unloaded_or_nonexistent")
            counters[key]+=1
        print("SURVEY advisory ONLY; not a live collision/path check:",
              json.dumps(counters))
    if not args.yes:
        print("PREVIEW ONLY. Nothing queued; apply --yes to request one stage.")
        return
    if args.command!="apply":fail("Preview cannot apply")
    if data["allow_existing"] and not args.allow_existing:
        fail("Native existing-object removal requires explicit --allow-existing")
    if os.geteuid()!=0:fail("Construction writes require sudo/root")
    scanctl.assert_module_ready(args.world,"SiegerAdminConstruction")
    old=previous(args.world)
    if old:
        ack=receipt(args.world,old)
        if ack["status"] in ("pending","running"):fail("Previous construction request not finished")
        if ack["status"]=="error" and not args.acknowledge_failed:
            fail("Last stage may have partially applied; review first")
    rid=secrets.token_hex(16)
    exp=int(time.time()*1000)+30000
    require=",".join(data["requires"]) or "-"
    header="\t".join(["v1",rid,args.world,data["settlement"],data["stage"],
        data["digest"],str(data["actions"]),require,
        "1" if args.allow_existing else "0",str(exp),"end"])+"\n"
    packet=header+"\n".join(data["rows"])+"\n"
    if len(packet.encode("ascii"))>MAX_BYTES:fail("Request transport size exceeded")
    req,_=paths(args.world)
    scanctl.atomic_request(req,packet)
    print("QUEUED",rid,"; NOT proof of construction")
    print("Check: sudo pz story build status",args.world)

def verify(args):
    """Read-only POST-stage AreaScan comparison; no tag/orientation attestation."""
    plan=load(args.file,args.world,args.stage)
    file=Path(args.survey)
    if file.is_symlink() or not file.is_file() or file.stat().st_size>200*1024*1024:
        fail("Unsafe/missing post-stage AreaScan")
    snap=json.loads(file.read_text("utf-8"))
    if not isinstance(snap,dict) or not isinstance(snap.get("records"),list):
        fail("Malformed AreaScan")
    summary=snap.get("summary",{})
    if not isinstance(summary,dict):fail("Malformed survey summary")
    if snap.get("schema")=="sieger-private-merged-area-survey-v1":
        if summary.get("source_errors")!=0 or summary.get("source_truncated") is not False or \
           summary.get("all_requested_coordinates_visited") is not True or \
           snap.get("snapshot_mode")!="two sequential incremental scans, not simultaneous":
            fail("Merged post-stage survey lacks complete provenance")
    elif summary.get("status")!="complete" or summary.get("truncated") is not False or \
         summary.get("errors")!=0:
        fail("Post-stage AreaScan is incomplete or contains errors")
    supplied_world=snap.get("world")
    if supplied_world is None:
        if args.source_world!=args.world:
            fail("Legacy survey has no world marker: explicit --source-world required")
    elif supplied_world!=args.world:
        fail("Post-stage survey belongs to a different world")
    squares={}
    objects={}
    for object in snap["records"]:
        if not isinstance(object,dict):fail("Non-object AreaScan record")
        address=(object.get("x"),object.get("y"),object.get("z"))
        if object.get("kind")=="square":
            if address in squares:fail("Ambiguous duplicate scanned square")
            if type(object.get("loaded")) is not bool:fail("Invalid square coverage")
            squares[address]=object["loaded"]
        elif object.get("kind")=="object":
            objects.setdefault(address,[]).append(object)
    types={"wall":"IsoThumpable","fence":"IsoThumpable",
           "floor":"IsoThumpable","door":"IsoDoor","window":"IsoWindow",
           "generator":"IsoGenerator","decor":"IsoObject"}
    results=[]
    counts={"seen_place":0,"missing_place":0,"unobserved":0,
            "ambiguous":0,"unverified_ownership":0,"apparently_removed":0,
            "existing_similar_remains":0}
    for command in plan["rows"]:
        row=command.split("\t")
        _,action_id,verb,kind,x,y,z,face,sprite,alt,*other=row
        addr=(int(x),int(y),int(z))
        entry={"id":action_id,"at":list(addr),"op":verb}
        if squares.get(addr) is not True:
            entry["result"]="unobserved"    # unloaded and out-of-coverage are not empty
            counts["unobserved"]+=1
        else:
            expected=types[kind] if verb=="place" else kind
            if kind=="door" and alt!="-":expected="IsoThumpable"
            candidates=[obj for obj in objects.get(addr,[])
                if obj.get("class")==expected and
                (kind=="generator" or obj.get("sprite")==sprite)]
            if verb=="place":
                mark=f'{plan["settlement"]}:{args.stage}:{action_id}'
                verified=[o for o in candidates if o.get("construction_tag")==mark and
                          (face=="-" or o.get("face")==face)]
                if len(verified)==1 and len(candidates)==1:
                    entry["result"]="observed_native_tag_face"
                    counts["seen_place"]+=1
                elif len(verified)>1 or len(candidates)>1:
                    entry["result"]="ambiguous_multiple_matches"
                    counts["ambiguous"]+=1
                elif candidates:
                    entry["result"]="native_found_tag_or_face_unverified"
                    counts["unverified_ownership"]+=1
                else:
                    entry["result"]="missing_from_loaded_square"
                    counts["missing_place"]+=1
            elif verb=="remove_tag":
                mark=row[11]
                still=[o for o in candidates if o.get("construction_tag")==mark and
                       (face=="-" or o.get("face")==face)]
                if still:
                    entry["result"]="tagged_object_still_present"
                    counts["existing_similar_remains"]+=1
                else:
                    entry["result"]="tag_absent_on_loaded_square"
                    counts["apparently_removed"]+=1
            elif candidates:
                entry["result"]="similar_existing_object_present"
                counts["existing_similar_remains"]+=1
            else:
                entry["result"]="apparently_removed"
                counts["apparently_removed"]+=1
        results.append(entry)
    report={"world":args.world,"settlement":plan["settlement"],"stage":args.stage,
            "survey_world_identity":"file" if supplied_world else "manual_operator_assertion",
            "evidence":"one post-stage loaded AreaScan; class/sprite/own tag/edge where applicable",
            "limitations":["Legacy AreaScan without tag/edge cannot prove construction ownership",
                "Matching a sprite does not prove save/reload, collision, electrical function or replication",
                "An absent object is not proven removed unless the exact square was loaded",
                "AreaScan snapshots have no trusted capture timestamps; verify that the scan was collected AFTER stage ACK"],
            "counts":counts,"results":results}
    print(json.dumps(report,indent=2,ensure_ascii=False))
    if counts["missing_place"] or counts["ambiguous"] or counts["unverified_ownership"] or \
       counts["existing_similar_remains"] or counts["unobserved"]:
        fail("Post-stage survey is incomplete or does not reconcile; review in game")

def status(args):
    old=previous(args.world)
    if not old:fail("No construction request")
    result=receipt(args.world,old)
    print(json.dumps(result,indent=2))
    if result["status"]=="error":
        fail("Construction stage failed or partially applied; do not replay without inspection")

def main():
    import constructionsite
    p=argparse.ArgumentParser(description=__doc__)
    subs=p.add_subparsers(dest="command",required=True)
    for cmd in ("preview","apply"):
        sub=subs.add_parser(cmd)
        sub.add_argument("world");sub.add_argument("--file",required=True)
        sub.add_argument("--stage",required=True)
        sub.add_argument("--survey",help="Optional local read-only AreaScan/merged JSON for advisory coverage")
        sub.add_argument("--allow-existing",action="store_true")
        sub.add_argument("--acknowledge-failed",action="store_true")
        if cmd=="apply":sub.add_argument("--yes",action="store_true")
        else:sub.set_defaults(yes=False)
        sub.set_defaults(handler=preview)
    sub=subs.add_parser("verify")
    sub.add_argument("world");sub.add_argument("--file",required=True)
    sub.add_argument("--stage",required=True);sub.add_argument("--survey",required=True)
    sub.add_argument("--source-world",help="Required for legacy AreaScan lacking source world name")
    sub.set_defaults(handler=verify)
    constructionsite.add_subcommand(subs)
    sub=subs.add_parser("status");sub.add_argument("world");sub.set_defaults(handler=status)
    args=p.parse_args()
    try:args.handler(args)
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as error:
        p.exit(2,"Construction: "+str(error)+"\n")

if __name__=="__main__":main()
