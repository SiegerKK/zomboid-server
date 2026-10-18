#!/usr/bin/env python3
"""Read-only tests of combined Story admin plans and exact receipts."""
import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import batchctl

DATA={
 "schema":1,"world":"story_test","actions":[
 {"target":"vehicle","id":253,"script":"Base.PickUpTruck",
  "at":[10620,9209,0],"changes":[
   {"op":"condition","part":"Engine","expect":61,"value":100},
   {"op":"fuel","expect":9.5,"value":30.5},
   {"op":"battery","expect":0.5,"value":0.95},
   {"op":"add","part":"TruckBed","item":"Example.CustomItem","count":18},
   {"op":"remove","part":"GloveBox","item":"Base.Bandage","count":6}]},
 {"target":"player","username":"operator","changes":[
   {"op":"heal"},{"op":"stat","name":"hunger","value":0},
   {"op":"add","item":"Example.CustomItem","count":20},
   {"op":"remove","item":"Base.Plank","count":8}]},
 {"target":"container","at":[10621,9209,0],"object_index":4,
  "container_index":0,"container_type":"counter","changes":[
   {"op":"add","item":"Example.CustomItem","count":21}]},
 {"target":"ground","at":[10622,9209,0],"changes":[
   {"op":"add","item":"Base.Bandage","count":3,"offset":[0.25,0.75,0]},
   {"op":"remove","item":"Base.Screwdriver","count":2}]}
]}

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.world=self.root/"worlds"/"story_test"
        (self.world/"data"/"Lua").mkdir(parents=True)
        (self.world/"profile").write_text("ok")
        self.plan=self.root/"edits.json"
        self.plan.write_text(json.dumps(DATA))
        self.old=batchctl.scanctl.STORE
        batchctl.scanctl.STORE=self.root
        self.addCleanup(setattr,batchctl.scanctl,"STORE",self.old)
    def args(self,yes=False):
        return argparse.Namespace(world="story_test",file=str(self.plan),
                                  yes=yes,acknowledge_failed=False)
    def test_compiler_accepts_installed_mod_types_and_batch(self):
        rows=batchctl.compile_plan(DATA,"story_test")
        self.assertEqual(len(rows),12)
        self.assertTrue(all(len(row.split("\t"))==12 for row in rows))
        self.assertTrue(any("Example.CustomItem" in row for row in rows))
        self.assertTrue(any("\theal\t" in row for row in rows))
        self.assertTrue(any("\tground\t" in "\t"+row for row in rows))
    def test_preview_never_queues(self):
        batchctl.execute(self.args())
        self.assertFalse(batchctl.paths("story_test")[0].exists())
    def test_exact_receipt_and_pending_duplicate_guard(self):
        with patch.object(batchctl.scanctl,"assert_module_ready"):
            batchctl.execute(self.args(yes=True))
            meta=batchctl.previous("story_test")
            self.assertEqual(meta["count"],12)
            with self.assertRaisesRegex(ValueError,"pending"):
                batchctl.execute(self.args(yes=True))
            _,res=batchctl.paths("story_test")
            res.write_text("v1\t"+meta["id"]+"\tstory_test\t"+meta["hash"]+
                           "\tcomplete\t12\t12\tserver_applied\n")
            self.assertEqual(batchctl.receipt("story_test",meta)["applied"],12)
            batchctl.execute(self.args(yes=True))
            self.assertNotEqual(batchctl.previous("story_test")["id"],meta["id"])
    def test_no_wrong_world_or_duplicate_json_keys(self):
        with self.assertRaisesRegex(ValueError,"world/schema"):
            batchctl.compile_plan(DATA,"road_home")
        self.plan.write_text('{"schema":1,"schema":1,"world":"story_test","actions":[]}')
        with self.assertRaisesRegex(ValueError,"Duplicate JSON"):
            batchctl.load(self.plan,"story_test")
    def test_arbitrary_lua_strings_and_invalid_ground_request_refused(self):
        bad={"schema":1,"world":"story_test","actions":[
            {"target":"player","username":"operator","changes":[
                {"op":"add","item":"os.execute()","count":1}]}]}
        with self.assertRaisesRegex(ValueError,"identifier"):
            batchctl.compile_plan(bad,"story_test")
        bad={"schema":1,"world":"story_test","actions":[
            {"target":"ground","at":[1,2,0],"changes":[
                {"op":"remove","item":"Base.Plank","world_index":0,"count":2}]}]}
        with self.assertRaisesRegex(ValueError,"count=1"):
            batchctl.compile_plan(bad,"story_test")
    def test_failed_receipt_requires_review(self):
        with patch.object(batchctl.scanctl,"assert_module_ready"):
            batchctl.execute(self.args(yes=True))
            meta=batchctl.previous("story_test")
            _,res=batchctl.paths("story_test")
            res.write_text("v1\t"+meta["id"]+"\tstory_test\t"+meta["hash"]+
                           "\terror\t3\t12\tpartial_possible\n")
            self.assertEqual(batchctl.receipt("story_test",meta)["applied"],3)
            with self.assertRaisesRegex(ValueError,"partially"):
                batchctl.execute(self.args(yes=True))

if __name__=="__main__":unittest.main()
