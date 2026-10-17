#!/usr/bin/env python3
"""Offline tests for natural loot placement and safe window planning."""
from __future__ import annotations
import argparse
import sys
import unittest
import tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
sys.path.insert(0,str(ROOT/"story/campaign"))
import storyctl,livectl,smokeys_window_plan

class PlacementTests(unittest.TestCase):
    def test_pose_ground_and_tabletop(self):
        loot={"id":"coffee_on_table","type":"loot","at":{"x":10622,"y":9221,"z":0},
            "placement":"ground","items":[{"type":"Base.Bandage","count":1}],
            "pose":{"x":0.15,"y":0.85,"z":0.65,"angle":271},
            "support":{"object_index":2,"sprite":"furniture_tables_01_15","class":"IsoObject"}}
        storyctl.check_action(loot,ready=True,allow_barricades=False)
        wire=livectl.encode_action(loot).split("\t")
        self.assertEqual(len(wire),16)
        self.assertEqual(wire[-6:],["150","850","650","271","2","furniture_tables_01_15"])
        bad=loot.copy()
        bad.pop("support")
        with self.assertRaisesRegex(ValueError,"support"):
            storyctl.check_action(bad,ready=True,allow_barricades=False)
        bad=loot.copy()
        bad["pose"]={"x":1.1,"y":0.3,"z":0.65,"angle":0}
        with self.assertRaises(ValueError):
            storyctl.check_action(bad,ready=True,allow_barricades=False)
        bad=loot.copy()
        bad["pose"]={"x":0.7,"y":0.5,"z":0.0,"angle":360}
        with self.assertRaises(ValueError):
            storyctl.check_action(bad,ready=True,allow_barricades=False)

    def test_relocate_requires_exact_token_and_permission(self):
        a={"id":"move_001","type":"relocate","at":{"x":10622,"y":9222,"z":0},
           "token":"SiegerStory:smokeys_bar_01_public:dining_detail_01:1:1",
           "destination":{"x":10621,"y":9221,"z":0},
           "pose":{"x":0.2,"y":0.72,"z":0.65,"angle":40},
           "support":{"object_index":1,"sprite":"furniture_tables_01_15","class":"IsoObject"}}
        with self.assertRaisesRegex(ValueError,"allow-relocate"):
            storyctl.check_action(a,ready=True,allow_barricades=False)
        storyctl.check_action(a,ready=True,allow_barricades=False,allow_relocate=True)
        wire=livectl.encode_action(a).split("\t")
        self.assertEqual(len(wire),19)
        self.assertEqual(wire[9],a["token"])
        self.assertEqual(wire[10:13],["10621","9221","0"])
        far={**a,"destination":{"x":9999,"y":9221,"z":0}}
        with self.assertRaises(ValueError):
            storyctl.check_action(far,ready=True,allow_barricades=False,allow_relocate=True)
        unowned={**a,"token":"Base.Bandage"}
        with self.assertRaises(ValueError):
            storyctl.check_action(unowned,ready=True,allow_barricades=False,allow_relocate=True)

    def test_inline_ground_offsets_and_relocate(self):
        x=argparse.Namespace(world="story_test",key="natural_001",type="loot",
            x=10622,y=9222,z=0,placement="ground",target_index=None,target_sprite=None,
            offset_x=0.12,offset_y=0.79,height=0.65,angle=90,
            support_index=1,support_sprite="furniture_tables_01_15",
            item="Base.Bandage",count=1,title=None,text=None,
            floor_sprite=None,splats=1,planks=2,script=None,direction="N",skin_index=-1,
            blood=1,token=None,to_x=None,to_y=None,to_z=None,
            allow_infected=False,allow_corpses=False,allow_barricades=False,
            allow_environment=False,allow_vehicles=False,allow_relocate=False,yes=False)
        scene,_=livectl.build_inline_scene(x)
        self.assertEqual(scene["actions"][0]["pose"]["z"],0.65)
        x.type="relocate";x.item=None;x.token="SiegerStory:smokeys_bar_01_public:dining_detail_01:1:1"
        x.to_x=10623;x.to_y=9221;x.to_z=0
        with self.assertRaisesRegex(ValueError,"allow-relocate"):
            livectl.build_inline_scene(x)
        x.allow_relocate=True
        self.assertEqual(livectl.build_inline_scene(x)[0]["actions"][0]["destination"]["x"],10623)

    def test_window_plan_all_32_and_missing_fails(self):
        windows=smokeys_window_plan.WINDOWS
        rows=[]
        for x,y,z,i,sprite in windows:
            rows.append({"kind":"square","x":x,"y":y,"z":z,"loaded":True})
            rows.append({"kind":"object","x":x,"y":y,"z":z,"class":"IsoWindow",
                "object_index":i,"sprite":sprite,"window_open":False,
                "window_smashed":False,"window_glass_removed":False,
                "window_barricaded_same":False,"window_barricaded_opposite":False})
        data={"status":"complete","meta":{"side":51,"min_z":0,"max_z":1,"modes":"squares,windows"},
              "summary":{"errors":0,"truncated":False},"records":rows}
        result=smokeys_window_plan.plan(data)
        self.assertEqual(result["total_original_windows"],32)
        self.assertEqual(result["operations_to_apply"],32)
        self.assertTrue(all("--yes" not in r["cmd_preview"] for r in result["operations"]))
        rows[1]["window_smashed"]=True
        rows[3]["window_barricaded_same"]=True
        result=smokeys_window_plan.plan(data)
        self.assertEqual(result["already_safe"],2)
        self.assertEqual(result["operations_to_apply"],30)
        rows[3]["window_barricaded_same"]=False
        del rows[3]["window_open"]
        with self.assertRaisesRegex(ValueError,"state"):
            smokeys_window_plan.plan(data)

if __name__=="__main__":
    unittest.main(verbosity=2)
