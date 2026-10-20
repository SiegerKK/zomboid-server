#!/usr/bin/env python3
"""Real archive extraction/slot replacement with mocked Docker state only."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('checkpoint', ROOT / 'story/checkpointctl.py')
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


class RestoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.enterContext(patch.object(cp, 'STORE', self.root))
        self.enterContext(patch.object(cp.os, 'geteuid', return_value=0))
        self.slot = self.root / 'worlds' / 'any_world'
        (self.slot / 'data/Lua').mkdir(parents=True)
        (self.slot / 'data/save.bin').write_bytes(b'new-world-state')
        (self.slot / 'data/Lua/native-stages.txt').write_text('new-stage')
        (self.slot / 'story/setup').mkdir(parents=True)
        (self.slot / 'story/setup/new.json').write_text('{}')
        (self.slot / 'profile').write_text('tlou')
        (self.slot / 'mods.env').write_text('MODS=test')
        (self.root / 'manager').mkdir()
        (self.root / 'manager/active-world').write_text('any_world')
        folder = self.root / 'backups/worlds/any_world'
        folder.mkdir(parents=True)
        self.archive = folder / 'world-baseline.tar.gz'
        self.request = self.root / 'request.json'
        self.files = {'profile': b'tlou', 'mods.env': b'MODS=test',
                      'deployment.txt': b'profile=tlou', 'data/save.bin': b'baseline',
                      'data/Lua/native-stages.txt': b'old-stage',
                      'story/setup/old.json': b'{"old":true}'}
        self.make_archive()
        self.container = [{'State': {'Status': 'exited', 'Running': False,
                                     'ExitCode': 0, 'OOMKilled': False},
                           'Mounts': [{'Destination': '/root/Zomboid',
                                       'Source': str(self.slot / 'data')}]}]
        self.docker = self.enterContext(patch.object(cp.subprocess, 'run', side_effect=self.inspect))

    def inspect(self, *args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, json.dumps(self.container))

    def make_archive(self, extra=None):
        with tarfile.open(self.archive, 'w:gz') as out:
            for directory in ('data', 'data/Lua', 'story', 'story/setup'):
                m = tarfile.TarInfo(directory)
                m.type = tarfile.DIRTYPE
                out.addfile(m)
            for name, content in self.files.items():
                m = tarfile.TarInfo(name)
                m.size = len(content)
                out.addfile(m, io.BytesIO(content))
            if extra is not None:
                out.addfile(extra, io.BytesIO(b''))
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        Path(str(self.archive) + '.sha256').write_text(digest + '  ' + self.archive.name + '\n')
        self.doc = dict(schema=1, world='any_world', archive=self.archive.name, sha256=digest)
        self.write_request()

    def write_request(self):
        self.request.write_text(json.dumps(self.doc))

    def run_restore(self, yes=True):
        return cp.restore('any_world', self.request, yes)

    def assert_untouched(self):
        self.assertEqual((self.slot / 'data/save.bin').read_bytes(), b'new-world-state')
        self.assertFalse((self.root / 'checkpoint-preserved').exists())

    def test_preview_never_writes_or_calls_docker(self):
        before = sorted(self.root.rglob('*'))
        self.assertEqual(self.run_restore(False)['mode'], 'preview')
        self.assertEqual(before, sorted(self.root.rglob('*')))
        self.docker.assert_not_called()

    def test_same_slot_restore_preserves_every_old_file_and_restores_both_ledgers(self):
        result = self.run_restore()
        self.assertEqual(result['mode'], 'restored')
        self.assertEqual((self.slot / 'data/save.bin').read_bytes(), b'baseline')
        self.assertEqual((self.slot / 'data/Lua/native-stages.txt').read_text(), 'old-stage')
        self.assertTrue((self.slot / 'story/setup/old.json').exists())
        self.assertFalse((self.slot / 'story/setup/new.json').exists())
        preserved = Path(result['preserved_slot'])
        self.assertEqual((preserved / 'data/save.bin').read_bytes(), b'new-world-state')
        self.assertTrue((preserved / 'story/setup/new.json').exists())
        self.assertEqual((self.root / 'manager/active-world').read_text(), 'any_world')
        self.assertEqual((self.slot / 'data/save.bin').stat().st_mode & 0o777, 0o600)

    def test_running_unknown_and_unclean_container_refused(self):
        for change in ({'Running': True, 'Status': 'running'}, {'Status': 'restarting'},
                       {'ExitCode': 137}, {'OOMKilled': True}):
            with self.subTest(change=change):
                old = dict(self.container[0]['State'])
                self.container[0]['State'].update(change)
                with self.assertRaises(ValueError):
                    self.run_restore()
                self.container[0]['State'] = old
                self.assert_untouched()

    def test_wrong_selected_world_and_mount_refused(self):
        (self.root / 'manager/active-world').write_text('other')
        with self.assertRaisesRegex(ValueError, 'selected'):
            self.run_restore()
        (self.root / 'manager/active-world').write_text('any_world')
        self.container[0]['Mounts'][0]['Source'] = '/other/data'
        with self.assertRaisesRegex(ValueError, 'mount'):
            self.run_restore()
        self.assert_untouched()

    def test_wrong_digest_cross_world_and_traversal_refused(self):
        original = dict(self.doc)
        for updates in ({'sha256': '0' * 64}, {'world': 'foreign'},
                        {'archive': '../world-baseline.tar.gz'}):
            self.doc = {**original, **updates}
            self.write_request()
            with self.assertRaises(ValueError):
                self.run_restore()
            self.assert_untouched()

    def test_unsafe_tar_paths_links_special_and_duplicate_refused(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('/tmp/escape', tarfile.REGTYPE),
                           ('data/link', tarfile.SYMTYPE), ('data/hard', tarfile.LNKTYPE),
                           ('data/fifo', tarfile.FIFOTYPE), ('data/save.bin', tarfile.REGTYPE)]:
            with self.subTest(name=name):
                item = tarfile.TarInfo(name)
                item.type = kind
                item.linkname = '/etc/shadow'
                self.make_archive(item)
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    self.run_restore()
                self.assert_untouched()

    def test_profile_mismatch_or_missing_provenance_refused(self):
        self.files['mods.env'] = b'MODS=foreign'
        self.make_archive()
        with self.assertRaisesRegex(ValueError, 'profile'):
            self.run_restore()
        self.files.pop('deployment.txt')
        self.make_archive()
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            self.run_restore()
        self.assert_untouched()

    def test_symlink_archive_and_path_refused(self):
        real = self.archive.with_suffix('.real')
        self.archive.rename(real)
        self.archive.symlink_to(real)
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            self.run_restore()
        self.assert_untouched()

    def test_nonroot_and_low_disk_refused(self):
        with patch.object(cp.os, 'geteuid', return_value=1003), self.assertRaisesRegex(ValueError, 'broker'):
            self.run_restore()
        usage = type('Usage', (), {'free': 1})()
        with patch.object(cp.shutil, 'disk_usage', return_value=usage), self.assertRaisesRegex(ValueError, 'disk'):
            self.run_restore()
        self.assert_untouched()

    def test_second_state_check_blocks_race_before_swap(self):
        with patch.object(cp, 'stopped', side_effect=[None, ValueError('state changed')]), \
             self.assertRaisesRegex(ValueError, 'state changed'):
            self.run_restore()
        self.assertEqual((self.slot / 'data/save.bin').read_bytes(), b'new-world-state')
        self.assertFalse(list((self.root / 'checkpoint-preserved').iterdir()))
        self.assertFalse(list(self.slot.parent.glob('.checkpoint-*')))

    def test_duplicate_restore_keys_rejected(self):
        self.request.write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.run_restore()
        self.assert_untouched()

    def test_swap_failure_keeps_original_slot(self):
        rename = cp.os.rename
        calls = []
        def failing(source, dest):
            calls.append(str(source))
            if len(calls) == 2:
                raise OSError('simulated swap failure')
            return rename(source, dest)
        with patch.object(cp.os, 'rename', side_effect=failing), self.assertRaises(OSError):
            self.run_restore()
        self.assertEqual((self.slot / 'data/save.bin').read_bytes(), b'new-world-state')
        self.assertFalse(list(self.slot.parent.glob('.checkpoint-*')))


if __name__ == '__main__':
    unittest.main()
