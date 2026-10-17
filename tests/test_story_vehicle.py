#!/usr/bin/env python3
"""Offline vehicle action safety validation; no car creation."""
import copy
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import storyctl,livectl

ACTION={
 "id":"route17_van_probe","type":"vehicle","enabled":True,
 "at":{"x":10620,"y":9209,"z":0},
 "script":"Base.Van","direction":"S","skin_index":-1
}

class VehicleValidation(unittest.TestCase):
    def test_allow_vehicles_is_required_and_wire_fixed(self):
        with self.assertRaisesRegex(ValueError,"allow-vehicles"):
            storyctl.check_action(ACTION,ready=True,allow_barricades=False)
        enabled,pos=storyctl.check_action(ACTION,ready=True,allow_barricades=False,allow_vehicles=True)
        self.assertTrue(enabled)
        self.assertEqual(pos,[10620,9209,0])
        fields=livectl.encode_action(ACTION).split("\t")
        self.assertEqual(fields,["vehicle","route17_van_probe","10620","9209","0",
                                 "-","-1","-","-","Base.Van","S","-1"])

    def test_reject_untrusted_scripts_invalid_area_and_missing_direction(self):
        for key,val in [
            ("script","TLOU.SpecialCar"),("script","Base.Van;bad"),
            ("direction","SOUTH"),("skin_index",100),("skin_index",True),
            ("at",{"x":3171,"y":12141,"z":0}),
            ("at",{"x":10620,"y":9209,"z":1})]:
            with self.subTest(key=key,value=val):
                a=copy.deepcopy(ACTION);a[key]=val
                with self.assertRaises(ValueError):
                    storyctl.check_action(a,ready=True,allow_barricades=False,
                                          allow_vehicles=True)

if __name__=="__main__":
    unittest.main(verbosity=2)
