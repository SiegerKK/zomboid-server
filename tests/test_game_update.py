import json,os,subprocess,tempfile,unittest,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class UpdateTests(unittest.TestCase):
 @unittest.skipUnless(shutil.which("javac"), "Compiler-only regression: run on developer host or CI with JDK")
 def test_structured_version_and_unreviewed_rejection(self):
  source='''public class VersionProbe {
    public static class V{String s;V(String s){this.s=s;}public String toString(){return s;}}
    public static class NewCore{String s;NewCore(String s){this.s=s;}public V getGameVersion(){return new V("42.22");}public String getGameAndBuildVersion(){return s;}public String getVersion(){return "42.22.2 git:abc [attached]";}}
    public static class OldCore{public String getVersion(){return "42.21";}}
    public static void main(String[] a)throws Exception{
      if(!sieger.server.Bootstrap.reviewedVersion(new NewCore("42.22.2")).equals("42.22.2"))throw new AssertionError();
      if(!sieger.server.Bootstrap.reviewedVersion(new OldCore()).equals("42.21"))throw new AssertionError();
      for(String s:new String[]{"42.22.3","42.23","43.0","42.22.2-unknown","42.22.2 git:abc"}){
       try{sieger.server.Bootstrap.reviewedVersion(new NewCore(s));throw new AssertionError("Accepted "+s);}
       catch(IllegalStateException expected){}
      }
    }}'''
  with tempfile.TemporaryDirectory()as d:
   p=Path(d);(p/'VersionProbe.java').write_text(source);jar=ROOT/'server/runtime/SiegerServer.jar'
   subprocess.run(['javac','--release','8','-cp',str(jar),'-d',str(p),str(p/'VersionProbe.java')],check=True,capture_output=True)
   subprocess.run(['java','-cp',str(jar)+os.pathsep+str(p),'VersionProbe'],check=True)
 def test_all_local_mod_metadata_supports_new_minor(self):
  for name in ['mods/SiegerAdmin/42/mod.info','mods/SiegerRadio/42/mod.info','config/radio-server-mod.info']:
   info=(ROOT/name).read_text()
   self.assertIn('versionMin=42.21',info)
   self.assertIn('versionMax=42.22',info)
 def test_refresh_refuses_running_and_keeps_pointer_on_download_failure(self):
  import sys,argparse
  from unittest.mock import patch
  sys.path.insert(0,str(ROOT/'story'));import workshopctl,scanctl
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);slot=root/'worlds/story_test';slot.mkdir(parents=True)
   (slot/'mods.env').write_text('WORKSHOP_ITEMS=3619862853;3809306528\n')
   marker=slot/'workshop-snapshot';marker.write_text('previous\n')
   a=argparse.Namespace(world='story_test',yes=True)
   with patch.object(scanctl,'slot',return_value=slot),patch.object(scanctl,'STORE',root):
    with patch.object(workshopctl.subprocess,'run',return_value=subprocess.CompletedProcess([],0,stdout='true'))as run:
     with self.assertRaisesRegex(ValueError,'Stop game'):workshopctl.run(a)
     self.assertEqual(run.call_count,1)
    def fail_download(cmd,**kw):
     if cmd[:2]==['docker','inspect']:return subprocess.CompletedProcess(cmd,0,stdout='false')
     if cmd[:2]==['docker','pull']:return subprocess.CompletedProcess(cmd,0)
     raise subprocess.CalledProcessError(2,cmd)
    with patch.object(workshopctl.subprocess,'run',side_effect=fail_download):
     with self.assertRaises(subprocess.CalledProcessError):workshopctl.run(a)
    self.assertEqual(marker.read_text(),'previous\n')
 def test_refresh_success_selects_only_verified_new_snapshot(self):
  import sys,argparse
  from unittest.mock import patch
  import zipfile
  sys.path.insert(0,str(ROOT/'story'));import workshopctl,scanctl
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);slot=root/'worlds/story_test';slot.mkdir(parents=True)
   (slot/'mods.env').write_text('WORKSHOP_ITEMS=3619862853;3809306528\n')
   def mock_download(cmd,**kw):
    if cmd[:2]==['docker','inspect']:return subprocess.CompletedProcess(cmd,0,stdout='false')
    if cmd[:2]==['docker','run']:
     target=next((root/'mod-snapshots').iterdir())/'workshop/content/108600'
     for wid in ['3619862853','3809306528']:
      p=target/wid/'mods/example/mod.info';p.parent.mkdir(parents=True);p.write_text('id=example')
     jar=target/'3619862853/mods/ZombieBuddy/libs/ZombieBuddy.jar';jar.parent.mkdir(parents=True)
     with zipfile.ZipFile(jar,'w')as z:
      z.writestr('me/zed_0xff/zombie_buddy/Callbacks.class',b'fixture only')
      z.writestr('META-INF/MANIFEST.MF','Premain-Class: me.zed_0xff.zombie_buddy.Agent')
    return subprocess.CompletedProcess(cmd,0)
   with patch.object(scanctl,'slot',return_value=slot),patch.object(scanctl,'STORE',root),patch.object(workshopctl.subprocess,'run',side_effect=mock_download):
    workshopctl.run(argparse.Namespace(world='story_test',yes=True))
   name=(slot/'workshop-snapshot').read_text().strip()
   self.assertTrue((root/'mod-snapshots'/name/'verified.json').is_file())
   self.assertEqual((slot/'workshop-snapshot').stat().st_mode&0o777,0o600)
 def test_image_overlay_changes_no_data_mods_or_network(self):
  env=os.environ.copy();env.update(PZ_STORY_BUNDLE='./story/examples/empty_bundle.lua',PZ_SECRETS_FILE='./.env.example',PZ_TEST_SECRETS_FILE='./.env.example',PZ_STORY_ADMIN_MODS='ZombieBuddy;TLOU_Infected_MP;SiegerAdmin',PZ_STORY_RADIO_MODS='ZombieBuddy;TLOU_Infected_MP;SiegerAdmin;SiegerRadio',PZ_SERVER_TOOLS_WORLD='story_test')
  def config(extra):
   cmd=['docker','compose','--env-file','.env.example']
   for f in ['compose.yaml','compose.mods.yaml','compose.story.yaml','compose.radio.yaml','compose.server-tools.yaml']+extra:cmd+=['-f',f]
   return json.loads(subprocess.run(cmd+['config','--format','json'],cwd=ROOT,env=env,text=True,capture_output=True,check=True).stdout)['services']['zomboid']
  before=config([]);after=config(['compose.engine-42.22.yaml'])
  for k in ['volumes','ports','mem_limit','entrypoint']:self.assertEqual(before[k],after[k])
  self.assertEqual(before['environment']['MODS'],after['environment']['MODS'])
  self.assertEqual(after['environment']['WORKSHOP_AUTO_UPDATE'],'0')
  self.assertEqual(after['image'],'ghcr.io/meshi-team/project-zomboid-server@sha256:cec925cd86a7d1d5e020c0c94a30abbf59fd7bc94707fc5649e786d48306898a')
if __name__=='__main__':unittest.main()
