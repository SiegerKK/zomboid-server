#!/usr/bin/env python3
"""True 101-tile source frames, disjoint mosaics, strict failure modes."""
from __future__ import annotations
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import scanregion as region
import constructionsite as site

class Mosaic(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.plan=region.build_plan(
            "sample_world","admin",[10,20,215,126],0,0,
            "squares,objects,vehicles,windows")
        self.manifest=self.folder/"plan.json"
        self.manifest.write_text(json.dumps(self.plan))
    def fixture(self,index):
        tile=self.plan["tiles"][index]
        cx,cy=tile["center"]
        rows=[{"kind":"square","x":x,"y":y,"z":0,"loaded":True,
               "room":""}
              for y in range(cy-50,cy+51)
              for x in range(cx-50,cx+51)]
        # Put one real-looking object in each distinct tile clip, plus another
        # source row outside the clip to prove no mixed-frame object indices.
        x,y=tile["clip_bbox"][:2]
        rows.append({"kind":"object","x":x,"y":y,"z":0,
                     "class":"IsoDoor","sprite":"fixtures_doors_01_5",
                     "object_index":1})
        return {"status":"complete",
                "meta":{"kind":"meta","request_id":f"{index+1:032x}",
                        "player":"admin","center_x":cx,"center_y":cy,
                        "side":101,"levels":1,"min_z":0,"max_z":0,
                        "modes":"squares,objects,vehicles,windows",
                        "snapshot_mode":"incremental"},
                "summary":{"kind":"summary","status":"complete",
                           "requested_squares":10201,
                           "scanned_squares":10201,
                           "loaded_squares":10201,
                           "unloaded_squares":0,
                           "errors":0,"truncated":False,
                           "records":len(rows),"vehicle_snapshot":"complete"},
                "records":rows}
    def write_tiles(self):
        for k,tile in enumerate(self.plan["tiles"]):
            (self.folder/tile["source"]).write_text(
                json.dumps(self.fixture(k)))
    def test_arbitrary_size_beyond_101_does_not_change_server_radius(self):
        self.assertEqual(len(self.plan["tiles"]),6)
        self.assertEqual(self.plan["tile_side"],101)
        self.assertEqual(self.plan["tiles"][0]["center"],[60,70])
        self.assertEqual(self.plan["tiles"][-1]["clip_bbox"],[212,121,215,126])
        self.write_tiles()
        result=region.merge(self.plan,self.manifest)
        self.assertEqual(result["summary"]["visited_cells"],205*106)
        self.assertEqual(result["summary"]["record_kinds"]["square"],205*106)
        self.assertEqual(result["summary"]["record_kinds"]["object"],6)
        self.assertEqual(len(result["cell_source_request_ids"]),205*106)
        self.assertEqual(result["snapshot_mode"],
                         "multiple_sequential_loaded_square_scans_not_simultaneous")
        self.assertEqual(len(result["sources"]),6)
        site_data,asserted=site.load_survey(
            self._write_result(result),"sample_world")
        self.assertTrue(asserted)
        analysis=site.analyze(site_data,"sample_world",
                              site.surveyed_bbox(site_data))
        self.assertEqual(analysis["floor_coverage"]["0"]["loaded"],205*106)
        self.assertEqual(analysis["observed_openings"]["doors"],6)
    def _write_result(self,result):
        path=self.folder/"full.json"
        path.write_text(json.dumps(result))
        return path
    def test_missing_tile_is_not_interpreted_as_empty(self):
        self.write_tiles()
        (self.folder/self.plan["tiles"][2]["source"]).unlink()
        with self.assertRaisesRegex(ValueError,"missing"):
            region.merge(self.plan,self.manifest)
    def test_source_mismatch_truncation_and_wrong_sample_id(self):
        self.write_tiles()
        p=self.folder/self.plan["tiles"][0]["source"]
        data=self.fixture(0)
        for mutation,reason in [
            (lambda d:d["meta"].__setitem__("center_x",999),"centre"),
            (lambda d:d["summary"].__setitem__("truncated",True),"truncated"),
            (lambda d:d["summary"].__setitem__("scanned_squares",13),"truncated"),
            (lambda d:d["records"].pop(),"footer"),
        ]:
            bad=copy.deepcopy(data)
            mutation(bad)
            p.write_text(json.dumps(bad))
            with self.subTest(reason=reason),self.assertRaises(ValueError):
                region.merge(self.plan,self.manifest)
        p.write_text(json.dumps(data))
        second=self.folder/self.plan["tiles"][1]["source"]
        bad=self.fixture(1)
        bad["meta"]["request_id"]=data["meta"]["request_id"]
        second.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,"Reused request ID"):
            region.merge(self.plan,self.manifest)
    def test_tampered_plan_or_coordinate_hole_refused(self):
        x=copy.deepcopy(self.plan)
        x["tiles"][0]["clip_bbox"][0]=9
        with self.assertRaisesRegex(ValueError,"modified|coverage"):
            region.exact_plan(x)
        self.write_tiles()
        first=self.folder/self.plan["tiles"][0]["source"]
        bad=self.fixture(0)
        bad["records"].pop(0)
        bad["summary"]["records"]-=1
        first.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError,"lacks one square"):
            region.merge(self.plan,self.manifest)
    def test_plan_validation_and_private_file_creation(self):
        with self.assertRaisesRegex(ValueError,"Invalid scan modes"):
            region.build_plan("sample_world","admin",
                              [10,20,215,126],0,0,"objects")
        with self.assertRaisesRegex(ValueError,"bbox"):
            region.bbox_parse("20,10,10,20")
        outfile=self.folder/"out.json"
        region.save_new(outfile,{"ok":True})
        self.assertEqual(outfile.stat().st_mode&0o777,0o600)
        with self.assertRaisesRegex(ValueError,"NEW private file"):
            region.save_new(outfile,{"ok":True})

if __name__=="__main__":
    unittest.main()
