#!/usr/bin/env python3
"""Staged settlement construction CLI tests; no live server/world mutations."""
import argparse,contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import constructionctl as ctl

PLAN={"schema":1,"world":"map_world","settlement":"refuge",
 "stages":[
  {"id":"shelter","description":"First perimeter","actions":[
   {"id":"north_wall","op":"place","kind":"wall","at":[9200,7700,0],
       "face":"N","sprite":"carpentry_02_80","health":350},
   {"id":"gate","op":"place","kind":"door","at":[9201,7700,0],
       "face":"N","sprite":"fixtures_doors_01_3"},
   {"id":"garden_fence","op":"place","kind":"fence","at":[9202,7700,0],
       "face":"W","sprite":"carpentry_02_24"},
   {"id":"temporary_generator","op":"place","kind":"generator",
       "at":[9203,7700,0],"item":"Base.Generator","health":88},
   {"id":"window","op":"place","kind":"window","at":[9204,7700,0],
       "face":"N","sprite":"fixtures_windows_01_24"}]},
  {"id":"infrastructure","requires":["shelter"],"actions":[
   {"id":"repair_door","op":"remove_exact","kind":"IsoDoor",
        "at":[9201,7700,0],"face":"N","sprite":"fixtures_doors_01_3",
        "index":4},
   {"id":"better_door","op":"place","kind":"door",
        "at":[9201,7700,0],"face":"N","sprite":"fixtures_doors_01_5"},
   {"id":"loft_floor","op":"place","kind":"floor",
        "at":[9205,7700,1],"sprite":"carpentry_02_12"},
   {"id":"wooden_chair","op":"place","kind":"decor",
        "at":[9206,7700,0],"sprite":"furniture_seating_indoor_01_1"}]},
  {"id":"expansion","requires":["infrastructure"],"actions":[
   {"id":"tear_down_old_wall","op":"remove_tag","kind":"IsoThumpable",
        "at":[9200,7700,0],"face":"N","sprite":"carpentry_02_80",
        "target_tag":"refuge:shelter:north_wall"}]}]}

class PlanTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.file=self.root/"plan.json"
  self.file.write_text(json.dumps(PLAN))
  self.lua=self.root/"Lua";self.lua.mkdir()
 def a(self,yes=False,stage="shelter",existing=False,survey=None):
  return argparse.Namespace(command="apply" if yes else "preview",
   world="map_world",stage=stage,file=str(self.file),
   survey=survey,yes=yes,allow_existing=existing,acknowledge_failed=False)
 def test_compiles_all_native_construction_classes(self):
  data=ctl.load(self.file,"map_world","shelter")
  self.assertEqual(data["actions"],5)
  self.assertFalse(data["allow_existing"])
  self.assertEqual({r.split("\t")[3] for r in data["rows"]},
                   {"wall","fence","door","generator","window"})
  self.assertTrue(all(len(r.split("\t"))==13 for r in data["rows"]))
  self.assertEqual(data["requires"],[])
  self.assertRegex(data["digest"],r"^[0-9a-f]{64}$")
 def test_staged_dependencies_and_targeted_removals(self):
  next=ctl.load(self.file,"map_world","infrastructure")
  self.assertTrue(next["allow_existing"])
  self.assertEqual(next["requires"],["shelter"])
  self.assertEqual(next["rows"][0].split("\t")[-1],"4")
  after=ctl.load(self.file,"map_world","expansion")
  self.assertEqual(after["rows"][0].split("\t")[-2],"refuge:shelter:north_wall")
 def test_bed_properties_compile_and_are_required_in_verification(self):
  doc=json.loads(json.dumps(PLAN))
  doc["stages"][0]["actions"]=[{"id":"cot_head","op":"place","kind":"bed",
    "at":[110,220,0],"sprite":"bed_head","bed_type":"averageBed"}]
  got=ctl.prepare(doc,"map_world","shelter")
  self.assertEqual(got["rows"][0].split("\t"),[
    "a","cot_head","place","bed","110","220","0","-","bed_head","-","-","averageBed","-"])
  for key,value in (("bed_type",None),("bed_type","goodChair"),
                    ("health",350),("face","N"),("capacity",50)):
   bad=json.loads(json.dumps(doc));bad["stages"][0]["actions"][0][key]=value
   with self.assertRaises(ValueError):ctl.prepare(bad,"map_world","shelter")
  optional=json.loads(json.dumps(doc));optional["stages"][0]["actions"][0].pop("bed_type")
  self.assertEqual(ctl.prepare(optional,"map_world","shelter")["rows"][0].split("\t")[11],"native")
  self.file.write_text(json.dumps(doc))
  post=self.root/"bed_post.json"
  rows=[{"kind":"square","x":110,"y":220,"z":0,"loaded":True},
        {"kind":"object","x":110,"y":220,"z":0,"class":"IsoObject",
         "sprite":"bed_head","construction_tag":"refuge:shelter:cot_head",
         "bed_type":"averageBed"}]
  args=argparse.Namespace(world="map_world",file=str(self.file),stage="shelter",
                         survey=str(post),source_world=None)
  for quality in ("averageBed",None,"badBed"):
   rows[1]["bed_type"]=quality
   post.write_text(json.dumps({"world":"map_world","summary":{
       "status":"complete","errors":0,"truncated":False},"records":rows}))
   with contextlib.redirect_stdout(io.StringIO()):
    if quality=="averageBed":ctl.verify(args)
    else:
     with self.assertRaisesRegex(ValueError,"does not reconcile"):ctl.verify(args)

 def test_functional_storage_is_not_a_decor_sprite(self):
  doc=json.loads(json.dumps(PLAN))
  doc["stages"][0]["actions"]=[{"id":"dry_stores","op":"place",
      "kind":"storage","at":[9280,7736,0],
      "sprite":"carpentry_02_15","health":400,"capacity":60}]
  got=ctl.prepare(doc,"map_world","shelter")
  self.assertFalse(got["allow_existing"])
  self.assertEqual(got["rows"][0].split("\t"),
      ["a","dry_stores","place","storage","9280","7736","0",
       "-","carpentry_02_15","-","400","60","-"])
  for change in (
      lambda a:a.pop("capacity"),
      lambda a:a.update(capacity=0),
      lambda a:a.update(capacity=101),
      lambda a:a.update(capacity=True),
      lambda a:a.update(face="N"),
      lambda a:a.update(item="Base.Generator"),
      lambda a:a.update(open_sprite="other_sprite"),
  ):
   broken=json.loads(json.dumps(doc))
   change(broken["stages"][0]["actions"][0])
   with self.assertRaises(ValueError):ctl.prepare(broken,"map_world","shelter")

 def test_existing_window_barricade_compiles_with_native_selector_and_permission(self):
  doc=json.loads(json.dumps(PLAN))
  doc["stages"][0]["actions"]=[{"id":"shutter","op":"barricade",
      "kind":"IsoWindow","at":[9274,7776,0],"face":"W",
      "sprite":"fixtures_windows_01_24","index":2,"planks":3}]
  got=ctl.prepare(doc,"map_world","shelter")
  self.assertEqual(got["actions"],1)
  self.assertTrue(got["allow_existing"])
  self.assertEqual(got["rows"][0].split("\t"),["a","shutter","barricade",
      "IsoWindow","9274","7776","0","W","fixtures_windows_01_24",
      "-","3","-","2"])
  for change in (
      lambda a:a.update(planks=0),
      lambda a:a.update(planks=5),
      lambda a:a.update(kind="IsoDoor"),
      lambda a:a.update(face="-"),
      lambda a:a.update(sprite="bad sprite"),
      lambda a:a.update(index=-1),
  ):
   broken=json.loads(json.dumps(doc))
   change(broken["stages"][0]["actions"][0])
   with self.assertRaises(ValueError):ctl.prepare(broken,"map_world","shelter")

 def test_exterior_barricades_use_window_edge_and_reserved_side_field(self):
  doc=json.loads(json.dumps(PLAN))
  a={"id":"outside_planks","op":"barricade","kind":"IsoWindow",
     "at":[9274,7776,0],"face":"W",
     "sprite":"fixtures_windows_01_24","index":2,"planks":2,
     "side":"outside"}
  doc["stages"][0]["actions"]=[a]
  got=ctl.prepare(doc,"map_world","shelter")
  self.assertEqual(got["rows"][0].split("\t")[11],"outside")
  a["side"]="inside"
  with self.assertRaisesRegex(ValueError,"exterior"):
   ctl.prepare(doc,"map_world","shelter")
  a["side"]="outside";a["face"]="E"
  with self.assertRaisesRegex(ValueError,"N/W"):
   ctl.prepare(doc,"map_world","shelter")

 def test_preview_with_survey_does_not_mutate(self):
  survey=self.root/"survey.json"
  survey.write_text(json.dumps({"world":"map_world","records":[
      {"kind":"square","x":9200,"y":7700,"z":0,"loaded":True},
      {"kind":"square","x":9201,"y":7700,"z":0,"loaded":False}
  ]}))
  with patch.object(ctl.scanctl,"lua_dir",return_value=self.lua),\
        contextlib.redirect_stdout(io.StringIO()) as io_out:
   ctl.preview(self.a(survey=str(survey)))
  self.assertIn('"loaded_at_survey": 1',io_out.getvalue())
  self.assertIn('"unloaded_or_nonexistent": 1',io_out.getvalue())
  self.assertFalse((self.lua/ctl.REQ).exists())
 def test_apply_is_exact_root_acknowledged_request(self):
  with patch.object(ctl.scanctl,"lua_dir",return_value=self.lua),\
       patch.object(ctl.scanctl,"assert_module_ready"),\
       patch.object(ctl.os,"geteuid",return_value=0),\
       contextlib.redirect_stdout(io.StringIO()):
   ctl.preview(self.a(yes=True))
   request=ctl.previous("map_world")
   self.assertEqual(request["count"],5)
   with self.assertRaisesRegex(ValueError,"not finished"):
    ctl.preview(self.a(yes=True))
   ack="\t".join(["v1",request["id"],"map_world","refuge","shelter",
                  request["digest"],"complete","5","5","server_applied"])+"\n"
   (self.lua/ctl.ACK).write_text(ack)
   self.assertEqual(ctl.receipt("map_world",request)["status"],"complete")
   ctl.preview(self.a(yes=True))
   self.assertNotEqual(ctl.previous("map_world")["id"],request["id"])
 def test_existing_removal_requires_explicit_approval(self):
  with patch.object(ctl.scanctl,"lua_dir",return_value=self.lua),\
       patch.object(ctl.scanctl,"assert_module_ready"),\
       patch.object(ctl.os,"geteuid",return_value=0),\
       contextlib.redirect_stdout(io.StringIO()):
   with self.assertRaisesRegex(ValueError,"--allow-existing"):
    ctl.preview(self.a(yes=True,stage="infrastructure"))
   self.assertFalse((self.lua/ctl.REQ).exists())
   ctl.preview(self.a(yes=True,stage="infrastructure",existing=True))
   raw=(self.lua/ctl.REQ).read_text().splitlines()[0].split("\t")
   self.assertEqual(raw[8],"1")
   self.assertEqual(raw[7],"shelter")
 def test_line_expansion_honors_gate_gaps(self):
  data=json.loads(json.dumps(PLAN))
  data["stages"][0]["actions"]=[{"id":"defense","op":"line",
    "kind":"wall","start":[9250,7701,0],"end":[9256,7701,0],
    "face":"N","sprite":"carpentry_02_80",
    "skip":[[9253,7701,0]]}]
  compiled=ctl.prepare(data,"map_world","shelter")
  self.assertEqual(compiled["actions"],6)
  self.assertEqual([r.split("\t")[1] for r in compiled["rows"]],
                   ["defense_0000","defense_0001","defense_0002",
                    "defense_0004","defense_0005","defense_0006"])
  data["stages"][0]["actions"][0]["skip"]=[[9253,7700,0]]
  with self.assertRaisesRegex(ValueError,"outside its endpoints"):
   ctl.prepare(data,"map_world","shelter")
 def test_injection_duplicate_and_wrong_world_refused(self):
  with self.assertRaisesRegex(ValueError,"world/schema"):
   ctl.prepare(PLAN,"other","shelter")
  malformed=json.loads(json.dumps(PLAN))
  malformed["stages"][0]["actions"][0]["sprite"]="carpentry_02_80;quit"
  with self.assertRaisesRegex(ValueError,"Invalid named"):
   ctl.prepare(malformed,"map_world","shelter")
  malformed=json.loads(json.dumps(PLAN))
  malformed["stages"][0]["actions"][1]["id"]="north_wall"
  with self.assertRaisesRegex(ValueError,"Duplicate construction action"):
   ctl.prepare(malformed,"map_world","shelter")
  self.file.write_text('{"schema":1,"schema":1,"world":"map_world","settlement":"refuge","stages":[]}')
  with self.assertRaisesRegex(ValueError,"Duplicate JSON"):
   ctl.load(self.file,"map_world","shelter")
 def test_verify_observed_native_objects_and_flag_incomplete(self):
  expected={
   "wall":("IsoThumpable","carpentry_02_80"),
   "door":("IsoDoor","fixtures_doors_01_3"),
   "fence":("IsoThumpable","carpentry_02_24"),
   "generator":("IsoGenerator","appliances_misc_01_0"),
   "window":("IsoWindow","fixtures_windows_01_24")
  }
  rows=[]
  for op in PLAN["stages"][0]["actions"]:
   x,y,z=op["at"]
   rows.append({"kind":"square","x":x,"y":y,"z":z,"loaded":True})
   native,sprite=expected[op["kind"]]
   o={"kind":"object","x":x,"y":y,"z":z,
        "class":native,"sprite":sprite,"object_index":1,
        "construction_tag":f'refuge:shelter:{op["id"]}'}
   if op["kind"] in ("wall","door","fence","window"):o["face"]=op["face"]
   rows.append(o)
  file=self.root/"post.json"
  file.write_text(json.dumps({"world":"map_world","summary":{"status":"complete","errors":0,
                                     "truncated":False},"records":rows}))
  args=argparse.Namespace(world="map_world",file=str(self.file),
           stage="shelter",survey=str(file),source_world=None)
  with contextlib.redirect_stdout(io.StringIO()) as output:
   ctl.verify(args)
  result=json.loads(output.getvalue())
  self.assertEqual(result["counts"]["seen_place"],5)
  rows[1].pop("construction_tag")
  file.write_text(json.dumps({"world":"map_world",
     "summary":{"status":"complete","errors":0,"truncated":False},"records":rows}))
  with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,"does not reconcile"):
   ctl.verify(args)
  rows[1]["construction_tag"]="refuge:shelter:north_wall"
  self.assertEqual(result["counts"]["unobserved"],0)
  # A claimed empty square is not evidence the wall is missing.
  rows[0]["loaded"]=False
  complete={"status":"complete","errors":0,"truncated":False}
  file.write_text(json.dumps({"world":"map_world","summary":complete,"records":rows}))
  with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,"incomplete"):
   ctl.verify(args)
  file.write_text(json.dumps({"summary":complete,"records":rows}))
  with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,"--source-world"):
   ctl.verify(args)
 def test_verify_rejects_decoration_masquerading_as_storage(self):
  plan=json.loads(json.dumps(PLAN))
  plan["stages"][0]["actions"]=[{"id":"crate01","op":"place",
    "kind":"storage","at":[9301,7720,0],
    "sprite":"carpentry_02_15","capacity":45}]
  self.file.write_text(json.dumps(plan))
  post=self.root/"crate_post.json"
  row={"kind":"object","x":9301,"y":7720,"z":0,
       "object_index":2,"class":"IsoThumpable",
       "sprite":"carpentry_02_15",
       "construction_tag":"refuge:shelter:crate01",
       "storage_type":"crate","storage_capacity":45}
  doc={"world":"map_world","summary":{"status":"complete",
       "errors":0,"truncated":False},"records":[
       {"kind":"square","x":9301,"y":7720,"z":0,"loaded":True},row]}
  args=argparse.Namespace(world="map_world",file=str(self.file),
       stage="shelter",survey=str(post),source_world=None)
  post.write_text(json.dumps(doc))
  with contextlib.redirect_stdout(io.StringIO()) as out:
   ctl.verify(args)
  self.assertEqual(json.loads(out.getvalue())["counts"]["seen_place"],1)
  for wrong in ({"storage_type":"other"},
                {"storage_capacity":0},
                {"storage_capacity":100},
                {"storage_type":None}):
   candidate=json.loads(json.dumps(doc))
   candidate["records"][1].update(wrong)
   post.write_text(json.dumps(candidate))
   with contextlib.redirect_stdout(io.StringIO()),        self.assertRaisesRegex(ValueError,"does not reconcile"):
    ctl.verify(args)

 def test_completed_stage_history_is_exact_and_rejects_corruption(self):
  f=self.lua/"SiegerAdminConstructionStages.txt"
  f.write_text("refuge\tshelter\t"+"a"*64+"\n")
  with patch.object(ctl.scanctl,"lua_dir",return_value=self.lua),\
       patch.object(ctl.scanctl,"slot"),\
       contextlib.redirect_stdout(io.StringIO()) as report:
   ctl.history(argparse.Namespace(world="map_world"))
  self.assertEqual(json.loads(report.getvalue())["completed"][0]["stage"],"shelter")
  f.write_text("refuge\tshelter\t"+"a"*64+"\nrefuge\tshelter\t"+"a"*64+"\n")
  with patch.object(ctl.scanctl,"lua_dir",return_value=self.lua),\
       patch.object(ctl.scanctl,"slot"),\
       self.assertRaisesRegex(ValueError,"Corrupt"):
   ctl.history(argparse.Namespace(world="map_world"))
 def test_stage_rejects_removal_after_place(self):
  bad=json.loads(json.dumps(PLAN))
  operations=bad["stages"][1]["actions"]
  bad["stages"][1]["actions"]=[operations[1],operations[0]]
  with self.assertRaisesRegex(ValueError,"removals must precede"):
   ctl.prepare(bad,"map_world","infrastructure")
 def test_negative_cases_rejected_no_automatic_action(self):
  for bad in [
   {"op":"place","kind":"window","id":"v","at":[1,1,0],
      "face":"S","sprite":"fixtures_windows_01_24"},
   {"op":"place","kind":"generator","id":"v","at":[1,1,0],
      "item":"Base.Generator","sprite":"blends_natural_01_20"},
   {"op":"remove_exact","kind":"IsoGenerator","id":"v","at":[1,1,0],
      "sprite":"Base.Generator","index":0},
   {"op":"remove_tag","kind":"IsoDoor","id":"v","at":[1,1,0],
      "sprite":"fixtures_doors_01_24","target_tag":"other"}]:
   data=json.loads(json.dumps(PLAN))
   data["stages"][0]["actions"]=[bad]
   with self.subTest(bad=bad),self.assertRaises(ValueError):
    ctl.prepare(data,"map_world","shelter")

if __name__=="__main__":unittest.main()
