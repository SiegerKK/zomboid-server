#!/usr/bin/env python3
"""Synthetic read-only checks for the five west exterior windows of Auto Shop."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"story/campaign"))
import autoshop_window_audit as audit

def survey():
    data={"status":"complete","meta":{"modes":"windows,squares"},
          "summary":{"errors":0,"truncated":False},"records":[]}
    for x,y,z,index,sprite in audit.EXTERIOR:
        data["records"] += [
          {"kind":"square","x":x,"y":y,"z":z,"loaded":True,"room":"office"},
          {"kind":"square","x":x-1,"y":y,"z":z,"loaded":True,"room":""},
          {"kind":"object","x":x,"y":y,"z":z,"object_index":index,"sprite":sprite,
           "class":"IsoWindow","window_open":False,
           "window_smashed":False,"window_glass_removed":False,
           "window_barricaded_same":False,"window_barricaded_opposite":False}
        ]
    # The separate mechanic-room partition is not external: don't board it.
    for y in (9407,9412):
        data["records"].append({"kind":"object","x":10605,"y":y,"z":0,
          "object_index":1,"sprite":"walls_commercial_02_4","class":"IsoWindow"})
    return data

class ExternalWindowTests(unittest.TestCase):
    def test_full_staging_and_two_damage_spots(self):
        data=survey()
        planned=audit.verify(data,"pre_board")
        self.assertEqual(planned["total_external_windows"],5)
        self.assertEqual(sum(r["status"]=="must_board" for r in planned["windows"]),5)
        for r in data["records"]:
            if r.get("kind")=="object" and r.get("x")==10601:
                r["window_barricaded_same"]=True
        ready=audit.verify(data,"pre_breach")
        self.assertEqual(sum(r["status"]=="ready_for_explicit_breach"
                             for r in ready["windows"]),2)
        for r in data["records"]:
            if r.get("kind")=="object" and (r.get("x"),r.get("y"),r.get("z")) in audit.BROKEN_AFTER_BOARDS:
                r["window_smashed"]=True
        self.assertEqual(len(audit.verify(data,"verify")["windows"]),5)

    def test_fail_closed_missing_west_neighbour_and_missing_boards(self):
        data=survey()
        data["records"]=[r for r in data["records"] if not (
            r["kind"]=="square" and r["x"]==10600 and r["y"]==9407)]
        with self.assertRaisesRegex(ValueError,"neighbour"):
            audit.verify(data,"pre_board")
        data=survey()
        with self.assertRaisesRegex(ValueError,"No barricade"):
            audit.verify(data,"pre_breach")
        data=survey()
        for r in data["records"]:
            if r["kind"]=="object" and r.get("x")==10601 and r.get("y")==9408:
                r["sprite"]="changed_sprite"
        with self.assertRaisesRegex(ValueError,"Historic"):
            audit.verify(data,"pre_board")

if __name__=="__main__":
    unittest.main(verbosity=2)
