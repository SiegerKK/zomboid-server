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
assert "/pzomboid-server/media/lua/server/SiegerStoryAreaScan.lua" not in mounts(base)
assert "/pzomboid-server/media/lua/server/SiegerStoryRadio.lua" not in mounts(base)
assert "/pzomboid-server/media/lua/server/SiegerStoryOps.lua" not in mounts(base)
assert ports(base)=={("16261","udp"),("16262","udp")}
assert all("/root/Zomboid" in mounts(base) for _ in range(1))
assert int(base["mem_limit"])==12884901888

with_story=config(["compose.yaml","compose.story.yaml"])
assert ports(with_story)==ports(base)
assert mounts(base)<=mounts(with_story)
assert "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua" in mounts(with_story)
assert "/pzomboid-server/media/lua/server/SiegerStoryAreaScan.lua" in mounts(with_story)
assert "/pzomboid-server/media/lua/server/SiegerStoryRadio.lua" in mounts(with_story)
assert "/pzomboid-server/media/lua/server/SiegerStoryOps.lua" in mounts(with_story)
assert "/pzomboid-server/media/lua/server/ZZ_SiegerStoryScenes.lua" in mounts(with_story)

modded=config(["compose.yaml","compose.mods.yaml"])
with_both=config(["compose.yaml","compose.mods.yaml","compose.story.yaml"])
assert ports(with_both)==ports(base)
assert mounts(modded)<=mounts(with_both)
assert mounts(with_story)<=mounts(with_both) | mounts(base)
assert "/bootstrap/ZombieBuddy.jar" in mounts(with_both)
assert "/pzomboid-server/media/lua/server/SiegerStoryAreaScan.lua" in mounts(with_both)
assert "/bootstrap/image-entrypoint.sh" in mounts(with_both)
assert "/bootstrap/run-redacted.py" in mounts(with_both)
assert int(with_both["mem_limit"])==12884901888
assert "/pzomboid-server/media/lua/server/SiegerRuntimeAudit.lua" in mounts(with_both)
for mount in with_both["volumes"]:
    if mount["target"] in (
        "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua",
        "/pzomboid-server/media/lua/server/SiegerStoryAreaScan.lua",
        "/pzomboid-server/media/lua/server/SiegerStoryRadio.lua",
        "/pzomboid-server/media/lua/server/SiegerStoryOps.lua",
        "/pzomboid-server/media/lua/server/ZZ_SiegerStoryScenes.lua",
        "/pzomboid-server/media/lua/server/SiegerRuntimeAudit.lua",
        "/root/.local/share/Steam/steamapps/workshop",
        "/bootstrap/ZombieBuddy.jar",
    ):
        assert mount.get("read_only") is True, mount["target"]
print("PASS: story overlay preserves all game mounts, TLOU agent, UDP ports and 12-GiB memory cap")

# Installing a local client pack must also activate its Mod ID in MP.
ENV["PZ_STORY_RADIO_MODS"]="ZombieBuddy;StarlitLibrary;ZomboidForge;TLOU_Infected_MP;Viewpoint;ImmersiveDriving;SiegerRadio"
radio=config(["compose.yaml","compose.mods.yaml","compose.story.yaml","compose.radio.yaml"])
# Explicit radio overlay replaces unsafe vanilla Lua injections only.
removed={m for m in mounts(with_both) if m.startswith('/pzomboid-server/media/lua/server/')}
assert mounts(with_both)-removed<=mounts(radio)
assert not any(m.startswith('/pzomboid-server/media/lua/') for m in mounts(radio))
assert '/root/Zomboid/Lua/SiegerStoryBundle.txt' in mounts(radio)
assert (REPO/'mods/SiegerRadio/42/media/lua/server/SiegerRadioStation.lua').is_file()
assert not (REPO/'story/runtime/SiegerRadioStation.lua').exists()
assert ports(radio)==ports(base)
assert radio["environment"]["MODS"]==ENV["PZ_STORY_RADIO_MODS"]
assert int(radio["mem_limit"])==12884901888
pack=[m for m in radio["volumes"] if m["target"]=="/root/Zomboid/mods/SiegerRadio"]
assert len(pack)==1 and pack[0].get("read_only") is True
print("PASS: radio opt-in activates exactly the selected mods and preserves mounts")

# A client-only Java declaration is parsed too early by ZombieBuddy 2.3.4
# for /root/Zomboid local paths. Dedicated metadata must not expose it.
metadata_target='/root/Zomboid/mods/SiegerRadio/42/mod.info'
metadata=[v for v in radio['volumes'] if v['target']==metadata_target]
assert len(metadata)==1 and metadata[0].get('read_only') is True
assert Path(metadata[0]['source']).resolve()==(REPO/'config/radio-server-mod.info').resolve()
client=(REPO/'mods/SiegerRadio/42/mod.info').read_text().splitlines()
server=(REPO/'config/radio-server-mod.info').read_text().splitlines()
assert server==[line for line in client if not line.startswith(('javaJarFile=','javaPkgName='))]
assert any(line.startswith('javaJarFile=media/java/client/') for line in client)
print('PASS: dedicated radio metadata preserves client identity/dependencies and exposes no client Java loader entry')
