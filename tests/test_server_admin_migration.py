"""Boundary tests: identical algorithms, minimal client, exact mount/boot identity."""
import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'story')]
import server_admin_assets as assets
import admin_assets,admin_pack,scanctl,animals
class MigrationTests(unittest.TestCase):
 def test_all_server_handlers_moved_without_algorithm_changes(self):
  assets.check()
  self.assertEqual(set(assets.MODULES),set(admin_assets.MODULES)|{'SiegerRuntimeAudit'})
  java=(ROOT/'server/src/sieger/server/Bootstrap.java').read_text()
  for name in assets.MODULES:
   self.assertIn('"'+name+'"',java)
   src=assets.render()[ROOT/'server/lua/admin'/(name+'.lua')]
   self.assertTrue(src.endswith('\nSiegerServerLoadedModules["'+name+'"] = true\n'))
  self.assertLess(java.index('SiegerServerAdminPreflight.lua'),java.index('for(String name:',java.index('SiegerServerAdminPreflight.lua')))
  self.assertLess(java.index('for(String name:',java.index('SiegerServerAdminPreflight.lua')),java.index('SiegerServerAdminReady.lua'))
 def test_minimal_client_retains_exact_rpc_and_shared_contract(self):
  files=admin_pack.expected(server_compat=True)
  self.assertEqual(set(files),{'SiegerAdmin/'+p for p in admin_assets.AUTHORED})
  self.assertFalse(any('/server/'in p for p in files))
  for rel in admin_assets.AUTHORED:
   self.assertEqual(files['SiegerAdmin/'+rel],(ROOT/'mods/SiegerAdmin'/rel).read_bytes())
  with tempfile.TemporaryDirectory() as d:admin_pack.build(Path(d)/'compat.zip',True)
 def test_explicit_opt_in_and_stopped_backup_gate(self):
  manager=(ROOT/'pz').read_text()
  self.assertIn('story/server-admin.enabled',manager)
  self.assertIn('--client-ready',manager)
  fn=manager.split('story_server_admin() {',1)[1].split('command_story()',1)[0]
  self.assertLess(fn.index('container_running && die'),fn.index('backup_world "$name"'))
  self.assertLess(fn.index('backup_world "$name"'),fn.index('mv -- "$temp" "$marker"'))
  self.assertIn('"$name" == story_test',fn)
 def test_exact_mounts_and_boot_required(self):
  with tempfile.TemporaryDirectory() as d:
   slot=Path(d);(slot/'data/Lua').mkdir(parents=True);(slot/'story').mkdir()
   mounts={'/root/Zomboid/mods/SiegerAdmin':assets.COMPAT.resolve(),
    '/bootstrap/sieger-server':(ROOT/'server/lua').resolve(),
    '/bootstrap/SiegerServer.jar':(ROOT/'server/runtime/SiegerServer.jar').resolve(),
    '/root/Zomboid':(slot/'data').resolve(),'/root/Zomboid/Lua/SiegerStoryBundle.txt':(slot/'story/bundle.lua').resolve()}
   boot='11111111-1111-1111-1111-111111111111'
   with patch.object(scanctl,'slot',return_value=slot),patch.object(animals,'ready',return_value=(slot/'data/Lua',boot)):
    with self.assertRaisesRegex(ValueError,'not initialized'):scanctl.server_admin_runtime(mounts,'story_test')
    p=slot/'data/Lua/SiegerServerAdminReady.txt';p.write_text('v1\tstory_test\t'+boot+'\tadmin-v1\n')
    self.assertTrue(scanctl.packaged_runtime(mounts,'story_test'))
    p.write_text('v1\tstory_test\tstale-boot\tadmin-v1\n')
    with self.assertRaisesRegex(ValueError,'not initialized'):scanctl.server_admin_runtime(mounts,'story_test')
    mounts.pop('/bootstrap/SiegerServer.jar')
    with self.assertRaisesRegex(ValueError,'Incomplete'):scanctl.server_admin_runtime(mounts,'story_test')
 def test_bootstrap_migration_order_and_failure_gate(self):
  import os,subprocess
  sources={
   'me/zed_0xff/zombie_buddy/Callbacks.java':'package me.zed_0xff.zombie_buddy;public class Callbacks{public static final Callback onGameInitComplete=new Callback();public static class Callback{public Runnable r;public void register(Runnable r){this.r=r;}}}',
   'zombie/network/GameServer.java':'package zombie.network;public class GameServer{public static boolean server=true;public static Thread mainThread=Thread.currentThread();}',
   'zombie/core/Core.java':'package zombie.core;public class Core{public static Core getInstance(){return new Core();}public String getVersion(){return "42.21.0";}}',
   'se/krka/kahlua/vm/KahluaTable.java':'package se.krka.kahlua.vm;public interface KahluaTable{void rawset(Object k,Object v);Object rawget(Object k);}',
   'zombie/Lua/LuaManager.java':r'''package zombie.Lua;public class LuaManager{
    public static boolean checksumDone=true;public static String checksum="original";
    public static Table env=new Table();public static Platform platform=new Platform();
    public static java.util.List<String> calls=new java.util.ArrayList<String>();
    public static Object RunLua(String path){calls.add(path);
     if(path.endsWith("/SiegerServer.lua"))env.rawset("SiegerServerModuleRevision","animals-v1");
     else if(path.endsWith("/SiegerServerAdminPreflight.lua")){env.rawset("SiegerServerAdminPreflight",true);env.rawset("SiegerServerLoadedModules",new Table());}
     else if(path.contains("/admin/")){
      String name=path.substring(path.lastIndexOf('/')+1,path.length()-4);
      if(!name.equals(System.getProperty("fail.module")))((Table)env.rawget("SiegerServerLoadedModules")).rawset(name,true);
     }else if(path.endsWith("/SiegerServerAdminReady.lua"))env.rawset("SiegerServerAdminRevision","admin-v1");
     else throw new AssertionError("Unexpected load: "+path);return null;}
    public static class Table implements se.krka.kahlua.vm.KahluaTable{
     java.util.Map<Object,Object> data=new java.util.HashMap<Object,Object>();
     public void rawset(Object k,Object v){data.put(k,v);}public Object rawget(Object k){return data.get(k);}}
    public static class Platform{public Table newTable(){return new Table();}}
   }''',
   'MigrationProbe.java':r'''public class MigrationProbe{public static void main(String[] args){
    sieger.server.Bootstrap.premain("story_test",null);
    Runnable r=me.zed_0xff.zombie_buddy.Callbacks.onGameInitComplete.r;r.run();
    java.util.List<String> calls=zombie.Lua.LuaManager.calls;
    boolean fail=System.getProperty("fail.module")!=null;
    if(!calls.get(0).endsWith("/SiegerServer.lua")||!calls.get(1).endsWith("/SiegerServerAdminPreflight.lua"))throw new AssertionError("Wrong initial order");
    boolean ready=zombie.Lua.LuaManager.env.rawget("SiegerServerAdminRevision")!=null;
    if(ready==fail)throw new AssertionError("Incorrect ready state");
    if(!fail){String[] names={NAMES};if(calls.size()!=names.length+3)throw new AssertionError("Wrong count");
     for(int i=0;i<names.length;i++)if(!calls.get(i+2).equals("/bootstrap/sieger-server/admin/"+names[i]+".lua"))throw new AssertionError("Wrong module order");}
    if(!zombie.Lua.LuaManager.checksum.equals("original"))throw new AssertionError("Checksum changed");
    int count=calls.size();r.run();if(calls.size()!=count)throw new AssertionError("Double load");
    System.out.println("PASS bootstrap order, single registration, checksum and failed-module readiness gate");}}
   '''.replace('NAMES',','.join('"'+n+'"' for n in assets.MODULES))
  }
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);classes=root/'classes';classes.mkdir()
   for name,body in sources.items():p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(body)
   jar=ROOT/'server/runtime/SiegerServer.jar'
   subprocess.run(['javac','--release','8','-cp',str(jar),'-d',str(classes),*map(str,root.rglob('*.java'))],check=True,capture_output=True)
   for failed in (False,True):
    cmd=['java','-Dsieger.server.data='+str(root/('data'+str(failed)))]
    if failed:cmd+=['-Dfail.module=SiegerStoryAreaScan']
    env=os.environ.copy();env['PZ_SERVER_ADMIN']='1'
    subprocess.run(cmd+['-cp',str(jar)+os.pathsep+str(classes),'MigrationProbe'],env=env,check=True,capture_output=True,text=True)
 def test_behavioral_regressions_against_migrated_modules(self):
  import shutil,subprocess
  lua=shutil.which('lua5.1')
  if not lua:self.skipTest('Lua 5.1 interpreter unavailable; CI requires it')
  fixtures={
   'admin_clock':'SiegerAdminClock','zombie_debug':'SiegerAdminZombieDebug',
   'building_atlas':'SiegerAdminBuildingAtlas','story_construction':'SiegerAdminConstruction',
   'story_area_scan':'SiegerStoryAreaScan','story_runtime':'SiegerStoryDirector',
   'story_live':'SiegerStoryDirector','story_quest':'SiegerStoryDirector',
   'story_corpse':'SiegerStoryDirector','story_environment':'SiegerStoryDirector',
   'story_vehicle':'SiegerStoryDirector','story_batch':'SiegerStoryBatch',
   'story_ops':'SiegerStoryOps','story_tlou':'SiegerStoryTLOUDiagnostics',
   'story_vehicle_control':'SiegerStoryVehicleControl','story_player_control':'SiegerStoryPlayerControl'}
  for fixture,module in fixtures.items():
   with self.subTest(fixture=fixture):
    program='SiegerServerLoadedModules={};arg={[1]="server/lua/admin/'+module+'.lua"};dofile("tests/'+fixture+'.lua")'
    subprocess.run([lua,'-e',program],cwd=ROOT,check=True,capture_output=True,text=True)
  program='SiegerServerLoadedModules={};arg={[1]="server/client-compat/SiegerAdmin/42/media/lua/client/SiegerStoryCharacterClient.lua",[2]="server/lua/admin/SiegerStoryCharacter.lua",[3]="server/client-compat/SiegerAdmin/42/media/lua/shared/SiegerCharacterProfiles.lua"};dofile("tests/story_character.lua")'
  subprocess.run([lua,'-e',program],cwd=ROOT,check=True,capture_output=True,text=True)
 def test_overlay_changes_only_admin_source(self):
  import os,subprocess
  env=os.environ.copy();env.update(PZ_STORY_BUNDLE='./story/examples/empty_bundle.lua',PZ_SECRETS_FILE='./.env.example',PZ_TEST_SECRETS_FILE='./.env.example',PZ_STORY_ADMIN_MODS='ZombieBuddy;TLOU_Infected_MP;SiegerAdmin',PZ_STORY_RADIO_MODS='ZombieBuddy;TLOU_Infected_MP;SiegerAdmin;SiegerRadio',PZ_SERVER_TOOLS_WORLD='story_test')
  def config(extra):
   cmd=['docker','compose','--env-file','.env.example']
   for f in ['compose.yaml','compose.mods.yaml','compose.story.yaml','compose.radio.yaml','compose.server-tools.yaml']+extra:cmd+=['-f',f]
   cp=subprocess.run(cmd+['config','--format','json'],cwd=ROOT,env=env,text=True,capture_output=True,check=True)
   return json.loads(cp.stdout)['services']['zomboid']
  old,new=config([]),config(['compose.server-admin.yaml'])
  def mounts(s):return {m['target']:m for m in s['volumes']}
  before,after=mounts(old),mounts(new)
  self.assertEqual(set(before),set(after))
  for target in before:
   if target!='/root/Zomboid/mods/SiegerAdmin':self.assertEqual(before[target],after[target])
  self.assertEqual(after['/root/Zomboid/mods/SiegerAdmin']['source'],str(assets.COMPAT))
  self.assertTrue(after['/root/Zomboid/mods/SiegerAdmin']['read_only'])
  self.assertEqual(old['ports'],new['ports']);self.assertEqual(old['mem_limit'],new['mem_limit'])
  self.assertEqual(old['environment']['MODS'],new['environment']['MODS'])
if __name__=='__main__':unittest.main()
