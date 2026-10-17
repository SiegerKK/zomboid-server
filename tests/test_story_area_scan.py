#!/usr/bin/env python3
"""Offline tests for root-only read-only Story area scan hand-off and report."""
import argparse
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("story_scan", ROOT/"story/scanctl.py")
scan=importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(scan)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.store=root/"store"
        w=self.store/"worlds/story_test"
        (w/"story").mkdir(parents=True)
        (w/"data/Lua").mkdir(parents=True)
        (w/"profile").write_text("mp-test\n")
        (w/"story/bundle.lua").write_text("SiegerStoryScenes={schema=1}\n")
        (self.store/"manager").mkdir()
        (self.store/"manager/active-world").write_text("story_test\n")
        self.original=scan.STORE
        scan.STORE=self.store
        self.addCleanup(self.restore)
        self.req=scan.request_path("story_test")
        self.resp=scan.response_path("story_test")

    def restore(self):
        scan.STORE=self.original

    def mock_mounts(self):
        return {
            "/root/Zomboid": (self.store/"worlds/story_test/data").resolve(),
            "/pzomboid-server/media/lua/server/SiegerStoryAreaScan.lua": ROOT/"story/runtime/SiegerStoryAreaScan.lua",
            "/pzomboid-server/media/lua/server/SiegerStoryDirector.lua": ROOT/"story/runtime/SiegerStoryDirector.lua",
        }

    def sample(self,id):
        meta={"kind":"meta","request_id":id,"player":"kyrylo","center_x":3177,
              "center_y":12116,"center_z":0,"side":25,"levels":5}
        entries=[
            {"kind":"object","x":3175,"y":12116,"z":0,"object_index":1,
             "sprite":"walls_commercial_01_40"},
            {"kind":"container","x":3175,"y":12116,"z":0,
             "object_index":1,"container_index":0,"container_type":"medicine","item_count":1},
            {"kind":"container_item","x":3175,"y":12116,"z":0,"object_index":1,
             "container_index":0,"slot":0,"full_type":"Base.Bandage","name":"Бинт"},
        ]
        footer={"kind":"summary","request_id":id,"status":"complete","requested_squares":3125,
                "loaded_squares":1500,"unloaded_squares":1625,"errors":0,"objects":1,
                "containers":1,"container_items":1,"ground_items":0,"truncated":False,
                "scanned_squares":3125,"records":3}
        self.resp.write_text("\n".join(json.dumps(x,ensure_ascii=False)
                              for x in [meta,*entries,footer])+"\n",encoding="utf-8")

    def test_request_active_running_world_only_and_no_other_world(self):
        args=argparse.Namespace(world="story_test",username="kyrylo",yes=True)
        with patch.object(scan,"docker_mounts",return_value=self.mock_mounts()):
            with redirect_stdout(io.StringIO()):
                scan.scan(args)
        req=scan.parse_req("story_test")
        self.assertRegex(req["id"],r"^[0-9a-f]{32}$")
        self.assertEqual(req["username"],"kyrylo")
        self.assertEqual(self.req.stat().st_mode & 0o777,0o600)
        with patch.object(scan,"docker_mounts",return_value=self.mock_mounts()):
            with self.assertRaisesRegex(ValueError,"Previous request is pending"):
                scan.scan(args)
        self.sample(req["id"])
        with patch.object(scan,"docker_mounts",return_value=self.mock_mounts()):
            with redirect_stdout(io.StringIO()):
                scan.scan(args)
        self.assertNotEqual(scan.parse_req("story_test")["id"],req["id"])

    def test_only_accept_matching_request_and_completed_response(self):
        request_id="c"*32
        self.req.write_text(f"v1\t{request_id}\tkyrylo\t25\t5\n")
        self.sample("d"*32)
        self.assertEqual(scan.read_response("story_test",request_id),{"status":"pending"})
        self.sample(request_id)
        full=scan.read_response("story_test",request_id)
        self.assertEqual(full["summary"]["loaded_squares"],1500)
        self.assertEqual(full["records"][2]["name"],"Бинт")
        with redirect_stdout(io.StringIO()) as output:
            scan.report(argparse.Namespace(world="story_test",json=False,output=None))
        self.assertIn("container @ (3175,12116,0)",output.getvalue())
        dst=Path(self.temp.name)/"scan.json"
        with redirect_stdout(io.StringIO()):
            scan.report(argparse.Namespace(world="story_test",json=False,output=str(dst)))
        self.assertEqual(json.loads(dst.read_text())["records"][2]["full_type"],"Base.Bandage")
        self.assertEqual(dst.stat().st_mode&0o777,0o600)
        with self.assertRaisesRegex(ValueError,"already exists"):
            scan.report(argparse.Namespace(world="story_test",json=False,output=str(dst)))

    def test_fail_closed_wrong_world_missing_mount_and_invalid_account(self):
        with self.assertRaisesRegex(ValueError,"Invalid world"):
            scan.slot("../road_home")
        args=argparse.Namespace(world="story_test",username="wrong username",yes=True)
        with self.assertRaisesRegex(ValueError,"exact simple game login"):
            scan.scan(args)
        args.username="kyrylo"
        (self.store/"manager/active-world").write_text("road_home\n")
        with self.assertRaisesRegex(ValueError,"Active world is not"):
            scan.scan(args)
        (self.store/"manager/active-world").write_text("story_test\n")
        with patch.object(scan,"docker_mounts",return_value={"/root/Zomboid":(self.store/"worlds/story_test/data").resolve()}):
            with self.assertRaisesRegex(ValueError,"not mounted"):
                scan.scan(args)

    def test_partial_report_never_appears_complete(self):
        request_id="e"*32
        self.req.write_text(f"v1\t{request_id}\tkyrylo\t25\t5\n")
        self.resp.write_text(json.dumps({"kind":"meta","request_id":request_id})+"\n")
        self.assertEqual(scan.read_response("story_test",request_id),{"status":"pending"})
        self.resp.write_text('{"kind":"meta","request_id":"'+request_id+'"}\n{"kind":')
        self.assertEqual(scan.read_response("story_test",request_id),{"status":"pending"})

    def test_corrupt_footer_and_partial_exit(self):
        ident='f'*32
        self.req.write_text(f'v1\t{ident}\tkyrylo\t25\t5\n')
        for change in ({'records':99},{'scanned_squares':5},{'truncated':True},{'errors':1}):
            self.sample(ident)
            rows=[json.loads(l) for l in self.resp.read_text().splitlines()]
            rows[-1].update(change)
            self.resp.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            with self.assertRaises(ValueError):scan.read_response('story_test',ident)
        self.sample(ident)
        rows=[json.loads(l) for l in self.resp.read_text().splitlines()]
        rows[-1].update(status='partial',truncated=True)
        self.resp.write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'partial'):
            scan.status(argparse.Namespace(world='story_test'))
        dst=Path(self.temp.name)/'partial.json'
        with redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'partial'):
            scan.report(argparse.Namespace(world='story_test',output=str(dst),json=False))
        self.assertEqual(json.loads(dst.read_text())['status'],'partial')

    def test_export_must_not_write_private_data_inside_repo(self):
        ident='a'*32
        self.req.write_text(f'v1\t{ident}\tkyrylo\t25\t5\n')
        self.sample(ident)
        with self.assertRaisesRegex(ValueError,'outside the source'):
            scan.report(argparse.Namespace(world='story_test',json=False,output=str(ROOT/'private-scan.json')))


if __name__=="__main__":
    unittest.main(verbosity=2)
