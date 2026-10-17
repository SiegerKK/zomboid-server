#!/usr/bin/env python3
"""Offline validation of authored Route 17 window and blood actions."""
import copy
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import storyctl,livectl


class EnvironmentSceneTests(unittest.TestCase):
    def test_two_location_scenes_and_explicit_flags(self):
        for scene_id in ("smokeys_bar_06_fortification","smokeys_shop_05_window_blood"):
            raw,_=storyctl.read_scene(storyctl.resolve_scene(scene_id))
            types={a["type"] for a in raw["actions"]}
            self.assertIn("blood",types)
            self.assertIn("barricade",types)
            with self.assertRaisesRegex(ValueError,"allow"):
                storyctl.read_scene(storyctl.resolve_scene(scene_id),ready=True)
            reviewed,_=storyctl.read_scene(storyctl.resolve_scene(scene_id),ready=True,
                                            allow_environment=True,allow_barricades=True)
            self.assertEqual(reviewed["world"],"story_test")
            for action in reviewed["actions"]:
                wire=livectl.encode_action(action).split("\t")
                if action["type"]=="blood":
                    self.assertEqual(len(wire),11)
                    self.assertEqual(wire[5:9],["-","-1","-","-"])
                    self.assertEqual(wire[9],action["floor_sprite"])
                    self.assertEqual(wire[10],str(action["splats"]))
                else:
                    self.assertEqual(len(wire),10)
                    self.assertEqual(wire[5],"window")
                    self.assertEqual(wire[8],"IsoWindow")
                    if action["type"]=="window":
                        self.assertEqual(wire[9],"smash")
                    else:
                        self.assertEqual(wire[9],str(action["planks"]))

    def test_window_repair_is_fail_closed(self):
        data,_=storyctl.read_scene(storyctl.resolve_scene("smokeys_shop_05_window_blood"))
        action=next(a for a in data["actions"] if a["type"]=="window")
        modified=copy.deepcopy(action)
        modified['enabled']=True
        modified["operation"]="repair"
        with self.assertRaisesRegex(ValueError,"not verified"):
            storyctl.check_action(modified,ready=True,allow_barricades=True,
                                  allow_environment=True)
        with self.assertRaisesRegex(ValueError,"repair is not approved"):
            livectl.encode_action(modified)

    def test_strict_blood_validation(self):
        data,_=storyctl.read_scene(storyctl.resolve_scene("smokeys_shop_05_window_blood"))
        item=next(a for a in data["actions"] if a["type"]=="blood")
        for key,value in (("splats",0),("splats",True),("splats",4),
                          ("floor_sprite","bad.sprite")):
            with self.subTest(key=key):
                altered=copy.deepcopy(item)
                altered[key]=value
                with self.assertRaises(ValueError):
                    storyctl.check_action(altered,ready=True,allow_barricades=True,
                                          allow_environment=True)


if __name__=="__main__":
    unittest.main(verbosity=2)
