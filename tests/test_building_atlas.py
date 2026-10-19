#!/usr/bin/env python3
"""Universal Building Atlas protocol and one-frame density regression suite."""
from __future__ import annotations
import argparse
import contextlib
import io
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import buildingatlas as a
import buildingdensity as d

def fixture(rid,world="map_world"):
    # One large school with two OVERLAPPING room rectangles + two floors.
    lines=[
        "\t".join(["v1",rid,world,"100","200","140","240","0","1","chunk_presence","3"]),
        "\t".join(["b","b0","100","200","120","220","7363686f6f6c"]),
        "\t".join(["r","b0","b0_r0","0","101","201","110","211","636c617373"]),
        "\t".join(["r","b0","b0_r0","0","108","209","117","217","636c617373"]),
        "\t".join(["r","b0","b0_r1","1","100","200","112","212","7570706572"]),
        "\t".join(["b","b2","122","210","127","218","-"]),
        "\t".join(["r","b2","b2_r0","0","123","210","126","217","676172616765"]),
        "\t".join(["c","10","20"]),
        "end\t7\t2\t3\t4\t1"
    ]
    return "\n".join(lines)+"\n"

def roster():
    zs=[
        {"snapshot_index":0,"x":102,"y":202,"z":0,"type":"TLOU_Runner"},
        {"snapshot_index":1,"x":109,"y":210,"z":0,"type":"TLOU_Clicker"},
        {"snapshot_index":2,"x":125,"y":215,"z":0,"type":"TLOU_Stalker"},
        {"snapshot_index":3,"x":111,"y":201,"z":1,"type":"unknown"},
        {"snapshot_index":4,"x":135,"y":235,"z":0,"type":"TLOU_Runner"},
        {"snapshot_index":5,"x":900,"y":900,"z":0,"type":"TLOU_Runner"}
    ]
    return {"status":"complete","operation":"roster",
            "coverage":{"inspected":len(zs),"null_slots":1,
                        "list_slots":len(zs)+1,"truncated":False},
            "zombies":zs}

class AtlasTests(unittest.TestCase):
    def test_real_lua_wire_output_is_accepted_by_python(self):
        lua=shutil.which("lua5.1")
        if not lua:self.skipTest("Lua 5.1 unavailable")
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/"atlas.txt"
            subprocess.run([lua,str(ROOT/"tests/building_atlas.lua"),
                str(ROOT/"story/runtime/SiegerAdminBuildingAtlas.lua"),str(output)],
                check=True,capture_output=True,text=True)
            parsed=a.read_atlas(output)
            self.assertEqual(parsed["counts"]["room_rectangles"],4)
    def test_atlas_runtime_passes_real_readiness_name_gate(self):
        # Keep the actual name gate: mocking assert_module_ready hid a broken
        # production capture despite all protocol fixtures passing.
        class ReachedReadiness(Exception):pass
        with patch.object(a.scanctl,"assert_ready",side_effect=ReachedReadiness):
            with self.assertRaises(ReachedReadiness):
                a.scanctl.assert_module_ready("story_test","SiegerAdminBuildingAtlas")
            with self.assertRaisesRegex(ValueError,"Invalid Story runtime name"):
                a.scanctl.assert_module_ready("story_test","SiegerAdminArbitrary")
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.world="map_world"
        self.file=self.root/"atlas.txt"
        self.id="a"*32
        self.file.write_text(fixture(self.id),encoding="utf-8")
    def test_exact_geometry_and_geojson(self):
        data=a.read_atlas(self.file)
        self.assertEqual(data["world"],"map_world")
        self.assertEqual(data["counts"],{
            "buildings":2,"rooms":3,"room_rectangles":4,"loaded_chunks":1,"rows":7})
        self.assertEqual(data["buildings"][0]["map_id"],"school")
        self.assertEqual(data["buildings"][0]["rooms"][0]["name"],"class")
        self.assertEqual(len(a.geojson(data)["features"]),6)
        self.assertEqual(a.geojson(data)["pz_coordinate_system"],
                         "local tiles (NOT WGS84)")
    def test_status_and_queued_request_identity(self):
        with patch.object(a.scanctl,"slot",return_value=self.root),\
                patch.object(a.scanctl,"lua_dir",return_value=self.root),\
                patch.object(a.scanctl,"assert_module_ready"),\
                contextlib.redirect_stdout(io.StringIO()):
            args=argparse.Namespace(world=self.world,bbox="100,200,140,240",
                  floors="0:1",max_rows=250000,yes=False,acknowledge_failed=False)
            a.capture(args)
            self.assertFalse((self.root/a.REQUEST).exists())
            args.yes=True;a.capture(args)
            meta=a.request(self.world)
            self.assertEqual(meta["bbox"],[100,200,140,240])
            with self.assertRaisesRegex(ValueError,"pending"):
                a.capture(args)
            status=("v1\t"+meta["id"]+"\tmap_world\tcomplete\t2\t3\t4\t1\t7\t"+
                    a.PREFIX+meta["id"]+".txt\tmeta_buildings\n")
            (self.root/a.ACK).write_text(status)
            self.assertEqual(a.receipt(self.world,meta)["status"],"complete")
    def test_partial_and_tampered_export_rejected(self):
        for modified in [
            fixture(self.id).replace("end\t7\t2\t3\t4\t1\n",""),
            fixture(self.id).replace("end\t7\t2\t3\t4\t1","end\t7\t2\t2\t4\t1"),
            fixture(self.id).replace("c\t10\t20","c\t999\t20"),
            fixture(self.id).replace("r\tb0","r\tb999",1),
            fixture(self.id)+"c\t10\t20\n"
        ]:
            self.file.write_text(modified)
            with self.subTest(tail=modified[-25:]),self.assertRaises(ValueError):
                a.read_atlas(self.file)
    def test_density_uses_actual_rooms_not_building_bounding_box(self):
        atlas=a.read_atlas(self.file)
        source,origin=d.source_roster(roster(),"map_world","map_world")
        result=d.summarize(atlas,source,origin,10)
        self.assertEqual(result["counts"]["observed_in_bounds"],5)
        # 3 physically inside room rectangles; floor1 zombie is outside actual
        # upper room footprint (x=111,y=201 lies inside), so 4 total rooms.
        self.assertEqual(result["counts"]["matched_to_room_footprint"],4)
        self.assertEqual(result["counts"]["unmatched_or_outdoor"],1)
        self.assertEqual(result["counts"]["observed_occupied_buildings"],2)
        self.assertEqual(result["counts"]["by_type"]["TLOU_Runner"],2)
        self.assertEqual(result["coverage"]["loaded_chunk_horizontal_tiles_estimate"],100)
        # Overlapping classroom areas 9*10+9*8-(2*2)=158; exact union.
        self.assertEqual(result["buildings"][0]["indoor_tiles_by_floor"]["0"],158)
        self.assertEqual(result["buildings"][0]["indoor_tiles_by_floor"]["1"],144)
        self.assertTrue(any(c["per_1000_loaded_chunk_tiles_estimate"] is None
                            for c in result["grids"]))
        self.assertTrue(all(c["per_1000_horizontal_tiles"]>=0 for c in result["grids"]))
    def test_roster_world_is_explicit_attestation(self):
        with self.assertRaisesRegex(ValueError,"world identity"):
            d.source_roster(roster(),"map_world",None)
        with self.assertRaisesRegex(ValueError,"world identity"):
            d.source_roster(roster(),"map_world","story_test")
    def test_trace_uses_one_frame_not_double_counted(self):
        rid="c"*32
        trace={"schema":1,"recording_id":rid,"capture_complete":True,
               "terminal_status":"complete","records":[
            {"kind":"start","schema":1,"world":"map_world","id":rid},
            {"kind":"sample","id":rid,"seq":1,"expected_slots":1},
            {"kind":"zombie","id":rid,"sample":1,"x":105,"y":206,"z":0,
                "type":"TLOU_Runner"},
            {"kind":"sample_end","id":rid,"seq":1,"inspected":1,
                "null_slots":0,"errors":0,"coverage_complete":True},
            {"kind":"sample","id":rid,"seq":2,"expected_slots":1},
            {"kind":"zombie","id":rid,"sample":2,"x":124,"y":214,"z":0,
                "type":"TLOU_Stalker"},
            {"kind":"sample_end","id":rid,"seq":2,"inspected":1,
                "null_slots":0,"errors":0,"coverage_complete":True},
            {"kind":"end","id":rid,"status":"complete","samples":2}
        ]}
        zs,meta=d.source_trace(trace,"map_world","last")
        self.assertEqual(len(zs),1)
        self.assertEqual(zs[0]["type"],"TLOU_Stalker")
        self.assertEqual(meta["sample_sequence"],2)
        with self.assertRaisesRegex(ValueError,"header world"):
            d.source_trace(trace,"other_world","last")
        with self.assertRaisesRegex(ValueError,"complete"):
            d.source_trace({**trace,"capture_complete":False},"map_world","last")

if __name__=="__main__":unittest.main()
