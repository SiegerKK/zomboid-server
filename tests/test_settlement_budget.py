#!/usr/bin/env python3
"""Offline settlement reserve arithmetic and independent sleeping place tests."""
from __future__ import annotations
import copy
import unittest
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import settlementbudget as budget

def sample(phase="phase01",n=2,days=7,fuel=0,generators=0,duty=0):
    food=n*days*2400;water=n*days*4
    zones=[]
    for ix,label in enumerate(("kitchen","upstairs","barn","warehouse")):
        zones.append({"zone":label,"function":"Current stage reviewed purpose",
           "capacity_proved_by_snapshot":False,
           "quantitative_reserve_target":{
                "food_kcal":food if ix==0 else 0,
                "potable_water_l":water if ix==0 else 0,
                "reserve_gasoline_l":fuel if ix==3 else 0}})
    regular=n if phase!="phase04" else n-2
    beds=[{"name":f"Person {ix}","bed":f"B{ix}",
           "belongings":["journal","repaired glove"],
           "status":"regular" if ix<regular else "optional_visitor"}
          for ix in range(n)]
    return {"schema":budget.SCHEMA,"world":"test_world","settlement":"survival_farm",
      "stage":phase,"residents_planned":n,"residents_regular":regular,
      "reserve_days":days,
      "model":{"food_kcal_person_day":2400,"potable_l_person_day":4,
        "sanitation_l_person_day":6,"game_consumption_not_measured":True},
      "requirements":{"food_kcal":food,"potable_water_l":water,
        "sanitation_water_usage_l_not_stored":n*days*6,
        "fuel_l":fuel,"generator_units":generators,
        "generator_duty_hours_day":duty,
        "generator_gasoline_l_for_assumed_duty":0.6*days*duty,
        "fuel_assumption_not_verified_on_game_server":True},
      "zones":zones,"sleeping_personal_effects":beds,
      "agriculture":{"livestock":False,"farming_spawn_adapter_available":False,
                     "observed_corpses_needing_review":14,"plot_cells_target":0},
      "important_caveats":["calorie verification missing",
           "liquid verification missing","sleeping API missing","cleaning pending"]}

class StockTests(unittest.TestCase):
    def test_every_phase_is_arithmetically_complete_but_not_falsely_claimed_installed(self):
        for args in (("phase01",2,7,0,0,0),
                     ("phase02",4,14,35,1,4),
                     ("phase03",6,21,70,1,5),
                     ("phase04",10,21,110,2,5)):
            with self.subTest(phase=args[0]):
                got=budget.validate(sample(*args))
                self.assertEqual(got["status"],"design_balanced_not_game_resource_verified")
                self.assertEqual(got["named_sleeping_places"],args[1])
                self.assertEqual(got["food_kcal_required"],args[1]*args[2]*2400)
                self.assertEqual(got["potable_water_l_required"],args[1]*args[2]*4)
                self.assertEqual(len(got["blockers"]),5)
    def test_missing_water_calories_or_unallocated_fuel_refused(self):
        good=sample("phase04",10,21,110,2,5)
        for mutation in (
            lambda d:d["requirements"].__setitem__("potable_water_l",0),
            lambda d:d["requirements"].__setitem__("food_kcal",300),
            lambda d:d["zones"][3]["quantitative_reserve_target"].__setitem__("reserve_gasoline_l",0),
            lambda d:d["zones"][1].__setitem__("zone","kitchen"),
            lambda d:d["sleeping_personal_effects"][2].__setitem__("bed","B1"),
            lambda d:d["sleeping_personal_effects"].pop(),
            lambda d:d["requirements"].__setitem__("generator_units",0),
            lambda d:d["agriculture"].__setitem__("livestock",True),
            lambda d:d["model"].__setitem__("game_consumption_not_measured",False),
        ):
            broken=copy.deepcopy(good)
            mutation(broken)
            with self.assertRaises(ValueError):budget.validate(broken)
    def test_stage_one_no_power_and_stage_four_guest_count(self):
        zero=sample()
        zero["requirements"]["fuel_l"]=10
        zero["zones"][3]["quantitative_reserve_target"]["reserve_gasoline_l"]=10
        with self.assertRaisesRegex(ValueError,"First phase"):
            budget.validate(zero)
        guest=sample("phase04",10,21,110,2,5)
        guest["residents_regular"]=10
        with self.assertRaisesRegex(ValueError,"Regular population"):
            budget.validate(guest)
if __name__=="__main__":unittest.main()
