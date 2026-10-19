#!/usr/bin/env python3
"""Offline stage-by-stage logistics audit for private survivor settlements.

A nutrition/water/fuel ledger is NOT proof that a game world contains usable
calories, purified water, filled B42 FluidContainers or live farm crops.
This validator intentionally distinguishes planned stocks from game-observed
stocks. No world I/O, RCON, game saves or scene execution.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re

SCHEMA="sieger-private-farm-stock-v6"
LEGACY_SCHEMA="sieger-private-farm-stock-v5"
COLLECTOR_CAPACITY_L={"crate":400,"barrel":600}
EXPECTED_COLLECTORS=((0,0),(1,0),(1,1),(2,2))
STAGES=("phase01","phase02","phase03","phase04")
MAX_INPUT=2*1024*1024
WORLD=re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}\Z")
IDENT=re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,63}\Z")
RESOURCES=("food_kcal","potable_water_l","reserve_gasoline_l")
RATIONS=("food_kcal_person_day","potable_l_person_day","sanitation_l_person_day")

def fail(message):raise ValueError(message)

def read(path):
    f=Path(path)
    if not f.is_file() or f.is_symlink() or f.stat().st_size>MAX_INPUT:
        fail("Resource ledger missing/unsafe/oversized")
    def unique(pairs):
        obj={}
        for k,v in pairs:
            if k in obj:fail("Duplicate JSON key: "+k)
            obj[k]=v
        return obj
    return json.loads(f.read_text("utf-8"),object_pairs_hook=unique,
                      parse_constant=lambda x:fail("Invalid nonfinite quantity"))

def quantity(value,key):
    if type(value) is not int or value<0 or value>10**9:
        fail("Invalid nonnegative integer quantity: "+key)
    return value

def validate(doc):
    if not isinstance(doc,dict) or doc.get("schema") not in (SCHEMA,LEGACY_SCHEMA):
        fail("Unsupported settlement resource schema")
    world=doc.get("world");settlement=doc.get("settlement")
    if not isinstance(world,str) or not WORLD.fullmatch(world) or \
       not isinstance(settlement,str) or not IDENT.fullmatch(settlement):
        fail("Invalid world/settlement")
    stage=doc.get("stage")
    if stage not in STAGES:fail("Not a supported four-phase settlement state")
    index=STAGES.index(stage)
    people=quantity(doc.get("residents_planned"),"residents_planned")
    regular=quantity(doc.get("residents_regular"),"residents_regular")
    if not ((people in (2,4,6) and people==2*index+2) if index<3
            else (8<=people<=10)) or regular>people or regular<2:
        fail("Population does not match the reviewed 2→4→6→8–10 progression")
    days=quantity(doc.get("reserve_days"),"reserve_days")
    if days<3 or days>90:fail("Unsupported stock coverage horizon")
    norms=doc.get("model");requested=doc.get("requirements")
    if not isinstance(norms,dict) or not isinstance(requested,dict):
        fail("Missing ration model or requirements")
    for key in RATIONS:
        if quantity(norms.get(key),key)<1:fail("Ration norm cannot be zero")
    expected={
        "food_kcal":people*days*norms["food_kcal_person_day"],
        "potable_water_l":people*days*norms["potable_l_person_day"],
        "sanitation_water_usage_l_not_stored":
              people*days*norms["sanitation_l_person_day"]
    }
    for key,value in expected.items():
        if quantity(requested.get(key),key)!=value:
            fail("Resource budget does not cover people and days: "+key)
    fuel=quantity(requested.get("fuel_l"),"fuel_l")
    genn=quantity(requested.get("generator_units"),"generator_units")
    if genn!=(0 if index==0 else (2 if index==3 else 1)):
        fail("Stage generator progression does not match reviewed design")
    if index==0 and (fuel!=0 or requested.get("generator_duty_hours_day")!=0):
        fail("First phase must not consume generator fuel")
    duty=quantity(requested.get("generator_duty_hours_day"),"generator_duty_hours_day")
    if duty>24:fail("More than 24 hours/day of generation")
    forecast=requested.get("generator_gasoline_l_for_assumed_duty")
    if type(forecast) not in (float,int) or forecast<0 or \
       fuel+1e-6<forecast:
        fail("Generator fuel reserve does not cover own estimated duty")
    if norms.get("game_consumption_not_measured") is not True or \
       requested.get("fuel_assumption_not_verified_on_game_server") is not True:
        fail("Unmeasured fuel consumption must not be called game-verified")
    zones=doc.get("zones")
    if not isinstance(zones,list) or len(zones)<4:fail("Missing per-room/building site inventories")
    seen=set();sums=Counter()
    for zone in zones:
        if not isinstance(zone,dict):fail("Invalid zone")
        token=zone.get("zone")
        if not isinstance(token,str) or not IDENT.fullmatch(token) or token in seen:
            fail("Duplicate or invalid storage zone")
        seen.add(token)
        if not isinstance(zone.get("function"),str) or not zone["function"]:
            fail("Every zone needs an explicit current purpose")
        amounts=zone.get("quantitative_reserve_target")
        if not isinstance(amounts,dict) or set(amounts)!=set(RESOURCES):
            fail("Incomplete per-zone stock budget")
        for key in RESOURCES:sums[key]+=quantity(amounts[key],key)
        if zone.get("capacity_proved_by_snapshot") is not False:
            fail("Historical container list cannot prove present storage capacity")
    for key,expected_total in (
        ("food_kcal",expected["food_kcal"]),
        ("potable_water_l",expected["potable_water_l"]),
        ("reserve_gasoline_l",fuel)):
        if sums[key]!=expected_total:fail("Per-zone logistics do not reconcile: "+key)
    beds=doc.get("sleeping_personal_effects")
    if not isinstance(beds,list) or len(beds)!=people:
        fail("Every resident needs one independent named sleeping assignment")
    labels=set();names=set();regular_count=0
    for bed in beds:
        if not isinstance(bed,dict) or not isinstance(bed.get("name"),str) or \
           not isinstance(bed.get("bed"),str) or \
           not isinstance(bed.get("belongings"),list) or len(bed["belongings"])<2:
            fail("Bed lacks identity and personal belongings")
        if bed["name"] in names or bed["bed"] in labels:
            fail("Repeated person or bunk identifier")
        names.add(bed["name"]);labels.add(bed["bed"])
        if bed.get("status")=="regular":regular_count+=1
        elif bed.get("status")!="optional_visitor":
            fail("Bed status must be a regular or optional visitor")
    if regular_count!=regular:fail("Regular population doesn't match sleeping assignments")
    farming=doc.get("agriculture")
    if not isinstance(farming,dict) or farming.get("livestock") is not False or \
       farming.get("farming_spawn_adapter_available") is not False:
        fail("Native crop simulation is unverified; no chickens/livestock in this plan")
    # The legacy snapshot contained bodies/items, but the owner has since
    # cleared the area. Never require that historical count in a NEW ledger.
    historical=farming.get("observed_corpses_needing_review")
    if historical is not None:quantity(historical,"historical_corpses_not_current")
    collectors=[];collector_capacity=0;dry_day_irrigation=0
    water_design=doc.get("rainwater_collection")
    if doc["schema"]==SCHEMA and water_design is None:
        fail("v6 requires a rainwater harvesting and treatment plan")
    if water_design is not None:
        if not isinstance(water_design,dict) or set(water_design)!={
                "collectors","treatment","collector_contents_not_assumed",
                "actual_volume_game_verified","plumbing_game_verified",
                "crop_irrigation_l_per_dry_day"}:
            fail("Invalid rainwater management plan")
        if water_design["treatment"] not in ("boil","boil_and_tablets"):
            fail("Unreviewed drinking-water purification method")
        if (water_design["collector_contents_not_assumed"] is not True or
            water_design["actual_volume_game_verified"] is not False or
            water_design["plumbing_game_verified"] is not False):
            fail("Nominal rain capacity is never proof of filled or potable water")
        collectors=water_design["collectors"]
        if not isinstance(collectors,list):fail("Collector list required")
        seen_collectors=set();kind_counts=Counter()
        for collector in collectors:
            if not isinstance(collector,dict) or set(collector)!={
                    "id","kind","capacity_l","site","introduced_stage",
                    "open_sky_requires_live_check"}:
                fail("Rain collector fields must be fully specified")
            ident=collector["id"];kind=collector["kind"]
            if not isinstance(ident,str) or not IDENT.fullmatch(ident) or
               ident in seen_collectors or kind not in COLLECTOR_CAPACITY_L:
                fail("Unknown/duplicate rain collector")
            if collector["capacity_l"]!=COLLECTOR_CAPACITY_L[kind] or
               collector["introduced_stage"] not in STAGES or
               STAGES.index(collector["introduced_stage"])>index or
               not isinstance(collector["site"],str) or
               not IDENT.fullmatch(collector["site"]) or
               collector["open_sky_requires_live_check"] is not True:
                fail("Unreviewed collector capacity, stage, or placement")
            seen_collectors.add(ident)
            kind_counts[kind]+=1
            collector_capacity+=collector["capacity_l"]
        if (kind_counts["crate"],kind_counts["barrel"])!=EXPECTED_COLLECTORS[index]:
            fail("Collector counts do not match cumulative four-stage water plan")
        dry_day_irrigation=quantity(
            water_design["crop_irrigation_l_per_dry_day"],
            "crop_irrigation_l_per_dry_day")
    if not isinstance(doc.get("important_caveats"),list) or len(doc["important_caveats"])<4:
        fail("Missing implementation caveats")
    return {
      "world":world,"settlement":settlement,"stage":stage,"residents":people,
      "regular_residents":regular,"reserve_days":days,
      "food_kcal_required":expected["food_kcal"],
      "potable_water_l_required":expected["potable_water_l"],
      "sanitation_water_l_flow_not_stock":expected["sanitation_water_usage_l_not_stored"],
      "generator_units":genn,"generator_duty_h_day":duty,
      "fuel_l_bookkeeping":fuel,"storage_zones":len(zones),
      "rain_collectors":len(collectors),
      "rainwater_nominal_raw_capacity_l":collector_capacity,
      "rainwater_actual_stored_l":None,
      "rainwater_potable_l":None,
      "estimated_dry_day_irrigation_l_not_in_drinking_budget":dry_day_irrigation,
      "historical_corpse_count_not_current":historical,
      "named_sleeping_places":len(beds),
      "former_chicken_pen_vegetable_plot_target":farming.get("plot_cells_target",0),
      "status":"design_balanced_not_game_resource_verified",
      "blockers":[
        "Unverified installed-item calories and selected item-factory IDs",
        "Unverified B42 FluidContainer fill/purity/persistence, fuel quantities",
        "Unverified native crop tiling/watering/growth; owner reports site cleanup after historical scan, resurvey required",
        "New room roofs, warmth, bed sleepability and second-client save/restart",
        "Stale previous-stage tagged supplies cannot be automatically reconciled without exact tag cleanup",
        "Rainwater collectors require real crafting/native registration, open sky and safe-water purification; not supported by generic decorative placement"
      ],
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",required=True,action="append",
                   help="Private per-stage ledger; may be repeated for four phases")
    p.add_argument("--world",help="Reject private ledger from a different world")
    p.add_argument("--output",help="Optional NEW private report outside repository")
    args=p.parse_args()
    try:
        reports=[validate(read(v)) for v in args.manifest]
        if args.world and any(r["world"]!=args.world for r in reports):
            fail("Manifest world mismatch")
        if len(reports)>1 and (
            len(reports)!=4 or [r["stage"] for r in reports]!=list(STAGES) or
            len({(r["world"],r["settlement"]) for r in reports})!=1):
            fail("For series auditing supply exactly four ordered phases of one settlement")
        report={"schema":"sieger-settlement-budget-review-v1",
                "ready_to_execute_full_stock_simulation":False,
                "stages":reports}
        output=json.dumps(report,ensure_ascii=False,indent=2)+"\n"
        if args.output:
            dest=Path(args.output)
            if dest.is_symlink() or dest.exists() or not dest.parent.is_dir() or \
               dest.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
                fail("Private report must be NEW and outside repository")
            import os
            fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as f:f.write(output)
            print("SAVED",dest)
        else:print(output,end="")
    except (ValueError,OSError,UnicodeError,json.JSONDecodeError) as e:
        p.exit(2,"Settlement resource review: "+str(e)+"\n")
if __name__=="__main__":main()
