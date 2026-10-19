#!/usr/bin/env python3
"""Offline tests for exact, bounded, read-only Story Ops request protocol."""
from __future__ import annotations
import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import opsctl as ops

class OpsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.previous=ops.scanctl.STORE
        ops.scanctl.STORE=Path(self.temp.name)
        self.base=ops.scanctl.STORE/"worlds"/"story_test"
        (self.base/"data"/"Lua").mkdir(parents=True)
        (self.base/"profile").write_text("ok")
    def tearDown(self):
        ops.scanctl.STORE=self.previous
        self.temp.cleanup()
    def cmd(self,mode,yes=False,**kwargs):
        fields=dict(world="story_test",operation=mode,player="admin",radius=10,
                    yes=yes,acknowledge_failed=False)
        fields.update(kwargs)
        return argparse.Namespace(**fields)
    def test_preview_and_radius_validation(self):
        ops.queue(self.cmd("nearby"))
        self.assertFalse((self.base/"data"/"Lua"/ops.REQUEST).exists())
        for rad in (0,21):
            with self.assertRaisesRegex(ValueError,"radius"):
                ops.queue(self.cmd("nearby",radius=rad))
    def test_players_census_protocol(self):
        with patch.object(ops,"ready"):
            ops.queue(self.cmd("players",yes=True))
        old=ops.request("story_test")
        self.assertEqual(old["operation"],"players")
        self.assertEqual(ops.result("story_test",old["id"]),{"status":"pending"})
        (self.base/"data"/"Lua"/ops.RESPONSE).write_text(
            "v1\t"+old["id"]+"\tstory_test\tplayers\tcomplete\tserver_snapshot\t2\n"
            "player\tadmin\t100.0\t100.0\t0.0\t-\n"
            "player\tfriend\t104.0\t100.0\t0.0\t253\nend\n")
        result=ops.result("story_test",old["id"])
        self.assertEqual(len(result["data"]),2)
        self.assertEqual(result["data"][1]["vehicle_id"],253)
        with patch.object(ops,"ready"):
            ops.queue(self.cmd("players",yes=True))
        self.assertNotEqual(ops.request("story_test")["id"],old["id"])
    def test_nearby_census_coverage_and_request_matching(self):
        with patch.object(ops,"ready"):
            ops.queue(self.cmd("nearby",yes=True))
        old=ops.request("story_test")
        (self.base/"data"/"Lua"/ops.RESPONSE).write_text(
            "v1\t"+old["id"]+"\tstory_test\tnearby\tcomplete\tserver_snapshot\t1\n"
            "nearby\tadmin\t10\t2\t3.0\t1\t1\t316\t317\nend\n")
        result=ops.result("story_test",old["id"])
        self.assertEqual(result["data"][0]["loaded_zombies"],2)
        self.assertEqual(result["data"][0]["loaded_tiles"],316)
        self.assertEqual(result["data"][0]["survey_tiles"],317)
    def test_reject_synthetic_replies(self):
        with patch.object(ops,"ready"):
            ops.queue(self.cmd("nearby",yes=True))
        rid=ops.request("story_test")["id"]
        result_file=self.base/"data"/"Lua"/ops.RESPONSE
        result_file.write_text(
            "v1\t"+rid+"\tstory_test\tnearby\tcomplete\tserver_snapshot\t1\n"
            "nearby\tadmin\t10\t2\t3.0\t1\t1\t320\t317\nend\n")
        with self.assertRaisesRegex(ValueError,"coverage"):
            ops.result("story_test",rid)
        result_file.write_text(
            "v1\t"+"f"*32+"\tstory_test\tnearby\tcomplete\tserver_snapshot\t1\n"
            "nearby\tadmin\t10\t2\t3.0\t1\t1\t316\t317\nend\n")
        self.assertEqual(ops.result("story_test",rid),{"status":"pending"})

if __name__=="__main__":unittest.main()
