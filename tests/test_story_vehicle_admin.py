#!/usr/bin/env python3
"""Offline fail-closed tests for root-issued existing vehicle actions."""
import argparse
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/"story"))
import vehiclectl as v

class VehicleAdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.lua=self.root/"worlds"/"story_test"/"data"/"Lua"
        self.lua.mkdir(parents=True)
        (self.root/"worlds"/"story_test"/"profile").write_text("ok")
        self.original=v.scanctl.STORE
        v.scanctl.STORE=self.root
    def tearDown(self):
        v.scanctl.STORE=self.original
        self.tmp.cleanup()
    def args(self,op="condition",**kwargs):
        a=dict(operation=op,world="story_test",id=253,
               script="Base.PickUpTruck",x=10620,y=9209,z=0,
               part="RearWindow",expect=98,value=99,item=None,
               count=1,yes=False)
        a.update(kwargs)
        return argparse.Namespace(**a)
    def test_preview_never_writes(self):
        v.run(self.args())
        self.assertFalse((self.lua/v.REQUEST).exists())
    def test_invalid_identity_and_value_fail(self):
        for a in (self.args(script="../Evil"),self.args(id=-1),
                  self.args(x=-5),self.args(value=101),
                  self.args(op="add",item="Base.Unapproved"),
                  self.args(op="remove",part="../../evil",item="Base.Pen")):
            with self.assertRaises(ValueError):v.run(a)
    def test_exact_wire_and_pending_lock(self):
        with patch.object(v,"ready"):
            v.run(self.args(yes=True))
            previous=v.prior_request("story_test")
            self.assertRegex(previous["id"],r"^[0-9a-f]{32}$")
            with self.assertRaisesRegex(ValueError,"pending"):
                v.run(self.args(yes=True))
            p=(self.lua/v.RESULT)
            p.write_text("v1\t"+previous["id"]+
                "\tstory_test\tcondition\tcomplete\tcondition_99\tRearWindow\n")
            self.assertEqual(v.response("story_test",previous["id"])["status"],"complete")
            v.run(self.args(yes=True))
    def test_wrong_reply_does_not_ack(self):
        with patch.object(v,"ready"):
            v.run(self.args(yes=True))
            (self.lua/v.RESULT).write_text("v1\t"+("f"*32)+
                "\tstory_test\tcondition\tcomplete\tok\t-\n")
            with self.assertRaisesRegex(ValueError,"pending"):
                v.run(self.args(yes=True))
    def test_failed_operation_not_automatically_retried(self):
        with patch.object(v,"ready"):
            v.run(self.args(yes=True))
            rid=v.prior_request("story_test")["id"]
            (self.lua/v.RESULT).write_text("v1\t"+rid+
                "\tstory_test\tcondition\terror\tmanual_review_server_logs\t-\n")
            with self.assertRaisesRegex(ValueError,"failed/partial"):
                v.run(self.args(yes=True))

if __name__=="__main__":unittest.main()
