import json,os,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class UpdateTests(unittest.TestCase):
 def test_structured_version_and_unreviewed_rejection(self):
  source='''public class VersionProbe {
    public static class V{String s;V(String s){this.s=s;}public String toString(){return s;}}
    public static class NewCore{String s;NewCore(String s){this.s=s;}public V getGameVersion(){return new V(s);}public String getVersion(){return "42.22.2 git:abc [attached]";}}
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
