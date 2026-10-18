import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import viewpoint_lite_pack as tool


class PackTests(unittest.TestCase):
    def test_release_zip_is_reproducible_and_source_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "one.zip", Path(folder) / "two.zip"
            digest1 = tool.build(a)
            digest2 = tool.build(b)
            self.assertEqual(digest1, digest2)
            self.assertEqual(digest1, hashlib.sha256(a.read_bytes()).hexdigest())
            self.assertEqual(tool.verify(a), digest1)
            with zipfile.ZipFile(a) as z:
                self.assertEqual(set(z.namelist()),
                    {"SiegerViewpointLite/" + p for p in tool.ALLOWED})
                self.assertFalse(any(name.endswith(".jar") for name in z.namelist()))

    def test_reject_modified_or_extra_members(self):
        with tempfile.TemporaryDirectory() as folder:
            a, bad = Path(folder) / "good.zip", Path(folder) / "evil.zip"
            tool.build(a)
            with zipfile.ZipFile(bad, "w") as z:
                for name, data in tool.expected().items():
                    z.writestr(name, data)
                z.writestr("../bad.lua", b"oops")
            with self.assertRaisesRegex(ValueError, "missing/extra"):
                tool.verify(bad)
            with self.assertRaisesRegex(ValueError, "output"):
                tool.build(a)

    def test_absent_source_fails_without_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            dst = Path(folder) / "not-created.zip"
            with patch.object(tool, "MOD", Path(folder) / "missing"):
                with self.assertRaisesRegex(ValueError, "missing/unsafe"):
                    tool.build(dst)
            self.assertFalse(dst.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
