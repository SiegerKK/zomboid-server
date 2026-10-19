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

class RosterTests(unittest.TestCase):
    setUp=TLOUOffline.setUp
    tearDown=TLOUOffline.tearDown
    args=TLOUOffline.args
    def queue_roster(self):
        a=self.args("roster",yes=True);a.player="player_test"
        with patch.object(t,"ready"):t.run(a)
        return t.previous("story_test")["id"]
    def payload(self,rid):
        return (f"v3\t{rid}\tstory_test\troster\tcomplete\tcomplete_loaded_roster\t4\tplayer_test\n"
                "origin\tplayer_test\t100\t100\t0\n"
                "coverage\t3\t2\t1\tloaded_list_only\n"
                "zombie\t0\t7\tTLOU_Clicker\t103\t104\t1\t5\t1\n"
                "zombie\t2\t7\tunknown\t101\t100\t0\t1\t0\nend\n")
    def test_roster_exact_target_sort_and_duplicate_online_ids(self):
        rid=self.queue_roster();t.paths("story_test")[1].write_text(self.payload(rid))
        data=t.read_result("story_test",rid)
        self.assertEqual(data["coverage"],dict(list_slots=3,inspected=2,null_slots=1,truncated=False))
        self.assertEqual([z["distance_tiles_2d"] for z in data["zombies"]],[1,5])
        self.assertEqual([z["online_id"] for z in data["zombies"]],[7,7])
        # Session IDs may collide; never deduplicate distinct snapshot slots.
        self.assertEqual(data["zombies"][1]["floor_delta"],1)
    def test_roster_rejects_inconsistent_or_malformed_reports(self):
        rid=self.queue_roster();p=t.paths("story_test")[1];good=self.payload(rid)
        for bad in [good.replace("coverage\t3\t2\t1","coverage\t3\t1\t1"),
                    good.replace("zombie\t2\t7","zombie\t0\t7"),
                    good.replace("\t5\t1\n","\t6\t1\n"),
                    good.replace("\t103\t104", "\tnan\t104"),
                    good.replace("\tplayer_test\n","\tother_player\n"),
                    good.removesuffix("end\n")]:
            p.write_text(bad)
            with self.assertRaises(ValueError):t.read_result("story_test",rid)
    def test_roster_preview_and_invalid_login(self):
        a=self.args("roster");a.player="player_test";t.run(a)
        self.assertFalse(t.paths("story_test")[0].exists())
        for user in ("../player","bad\nname", "", "a"*41):
            a.player=user
            with self.assertRaises(ValueError):t.run(a)
    def test_roster_export_is_private_and_never_overwrites(self):
        import contextlib,io
        rid=self.queue_roster();t.paths("story_test")[1].write_text(self.payload(rid))
        output=Path(self.temp.name)/"private.json"
        a=argparse.Namespace(world="story_test",output=str(output))
        with contextlib.redirect_stdout(io.StringIO()):t.result(a)
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        with self.assertRaises(FileExistsError):t.result(a)
        link=Path(self.temp.name)/"link";link.symlink_to(output);a.output=str(link)
        with self.assertRaises(FileExistsError):t.result(a)
    def test_roster_empty_snapshot_and_stale_receipt(self):
        rid=self.queue_roster();p=t.paths("story_test")[1]
        p.write_text(f"v3\t{rid}\tstory_test\troster\tcomplete\tcomplete_loaded_roster\t2\tplayer_test\norigin\tplayer_test\t100\t100\t0\ncoverage\t0\t0\t0\tloaded_list_only\nend\n")
        self.assertEqual(t.read_result("story_test",rid)["zombies"],[])
        self.assertEqual(t.read_result("story_test","f"*32),{"status":"pending"})

if __name__=="__main__":unittest.main()
