#!/usr/bin/env python3
"""Offline contracts for parameterised scanner, typed player requests, and profiler."""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"story"))
import scanctl
import playerctl
import profilectl
import livectl


class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Path(self.tmp.name)/"store"
        (self.store/"worlds/story_test/data/Lua").mkdir(parents=True)
        (self.store/"worlds/story_test/story").mkdir(parents=True)
        (self.store/"worlds/story_test/profile").write_text("test")
        (self.store/"worlds/story_test/story/bundle.lua").write_text("ok")
        (self.store/"manager").mkdir()
        (self.store/"manager/active-world").write_text("story_test")
        original=scanctl.STORE
        scanctl.STORE=self.store
        self.addCleanup(lambda:setattr(scanctl,"STORE",original))
        self.player_original=None
        self.lua=self.store/"worlds/story_test/data/Lua"

    def mounts(self):
        return {"/root/Zomboid":(self.store/"worlds/story_test/data").resolve(),
                "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua":ROOT/"story/runtime/SiegerStoryDirector.lua",
                "/pzomboid-server/media/lua/server/SiegerStoryAreaScan.lua":ROOT/"story/runtime/SiegerStoryAreaScan.lua",
                "/pzomboid-server/media/lua/server/SiegerStoryPlayerControl.lua":ROOT/"story/runtime/SiegerStoryPlayerControl.lua"}

    def test_dynamic_scan_protocol_and_args(self):
        args=argparse.Namespace(world="story_test",username="admin",modern=True,
            center="10622,9221",radius=13,z_min=0,z_max=2,
            include="squares,objects,containers,items,vehicles,windows,blood",yes=True)
        with patch.object(scanctl,"docker_mounts",return_value=self.mounts()):
            with redirect_stdout(io.StringIO()):
                scanctl.scan(args)
        req=scanctl.parse_req("story_test")
        self.assertEqual(req["version"],"v3")
        self.assertEqual(req["side"],27)
        self.assertEqual(req["levels"],3)
        self.assertEqual(req["center_x"],10622)
        self.assertEqual(req["modes"],args.include.split(","))
        self.assertEqual((self.lua/"SiegerStoryScanRequest.txt").stat().st_mode & 0o777,0o600)
        args.include="squares,blood,vehicles"
        args.center="11000,9221"
        with self.assertRaisesRegex(ValueError,"Previous request"):
            with patch.object(scanctl,"docker_mounts",return_value=self.mounts()):
                scanctl.scan(args)
        for bad in ["items", "blood", "squares,squares", "actors,forbidden"]:
            args.include=bad
            with self.assertRaises(ValueError):
                with patch.object(scanctl,"docker_mounts",return_value=self.mounts()):
                    scanctl.scan(args)

    def test_v3_response_scopes_floor_count_and_car_census(self):
        rid="a"*32
        (self.lua/"SiegerStoryScanRequest.txt").write_text(
            "v3\t"+rid+"\tadmin\t-\t-\t2\t0\t1\tsquares,vehicles\n")
        head={"kind":"meta","request_id":rid,"player":"admin","side":5,
              "levels":2}
        vehicle={"kind":"vehicle","x":100,"y":200,"z":0,"vehicle_id":5,
                 "script":"Base.Van","part_count":0}
        end={"kind":"summary","request_id":rid,"status":"complete",
             "requested_squares":50,"scanned_squares":50,"loaded_squares":20,
             "unloaded_squares":30,"records":1,"errors":0,"truncated":False,
             "vehicles":1,"vehicle_parts":0,"vehicle_containers":0,
             "vehicle_items":0,"vehicle_snapshot":"complete"}
        resp=self.lua/"SiegerStoryScanResult.txt"
        resp.write_text("\n".join(json.dumps(x)for x in [head,vehicle,end])+"\n")
        result=scanctl.read_response("story_test",rid)
        self.assertEqual(result["summary"]["vehicles"],1)
        end["vehicle_snapshot"]="incomplete"
        resp.write_text("\n".join(json.dumps(x)for x in [head,vehicle,end])+"\n")
        with self.assertRaisesRegex(ValueError,"vehicle"):
            scanctl.read_response("story_test",rid)

    def test_player_queue_private_status_and_validation(self):
        with patch.object(scanctl,"docker_mounts",return_value=self.mounts()):
            args=argparse.Namespace(world="story_test",player="admin",operation="grant",
                    item="Base.Bandage",count=2,yes=True,acknowledge_failed=False)
            with redirect_stdout(io.StringIO()):
                playerctl.command(args)
        req=playerctl.read_request("story_test")
        self.assertEqual(req["action"],"grant")
        self.assertEqual(req["count"],2)
        with patch.object(scanctl,"docker_mounts",return_value=self.mounts()):
            with self.assertRaisesRegex(ValueError,"pending"):
                playerctl.command(args)
        token="SiegerStory:admin_player_ops:grant_item:abc:1"
        resp=self.lua/"SiegerStoryPlayerResult.txt"
        resp.write_text(f"v1\t{req['id']}\tstory_test\tadmin\tgrant\tcomplete\tserver_ack\n"
                        "field\tgranted_type\tBase.Bandage\n"
                        "field\tgranted_count\t2\nend\n")
        data=playerctl.read_response("story_test",req["id"])
        self.assertEqual(data["fields"]["granted_type"],"Base.Bandage")
        args.operation="remove-tagged";args.token=token
        with patch.object(scanctl,"docker_mounts",return_value=self.mounts()):
            with redirect_stdout(io.StringIO()):
                playerctl.command(args)
        self.assertEqual(playerctl.read_request("story_test")["arg"],token)
        next_req=playerctl.read_request("story_test")
        resp.write_text(f"v1\t{next_req['id']}\tstory_test\tadmin\tremove-tagged\tcomplete\tserver_ack\nend\n")
        args.operation="heal";args.experimental_health=False
        with self.assertRaisesRegex(ValueError,"--experimental-health"):
            with patch.object(scanctl,"docker_mounts",return_value=self.mounts()):
                playerctl.command(args)
        args.experimental_health=True
        with patch.object(scanctl,"docker_mounts",return_value=self.mounts()):
            with redirect_stdout(io.StringIO()):
                playerctl.command(args)
        self.assertEqual(playerctl.read_request("story_test")["action"],"heal")

    def test_adhoc_scene_generates_stable_id_and_optin(self):
        args=argparse.Namespace(
            world="story_test", key="smokeys_test_bandage_01", type="loot",
            x=10622, y=9221, z=0, placement="ground",
            target_index=None, target_sprite=None,
            item="Base.Bandage", count=2, title=None, text=None,
            floor_sprite=None, blood=1, allow_infected=False,
            allow_corpses=False, yes=False,
        )
        scene,_=livectl.build_inline_scene(args)
        self.assertEqual(scene["id"],"ops_smokeys_test_bandage_01")
        self.assertEqual(scene["actions"][0]["items"],
                         [{"type":"Base.Bandage","count":2}])
        with redirect_stdout(io.StringIO()) as output:
            livectl.apply_inline(args)
        self.assertIn("READ-ONLY",output.getvalue())
        self.assertEqual(scene,livectl.build_inline_scene(args)[0])
        args.key="INVALID"
        with self.assertRaisesRegex(ValueError,"Stable"):
            livectl.build_inline_scene(args)
        args.key="smokeys_enemy_01"
        args.type="infected"
        with self.assertRaisesRegex(ValueError,"allow-infected"):
            livectl.build_inline_scene(args)
        args.allow_infected=True
        self.assertEqual(livectl.build_inline_scene(args)[0]["actions"][0]["count"],1)
        args.type="corpse"
        args.floor_sprite="floors_interior_tilesandwood_01_21"
        with self.assertRaisesRegex(ValueError,"allow-corpses"):
            livectl.build_inline_scene(args)
        args.allow_corpses=True
        self.assertEqual(livectl.build_inline_scene(args)[0]["actions"][0]["ground_item"],
                         "Base.Revolver")

    def test_parser_and_profile_math(self):
        self.assertEqual(profilectl.parse_size("1.50GiB"),round(1.5*1024**3))
        cpu,used,limit=profilectl.parse_stats(
            {"CPUPerc":"36.2%","MemUsage":"4.2GiB / 12GiB"})
        self.assertEqual(cpu,36.2)
        self.assertGreater(used,4*1024**3)
        self.assertEqual(limit,12*1024**3)
        with self.assertRaises(ValueError):
            profilectl.parse_stats({"CPUPerc":"unavailable","MemUsage":"none"})
        self.assertNotIn("Base.Shotgun",playerctl.TYPES)
        self.assertFalse(playerctl.TOKEN.fullmatch("Base.Bandage"))

if __name__=="__main__":
    unittest.main(verbosity=2)
