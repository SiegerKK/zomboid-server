#!/usr/bin/env python3
"""Sequence one existing build stage and one combined supply batch.

No new game protocol: use constructionctl, batchctl, their exact receipts and
native build ledger. A small world-local receipt journal prevents automatic
reissuance of non-idempotent supplies. Run through pz's operation lock.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import time

import batchctl as batch
import constructionctl as build
import constructionsite
import livectl
import scanctl


def fail(message):
    raise ValueError(message)


def read_json(path, limit=build.MAX_BYTES):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        fail("Missing, unsafe or oversized setup input: " + str(path))
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(path.read_text("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: fail("Non-finite JSON number"))


def encoded(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


SCENES = {"survival_farm": Path(__file__).resolve().parent / "camp" / "scenes" / "survival_farm"}


def resolve_inputs(args):
    """Resolve an explicit built-in scene; never load arbitrary scene paths."""
    scene = getattr(args, "scene", None)
    if scene:
        if scene not in SCENES or args.file or args.batch or args.source_world:
            fail("Use a known --scene without --file, --batch or --source-world")
        if args.stage not in {"phase01", "phase02", "phase03", "phase04"}:
            fail("Scene stage must be phase01..phase04")
        folder = SCENES[scene]
        if any(p.is_symlink() for p in (folder, *folder.parents)):
            fail("Bundled scene directory must not be a symlink")
        args.file = str(folder / "stages_build.json")
        suffixes = ("items", "liquids") + (("bedding",) if args.stage != "phase01" else ())
        args.batch = [str(folder / f"{args.stage}_{suffix}_batch.json") for suffix in suffixes]
    elif not args.file or not args.batch:
        fail("Use --scene or both --file and --batch")


def prepare(args):
    args = argparse.Namespace(**vars(args))
    resolve_inputs(args)
    if not scanctl.WORLD.fullmatch(args.world):
        fail("Invalid destination world")
    plan = read_json(args.file)
    source_world = args.source_world or plan.get("world")
    if not isinstance(source_world, str) or not scanctl.WORLD.fullmatch(source_world):
        fail("Invalid source world in plan")
    build.prepare(plan, source_world, args.stage)
    plan["world"] = args.world  # Explicit source/destination; never switches worlds.
    compiled = build.prepare(plan, args.world, args.stage)
    groups, inputs, seen = [], [], set()
    for filename in args.batch:
        path = Path(filename)
        if path.resolve() in seen:
            fail("Repeated supply input")
        seen.add(path.resolve())
        doc = read_json(path, batch.MAX_INPUT)
        batch.compile_plan(doc, source_world)
        for group in doc["actions"]:
            if group["target"] not in ("container", "ground") or any(
                    change["op"] != "add" for change in group["changes"]):
                fail("Setup supplies allow container/ground additions only")
            if group.get("source", "square") != "square":
                fail("Setup does not stock corpse/static containers")
        groups.extend(doc["actions"])
        inputs.append(str(path))
    supplies = {"schema": 1, "world": args.world, "actions": groups}
    stock_rows = batch.compile_plan(supplies, args.world)
    if len(encoded(supplies).encode("utf-8")) > batch.MAX_INPUT:
        fail("Combined supply batch exceeds the existing input budget")
    stock_digest = digest("\n".join(stock_rows) + "\n")
    identity = {"world": args.world, "source_world": source_world,
                "settlement": compiled["settlement"], "stage": args.stage,
                "build_sha256": compiled["digest"], "stock_sha256": stock_digest,
                "requires": compiled["requires"]}
    return plan, supplies, compiled, identity, inputs


def survey_check(path, world, compiled, supplies, *, check_build=True):
    data, _ = constructionsite.load_survey(path, world)
    squares, objects, containers = {}, {}, {}
    for row in data["records"]:
        if not isinstance(row, dict):
            fail("Invalid survey row")
        kind = row.get("kind")
        if kind not in ("square", "object", "container"):
            continue
        at = tuple(row.get(key) for key in ("x", "y", "z"))
        if any(type(n) is not int for n in at):
            fail("Invalid survey tile")
        if kind == "square":
            if at in squares or type(row.get("loaded")) is not bool:
                fail("Duplicate or invalid survey square")
            squares[at] = row["loaded"]
        elif kind == "object":
            objects.setdefault(at, []).append(row)
        else:
            key = (at, row.get("source", "square"), row.get("object_index"),
                   row.get("container_index"))
            if key in containers:
                fail("Duplicate survey container")
            containers[key] = row
    future = {}
    targets = set()
    for wire in compiled["rows"]:
        row = wire.split("\t")
        at = tuple(map(int, row[4:7]))
        targets.add(at)
        if row[2:4] == ["place", "storage"]:
            tag = f'{compiled["settlement"]}:{compiled["stage"]}:{row[1]}'
            future[tag] = at
        if check_build and row[2] in ("barricade", "remove_exact", "remove_tag"):
            matches = [o for o in objects.get(at, []) if
                       o.get("class") == row[3] and o.get("sprite") == row[8] and
                       (row[7] == "-" or o.get("face") == row[7]) and
                       (o.get("construction_tag") == row[11] if row[2] == "remove_tag"
                        else o.get("object_index") == int(row[12]))]
            if len(matches) != 1:
                fail("Current object selector does not match survey: " + row[1])
            if row[2] == "barricade":
                observed=matches[0]
                if observed.get("window_barricaded_same") is not False or (
                        row[11]=="outside" and
                        observed.get("window_barricaded_opposite") is not False):
                    fail("Window already barricaded or windows survey missing: " + row[1])
                if row[11]=="outside":
                    adjacent=(at[0]-(row[7]=="W"),at[1]-(row[7]=="N"),at[2])
                    targets.add(adjacent)
                    if not isinstance(observed.get("room"),str):
                        fail("Native window room side not observed: " + row[1])
    for group in supplies["actions"]:
        at = tuple(group["at"])
        targets.add(at)
        if group["target"] == "ground":
            surface=group.get("surface")
            if surface:
                tag=surface.get("construction_tag")
                if tag and check_build:
                    built=[r.split("\t") for r in compiled["rows"]
                        if r.split("\t")[2:4]==["place","decor"] and
                        f"{compiled['settlement']}:{compiled['stage']}:{r.split(chr(9))[1]}"==tag]
                    if len(built)!=1 or tuple(map(int,built[0][4:7]))!=at:
                        fail("Surface tag does not match a newly placed work table")
                else:
                    options=[o for o in objects.get(at,[]) if
                        "sprite" in surface and o.get("sprite")==surface["sprite"]]
                    if tag:
                        options=[o for o in objects.get(at,[]) if
                            o.get("construction_tag")==tag]
                    if (len(options)!=1 or
                            options[0].get("class")!="IsoObject" or
                            options[0].get("table_surface") is not True or
                            options[0].get("surface_offset_no_table")!=surface["height_units"]):
                        fail("Ground surface is not an exact measured tabletop")
            continue
        tag = group.get("construction_tag")
        if tag in future and check_build:
            if future[tag] != at or group["container_type"] != "crate" or group["container_index"] != 0:
                fail("Supply does not match the crate planned in this stage")
            continue  # The native batch will resolve it AFTER build acknowledgement.
        index = group.get("object_index")
        sprite = group.get("object_sprite")
        if sprite:
            matches = [o for o in objects.get(at, []) if o.get("sprite") == sprite]
            if len(matches) != 1:
                fail("Sprite supply container not uniquely observed: " + sprite)
            index = matches[0].get("object_index")
        if tag:
            matches = [o for o in objects.get(at, []) if o.get("construction_tag") == tag]
            if len(matches) != 1:
                fail("Tagged supply container not uniquely observed: " + tag)
            index = matches[0].get("object_index")
        found = containers.get((at, "square", index, group["container_index"]))
        if found is None or found.get("container_type") != group["container_type"]:
            fail("Current container selector does not match survey at " + str(at))
    missing = sorted(at for at in targets if squares.get(at) is not True)
    if missing:
        fail("Setup target squares not fully observed/loaded: " + str(missing[:8]))
    return {"loaded_target_tiles": len(targets), "survey_sha256": digest(encoded(data)),
            "freshness": "operator_supplied_not_trusted_capture_time"}


def capture(function, args):
    with contextlib.redirect_stdout(io.StringIO()) as stream:
        function(args)
    return json.loads(stream.getvalue())


def history(world):
    rows = capture(build.history, argparse.Namespace(world=world))["completed"]
    return {(row["settlement"], row["stage"]): row["sha256"] for row in rows}


def journal_dir(world, settlement, stage):
    root = scanctl.slot(world) / "story" / "setup"
    folder = root / settlement / stage
    for path in (root.parent, root, folder.parent, folder):
        if path.is_symlink():
            fail("Setup journal directory must not be a symlink")
    return folder


def save(path, state):
    livectl.atomic_write(path, encoded(state))
    # Also persist the rename before any non-idempotent game request.
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def await_receipt(world, kind, wanted, timeout):
    module = build if kind == "build" else batch
    deadline = time.monotonic() + timeout
    while True:
        current = module.previous(world)
        if not current or current["id"] != wanted["id"]:
            fail("Setup request channel was replaced; inspect before continuing")
        result = module.receipt(world, wanted)
        if result["status"] == "error":
            fail("Native request failed; partial_possible, do not replay: " + encoded(result))
        if result["status"] == "complete":
            if result.get("applied") != wanted["count"] or result.get("total") != wanted["count"]:
                fail("Incomplete counters in complete receipt")
            return result
        if time.monotonic() >= deadline:
            fail("Receipt timeout; request may still execute. Resume polls it, never resends it")
        time.sleep(0.25)


def validate_state(state, build_count, stock_count):
    steps = state.get("steps")
    if (state.get("status") not in ("running", "server_applied") or
            not isinstance(steps, dict) or set(steps) - {"build", "stock"}):
        fail("Invalid setup journal")
    for kind, step in steps.items():
        if not isinstance(step, dict) or step.get("status") not in ("intent", "queued", "complete"):
            fail("Invalid setup step")
        if step["status"] == "intent":
            continue
        request = step.get("request", {})
        wanted_hash = state["identity"]["build_sha256" if kind == "build" else "stock_sha256"]
        count = build_count if kind == "build" else stock_count
        if (not build.RID.fullmatch(str(request.get("id", ""))) or
                request.get("count") != count or
                request.get("digest", request.get("hash")) != wanted_hash):
            fail("Corrupt setup request identity")
        if step["status"] == "complete":
            receipt = step.get("receipt", {})
            if (receipt.get("status") != "complete" or receipt.get("request_id") != request["id"] or
                    receipt.get("sha256") != wanted_hash or receipt.get("applied") != count or
                    receipt.get("total") != count):
                fail("Corrupt completed setup receipt")
    if "stock" in steps and steps.get("build", {}).get("status") != "complete":
        fail("Supply step recorded before completed construction")
    if state["status"] == "server_applied" and any(
            steps.get(k, {}).get("status") != "complete" for k in ("build", "stock")):
        fail("Missing completed setup steps")


def supply_signature(doc):
    # Retrying a rejected shipment may redistribute containers, never increase
    # quantities, change item/fluid definitions or move the ground dressing.
    from collections import Counter
    counts = Counter()
    ground = []
    for group in doc['actions']:
        if group['target'] == 'ground':
            ground.append(group)
        else:
            for change in group['changes']:
                key = encoded({k:v for k,v in change.items() if k != 'count'})
                counts[key] += change['count']
    return counts, sorted(encoded(g) for g in ground)


def redistribute_failed_stock(state, identity, compiled, supplies, args, folder, ledger):
    old_identity = state.get('identity', {})
    if (state.get('schema') != 1 or state.get('status') != 'running' or
            {k:v for k,v in old_identity.items() if k != 'stock_sha256'} !=
            {k:v for k,v in identity.items() if k != 'stock_sha256'}):
        fail('Stock retry must keep the same world and completed build identity')
    step = state.get('steps', {}).get('stock', {})
    wanted = step.get('request', {})
    validate_state(state, compiled['actions'], wanted.get('count'))
    if (state.get('steps', {}).get('build', {}).get('status') != 'complete' or
            step.get('status') != 'queued' or
            ledger.get((compiled['settlement'], args.stage)) != compiled['digest']):
        fail('Stock retry requires a confirmed unchanged native build')
    current = batch.previous(args.world)
    if current != wanted:
        fail('Stock retry channel changed; do not resend')
    result = batch.receipt(args.world, current)
    if (result.get('status') != 'error' or result.get('applied') != 0 or
            result.get('reason') != 'preflight_failed' or result.get('total') != wanted['count']):
        fail('Stock retry requires definitive preflight_failed with zero applied')
    old_stock = read_json(folder / 'stock.json', batch.MAX_INPUT)
    old_hash = digest('\n'.join(batch.compile_plan(old_stock,args.world))+'\n')
    if old_hash != old_identity['stock_sha256']:
        fail('Archived failed shipment does not match its identity')
    if supply_signature(old_stock) != supply_signature(supplies):
        fail('Stock redistribution must preserve every item count, fluid and ground action')
    proof = survey_check(args.survey,args.world,compiled,supplies,check_build=False)
    audit = {'identity':old_identity,'request':wanted,'receipt':result,'stock':old_stock,
             'replacement_sha256':identity['stock_sha256'],'survey':proof}
    livectl.atomic_write(folder / ('failed-stock-'+wanted['id']+'.json'),encoded(audit),exclusive=True)
    state.setdefault('stock_retries',[]).append({'request_id':wanted['id'],
        'old_sha256':old_hash,'replacement_sha256':identity['stock_sha256']})
    state['identity'] = identity
    state['survey'] = proof
    del state['steps']['stock']
    return wanted['id']


def run(args):
    retry_stock = getattr(args,"retry_stock",False)
    retry_failed_id = None
    if retry_stock and (not args.yes or args.status):
        fail("--retry-stock requires explicit --yes")
    if args.resume and not args.yes:
        fail("--resume requires --yes; no automatic retries")
    plan, supplies, compiled, identity, inputs = prepare(args)
    folder = journal_dir(args.world, compiled["settlement"], args.stage) if (args.yes or args.status) else None
    state_path = folder / "receipt.json" if folder else None
    if args.status:
        state = read_json(state_path)
        if state.get("identity") != identity:
            fail("Setup inputs differ from the recorded attempt")
        validate_state(state, compiled["actions"], len(batch.compile_plan(supplies, args.world)))
        print(encoded(state), end="")
        return
    report = {**identity, "build_actions": compiled["actions"],
              "supply_actions": len(batch.compile_plan(supplies, args.world)),
              "supply_files": inputs, "mode": "apply" if args.yes else "preview",
              "native_gameplay_accepted": False}
    if not args.yes:
        if args.survey:
            report["survey"] = survey_check(args.survey, args.world, compiled, supplies)
        print(encoded(report), end="")
        print("PREVIEW ONLY: no requests, files, server or world changes")
        return
    if os.geteuid() != 0:
        fail("Setup writes require root via pz")
    backup_name = getattr(args, "backup_name", None)
    if backup_name:
        import re
        if not re.fullmatch(r"world-[A-Za-z0-9_-]+\.tar\.gz", backup_name):
            fail("Invalid manager backup basename")
        args.backup = str(scanctl.STORE / "backups" / "worlds" / args.world / backup_name)
    if not args.survey or not args.backup:
        fail("Setup apply needs --survey CURRENT.json and --backup verified-world.tar.gz")
    if compiled["allow_existing"] and not args.allow_existing:
        fail("Existing-window changes require --allow-existing")
    scanctl.assert_module_ready(args.world, "SiegerAdminConstruction")
    scanctl.assert_module_ready(args.world, "SiegerStoryBatch")
    backup, sha = livectl.checksum_backup(args.world, args.backup)
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    lock_path = folder.parent / ".setup.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("Another setup is running for this settlement")
        existing = history(args.world)
        for dep in compiled["requires"]:
            required = build.prepare(plan, args.world, dep)
            if existing.get((compiled["settlement"], dep)) != required["digest"]:
                fail("Missing or changed completed build prerequisite: " + dep)
            prior = read_json(folder.parent / dep / "receipt.json")
            previous_identity = prior.get("identity", {})
            if (prior.get("status") != "server_applied" or
                    any(previous_identity.get(key) != value for key, value in (
                        ("world", args.world), ("settlement", compiled["settlement"]),
                        ("stage", dep), ("build_sha256", required["digest"])))):
                fail("Prerequisite setup supplies not acknowledged: " + dep)
            validate_state(prior, required["actions"],
                           prior.get("steps", {}).get("stock", {}).get("request", {}).get("count"))
        if state_path.exists() or state_path.is_symlink():
            state = read_json(state_path)
            if retry_stock:
                retry_failed_id = redistribute_failed_stock(state,identity,compiled,
                    supplies,args,folder,existing)
            elif state.get("schema") != 1 or state.get("identity") != identity:
                fail("Setup inputs changed; refusing automatic replay")
            validate_state(state, compiled["actions"], len(batch.compile_plan(supplies, args.world)))
            if state.get("status") == "server_applied":
                if existing.get((compiled["settlement"], args.stage)) != compiled["digest"]:
                    fail("Native build ledger changed/was restored; manual inspection required")
                print("ALREADY APPLIED: no build or supplies repeated")
                print(encoded(state), end="")
                return
            if not args.resume and not retry_stock:
                fail("An attempt exists. --resume only continues known requests; never retries failed mutations")
        else:
            if args.resume or retry_stock:
                fail("No setup attempt to resume")
            if (compiled["settlement"], args.stage) in existing:
                fail("Stage already built outside this setup; inspect/adopt manually, do not restock automatically")
            state = {"schema": 1, "identity": identity, "status": "running",
                     "backup": {"path": backup, "sha256": sha}, "steps": {}}
        # A pending request needs receipt reconciliation, not a contradictory
        # pre-build scan of a stage which may already have appeared in the world.
        if not state["steps"]:
            state["survey"] = survey_check(args.survey, args.world, compiled, supplies)
            for module in (build, batch):
                old = module.previous(args.world)
                if old:
                    result = module.receipt(args.world, old)
                    if result["status"] != "complete" or result.get("applied") != old["count"]:
                        fail("Previous native request is pending/failed; setup will not overwrite it")
        if state["steps"].get("build", {}).get("status") == "complete":
            if existing.get((compiled["settlement"], args.stage)) != compiled["digest"]:
                fail("Native stage ledger missing or changed after build receipt")
        # Keep exact retargeted inputs in the private world-local audit folder.
        build_path, stock_path = folder / "build.json", folder / "stock.json"
        livectl.atomic_write(build_path, encoded(plan))
        livectl.atomic_write(stock_path, encoded(supplies))
        save(state_path, state)
        for kind, module, filename in (("build", build, build_path), ("stock", batch, stock_path)):
            step = state["steps"].get(kind)
            if step and step.get("status") == "complete":
                continue
            if step is None:
                # Refuse unresolved work in either existing request channel.
                old = module.previous(args.world)
                if old:
                    receipt = module.receipt(args.world, old)
                    retry_rejected = kind == "stock" and old['id'] == retry_failed_id
                    if not retry_rejected and (receipt["status"] != "complete" or receipt.get("applied") != old["count"]):
                        fail("Previous native request is pending/failed; setup will not overwrite it")
                step = {"status": "intent"}
                state["steps"][kind] = step
                save(state_path, state)  # Crash after this point must not resend.
                native = argparse.Namespace(command="apply", world=args.world,
                    file=str(filename), stage=args.stage, survey=None, yes=True,
                    allow_existing=args.allow_existing,
                    acknowledge_failed=(kind == "stock" and retry_failed_id is not None))
                (build.preview if kind == "build" else batch.execute)(native)
                wanted = module.previous(args.world)
                expected = compiled["digest"] if kind == "build" else identity["stock_sha256"]
                expected_count = compiled["actions"] if kind == "build" else report["supply_actions"]
                if (not wanted or wanted.get("digest", wanted.get("hash")) != expected or
                        wanted.get("count") != expected_count or (old and wanted["id"] == old["id"])):
                    fail("Queued request identity mismatch")
                step.update(status="queued", request=wanted)
                save(state_path, state)
            if step.get("status") == "intent" or not step.get("request"):
                fail("Interrupted queue with unknown request ID; inspect manually, do not resend")
            result = await_receipt(args.world, kind, step["request"], args.timeout)
            if kind == "build" and history(args.world).get((compiled["settlement"], args.stage)) != compiled["digest"]:
                fail("Build receipt has no matching native stage ledger; supplies not sent")
            step.update(status="complete", receipt=result)
            save(state_path, state)
        state["status"] = "server_applied"
        state["native_gameplay_accepted"] = False
        save(state_path, state)
        print("SERVER APPLIED: take a new post-stage scan and run build verify; gameplay not certified")
        print(encoded({**report, "receipt": str(state_path), "build_file": str(build_path)}), end="")


def add_subcommand(subs):
    parser = subs.add_parser("setup", allow_abbrev=False, help="One build stage then one combined supply batch; preview by default")
    parser.add_argument("world")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--file")
    inputs.add_argument("--scene", choices=sorted(SCENES), help="Bundled staged scene, retargeted to WORLD; preview by default")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--batch", action="append", help="Supply JSON; repeat to combine before preflight")
    parser.add_argument("--source-world", help="Explicit origin when applying the plan to a separately prepared copy")
    parser.add_argument("--survey", help="Current complete target-world AreaScan; never relabeled")
    backups = parser.add_mutually_exclusive_group()
    backups.add_argument("--backup", help="Existing manager cold backup; verified, not created/restored")
    backups.add_argument("--backup-name", help="Manager archive basename in destination-world backups; limited gateway compatible")
    parser.add_argument("--allow-existing", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-stock", action="store_true", help="Explicit redistribution retry only after definitive zero-applied stock preflight failure")
    parser.add_argument("--timeout", type=int, choices=range(1, 601), metavar="SECONDS", default=120)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--yes", action="store_true")
    mode.add_argument("--status", action="store_true")
    parser.set_defaults(handler=run)
