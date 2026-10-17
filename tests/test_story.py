#!/usr/bin/env python3
"""Offline tests: validate scene DSL and safe per-world compilation."""
import argparse
import hashlib
import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("storyctl", REPO / "story/storyctl.py")
story = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(story)


class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.scenes = root / "repo/story/scenes"
        self.scenes.mkdir(parents=True)
        self.store = root / "store"
        self.world = self.store / "worlds/road_home"
        (self.world / "data").mkdir(parents=True)
        (self.world / "profile").write_text("mp-test\n")
        self.orig_scenes = story.SCENE_FOLDER
        self.orig_store = story.STORE
        story.SCENE_FOLDER = self.scenes
        story.STORE = self.store
        self.addCleanup(self.restore_globals)
        self.scene = json.loads((REPO / "story/scenes/clinic_last_shift.json").read_text(encoding="utf-8"))
        self.scene["world"] = "road_home"  # isolated fixture, not the deployed draft target
        self.filename = self.scenes / "clinic_last_shift.json"
        self.write()

    def restore_globals(self):
        story.SCENE_FOLDER = self.orig_scenes
        story.STORE = self.orig_store

    def write(self):
        self.filename.write_text(json.dumps(self.scene, ensure_ascii=False), encoding="utf-8")

    def mapped(self):
        self.scene["enabled"] = True
        for i, action in enumerate(self.scene["actions"]):
            if action.get("enabled", True):
                action["at"] = {"x": 12000 + i, "y": 9100 + i, "z": 0}
                if "selector" in action:
                    action["selector"] = {
                        "object_index": 3,
                        "sprite": "furniture_storage_01_0",
                        "class": "IsoObject",
                    }
        self.write()

    def backup(self):
        folder = self.store / "backups/worlds/road_home"
        folder.mkdir(parents=True)
        archive = folder / ("world-" + str(int(time.time())) + "-test.tar.gz")
        archive.write_bytes(b"fake offline test backup; no game save is included")
        h = hashlib.sha256(archive.read_bytes()).hexdigest()
        (folder / (archive.name + ".sha256")).write_text(h + "  " + archive.name + "\n")
        return archive

    def test_draft_valid_and_apply_refused(self):
        s, stat = story.read_scene(self.filename)
        self.assertFalse(s["enabled"])
        self.assertGreater(stat["unmapped"], 0)
        with self.assertRaises(ValueError):
            story.read_scene(self.filename, ready=True)
        encoded = story.lua_literal('"; os.execute("boom") --')
        self.assertIn("\\034", encoded)
        self.assertTrue(encoded.startswith('"') and encoded.endswith('"'))

    def test_unknown_action_or_fields_rejected(self):
        self.scene["actions"][0]["lua"] = "os.execute"
        self.write()
        with self.assertRaisesRegex(ValueError, "unexpected keys"):
            story.read_scene(self.filename)
        del self.scene["actions"][0]["lua"]
        self.scene["actions"][0]["type"] = "delete_everything"
        self.write()
        with self.assertRaisesRegex(ValueError, "Unsupported action"):
            story.read_scene(self.filename)

    def test_disable_special_infected_until_adapter_is_proven(self):
        self.mapped()
        self.scene["actions"][4]["enabled"] = True
        self.scene["actions"][4]["at"] = {"x": 10200, "y": 9200, "z": 0}
        self.write()
        with self.assertRaisesRegex(ValueError, "adapter"):
            story.read_scene(self.filename, ready=True)

    def test_exact_target_and_barricade_approval(self):
        self.mapped()
        self.scene["actions"][3]["enabled"] = True
        self.scene["actions"][3]["at"] = {"x": 10201, "y": 9222, "z": 0}
        self.scene["actions"][3]["selector"] = {
            "object_index": 2, "sprite": "walls_exterior_house_01_1", "class": "IsoWindow"
        }
        self.write()
        with self.assertRaisesRegex(ValueError, "allow-barricades"):
            story.read_scene(self.filename, ready=True)
        self.assertEqual(story.read_scene(self.filename, ready=True, allow_barricades=True)[1]["active"], 3)

    def test_apply_is_per_world_and_idempotent_with_recent_backup(self):
        self.mapped()
        self.backup()
        args = argparse.Namespace(world="road_home", scene=str(self.filename), yes=True, allow_barricades=False)
        with patch.object(story, "ensure_stopped"):
            story.command_apply(args)
            with self.assertRaisesRegex(ValueError, "already staged"):
                story.command_apply(args)
        bundle = (self.world / "story/bundle.lua").read_text()
        self.assertIn("SiegerStoryScenes = {", bundle)
        self.assertIn('world="road_home"', bundle)
        self.assertIn("doctor_note", bundle)
        self.assertNotIn("basement_stalkers", bundle)
        self.assertIn("\\208", bundle)  # UTF-8 bytes emitted as Lua escapes, not code.
        self.assertEqual((self.world / "story/scenes/clinic_last_shift.json").stat().st_mode & 0o777, 0o600)
        # Validate inspection triggers and combines with existing scene data.
        probe = argparse.Namespace(world="road_home", x=12000, y=9100, z=0, yes=True)
        with patch.object(story, "ensure_stopped"):
            story.command_inspect(probe)
        new_bundle = (self.world / "story/bundle.lua").read_text()
        self.assertIn("inspect={{x=12000,y=9100,z=0}}", new_bundle)
        story.command_status(argparse.Namespace(world="road_home"))

    def test_requires_real_recent_cold_backup(self):
        self.mapped()
        args = argparse.Namespace(world="road_home", scene=str(self.filename), yes=True, allow_barricades=False)
        with patch.object(story, "ensure_stopped"):
            with self.assertRaisesRegex(ValueError, "No verified cold backup"):
                story.command_apply(args)
        self.assertFalse((self.world / "story/bundle.lua").exists())

    def test_preview_accepts_documented_scene_id(self):
        with patch.object(story, "SCENE_FOLDER", self.scenes):
            story.command_preview(argparse.Namespace(scene="clinic_last_shift"))

    def test_docker_state_must_be_proven(self):
        result = lambda code, out: SimpleNamespace(returncode=code, stdout=out)
        for state in ("true", "unknown", ""):
            with patch.object(story.subprocess, "run", return_value=result(0, state)):
                with self.assertRaises(ValueError):
                    story.ensure_stopped()
        with patch.object(story.subprocess, "run", return_value=result(0, "false")):
            story.ensure_stopped()
        with patch.object(story.subprocess, "run", side_effect=[result(1, ""), result(0, "")]):
            story.ensure_stopped()  # reachable Docker, absent container
        for followup in (result(1, ""), result(0, "zomboid-server")):
            with patch.object(story.subprocess, "run", side_effect=[result(1, ""), followup]):
                with self.assertRaisesRegex(ValueError, "Cannot prove"):
                    story.ensure_stopped()


if __name__ == "__main__":
    unittest.main(verbosity=2)
