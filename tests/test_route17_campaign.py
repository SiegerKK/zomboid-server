#!/usr/bin/env python3
"""Route 17 authored scene contract tests; never modifies a running world."""
from __future__ import annotations

import sys
import unittest
import os
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
    "smokeys_bar_07_upstairs_fortification",
]
SHOP = [
    "smokeys_shop_01_aftermath",
    "smokeys_shop_02_details",
    "smokeys_shop_03_infected",
    "smokeys_shop_04_bathroom_corpse",
    "smokeys_shop_05_window_blood",
    "smokeys_shop_06_boarded_glass_breach",
]


class CampaignTests(unittest.TestCase):
    def test_system_manager_remains_executable(self):
        self.assertTrue(os.access(ROOT / 'pz', os.X_OK))

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
                                          allow_barricades=True,
                                          allow_barricaded_smash=True)
            self.assertEqual(stats["unmapped"], 0)
            self.assertEqual(stats["active"], sum(a.get('enabled', True) for a in validated['actions']))
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
        self.assertEqual(totals["notes"], 14)
        self.assertEqual(totals["items"], 64)  # One scene radio prop; otherwise original 63.
        self.assertEqual(totals["infected"], 10)
        self.assertEqual(totals["actions"], 105)

    def test_van_only_quest_items_are_not_placed_in_bar(self):
        notes = []
        for sid in BAR:
            data, _ = read_scene(resolve_scene(sid))
            notes.extend(a for a in data["actions"] if a["type"] == "note")
        canon = {a["id"] for a in notes}
        for required in (
            "house_rules", "common_trade", "open_accounts", "sarah_medical_log",
            "radio_watch", "shop_run_original", "northbound_ledger",
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

    def test_notes_visibility_page_medium_and_radio_location(self):
        figures={}
        for site, scenes in (("bar",BAR),("shop",SHOP)):
            notes=[]
            for sid in scenes:
                scene,_=read_scene(resolve_scene(sid))
                notes += [a for a in scene["actions"] if a["type"]=="note" and a.get("enabled",True)]
            hidden=[a for a in notes if a["placement"]=="container"]
            figures[site]=(len(notes),len(hidden))
            self.assertGreaterEqual(len(hidden)*100,30*len(notes))
            self.assertLessEqual(len(hidden)*100,50*len(notes))
            self.assertTrue(all(len(n["pages"]) in (1,4) for n in notes))
        self.assertEqual(figures,{"bar":(10,5),"shop":(4,2)})
        scene,_=read_scene(resolve_scene("smokeys_bar_03_upstairs"))
        radio=next(a for a in scene["actions"] if a["id"]=="thomas_kitchen_radio")
        schedule=next(a for a in scene["actions"] if a["id"]=="radio_watch")
        self.assertEqual(radio["at"],{"x":10621,"y":9232,"z":1})
        self.assertEqual(schedule["at"],radio["at"])
        self.assertEqual(radio["items"][0]["type"],"Base.HamRadio1")
        self.assertEqual(radio["support"]["sprite"],"furniture_tables_high_01_15")
        self.assertEqual(schedule["support"],radio["support"])
        self.assertEqual(len(next(a for a in scene["actions"] if a["id"]=="northbound_ledger")["pages"]),4)

    def test_all_windows_barricaded_and_shop_damage_explicitly_staged(self):
        bar_windows=[]
        for sid in ("smokeys_bar_06_fortification","smokeys_bar_07_upstairs_fortification"):
            data,_=read_scene(resolve_scene(sid))
            bar_windows.extend(a for a in data["actions"] if a["type"]=="barricade")
        self.assertEqual(len(bar_windows),32)
        self.assertEqual(len({(a["at"]["x"],a["at"]["y"],a["at"]["z"])
                             for a in bar_windows}),32)
        self.assertTrue(all(1<=a["planks"]<=4 for a in bar_windows))
        exterior,_=read_scene(resolve_scene("smokeys_shop_05_window_blood"))
        boarded=[a for a in exterior["actions"] if a["type"]=="barricade"]
        self.assertEqual({(a["at"]["x"],a["at"]["y"]) for a in boarded},
                         {(10601,y) for y in (9407,9408,9409,9411,9412)})
        self.assertEqual(len([a for a in exterior["actions"] if a["type"]=="blood"]),9)
        stage,_=read_scene(resolve_scene("smokeys_shop_06_boarded_glass_breach"))
        predecessors={a["id"] for a in boarded}
        self.assertEqual(len(stage["actions"]),2)
        self.assertTrue(all(a["operation"]=="smash_barricaded"
            and a["requires_action"] in predecessors for a in stage["actions"]))

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
