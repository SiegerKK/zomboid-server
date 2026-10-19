"""Read-only backup reporting: integrity, fixed inputs and no link traversal."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('backupctl', Path(__file__).resolve().parents[1] / 'story/backupctl.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class BackupInfo(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / 'worlds/story_test'
        folder.mkdir(parents=True)
        self.archive = folder / 'world-20261019T000000Z-1.tar.gz'
        with tarfile.open(self.archive, 'w:gz') as archive:
            info = tarfile.TarInfo('data/test')
            info.size = 7
            archive.addfile(info, io.BytesIO(b'private'))
        self.sidecar = Path(str(self.archive) + '.sha256')
        self.sidecar.write_text(hashlib.sha256(self.archive.read_bytes()).hexdigest() + '  ' + self.archive.name + '\n')

    def test_verified_private_metadata_and_no_writes(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = m.report(self.root, 'story_test')
        self.assertTrue(result['verified_latest']['sha256_match'])
        self.assertEqual(result['verified_latest']['regular_payload_bytes'], 7)
        self.assertEqual(result['archives'], 1)
        self.assertNotIn('private', str(result))
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_corrupt_archive_and_bad_sidecar_rejected(self):
        self.archive.write_bytes(self.archive.read_bytes() + b'corrupt')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            m.report(self.root, 'story_test')
        self.sidecar.write_text('bad checksum')
        with self.assertRaisesRegex(ValueError, 'sidecar'):
            m.report(self.root, 'story_test')

    def test_links_and_traversal_refused(self):
        (self.root / 'escape').symlink_to('/etc')
        self.assertEqual(m.report(self.root)['skipped_unsafe_entries'], 1)
        for world in ('../etc', '/etc', '', 'x\n'):
            with self.assertRaises(ValueError):
                m.report(self.root, world)
        self.sidecar.unlink()
        self.sidecar.symlink_to('/etc/passwd')
        with self.assertRaises(OSError):
            m.report(self.root, 'story_test')

    def test_invalid_tar_with_valid_checksum_rejected(self):
        self.archive.write_bytes(b'not a tar')
        self.sidecar.write_text(hashlib.sha256(self.archive.read_bytes()).hexdigest() + '  ' + self.archive.name)
        with self.assertRaises(tarfile.TarError):
            m.report(self.root, 'story_test')

if __name__ == '__main__':
    unittest.main()
