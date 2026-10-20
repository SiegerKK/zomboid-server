#!/usr/bin/env python3
"""Review practical Story Director notes accompanying farm stages II–IV.

They are real readable B42 notes, but NOT part of constructionsetup's stock
batch. Activating them requires a separate reviewed Story live session.
"""
from __future__ import annotations
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "story"))
import storyctl
import livectl

EXPECTED = {
    2: ("kitchen_ration_sheet", "house_duty_rota", "first_generator_log"),
    3: ("workshop_job_book", "greenhouse_planting_sheet", "hygiene_water_rota"),
    4: ("resident_allocation_book", "north_store_stock_book",
        "gate_watch_log", "reserve_generator_card"),
}

class FarmHouseholdNotes(unittest.TestCase):
    def test_all_readable_note_scenes_validate_using_existing_runtime_protocol(self):
        for phase, names in EXPECTED.items():
            with self.subTest(phase=phase):
                path = ROOT / "story" / "scenes" / f"farm_household_{phase:02d}.json"
                scene, report = storyctl.read_scene(path, ready=True)
                self.assertEqual(scene["id"], path.stem)
                self.assertEqual(scene["world"], "story_test")
                self.assertTrue(scene["enabled"])
                self.assertEqual(report["active"], len(names))
                self.assertEqual(report["unmapped"], 0)
                self.assertEqual(tuple(a["id"] for a in scene["actions"]), names)
                self.assertLess(len(scene["actions"]), livectl.MAX_SCENE_ACTIONS)
                wires = [livectl.encode_action(a) for a in scene["actions"]]
                self.assertLess(len(("\n".join(wires) + "\n").encode()),
                                livectl.MAX_REQUEST_BYTES)
                for a in scene["actions"]:
                    self.assertEqual(a["type"], "note")
                    self.assertEqual(a["placement"], "ground")
                    self.assertNotIn("selector", a)
                    self.assertIn("support", a)
                    self.assertEqual(a["support"]["class"], "IsoObject")
                    self.assertGreater(a["pose"]["z"], 0)
                    self.assertLess(a["pose"]["z"], 0.9)
                    self.assertGreaterEqual(len(a["purpose"]), 12)
                    self.assertTrue(1 <= len(a["pages"]) <= 8)
                    x, y, z = a["at"].values()
                    self.assertTrue(9255 <= x <= 9296 and 7699 <= y <= 7799)
                    self.assertTrue(z in (0, 1))
                    text = "\n".join(a["pages"]).lower()
                    self.assertNotIn("игрок", text)
                    self.assertNotIn("найдите", text)
                    self.assertNotIn("если вы читаете", text)

    def test_no_stage_one_household_papers(self):
        self.assertFalse((ROOT / "story" / "scenes" / "farm_household_01.json").exists())

    def test_operations_depend_on_actual_stage_progress(self):
        from json import loads
        manifest = ROOT / "story" / "camp" / "scenes" / "survival_farm" / "stages_build.json"
        plan = loads(manifest.read_text("utf-8"))
        self.assertEqual([s["id"] for s in plan["stages"]],
                         ["phase01", "phase02", "phase03", "phase04"])
        expected_tags = {
            2: {"first_generator", "water_service_crate"},
            3: {"workshop_parts_crate", "sleep_hut_personal_crate"},
            4: {"reserve_generator", "guard_medical_crate"}
        }
        for phase, required in expected_tags.items():
            stage = plan["stages"][phase - 1]
            self.assertTrue(required <= {a["id"] for a in stage["actions"]})

if __name__ == "__main__":
    unittest.main()
