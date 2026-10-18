#!/usr/bin/env python3
"""Verify full TLOU-census wire protocol without starting PZ."""
from __future__ import annotations
import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import tlouctl as t

def fixture(rid,wrong=False):
    rows=[["framework","available","yes"]]
    for key in t.TYPES:
        rows.append(["ztype",key,"250","100","-","-","-","1"])
    for setting in t.SETTINGS:
        rows.append(["setting",setting,"true"])
    rows.append(["census","1300","1300","0","0","1","42","loaded_list_only"])
    for key in t.TYPES:
        rows.append(["observed",key,"325","325","80.00","150","325","90","325"])
    rows.append(["observed","other","0","0","-","0","0","0","0"])
    rows.append(["observed","unknown","0" if wrong else "0","0","-","0","0","0","0"])
    if not wrong:
        rows[8] # benign read to retain 20-row fixture clarity
    return ("v2\t"+rid+"\tstory_test\tcensus\tcomplete\tcomplete_loaded_census\t"+
            str(len(rows))+"\n" +
            "".join("\t".join(row)+"\n" for row in rows)+"end\n")

class TLOUOffline(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old=t.scanctl.STORE
        t.scanctl.STORE=Path(self.temp.name)
        self.base=t.scanctl.STORE/"worlds"/"story_test"
        (self.base/"data"/"Lua").mkdir(parents=True)
        (self.base/"profile").write_text("ok")
    def tearDown(self):
        t.scanctl.STORE=self.old
        self.temp.cleanup()
    def args(self,op,yes=False):
        return argparse.Namespace(world="story_test",command=op,yes=yes,
                                  acknowledge_failed=False)
    def test_preview_never_writes(self):
        t.run(self.args("census"))
        self.assertFalse((self.base/"data"/"Lua"/t.REQUEST).exists())
    def test_one_full_request_and_reconciliation(self):
        with patch.object(t,"ready"):
            t.run(self.args("census",yes=True))
        old=t.previous("story_test")
        self.assertEqual(old["operation"],"census")
        with self.assertRaisesRegex(ValueError,"pending"):
            with patch.object(t,"ready"):
                t.run(self.args("census",yes=True))
        (_,response)=t.paths("story_test")
        response.write_text(fixture(old["id"]))
        result=t.read_result("story_test",old["id"])
        self.assertEqual(result["census"]["list_slots"],1300)
        self.assertEqual(result["census"]["inspected"],1300)
        self.assertEqual(result["census"]["truncated"],False)
        self.assertEqual(sum(x["count"] for x in result["by_type"].values()),1300)
    def test_no_partial_counts_misreported_as_complete(self):
        with patch.object(t,"ready"):
            t.run(self.args("census",yes=True))
        old=t.previous("story_test")
        (_,response)=t.paths("story_test")
        response.write_text(fixture(old["id"]).replace(
            "census\t1300\t1300\t0\t0\t1",
            "census\t1300\t512\t0\t0\t1"))
        with self.assertRaisesRegex(ValueError,"totals"):
            t.read_result("story_test",old["id"])
    def test_bad_id_never_confirms(self):
        with patch.object(t,"ready"):
            t.run(self.args("census",yes=True))
        (_,response)=t.paths("story_test")
        response.write_text(fixture("f"*32))
        self.assertEqual(t.read_result("story_test",t.previous("story_test")["id"]),
                         {"status":"pending"})

if __name__=="__main__":unittest.main()
