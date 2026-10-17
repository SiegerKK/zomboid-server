#!/usr/bin/env python3
"""Check Story Director Compose overlay cannot erase important game mounts/ports."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
ENV=os.environ.copy()
ENV["PZ_STORY_BUNDLE"]="./story/examples/empty_bundle.lua"
ENV["PZ_SECRETS_FILE"]="./.env.example"
ENV["PZ_TEST_SECRETS_FILE"]="./.env.example"


def config(filenames):
    cmd=["docker","compose","--env-file",".env.example"]
    for filename in filenames:
        cmd.extend(["-f", filename])
    cmd.extend(["config","--format","json"])
    cp=subprocess.run(cmd,cwd=REPO,env=ENV,capture_output=True,text=True,check=True)
    return json.loads(cp.stdout)["services"]["zomboid"]


def mounts(service):
    return {v["target"] for v in service.get("volumes", [])}


def ports(service):
    return {(str(p.get("published")),p["protocol"]) for p in service.get("ports", [])}


base=config(["compose.yaml"])
assert "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua" not in mounts(base)
assert ports(base)=={("16261","udp"),("16262","udp")}
assert all("/root/Zomboid" in mounts(base) for _ in range(1))
assert int(base["mem_limit"])==12884901888

with_story=config(["compose.yaml","compose.story.yaml"])
assert ports(with_story)==ports(base)
assert mounts(base)<=mounts(with_story)
assert "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua" in mounts(with_story)
assert "/pzomboid-server/media/lua/server/ZZ_SiegerStoryScenes.lua" in mounts(with_story)

modded=config(["compose.yaml","compose.mods.yaml"])
with_both=config(["compose.yaml","compose.mods.yaml","compose.story.yaml"])
assert ports(with_both)==ports(base)
assert mounts(modded)<=mounts(with_both)
assert mounts(with_story)<=mounts(with_both) | mounts(base)
assert "/bootstrap/ZombieBuddy.jar" in mounts(with_both)
assert "/bootstrap/image-entrypoint.sh" in mounts(with_both)
assert "/bootstrap/run-redacted.py" in mounts(with_both)
assert int(with_both["mem_limit"])==12884901888
assert "/pzomboid-server/media/lua/server/SiegerRuntimeAudit.lua" in mounts(with_both)
for mount in with_both["volumes"]:
    if mount["target"] in (
        "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua",
        "/pzomboid-server/media/lua/server/ZZ_SiegerStoryScenes.lua",
        "/pzomboid-server/media/lua/server/SiegerRuntimeAudit.lua",
        "/root/.local/share/Steam/steamapps/workshop",
        "/bootstrap/ZombieBuddy.jar",
    ):
        assert mount.get("read_only") is True, mount["target"]
print("PASS: story overlay preserves all game mounts, TLOU agent, UDP ports and 12-GiB memory cap")
