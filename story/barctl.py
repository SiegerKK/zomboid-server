#!/usr/bin/env python3
"""Bounded, manual zombie census/clear of Smokey's on story_test, root-only.

This clears loaded active zombies ONCE; it does not permanently prevent new
zombies wandering in. No global spawn suppression or world resets.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
from pathlib import Path
import scanctl

REQUEST="SiegerStoryBarRequest.txt"
RESPONSE="SiegerStoryBarResult.txt"
ID=re.compile(r"[0-9a-f]{32}\Z")


def fail(msg):
    raise ValueError(msg)


def paths(world):
    base=scanctl.lua_dir(world)
    return base/REQUEST,base/RESPONSE


def request(world):
    f,_=paths(world)
    if not f.is_file():
        return None
    if f.is_symlink() or f.stat().st_size>100:
        fail("Unsafe bar control request file")
    raw=f.read_text("ascii")
    m=re.fullmatch(r"v1\t([0-9a-f]{32})\tstory_test\t(inspect|clear)\t(\d{1,3})\n?",raw)
    if not m:
        fail("Malformed previous bar control request")
    return {"id":m[1],"mode":m[2],"expected":int(m[3])}


def result(world,wanted_id):
    _,path=paths(world)
    if not path.is_file():
        return {"status":"pending"}
    if path.is_symlink() or path.stat().st_size>400:
        fail("Unsafe bar response file")
    m=re.fullmatch(
        r"v1\t([0-9a-f]{32})\tstory_test\t(inspect|clear)\t(complete|error)"
        r"\t(\d{1,3})\t(\d{1,3})\t([a-z_]+)\n?",
        path.read_text("ascii")
    )
    if not m:
        fail("Invalid bar result protocol")
    if m[1]!=wanted_id:
        return {"status":"pending"}
    return {"request_id":m[1],"mode":m[2],"status":m[3],
            "zombies":int(m[4]),"removed":int(m[5]),"reason":m[6]}


def require_world(world):
    if world!="story_test":
        fail("Only story_test may be inspected or cleared")
    scanctl.assert_ready(world)
    mounts=scanctl.docker_mounts()
    if "/pzomboid-server/media/lua/server/SiegerStoryBarControl.lua" not in mounts:
        fail("Bar control server module not mounted; install and restart first")


def run(args):
    require_world(args.world)
    if not args.yes:
        print("PREVIEW ONLY: no action queued. Include --yes after reviewing the scene.")
        return
    if args.mode=="clear" and args.expect is None:
        fail("Clear requires --expect equal to last completed inspect count")
    if args.mode=="inspect" and args.expect is not None:
        fail("Inspect must not set --expect")
    prev=request(args.world)
    if prev:
        resp=result(args.world,prev["id"])
        if resp["status"]=="pending":
            fail("Previous bar control request is pending")
        if resp["status"]=="error" and not args.acknowledge_failed:
            fail("Prior operation failed; inspect game manually before --acknowledge-failed")
        if args.mode=="clear":
            if prev["mode"]!="inspect" or resp["status"]!="complete":
                fail("Before any clear, run a fresh successful inspect")
            if args.expect!=resp["zombies"]:
                fail("Expected count differs from last on-server census")
    elif args.mode=="clear":
        fail("Clear requires a prior inspect")
    rid=secrets.token_hex(16)
    expected=args.expect if args.mode=="clear" else 0
    req,_=paths(args.world)
    scanctl.atomic_request(req,f"v1\t{rid}\tstory_test\t{args.mode}\t{expected}\n")
    print("Queued",args.mode,"for Smokey's only; request_id:",rid)
    print("Poll: sudo pz story bar-zombies-status story_test")


def status(args):
    if args.world!="story_test":
        fail("Only story_test")
    req=request(args.world)
    if not req:
        fail("No bar control operation was requested")
    resp=result(args.world,req["id"])
    print(resp)
    if resp["status"]=="error":
        fail("Server rejected operation, inspect logs before any retry")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    for operation in ("inspect","clear"):
        c=sub.add_parser(operation)
        c.add_argument("world")
        c.add_argument("--yes",action="store_true")
        c.add_argument("--expect",type=int)
        c.add_argument("--acknowledge-failed",action="store_true")
        c.set_defaults(handler=run,mode=operation)
    c=sub.add_parser("status")
    c.add_argument("world")
    c.set_defaults(handler=status)
    a=p.parse_args()
    try:
        a.handler(a)
    except (ValueError,OSError,UnicodeError) as ex:
        p.exit(2,"Story bar: "+str(ex)+"\n")

if __name__=="__main__":
    main()
