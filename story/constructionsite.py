#!/usr/bin/env python3
"""Universal offline settlement site inventory from native AreaScan JSON.

Reads-only: loaded coverage, building metadata, roads-as-sprite-hints,
objects, doors/windows, vehicles, and optional proposed-stage hazards.
No pathfinding claim and NEVER mutates game saves/chunks.
"""
from __future__ import annotations
import argparse,collections,json,os
from pathlib import Path
import constructionctl

MAX_SURVEY=200*1024*1024
def fail(why):raise ValueError(why)

def load_survey(path,world,source_world=None):
    f=Path(path)
    if f.is_symlink() or not f.is_file() or f.stat().st_size>MAX_SURVEY:
        fail("Missing/unsafe/oversized survey")
    # Strict duplicate detection: no arbitrary merged keys or duplicates.
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:fail("Duplicate JSON key in survey")
            result[key]=value
        return result
    data=json.loads(f.read_text("utf-8"),object_pairs_hook=unique,
                    parse_constant=lambda x:fail("Non-finite JSON number"))
    if not isinstance(data,dict) or not isinstance(data.get("records"),list):
        fail("Survey has no records array")
    if data.get("world") is not None:
        if data["world"]!=world:fail("Survey world mismatch")
        verified=True
    elif source_world==world:
        verified=False
    else:fail("Survey missing world identity; pass explicit --source-world")
    summary=data.get("summary")
    if not isinstance(summary,dict):fail("Survey lacks completed summary")
    if data.get("schema") in ("sieger-private-merged-area-survey-v1",
                              "sieger-private-mosaic-area-survey-v1"):
        mosaic=data["schema"]=="sieger-private-mosaic-area-survey-v1"
        mode=("multiple_sequential_loaded_square_scans_not_simultaneous" if mosaic
              else "two sequential incremental scans, not simultaneous")
        if summary.get("source_errors")!=0 or summary.get("source_truncated") is not False or \
           summary.get("all_requested_coordinates_visited") is not True or \
           data.get("snapshot_mode")!=mode:
            fail("Merged survey incomplete or without strict cell provenance")
        sources=data.get("sources")
        if not isinstance(sources,list) or len(sources)<(1 if mosaic else 2):
            fail("Missing merged survey sources")
        if mosaic and summary.get("source_count")!=len(sources):
            fail("Mosaic source count inconsistent")
    elif summary.get("status")!="complete" or summary.get("errors")!=0 or \
         summary.get("truncated") is not False:
        fail("AreaScan incomplete or contains errors")
    return data,verified

def bounds(raw,default):
    if raw is None:return default
    pieces=raw.split(",")
    if len(pieces)!=4 or any(not x.lstrip("-").isdigit() for x in pieces):
        fail("Specify --bbox X0,Y0,X1,Y1 (exclusive)")
    bbox=[int(x) for x in pieces]
    if any(abs(v)>1000000 for v in bbox) or not bbox[0]<bbox[2] or \
       not bbox[1]<bbox[3]:fail("Invalid bbox")
    return bbox

def surveyed_bbox(data):
    bbox=data.get("bbox_exclusive")
    if isinstance(bbox,list) and len(bbox)==4 and all(type(x) is int for x in bbox):
        return bbox
    sq=[r for r in data["records"] if isinstance(r,dict) and r.get("kind")=="square"]
    if not sq:fail("No square coverage")
    return [min(r["x"] for r in sq),min(r["y"] for r in sq),
            max(r["x"] for r in sq)+1,max(r["y"] for r in sq)+1]

def analyze(data,world,area,stage=None):
    x0,y0,x1,y1=area
    def inside(r):
        return type(r.get("x")) is int and type(r.get("y")) is int and \
            x0<=r["x"]<x1 and y0<=r["y"]<y1
    squares={};objects=collections.defaultdict(list)
    kinds=collections.Counter()
    for rec in data["records"]:
        if not isinstance(rec,dict):fail("Non-object survey record")
        if not inside(rec):continue
        key=(rec["x"],rec["y"],rec.get("z"))
        kind=rec.get("kind");kinds[kind]+=1
        if kind=="square":
            if key in squares:fail("Duplicate square coverage in merged survey")
            if type(rec.get("loaded")) is not bool:fail("Invalid loaded square")
            squares[key]=rec["loaded"]
        elif kind=="object":
            objects[key].append(rec)
    floors={}
    for (x,y,z),loaded in squares.items():
        node=floors.setdefault(str(z),{"loaded":0,"unloaded_or_nonexistent":0})
        node["loaded" if loaded else "unloaded_or_nonexistent"]+=1
    if not squares:fail("Selected bbox contains no scanned squares")
    classes=collections.Counter()
    road=set();vegetation=set();structures=set()
    windows,doors=[],[]
    for key,items in objects.items():
        for obj in items:
            kind=obj.get("class","unknown");classes[kind]+=1
            sp=obj.get("sprite","")
            if not isinstance(sp,str):continue
            if sp.startswith(("blends_street_","floors_exterior_street_")):
                road.add(key)
            if sp.startswith(("e_","f_","vegetation_")):
                vegetation.add(key)
            if sp.startswith(("walls_","fixtures_","carpentry_")):
                structures.add(key)
            if kind=="IsoWindow":windows.append(list(key))
            if kind=="IsoDoor":doors.append(list(key))
    vehicles=[]
    for rec in data["records"]:
        if isinstance(rec,dict) and rec.get("kind")=="vehicle" and inside(rec):
            vehicles.append({"x":rec["x"],"y":rec["y"],"z":rec.get("z"),
                "vehicle_id":rec.get("vehicle_id"),"script":rec.get("script")})
    buildings=[]
    for b in data.get("metadata_buildings",[]):
        if not isinstance(b,dict):continue
        bb=b.get("bbox")
        if isinstance(bb,list) and len(bb)==4 and max(bb[0],x0)<min(bb[2],x1) and \
           max(bb[1],y0)<min(bb[3],y1):
            buildings.append({"id":b.get("id"),"bbox":bb,
                              "rooms":sorted({r.get("name","") for r in b.get("rooms",[])
                                               if isinstance(r,dict)})})
    report={"schema":"sieger-build-site-analysis-v1","world":world,
        "bbox_exclusive":area,"survey":"historical, not live",
        "floor_coverage":floors,"record_kinds":dict(sorted(kinds.items())),
        "native_object_classes":dict(sorted(classes.items())),
        "sprite_hints":{"street_tiles":len(road),"vegetation_tiles":len(vegetation),
                        "existing_wall_or_fixture_tiles":len(structures)},
        "observed_openings":{"doors":len(doors),"windows":len(windows)},
        "vehicles":vehicles,"metadata_buildings":buildings,
        "limitations":["Terrain sprites are not confirmed vehicle routes or pathfinding",
           "Only loaded squares show object occupancy; upper missing does not mean buildable",
           "Snapshot may combine observations from different moments",
           "No map/sprite collisions, door leaf, generator exhaust or crop growth validated"]}
    if stage:
        plan=stage
        warnings=[]
        tally=collections.Counter()
        for wire in plan["rows"]:
            cols=wire.split("\t")
            verb,kind=cols[2:4];p=(int(cols[4]),int(cols[5]),int(cols[6]))
            event={"action":cols[1],"at":list(p),"operation":verb}
            loaded=squares.get(p)
            if loaded is None:
                event["risk"]="outside_survey";tally[event["risk"]]+=1
            elif not loaded:
                event["risk"]="unloaded_or_nonexistent";tally[event["risk"]]+=1
            elif verb=="barricade":
                event["risk"]="window_selector_requires_fresh_survey"
                tally[event["risk"]]+=1
            elif verb=="place":
                old=objects.get(p,[])
                if p in road and kind in ("wall","fence","door","window","generator","decor"):
                    event["risk"]="possible_road_or_driveway";tally[event["risk"]]+=1
                elif any(o.get("class") in ("IsoDoor","IsoWindow","IsoThumpable","IsoGenerator")
                         for o in old):
                    event["risk"]="existing_native_structure";tally[event["risk"]]+=1
                elif any(isinstance(o.get("sprite"),str) and o["sprite"].startswith(
                            ("fixtures_","walls_","furniture_","appliances_"))
                         for o in old):
                    event["risk"]="existing_fixture_or_wall";tally[event["risk"]]+=1
                elif any(abs(p[0]-v["x"])<=3 and abs(p[1]-v["y"])<=3 for v in vehicles):
                    event["risk"]="near_observed_vehicle";tally[event["risk"]]+=1
                else:
                    tally["no_known_snapshot_collision"]+=1
                    continue
            else:
                tally["removal_requires_fresh_live_selector"]+=1
                continue
            warnings.append(event)
        report["stage_assessment"]={"id":plan["stage"],"actions":plan["actions"],
            "counts":dict(sorted(tally.items())),"warnings":warnings,
            "advisory_only":True}
    return report

def output_file(path,body):
    dest=Path(path)
    if not dest.parent.is_dir() or dest.is_symlink() or \
       dest.resolve().is_relative_to(constructionctl.scanctl.REPO.resolve()):
        fail("Private export must be NEW and outside source repository")
    fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(body,stream,indent=2,ensure_ascii=False,allow_nan=False)
            stream.write("\n")
    except BaseException:
        dest.unlink(missing_ok=True);raise

def run(args):
    data,verified=load_survey(args.survey,args.world,args.source_world)
    area=bounds(args.bbox,surveyed_bbox(data))
    plan=constructionctl.load(args.file,args.world,args.stage) if args.file else None
    report=analyze(data,args.world,area,plan)
    report["survey_world_identity"]="file" if verified else "explicit_operator_assertion"
    if args.output:output_file(args.output,report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

def add_subcommand(subs):
    parser=subs.add_parser("site",help="Offline full-area inventory and optional staged plan collision warnings")
    parser.add_argument("world")
    parser.add_argument("--survey",required=True)
    parser.add_argument("--source-world",help="Required for raw AreaScan without an embedded world ID")
    parser.add_argument("--bbox",help="X0,Y0,X1,Y1 exclusive; omit for full survey")
    parser.add_argument("--file",help="Optional build plan to compare against observed square objects")
    parser.add_argument("--stage",help="Required when --file provided")
    parser.add_argument("--output",help="NEW private analysis JSON outside repository")
    parser.set_defaults(handler=lambda args:run(args) if bool(args.file)==bool(args.stage)
                        else fail("--file and --stage must be paired"))
