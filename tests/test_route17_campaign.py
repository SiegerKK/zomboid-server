#!/usr/bin/env python3
"""Route 17 authored scene contract tests; never modifies a running world."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "story"))
from storyctl import read_scene, resolve_scene

BAR = [
    "smokeys_bar_01_public",
    "smokeys_bar_02_service",
    "smokeys_bar_03_upstairs",
    "smokeys_bar_04_lived_in",
    "smokeys_bar_05_departure",
    "smokeys_bar_06_fortification",
]
SHOP = [
    "smokeys_shop_01_aftermath",
    "smokeys_shop_02_details",
    "smokeys_shop_03_infected",
    "smokeys_shop_04_bathroom_corpse",
    "smokeys_shop_05_window_blood",
]


class CampaignTests(unittest.TestCase):
    def test_expected_scenes_are_reviewed_and_live_bounded(self):
        totals = {"notes": 0, "items": 0, "infected": 0, "actions": 0}
        for sid in BAR + SHOP:
            path = resolve_scene(sid)
            raw, _ = read_scene(path)
            self.assertEqual(raw["world"], "story_test")
            self.assertTrue(raw["enabled"])
            self.assertLessEqual(len(raw["actions"]), 32)
            totals["actions"] += len(raw["actions"])
            allowed = {"note", "loot", "blood", "barricade"} if sid in BAR else {"note", "loot", "infected", "corpse", "blood", "window", "barricade"}
            self.assertTrue(set(a["type"] for a in raw["actions"]).issubset(allowed))
            validated, stats = read_scene(path, ready=True, allow_infected=True,
                                          allow_corpses=True, allow_environment=True,
                                          allow_barricades=True)
            self.assertEqual(stats["unmapped"], 0)
            self.assertEqual(stats["active"], len(validated["actions"]))
            self.assertEqual(len({a["id"] for a in validated["actions"]}), len(validated["actions"]))
            for action in validated["actions"]:
                self.assertIsInstance(action.get("purpose"), str, 
                    f"{sid}:{action['id']} must explain its narrative purpose")
                self.assertGreaterEqual(len(action["purpose"]), 12)
                self.assertFalse(action["id"].startswith((
                    "dining_detail_", "upper_living_", "upper_dining_",
                    "kitchen_trace_", "floor_debris_", "last_bay_")),
                    f"Generic filler action survived in {sid}")
                pos = action["at"]
                self.assertEqual(pos["z"], 0 if sid.startswith("smokeys_shop_") else pos["z"])
                if action["type"] == "note":
                    totals["notes"] += 1
                    self.assertLessEqual(len(action["pages"]), 8)
                    self.assertTrue(all(len(x) <= 2000 for x in action["pages"]))
                elif action["type"] == "loot":
                    totals["items"] += sum(x["count"] for x in action["items"])
                    self.assertTrue(all(x["type"].startswith("Base.") for x in action["items"]))
                    self.assertTrue(all(isinstance(x.get("purpose"), str)
                        and len(x["purpose"]) >= 12 for x in action["items"]),
                        f"Every item requires individual purpose: {sid}:{action['id']}")
                elif action["type"] == "infected":
                    totals["infected"] += 1
                    self.assertEqual((action["subtype"], action["count"]), ("vanilla", 1))
                elif action["type"] == "corpse":
                    self.assertEqual(action["ground_item"], "Base.Revolver")
                    self.assertEqual(action["room"], "bathroom")
                else:
                    self.assertIn(action["type"], ("blood", "window", "barricade"))
        self.assertEqual(totals["notes"], 24)
        self.assertEqual(totals["items"], 63)  # Every change requires explicit review.
        self.assertEqual(totals["infected"], 10)
        self.assertEqual(totals["actions"], 75)

    def test_van_only_quest_items_are_not_placed_in_bar(self):
        notes = []
        for sid in BAR:
            data, _ = read_scene(resolve_scene(sid))
            notes.extend(a for a in data["actions"] if a["type"] == "note")
        canon = {a["id"] for a in notes}
        for required in (
            "house_rules", "common_trade", "open_accounts", "sarah_medical_log",
            "sarah_noah", "radio_watch", "shop_run_original", "northbound_ledger",
            "dont_take_books", "last_board"
        ):
            self.assertIn(required, canon)
        self.assertNotIn("h_notes", canon)
        self.assertNotIn("sarah_letter", canon)
        self.assertNotIn("hale_original", canon)
        ledger = next(a for a in notes if a["id"] == "northbound_ledger")
        body = "\n".join(ledger["pages"])
        self.assertEqual(len(ledger["pages"]), 4)
        self.assertIn("KELLER, SARAH — MEDIC", body)
        self.assertIn("MADDOX, NOAH — MECHANIC", body)
        self.assertIn("SMOKEY'S CLOSED", body)
        self.assertIn("WHITE UTILITY VAN", body)

    def test_enemy_scene_requires_explicit_approval(self):
        with self.assertRaisesRegex(ValueError, "allow-infected"):
            read_scene(resolve_scene("smokeys_shop_03_infected"), ready=True)
        enemies, _ = read_scene(resolve_scene("smokeys_shop_03_infected"),
                                ready=True, allow_infected=True)
        ids = {a["id"] for a in enemies["actions"]}
        for person in ("gray_michael", "talbot_june", "mills_terry",
                       "barrett_cole", "webb_ellis"):
            self.assertIn(person, ids)
        self.assertEqual(len(ids), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
