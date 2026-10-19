import argparse
import contextlib
import shutil
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'story')]
import admin_assets
import admin_pack
import timecontrol as t
import scanctl

class AdminTests(unittest.TestCase):
 def test_independent_pack_and_no_radio_or_java_dependency(self):
  admin_assets.check()
  info=(ROOT/'mods/SiegerAdmin/42/mod.info').read_text()
  self.assertNotIn('require=',info);self.assertNotIn('javaJar',info)
  files=admin_pack.expected()
  self.assertTrue(any('SiegerAdminClock.lua'in k for k in files))
  self.assertFalse(any(k.endswith(('.wav','.jar')) for k in files))
  self.assertFalse(any(b'SiegerRadioBridge'in body for body in files.values()))
  with tempfile.TemporaryDirectory()as tmp:
   admin_pack.build(Path(tmp)/'admin.zip')

 def test_admin_pack_rejects_unreviewed_lua_and_symlink(self):
  with tempfile.TemporaryDirectory() as tmp:
   dest=Path(tmp)/'SiegerAdmin'
   shutil.copytree(ROOT/'mods/SiegerAdmin',dest)
   approved=admin_assets.approved_paths()
   admin_assets.verify_layout(dest,approved)
   extra=dest/'42/media/lua/server/OldStoryHandler.lua'
   extra.write_text('print("stale admin script")')
   with self.assertRaisesRegex(ValueError,'Unapproved'):
    admin_assets.verify_layout(dest,approved)
   extra.unlink()
   extra.symlink_to(dest/'42/mod.info')
   with self.assertRaisesRegex(ValueError,'Symlink'):
    admin_assets.verify_layout(dest,approved)

 def test_online_clock_preview_queue_and_matching_ack(self):
  with tempfile.TemporaryDirectory()as tmp:
   base=Path(tmp);req=base/t.REQ;resp=base/t.RESP
   a=argparse.Namespace(world='story_test',operation='set',value='07:30',yes=False,allow_players=False,acknowledge_failed=False)
   with patch.object(t,'paths',return_value=(req,resp)),patch.object(scanctl,'assert_module_ready'),contextlib.redirect_stdout(io.StringIO()):
    t.run(a);self.assertFalse(req.exists())
    a.yes=True;t.run(a);fields=req.read_text().split('\t');rid=fields[1]
    self.assertEqual(fields[3:5],['set','450'])
    with self.assertRaisesRegex(ValueError,'pending'):t.run(a)
    resp.write_text('\t'.join(['v1',rid,'story_test','set','complete','game_clock_verified','1993-12-01','21.000000','1993-12-01','7.500000','3','3'])+'\n')
    data=t.result('story_test',rid);self.assertEqual(data['after']['time_hours'],7.5)
    self.assertEqual(t.result('story_test','f'*32),{'status':'pending'})
    t.run(a);self.assertNotEqual(req.read_text().split('\t')[1],rid)

 def test_invalid_clock_and_advance_ranges(self):
  with tempfile.TemporaryDirectory()as tmp,patch.object(t,'paths',return_value=(Path(tmp)/'request',Path(tmp)/'response')):
   for op,value in [('set','24:00'),('set','7:30'),('advance','0'),('advance','1441'),('advance','nan')]:
    a=argparse.Namespace(world='story_test',operation=op,value=value,yes=False)
    with self.assertRaises(ValueError):t.run(a)
  with self.assertRaises(ValueError):t.paths('road_home')

if __name__=='__main__':unittest.main()
