#!/usr/bin/env python3
"""Exercise real CLI readiness against both deployment layouts, without Docker."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "story"))
import scanctl
import opsctl
import tlouctl
import vehiclectl


class ModuleMounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Path(self.tmp.name)
        self.world = self.store / "worlds/story_test"
        (self.world / "data").mkdir(parents=True)
        (self.world / "story").mkdir()
        (self.world / "profile").write_text("mp-test\n")
        (self.world / "story/bundle.lua").write_text("reviewed fixture")
        (self.store / "manager").mkdir()
        (self.store / "manager/active-world").write_text("story_test\n")
        self.mounts = {
            "/root/Zomboid": self.world / "data",
            "/root/Zomboid/mods/SiegerAdmin": ROOT / "mods/SiegerAdmin",
            "/root/Zomboid/Lua/SiegerStoryBundle.txt": self.world / "story/bundle.lua",
        }
        for p in (patch.object(scanctl, "STORE", self.store),
                  patch.object(scanctl, "docker_mounts", side_effect=lambda: self.mounts)):
            p.start()
            self.addCleanup(p.stop)

    def ready_all(self):
        for cli in (opsctl, tlouctl, vehiclectl):
            cli.ready("story_test")

    def test_packaged_radio_accepts_all_three_real_handlers(self):
        self.ready_all()

    def test_vanilla_overlay_accepts_only_exact_reviewed_sources(self):
        self.mounts.pop("/root/Zomboid/mods/SiegerAdmin")
        for name in ("SiegerStoryAreaScan", "SiegerStoryDirector", "SiegerStoryOps",
                     "SiegerStoryTLOUDiagnostics", "SiegerStoryVehicleControl"):
            self.mounts["/pzomboid-server/media/lua/server/" + name + ".lua"] = (
                ROOT / "story/runtime" / (name + ".lua"))
        self.ready_all()
        self.mounts["/pzomboid-server/media/lua/server/SiegerStoryOps.lua"] = Path("/tmp/other.lua")
        with self.assertRaisesRegex(ValueError, "not mounted"):
            opsctl.ready("story_test")

    def test_wrong_data_bundle_or_mod_mount_refused(self):
        for key in tuple(self.mounts):
            old = self.mounts[key]
            self.mounts[key] = Path("/tmp/wrong-world-or-code")
            for cli in (opsctl, tlouctl, vehiclectl):
                with self.assertRaises(ValueError):
                    cli.ready("story_test")
            self.mounts[key] = old

    def test_stale_packaged_handler_refused(self):
        original = Path.read_bytes
        def read(path):
            if str(path).endswith("media/lua/server/SiegerStoryOps.lua"):
                return b"stale runtime"
            return original(path)
        with patch.object(Path, "read_bytes", read):
            with self.assertRaisesRegex(ValueError, "differs"):
                opsctl.ready("story_test")

    def test_different_active_world_refused(self):
        (self.store / "manager/active-world").write_text("road_home\n")
        for cli in (opsctl, tlouctl, vehiclectl):
            with self.assertRaisesRegex(ValueError, "Active world"):
                cli.ready("story_test")


if __name__ == "__main__":
    unittest.main()
