#!/usr/bin/env python3
"""Offline site inventory tests; stage/site analysis never touches the server."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import constructionctl,constructionsite as site

DATA={"schema":"sieger-private-merged-area-survey-v1","world":"sample_world",
 "snapshot_mode":"two sequential incremental scans, not simultaneous",
 "sources":[{"name":"north"},{"name":"south"}],
 "bbox_exclusive":[10,20,13,24],
 "summary":{"source_errors":0,"source_truncated":False,
            "all_requested_coordinates_visited":True},
 "metadata_buildings":[{"id":"b01","bbox":[11,20,13,22],
                         "rooms":[{"name":"house"}]}],
 "records":[
  {"kind":"square","loaded":True,"x":10,"y":20,"z":0},
  {"kind":"square","loaded":True,"x":11,"y":20,"z":0},
  {"kind":"square","loaded":False,"x":12,"y":20,"z":1},
  {"kind":"square","loaded":True,"x":12,"y":22,"z":0},
  {"kind":"object","class":"IsoObject","sprite":"blends_street_01_53",
   "x":10,"y":20,"z":0,"object_index":0},
  {"kind":"object","class":"IsoDoor","sprite":"fixtures_doors_01_5",
   "x":11,"y":20,"z":0,"object_index":1},
  {"kind":"object","class":"IsoObject","sprite":"e_newgrass_1_96",
   "x":12,"y":22,"z":0,"object_index":1},
  {"kind":"vehicle","vehicle_id":50,"script":"Base.Sedan","x":11,"y":23,"z":0}
 ]}
class SiteTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.survey=self.root/"survey.json"
  self.survey.write_text(json.dumps(DATA))
 def test_complete_merged_counts_building_road_vehicles(self):
  d,authoritative=site.load_survey(self.survey,"sample_world")
  self.assertTrue(authoritative)
  result=site.analyze(d,"sample_world",site.surveyed_bbox(d))
  self.assertEqual(result["floor_coverage"]["0"]["loaded"],3)
  self.assertEqual(result["floor_coverage"]["1"]["unloaded_or_nonexistent"],1)
  self.assertEqual(result["observed_openings"]["doors"],1)
  self.assertEqual(result["sprite_hints"]["street_tiles"],1)
  self.assertEqual(result["metadata_buildings"][0]["rooms"],["house"])
  self.assertEqual(result["vehicles"][0]["vehicle_id"],50)
 def test_plan_warns_road_native_and_unknown_cell(self):
  plan={"schema":1,"world":"sample_world","settlement":"refuge",
        "stages":[{"id":"pioneer","actions":[
         {"id":"road_wall","op":"place","kind":"wall",
          "at":[10,20,0],"face":"N","sprite":"carpentry_02_80"},
         {"id":"old_door","op":"place","kind":"door",
          "at":[11,20,0],"face":"W","sprite":"fixtures_doors_01_5"},
         {"id":"upper","op":"place","kind":"wall",
          "at":[12,20,1],"face":"N","sprite":"carpentry_02_80"},
         {"id":"outside","op":"place","kind":"wall",
          "at":[50,50,0],"face":"N","sprite":"carpentry_02_80"}
        ]}]}
  parsed=constructionctl.prepare(plan,"sample_world","pioneer")
  d,_=site.load_survey(self.survey,"sample_world")
  out=site.analyze(d,"sample_world",site.surveyed_bbox(d),parsed)
  counts=out["stage_assessment"]["counts"]
  self.assertEqual(counts["possible_road_or_driveway"],1)
  self.assertEqual(counts["existing_native_structure"],1)
  self.assertEqual(counts["unloaded_or_nonexistent"],1)
  self.assertEqual(counts["outside_survey"],1)
  self.assertTrue(out["stage_assessment"]["advisory_only"])
 def test_rejects_wrong_world_unproven_merge_and_duplicate_square(self):
  with self.assertRaisesRegex(ValueError,"world mismatch"):
   site.load_survey(self.survey,"foreign")
  bad=json.loads(json.dumps(DATA))
  bad["summary"]["source_truncated"]=True
  self.survey.write_text(json.dumps(bad))
  with self.assertRaisesRegex(ValueError,"incomplete"):
   site.load_survey(self.survey,"sample_world")
  bad=json.loads(json.dumps(DATA))
  bad["records"].append(bad["records"][0])
  with self.assertRaisesRegex(ValueError,"Duplicate square"):
   site.analyze(bad,"sample_world",site.surveyed_bbox(bad))
 def test_raw_requires_explicit_world_and_complete_receipt(self):
  data={"meta":{"player":"admin"},
        "summary":{"status":"complete","truncated":False,"errors":0},
        "records":DATA["records"]}
  self.survey.write_text(json.dumps(data))
  with self.assertRaisesRegex(ValueError,"--source-world"):
   site.load_survey(self.survey,"sample_world")
  scan,authed=site.load_survey(self.survey,"sample_world","sample_world")
  self.assertFalse(authed)
  self.assertGreater(site.analyze(scan,"sample_world",site.surveyed_bbox(scan))
                    ["record_kinds"]["object"],0)
 def test_strict_private_export_outside_repo(self):
  out=self.root/"analysis.json"
  with patch.object(constructionctl.scanctl,"REPO",self.root):
   with self.assertRaisesRegex(ValueError,"outside source"):
    site.output_file(out,{"hello":"world"})
  with patch.object(constructionctl.scanctl,"REPO",Path("/tmp/other-project")):
   site.output_file(out,{"hello":"world"})
   self.assertTrue(out.is_file())
   with self.assertRaises(FileExistsError):
    site.output_file(out,{"hello":"again"})
 def test_rejects_non_finite_and_duplicate_key(self):
  self.survey.write_text('{"records":[],"world":"sample_world","world":"sample_world"}')
  with self.assertRaisesRegex(ValueError,"Duplicate JSON"):
   site.load_survey(self.survey,"sample_world")
if __name__=="__main__":unittest.main()
