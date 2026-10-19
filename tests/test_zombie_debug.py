"""Collector protocol, real Lua fixture traces and private offline analysis."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'story'))
import zombiedebug as z

class Traces(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  lua=shutil.which('lua5.1')
  if not lua:raise unittest.SkipTest('Lua 5.1 required for engine-shaped trace fixture')
  cls.temp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
  cls.base=Path(cls.temp.name)
  subprocess.run([lua,str(ROOT/'tests/zombie_debug.lua'),str(ROOT/'story/runtime/SiegerAdminZombieDebug.lua'),str(cls.base)],check=True,capture_output=True,text=True)
 def capture(self,name):
  path=self.base/(name+'.txt');rid=json.loads(path.read_text().splitlines()[0])['id'];return path,rid
 def test_snapshot_preserves_false_and_full_wall_timestamp(self):
  path,rid=self.capture('snapshot');rows=list(z.verified(path,rid))
  obs=[row for row in rows if row['kind']=='zombie']
  self.assertEqual(len(obs),2);self.assertEqual(len({row['tracking_id']for row in obs}),2)
  self.assertEqual([row['online_id']for row in obs],[7,7])
  self.assertIs(obs[0]['inside'],False);self.assertIs(obs[0]['moving'],False)
  self.assertIs(obs[0]['hide_rule']['bound'],True)
  self.assertEqual(rows[0]['timestamp_ms'],1792400002300)
 def test_changes_identity_coverage_and_no_death_from_loss(self):
  path,rid=self.capture('record');data=z.analyze(path,rid)
  self.assertEqual(data['samples'],3);self.assertEqual(data['complete_samples'],3)
  self.assertEqual(data['unique_observed_objects'],3)
  self.assertGreater(data['same_sample_online_id_collisions'],0)
  kinds=[row['kind']for row in data['derived_events']]
  self.assertIn('entered_building',kinds);self.assertIn('state_changed',kinds);self.assertIn('observation_lost',kinds)
  self.assertNotIn('observed_dead',kinds)
 def test_terminal_partial_cases_cannot_be_silently_complete(self):
  for name in ('stopped','pending_stopped','interrupted','limited','byte_limited','row_limited','entity_error','gap','expired'):
   with self.subTest(name=name):
    path,rid=self.capture(name)
    with self.assertRaisesRegex(ValueError,'incomplete'):list(z.verified(path,rid))
    data=z.analyze(path,rid,allow_partial=True)
    self.assertFalse(data['capture_complete'])
  path,rid=self.capture('interrupted');data=z.analyze(path,rid,True)
  self.assertIsNone(data['terminal'])
  self.assertEqual(data['samples'],1)
 def test_missing_optional_fields_are_null_not_zero(self):
  path,rid=self.capture('optional');rows=list(z.verified(path,rid));obs=[r for r in rows if r['kind']=='zombie']
  self.assertIsNone(obs[1]['health']);self.assertIn('getHealth',obs[1]['unavailable'])
 def test_missing_building_getter_is_unknown_not_outdoors(self):
  path,rid=self.capture('unknown_building');rows=list(z.verified(path,rid));obs=[r for r in rows if r['kind']=='zombie']
  self.assertIsNone(obs[1]['inside']);self.assertIn('getBuilding',obs[1]['unavailable'])
 def test_getter_error_is_gap_not_unloading_or_speed_jump(self):
  path,rid=self.capture('gap');data=z.analyze(path,rid,True)
  self.assertGreater(data['entity_errors'],0)
  lost=[e for e in data['derived_events']if e['kind']=='observation_lost']
  self.assertEqual(lost,[])
 def test_stall_candidates_require_simulation_to_advance(self):
  path,rid=self.capture('paused_path');data=z.analyze(path,rid)
  self.assertNotIn('stationary_path_candidate',[e['kind']for e in data['derived_events']])
  path,rid=self.capture('stationary_path');data=z.analyze(path,rid)
  self.assertIn('stationary_path_candidate',[e['kind']for e in data['derived_events']])
  self.assertGreaterEqual(data['zombies'][0]['max_stationary_path_ms'],10000)
 def test_day_night_grouping_is_observations_not_population(self):
  path,rid=self.capture('record');data=z.analyze(path,rid)
  group=data['observations_by_type_and_phase']['TLOU_Stalker']['seek_building']
  self.assertEqual(group['observations'],sum(zombie['samples']for zombie in data['zombies']))
  self.assertGreater(group['inside'],0)
 def test_derived_event_limit_is_explicit(self):
  path,rid=self.capture('record');data=z.analyze(path,rid,events_limit=0)
  self.assertTrue(data['events_truncated']);self.assertEqual(data['derived_events'],[])
  self.assertGreater(data['derived_event_count'],0)
 def test_malformed_trace_wrong_counts_ids_and_nan_refused(self):
  source,rid=self.capture('snapshot');raw=source.read_text()
  bads=[raw.replace('"rows_before_end":5','"rows_before_end":999'),raw.replace('"inspected":2','"inspected":3'),raw.replace('"x":100,','"x":NaN,'),raw.replace('"inside":false','"inside":"false"')]
  with tempfile.TemporaryDirectory()as tmp:
   path=Path(tmp)/'bad.txt'
   for bad in bads:
    self.assertNotEqual(bad,raw)
    path.write_text(bad)
    with self.assertRaises(ValueError):list(z.verified(path,rid))
   path.write_text(raw.replace(rid,'f'*32))
   with self.assertRaises(ValueError):list(z.verified(path,rid))
 def test_export_private_complete_and_no_overwrite(self):
  path,rid=self.capture('record')
  with tempfile.TemporaryDirectory()as tmp,patch.object(z,'logpath',return_value=(path,rid)),contextlib.redirect_stdout(io.StringIO()):
   dst=Path(tmp)/'trace.json';a=argparse.Namespace(world='story_test',id=rid,allow_partial=False,output=str(dst),command='report')
   z.report(a);data=json.loads(dst.read_text());self.assertEqual(data['recording_id'],rid)
   self.assertEqual(os.stat(dst).st_mode&0o777,0o600)
   with self.assertRaises(FileExistsError):z.report(a)
   dst.unlink();dst.symlink_to(path)
   with self.assertRaises(ValueError):z.report(a)
 def test_partial_export_refused_before_destination_creation(self):
  path,rid=self.capture('byte_limited')
  with tempfile.TemporaryDirectory()as tmp,patch.object(z,'logpath',return_value=(path,rid)):
   dst=Path(tmp)/'bad.json';a=argparse.Namespace(world='story_test',id=rid,allow_partial=False,output=str(dst),command='report')
   with self.assertRaises(ValueError):z.report(a)
   self.assertFalse(dst.exists())

class Protocol(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name)
  self.p=patch.object(z,'folder',return_value=self.base);self.p.start();self.addCleanup(self.p.stop)
 def args(self,**kwargs):
  data=dict(command='record',world='story_test',seconds=60,interval_ms=1000,max_mib=64,max_records=250000,max_zombies=10000,player=None,yes=False,acknowledge_failed=False)
  data.update(kwargs);return argparse.Namespace(**data)
 def test_preview_bounds_and_no_queue(self):
  with contextlib.redirect_stdout(io.StringIO()):z.queue(self.args())
  self.assertFalse((self.base/z.REQUEST).exists())
  for kwargs in ({'seconds':0},{'seconds':1801},{'interval_ms':99},{'max_mib':257},{'max_zombies':100001},{'player':'../admin'}):
   with self.assertRaises(ValueError):z.queue(self.args(**kwargs))
 def test_queue_busy_and_stop_exact_id(self):
  with patch.object(z.scanctl,'assert_module_ready'),contextlib.redirect_stdout(io.StringIO()):
   z.queue(self.args(yes=True));request=z.request('story_test')
   self.assertEqual(request['seconds'],60);self.assertEqual(z.status('story_test')['status'],'pending')
   with self.assertRaisesRegex(ValueError,'active/pending'):z.queue(self.args(yes=True))
   z.stop(argparse.Namespace(world='story_test',yes=True))
   self.assertEqual((self.base/z.STOP).read_text().strip(),request['id'])
 def test_status_staleness_and_malformed_controls(self):
  with patch.object(z.scanctl,'assert_module_ready'),contextlib.redirect_stdout(io.StringIO()):z.queue(self.args(yes=True))
  request=z.request('story_test');rid=request['id'];path=self.base/z.STATUS
  path.write_text(f'v1\t{rid}\tstory_test\trunning\tsampling\t1\t5\t2000\tSiegerAdminZombieDebug-{rid}.txt\t1\n')
  self.assertTrue(z.status('story_test')['stale_heartbeat'])
  path.write_text('bad\n')
  with self.assertRaises(ValueError):z.status('story_test')
 def test_no_arbitrary_source_path_or_links(self):
  with self.assertRaises(ValueError):z.logpath('story_test','../x')
  rid='a'*32;path=self.base/('SiegerAdminZombieDebug-'+rid+'.txt');path.symlink_to('/etc/passwd')
  with self.assertRaises(ValueError):z.logpath('story_test',rid)

if __name__=='__main__':unittest.main()
