#!/usr/bin/env python3
"""Offline integration for Story live session bookkeeping and strict requests."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
CONTROLLER=REPO/"story/livectl.py"


def call(*args,env=None):
    return subprocess.run([sys.executable,str(CONTROLLER),*map(str,args)],
                          capture_output=True,text=True,env=env)


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.repo=root/"repo"
        (self.repo/"story/scenes").mkdir(parents=True)
        self.store=root/"store"
        self.w=self.store/"worlds/story_test"
        (self.w/"data/Lua").mkdir(parents=True)
        (self.w/"story").mkdir(parents=True)
        (self.w/"profile").write_text("mp-test\n")
        (self.w/"story/bundle.lua").write_text("SiegerStoryScenes={schema=1}\n")
        (self.store/"manager").mkdir()
        (self.store/"manager/active-world").write_text("story_test\n")
        self.archives=self.store/"backups/worlds/story_test"
        self.archives.mkdir(parents=True)
        self.first=self.backup("world-a.tar.gz","initial state")
        self.second=self.backup("world-b.tar.gz","committed state")
        self.mockbin=root/"bin"
        self.mockbin.mkdir()
        self.docker=self.mockbin/"docker"
        self.docker.write_text("""#!/usr/bin/env python3
import json, os
base=os.environ["PZ_STORY_STORE_ROOT"]+"/worlds/story_test"
print(json.dumps({"State":{"Running":True},
    "Mounts":[{"Destination":"/root/Zomboid","Source":base+"/data"},
     {"Destination":"/pzomboid-server/media/lua/server/SiegerStoryDirector.lua",
      "Source":os.environ["PZ_STORY_REPO_ROOT"]+"/story/runtime/SiegerStoryDirector.lua"},
     {"Destination":"/pzomboid-server/media/lua/server/ZZ_SiegerStoryScenes.lua",
      "Source":base+"/story/bundle.lua"}]}))
""")
        self.docker.chmod(0o755)
        self.env=os.environ.copy()
        self.env.update({
            "PZ_STORY_REPO_ROOT":str(self.repo),
            "PZ_STORY_STORE_ROOT":str(self.store),
            "PATH":str(self.mockbin)+os.pathsep+self.env["PATH"]
        })
        self.scene={
            "schema":1,"id":"clinic_live_001","world":"story_test",
            "title":"Test live scene","enabled":True,
            "actions":[
                {"id":"note_one","type":"note","at":{"x":3171,"y":12141,"z":0},
                 "placement":"ground","title":"Дневник врача",
                 "pages":["Началось. Ночь темна.","Всё пропало."]},
                {"id":"supplies","type":"loot","at":{"x":3171,"y":12141,"z":0},
                 "placement":"container","selector":{
                    "object_index":2,"sprite":"location_business_office_generic_01_33","class":"IsoObject"},
                 "items":[{"type":"Base.Bandage","count":2}]}
            ]
        }
        (self.repo/"story/scenes/clinic_live_001.json").write_text(
            json.dumps(self.scene,ensure_ascii=False),encoding="utf-8")

    def backup(self,name,content):
        target=self.archives/name
        # Naming emulates manager format.
        target=self.archives/("world-"+name)
        target.write_bytes(content.encode())
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        (self.archives/(target.name+".sha256")).write_text(digest+"  "+target.name+"\n")
        return target

    def run_ok(self,*args):
        process=call(*args,env=self.env)
        self.assertEqual(process.returncode,0,
                         f"{args} failed:\n{process.stdout}\n{process.stderr}")
        return process.stdout

    def run_fail(self,*args):
        p=call(*args,env=self.env)
        self.assertNotEqual(p.returncode,0,f"Unexpected success: {args}")
        return p.stderr

    def state(self):
        return json.loads((self.w/"story/live/session.json").read_text())

    def ack(self,kind="complete",missing=None):
        req=(self.w/"data/Lua/SiegerStoryLiveRequest.txt").read_text()
        rows=req.splitlines()
        header=rows[0].split("\t")
        _,id,world,scene,sha,count=header
        result=[rows[0]]
        for idx,row in enumerate(rows[1:]):
            aid=row.split("\t")[1]
            status=("pending" if idx==missing else "applied") if kind=="complete" else "error"
            result.append("\t".join(["action",aid,status,""]))
        if kind=="complete":
            pending=0 if missing is None else 1
            result.append("\t".join(["end",id,"complete" if pending==0 else "pending",
                                     str(len(rows)-1-pending),str(pending),"0"]))
        else:
            result.append("\t".join(["end",id,"failed","0","0",str(len(rows)-1)]))
        (self.w/"data/Lua/SiegerStoryLiveResult.txt").write_text("\n".join(result)+"\n")

    def test_pre_live_post_evidence_and_non_duplicate_scene(self):
        self.run_ok("check-new","story_test")
        self.run_ok("begin-record","story_test","--backup",self.first)
        self.run_fail("check-new","story_test")
        self.run_fail("pre-commit","story_test")
        self.run_ok("apply-live","story_test","clinic_live_001","--yes")
        packet=(self.w/"data/Lua/SiegerStoryLiveRequest.txt").read_text()
        self.assertIn("note_one",packet)
        self.assertIn("supplies",packet)
        self.assertNotIn("Дневник врача",packet) # plain-text payload forbidden
        self.assertIn("Base.Bandage=2",packet)
        self.assertRegex(packet.splitlines()[0],r"^v1\t[0-9a-f]{32}\tstory_test")
        self.run_fail("apply-live","story_test","clinic_live_001","--yes")
        self.run_fail("pre-commit","story_test")
        self.ack("complete",missing=1)
        self.run_fail("pre-commit","story_test")
        self.ack()
        stdout=self.run_ok("live-status","story_test")
        self.assertIn("complete",stdout)
        self.assertEqual(self.state()["pending_job"],None)
        self.run_ok("pre-commit","story_test")
        self.run_ok("commit-record","story_test","--backup",self.second)
        self.assertEqual(self.state()["status"],"committed")
        self.assertEqual(len(self.state()["applied_scenes"]),1)
        self.run_fail("apply-live","story_test","clinic_live_001","--yes")
        self.run_ok("check-new","story_test")

    def test_invalid_scopes_and_failed_scene_cannot_commit(self):
        self.run_ok("begin-record","story_test","--backup",self.first)
        (self.store/"manager/active-world").write_text("road_home\n")
        self.run_fail("apply-live","story_test","clinic_live_001","--yes")
        (self.store/"manager/active-world").write_text("story_test\n")
        self.scene["actions"][0]["type"]="infected"
        path=self.repo/"story/scenes/clinic_live_001.json"
        path.write_text(json.dumps(self.scene))
        self.run_fail("apply-live","story_test","clinic_live_001","--yes")
        self.scene["actions"][0]["type"]="note"
        path.write_text(json.dumps(self.scene))
        self.run_ok("apply-live","story_test","clinic_live_001","--yes")
        self.ack("failed")
        self.run_fail("pre-commit","story_test")

    def test_requires_verified_correct_before_after(self):
        evil=self.archives/"world-evil.tar.gz"
        evil.write_bytes(b"wrong")
        self.run_fail("begin-record","story_test","--backup",evil)
        self.run_ok("begin-record","story_test","--backup",self.first)
        self.run_fail("commit-record","story_test","--backup",self.first)


if __name__=="__main__":
    unittest.main(verbosity=2)
