#!/usr/bin/env python3
"""Validate the exact Route 17 bathroom corpse scene and audit records."""
from __future__ import annotations
import copy
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import storyctl,livectl
spec=importlib.util.spec_from_file_location("corpse_questctl",ROOT/"story/questctl.py")
audit_module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class CorpseSceneTests(unittest.TestCase):
    def test_scene_validation_and_wire_protocol(self):
        src=storyctl.resolve_scene("smokeys_shop_04_bathroom_corpse")
        reviewed,stats=storyctl.read_scene(src)
        self.assertEqual(stats["total"],1)
        self.assertEqual(reviewed["world"],"story_test")
        with self.assertRaisesRegex(ValueError,"allow-corpses"):
            storyctl.read_scene(src,ready=True)
        ready,_=storyctl.read_scene(src,ready=True,allow_corpses=True)
        action=ready["actions"][0]
        self.assertEqual(action["at"],{"x":10602,"y":9403,"z":0})
        self.assertEqual(action["floor_sprite"],"floors_interior_tilesandwood_01_21")
        self.assertEqual(action["room"],"bathroom")
        self.assertEqual(action["ground_item"],"Base.Revolver")
        self.assertEqual(action["blood"],1)
        packet=livectl.encode_action(action).split("\t")
        self.assertEqual(len(packet),13)
        self.assertEqual(packet[:5],["corpse",action["id"],"10602","9403","0"])
        self.assertEqual(packet[-4:],["bathroom",action["floor_sprite"],"1","Base.Revolver"])

    def test_negative_payloads_fail_before_mutation(self):
        src=storyctl.resolve_scene("smokeys_shop_04_bathroom_corpse")
        scene,_=storyctl.read_scene(src)
        for key,bad in (
            ("room","office"),("ground_item","Base.Pistol"),("blood",-1),
            ("blood",4),("blood",True),("floor_sprite","bad.sprite")
        ):
            with self.subTest(key=key,bad=bad):
                act=copy.deepcopy(scene["actions"][0])
                act[key]=bad
                with self.assertRaises(ValueError):
                    storyctl.check_action(act,ready=True,allow_barricades=False,
                                          allow_corpses=True)

    def test_ledger_reports_both_objects_once(self):
        with tempfile.TemporaryDirectory() as folder:
            old=audit_module.STORE
            try:
                audit_module.STORE=Path(folder)
                w=audit_module.STORE/"worlds/story_test"
                (w/"data/Lua").mkdir(parents=True)
                (w/"profile").write_text("test")
                base="SiegerStory:smokeys_shop_04_bathroom_corpse:bathroom_body_and_revolver"
                (w/"data/Lua/SiegerStoryQuestEvents.txt").write_text(
                    "v1\tspawn\tsmokeys_shop_04_bathroom_corpse\tbathroom_body_and_revolver\t"
                    +base+":corpse\tcorpse\t10602\t9403\t0\t-1\n"
                    +"v1\tspawn\tsmokeys_shop_04_bathroom_corpse\tbathroom_body_and_revolver\t"
                    +base+":revolver\titem\t10602\t9403\t0\t-1\n")
                result=audit_module.audit("story_test","smokeys_shop_04_bathroom_corpse")
                self.assertEqual(result["counts"]["corpse_spawns"],1)
                self.assertEqual(result["counts"]["item_spawns"],1)
                self.assertEqual(result["counts"]["duplicate_rows"],0)
            finally:
                audit_module.STORE=old


if __name__=="__main__":
    unittest.main(verbosity=2)
