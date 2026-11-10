import argparse,datetime,hashlib,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'story'),str(ROOT/'scripts')]
import adminmode,scanctl,livectl,server_world_assets,animals
class OffTests(unittest.TestCase):
 def test_world_loader_is_only_restricted_data_parser(self):
  server_world_assets.check();body=server_world_assets.render()
  self.assertIn((ROOT/'story/runtime/ZZ_SiegerStoryScenes.lua').read_text(),body)
  self.assertNotIn('Events.',body);self.assertNotIn('loadstring',body.replace('-- Accept ONLY storyctl.lua_literal\'s grammar. No loadstring, eval or remote code.',''))
  self.assertNotIn('doAction',body)
 def test_switch_requires_stop_fresh_verified_backup_and_preserves_files(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);slot=root/'worlds/story_test';(slot/'story').mkdir(parents=True);(slot/'data').mkdir()
   bundle=slot/'story/bundle.lua';bundle.write_text('private fixture')
   store=root/'backups/worlds/story_test';store.mkdir(parents=True)
   args=argparse.Namespace(world='story_test',mode='off',yes=True)
   state={'State':{'Running':True,'FinishedAt':'2026-01-01T00:00:00Z'},'Mounts':[{'Destination':'/root/Zomboid','Source':str(slot/'data')}]}
   def call(*a,**kw):return subprocess.CompletedProcess([],0,stdout=json.dumps([state]))
   with patch.object(scanctl,'slot',return_value=slot),patch.object(scanctl,'active_world',return_value='story_test'),patch.object(scanctl,'STORE',root),patch.object(livectl,'STORE',root),patch.object(adminmode.subprocess,'run',side_effect=call):
    with self.assertRaisesRegex(ValueError,'Stop game'):adminmode.run(args)
    state['State']['Running']=False
    with self.assertRaisesRegex(ValueError,'backup'):adminmode.run(args)
    b=store/'world-fixture.tar.gz';b.write_bytes(b'fixture')
    Path(str(b)+'.sha256').write_text(hashlib.sha256(b.read_bytes()).hexdigest()+'  '+b.name+'\n')
    adminmode.run(args);self.assertTrue(adminmode.disabled('story_test'))
    self.assertEqual((slot/'story'/adminmode.MARKER).stat().st_mode&0o777,0o600)
    args.mode='on';adminmode.run(args);self.assertFalse(adminmode.disabled('story_test'))
    self.assertEqual(bundle.read_text(),'private fixture')
 def test_disabled_admin_rejects_requests_before_queue(self):
  with patch.object(scanctl,'admin_disabled',return_value=True):
   with self.assertRaisesRegex(ValueError,'disabled'):scanctl.assert_ready('story_test')
   with self.assertRaisesRegex(ValueError,'disabled'):scanctl.assert_module_ready('story_test','SiegerAdminClock')
  with tempfile.TemporaryDirectory()as d:
   base=Path(d);(base/'story').mkdir();(base/'story/sieger-admin.disabled').write_text('off-v1\n')
   with patch.object(livectl,'slot',return_value=base):
    with self.assertRaisesRegex(ValueError,'disabled'):livectl.running_world('story_test')
 def test_radio_requires_current_server_world_context_and_exact_source(self):
  with tempfile.TemporaryDirectory()as d:
   slot=Path(d);base=slot/'data/Lua';base.mkdir(parents=True)
   p=base/'SiegerServerReady.txt';p.write_text(json.dumps({'world_context':False}))
   mounts={'/root/Zomboid/Lua/SiegerStoryBundle.txt':(slot/'story/bundle.lua').resolve(),'/root/Zomboid/mods/SiegerRadio':(ROOT/'mods/SiegerRadio').resolve()}
   with patch.object(scanctl,'admin_disabled',return_value=True),patch.object(scanctl,'slot',return_value=slot),patch.object(scanctl,'docker_mounts',return_value=mounts),patch.object(animals,'ready',return_value=(base,'boot')):
    with self.assertRaisesRegex(ValueError,'context'):scanctl.assert_module_ready('story_test','SiegerStoryRadio')
    p.write_text(json.dumps({'world_context':True}));scanctl.assert_module_ready('story_test','SiegerStoryRadio')
 def test_manager_does_not_add_admin_when_disabled(self):
  body=(ROOT/'pz').read_text();self.assertIn('sieger-admin.disabled',body)
  block=body.split('if [[ -e "$WORLDS/$name/story/sieger-admin.disabled" ]]',1)[1].split('    fi',1)[0]
  off=block.split('    else',1)[0]
  self.assertNotIn(';}SiegerAdmin',off);self.assertIn('PZ_SERVER_ADMIN_DISABLED=1',off)
if __name__=='__main__':unittest.main()
