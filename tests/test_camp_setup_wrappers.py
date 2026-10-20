#!/usr/bin/env python3
"""Check stage wrappers without game access or any public farm coordinates."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "story" / "camp"


class CampWrapperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private = self.root / "private farm"
        self.private.mkdir()
        for name in ["stages_build.json"] + [
            f"phase{stage:02d}_{suffix}_batch.json"
            for stage in range(1, 5)
            for suffix in (("items", "liquids") if stage == 1 else
                           ("items", "liquids", "bedding"))
        ]:
            (self.private / name).write_text('{}\n')
        self.out = self.root / "calls.json"
        self.bin = self.root / "fake-pz"
        self.bin.write_text("#!/usr/bin/env python3\n"
                            "import json, os, sys\n"
                            "with open(os.environ['PZ_FAKE_OUTPUT'], 'w') as f:\n"
                            "    json.dump(sys.argv[1:], f)\n")
        self.bin.chmod(0o700)
        self.env = dict(os.environ, PZ_BIN=str(self.bin), PZ_FAKE_OUTPUT=str(self.out))

    def run_script(self, stage, *args, expected=0, env=None):
        script = SCRIPTS / f"setup_phase{stage:02d}.sh"
        result = subprocess.run(["bash", str(script), *args],
                                text=True, capture_output=True,
                                env=env or self.env, cwd=self.root)
        self.assertEqual(result.returncode, expected,
                         f"{script}: {result.stdout} {result.stderr}")
        return result

    def test_each_stage_calls_only_its_own_build_and_supply_inputs(self):
        for n in range(1, 5):
            with self.subTest(stage=n):
                self.out.unlink(missing_ok=True)
                self.run_script(n, "camp_copy", str(self.private), "--status")
                values = json.loads(self.out.read_text())
                self.assertEqual(values[:4], ["story", "build", "setup", "camp_copy"])
                self.assertEqual(values[values.index("--stage") + 1], f"phase{n:02d}")
                self.assertNotIn("--source-world", values)
                self.assertEqual(values[values.index("--file") + 1],
                                 str(self.private / "stages_build.json"))
                self.assertEqual(values[-1], "--status")
                self.assertNotIn("--yes", values)
                supplied = [values[i + 1] for i, value in enumerate(values[:-1])
                            if value == "--batch"]
                expected = [str(self.private / f"phase{n:02d}_{typ}_batch.json")
                            for typ in ("items", "liquids") +
                            (("bedding",) if n > 1 else ())]
                self.assertEqual(supplied, expected)

    def test_default_private_location_can_be_overridden_by_environment(self):
        env = dict(self.env, PZ_CAMP_PLAN_DIR=str(self.private))
        self.run_script(1, "camp_copy", "--status", env=env)
        self.assertEqual(json.loads(self.out.read_text())[-1], "--status")

    def test_explicit_yes_is_passed_only_when_requested(self):
        self.run_script(3, "camp_copy", str(self.private),
                        "--survey", "/tmp/new scan.json", "--allow-existing", "--yes")
        args = json.loads(self.out.read_text())
        self.assertEqual(args[-4:], ["--survey", "/tmp/new scan.json",
                                     "--allow-existing", "--yes"])

    def test_cannot_override_stage_source_or_input_paths(self):
        for override in ("--file", "--stage=phase04", "--batch",
                         "--source-world=foreign"):
            with self.subTest(override=override):
                self.out.unlink(missing_ok=True)
                self.run_script(1, "camp_copy", str(self.private), override,
                                "something", expected=2)
                self.assertFalse(self.out.exists())

    def test_missing_or_symlinked_private_plan_fails_before_pz(self):
        path = self.private / "phase04_bedding_batch.json"
        path.unlink()
        self.run_script(4, "camp_copy", str(self.private), expected=2)
        self.assertFalse(self.out.exists())
        path.symlink_to(self.private / "phase03_bedding_batch.json")
        self.run_script(4, "camp_copy", str(self.private), expected=2)
        self.assertFalse(self.out.exists())

    def test_no_world_or_missing_directory_is_an_error(self):
        self.run_script(1, expected=2)
        self.run_script(1, "camp_copy", str(self.private / "missing"), expected=2)
        self.assertFalse(self.out.exists())

    def test_public_directory_does_not_contain_private_source_plans(self):
        self.assertTrue((SCRIPTS / ".gitignore").exists())
        self.assertFalse((SCRIPTS / "stages_build.json").exists())
        self.assertFalse((SCRIPTS / "private" / "stages_build.json").exists())


if __name__ == "__main__":
    unittest.main()
