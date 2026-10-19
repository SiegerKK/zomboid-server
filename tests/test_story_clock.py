"""Pinned GameTime binary ABI and cold-backup guarded same-date edits."""
import contextlib
import io
import struct
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'story'))
import clockctl as c

def fixture():
    return b'GMTM' + struct.pack('>ifii ffiii',249,1.0,5,100,18.0,18.5,29,10,1994) + bytes(range(80))

class Clock(unittest.TestCase):
    def test_only_two_clock_floats_change_date_and_tail_preserved(self):
        body=fixture()
        output,before,after=c.changed(body,'07:30')
        self.assertEqual(after['date'],'1994-11-30')
        self.assertEqual(before['date'],after['date'])
        self.assertEqual(after['time_hours'],7.5)
        self.assertEqual(after['last_time_hours'],7.5)
        self.assertEqual(output[:20],body[:20])
        self.assertEqual(output[28:],body[28:])
        self.assertEqual(len(output),len(body))
        self.assertEqual(c.changed(output,'07:30')[0],output)

    def test_invalid_time_version_magic_and_nonfinite_refused(self):
        for time in ('24:00','7:30','07:60','nan','07:30\n'):
            with self.assertRaises(ValueError): c.changed(fixture(),time)
        body=fixture()
        for invalid in (body[:40],b'BAD!'+body[4:],body[:4]+struct.pack('>i',248)+body[8:],
                        body[:24]+struct.pack('>f',float('nan'))+body[28:]):
            with self.assertRaises(ValueError):c.changed(invalid,'07:30')

    def test_apply_exact_cold_backup_and_no_unrelated_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); path=root/'map_t.bin';path.write_bytes(fixture())
            archive=root/'backup.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                tar.add(path,arcname=str(c.RELATIVE))
            state={'State':{'FinishedAt':'2026-01-01T00:00:00Z'}}
            verification={'verified_latest':{'archive':str(archive),'sha256':'a'*64}}
            with patch.object(c,'state',return_value=(state,path)),patch.object(c.backupctl,'report',return_value=verification),contextlib.redirect_stdout(io.StringIO()):
                c.apply('story_test','07:30',False)
                self.assertEqual(path.read_bytes(),fixture())
                c.apply('story_test','07:30',True)
                self.assertEqual(c.decode(path.read_bytes())['time_hours'],7.5)
                with self.assertRaisesRegex(ValueError,'differs'):
                    c.apply('story_test','08:30',True)
            self.assertEqual(list(root.glob('.clock-*')),[])

    def test_running_or_wrong_world_refused(self):
        with patch.object(c.scanctl,'active_world',return_value='road_home'):
            with self.assertRaises(ValueError): c.state('story_test')
        import json
        response=type('Result',(),{'stdout':json.dumps([{'State':{'Running':True}}])})()
        with patch.object(c.scanctl,'active_world',return_value='story_test'),patch.object(c.subprocess,'run',return_value=response):
            with self.assertRaisesRegex(ValueError,'stop'): c.state('story_test')

if __name__=='__main__':unittest.main()
