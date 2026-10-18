#!/usr/bin/env python3
"""Offline read-only audit smoke tests with fake CP-only classes, no Viewpoint IP."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import viewpoint_jar_audit as audit


def sample_class():
    def text(value):
        encoded = value.encode("utf-8")
        return b"\x01" + struct.pack(">H", len(encoded)) + encoded

    def u2(*items):
        return struct.pack(">" + "H" * len(items), *items)

    # Constant pool (indices 1..12):
    pool = [
        text("viewpoint/FakeRenderer"), b"\x07" + u2(1),
        text("org/lwjgl/opengl/GL11"), b"\x07" + u2(3),
        text("glGenTextures"), text("()I"),
        b"\x0c" + u2(5, 6), b"\x0a" + u2(4, 7),
        text("glDeleteTextures"), text("(I)V"),
        b"\x0c" + u2(9, 10), b"\x0a" + u2(4, 11),
    ]
    return b"\xca\xfe\xba\xbe" + u2(0, 61, len(pool) + 1) + b"".join(pool)


class JarAuditTests(unittest.TestCase):
    def test_constant_pool_methods(self):
        refs = audit.cp_method_references(sample_class())
        self.assertIn(("org/lwjgl/opengl/GL11", "glGenTextures"), refs)
        self.assertIn(("org/lwjgl/opengl/GL11", "glDeleteTextures"), refs)

    def test_truncated_untrusted_class(self):
        for data in (b"", b"\xca\xfe\xba\xbe", sample_class()[:-2]):
            with self.assertRaises(audit.ClassFormatError):
                audit.cp_method_references(data)

    def test_run_and_exact_hash_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "Viewpoint.jar"
            with zipfile.ZipFile(path, "w") as file:
                file.writestr("viewpoint/FakeRenderer.class", sample_class())
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            result = audit.audit(path, digest)
            self.assertEqual(result["viewpoint_jar_sha256"], digest)
            self.assertEqual(result["class_count"], 1)
            self.assertEqual(result["candidates"][0]["class"], "viewpoint.FakeRenderer")
            self.assertEqual(result["candidates"][0]["allocation_api_refs"], 1)
            with self.assertRaisesRegex(ValueError, "unexpected Viewpoint"):
                audit.audit(path, "0"*64)
            self.assertNotIn("extracted", json.dumps(result).lower().split("limitations")[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
