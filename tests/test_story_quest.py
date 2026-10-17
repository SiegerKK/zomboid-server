#!/usr/bin/env python3
"""Offline Story clinic quest validation and ledger tests."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import storyctl,livectl

spec=importlib.util.spec_from_file_location("quest_audit",ROOT/"story/questctl.py")
quest=importlib.util.module_from_spec(spec)
spec.loader.exec_module(quest)

class QuestTests(unittest.TestCase):
    def test_real_mapped_scene_and_opt_in_gate(self):
        src=ROOT/"story/scenes/clinic_quest_001.json"
        scene,summary=storyctl.read_scene(src)
        self.assertEqual(scene["world"],"story_test")
        self.assertEqual(summary["total"],11)
        self.assertEqual(sum(a["type"]=="infected" for a in scene["actions"]),6)
        with self.assertRaisesRegex(ValueError,"allow-infected"):
            storyctl.read_scene(src,ready=True)
        checked,counts=storyctl.read_scene(src,ready=True,allow_infected=True)
        self.assertEqual(counts["unmapped"],0)
        for action in checked["actions"]:
            if action["type"]=="infected":
                self.assertEqual(action["subtype"],"vanilla")
                self.assertEqual(action["count"],1)
                wire=livectl.encode_action(action)
                self.assertEqual(len(wire.split("\t")),11)
                self.assertTrue(wire.startswith("infected\t"))
            elif action["type"] in ("note","loot"):
                self.assertEqual(action["placement"],"container")
                self.assertEqual(action["selector"]["class"],"IsoObject")
        self.assertEqual(len({a["id"] for a in checked["actions"]}),11)

    def test_quest_ledger_idempotence_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            old=quest.STORE
            try:
                quest.STORE=Path(tmp)
                world=quest.STORE/"worlds/story_test"
                (world/"data/Lua").mkdir(parents=True)
                (world/"profile").write_text("mp-test\n")
                p=world/"data/Lua/SiegerStoryQuestEvents.txt"
                token="SiegerStory:clinic_quest_001:morgue_guard_a:1"
                p.write_text(
                    "v1\tspawn\tclinic_quest_001\tmorgue_guard_a\t"+token+"\tinfected\t3169\t12122\t0\t7\n"
                    "v1\tdead\tclinic_quest_001\tmorgue_guard_a\t"+token+"\tinfected\t3170\t12123\t0\t7\n"
                    "v1\tdead\tclinic_quest_001\tmorgue_guard_a\t"+token+"\tinfected\t3170\t12123\t0\t7\n")
                data=quest.audit("story_test","clinic_quest_001")
                self.assertEqual(data["counts"]["infected_spawns"],1)
                self.assertEqual(data["counts"]["infected_deaths"],1)
                self.assertEqual(data["counts"]["duplicate_rows"],1)
                self.assertEqual(data["counts"]["infected_without_reported_death"],0)
                self.assertEqual(quest.audit("story_test","other_quest_001")["events_seen"],0)
                p.write_text("invalid\n")
                with self.assertRaisesRegex(ValueError,"Malformed"):
                    quest.audit("story_test","clinic_quest_001")
            finally:
                quest.STORE=old

if __name__=="__main__":
    unittest.main(verbosity=2)
