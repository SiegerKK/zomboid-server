#!/usr/bin/env python3
"""No game or client changes: protocol, packaging and JVM read-only scanner tests."""
import argparse,contextlib,hashlib,io,json,os,subprocess,sys,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'story'));import animals
class AnimalsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.boot='11111111-1111-1111-1111-111111111111';self.rid='a'*32
  self.req=self.root/'SiegerServerAnimalsRequest.txt';self.result=self.root/'SiegerServerAnimalsResult.txt'
 def args(self,cmd='snapshot',**kw):
  return argparse.Namespace(command=cmd,world='story_test',player='admin',radius=100,yes=True,output=None,**kw)
 def test_queue_typed_expiring_boot_bound_request(self):
  self.req.write_text('')  # Bootstrap pre-creates private empty control files.
  with patch.object(animals,'ready',return_value=(self.root,self.boot)),contextlib.redirect_stdout(io.StringIO()):animals.run(self.args())
  f=self.req.read_text().strip().split('\t');self.assertEqual(f[:1],['v1']);self.assertEqual(f[2:5],['story_test','admin','100']);self.assertEqual(f[6],self.boot)
  self.assertLessEqual(int(f[5])-int(time.time()*1000),30000)
  self.assertEqual(self.req.stat().st_mode&0o777,0o600)
 def prepare_result(self,status='complete',boot=None):
  self.req.write_text('\t'.join(['v1',self.rid,'story_test','admin','100',str(int(time.time()*1000)+30000),self.boot])+'\n')
  self.result.write_text(json.dumps({'schema':1,'world':'story_test','boot':boot or self.boot,'request_id':self.rid,'status':status,'count':0,'animals':[]}))
 def test_no_duplicate_pending_request(self):
  self.prepare_result('running')
  with patch.object(animals,'ready',return_value=(self.root,self.boot)),self.assertRaisesRegex(ValueError,'pending'):animals.run(self.args())
 def test_fail_closed_stale_boot_or_count(self):
  self.prepare_result(boot='22222222-2222-2222-2222-222222222222')
  with patch.object(animals,'ready',return_value=(self.root,self.boot)),self.assertRaises(ValueError):animals.run(self.args('status'))
  self.prepare_result();data=json.loads(self.result.read_text());data['count']=1;self.result.write_text(json.dumps(data))
  with patch.object(animals,'ready',return_value=(self.root,self.boot)),self.assertRaises(ValueError):animals.run(self.args('report'))
 def test_no_request_in_preview_or_invalid_name(self):
  a=self.args();a.yes=False
  with patch.object(animals,'ready',return_value=(self.root,self.boot)),contextlib.redirect_stdout(io.StringIO()):animals.run(a)
  self.assertFalse(self.req.exists());a.player='admin\ncommand'
  with patch.object(animals,'ready',return_value=(self.root,self.boot)),self.assertRaises(ValueError):animals.run(a)
 def test_client_mods_and_checksum_unchanged_contract(self):
  root=ROOT/'mods/SiegerAdmin';self.assertFalse(any('Animal' in p.name for p in root.rglob('*')))
  overlay=(ROOT/'compose.server-tools.yaml').read_text();self.assertNotIn('MODS:',overlay);self.assertNotIn('media/lua',overlay)
  code=(ROOT/'server/src/sieger/server/Bootstrap.java').read_text();self.assertNotIn('addTransformer',code)
  self.assertIn('onGameInitComplete',code);self.assertNotIn('ASM',code)
 def test_own_jar_has_only_bootstrap(self):
  with zipfile.ZipFile(ROOT/'server/runtime/SiegerServer.jar')as z:
   self.assertEqual(set(z.namelist()),{'META-INF/MANIFEST.MF','sieger/server/Bootstrap.class'})
 def test_bootstrap_build_without_game_or_third_party_jars(self):
  out=self.root/'agent.jar'
  subprocess.run([sys.executable,str(ROOT/'scripts/server_tools_build.py'),'--output',str(out)],check=True)
  with zipfile.ZipFile(out)as z:self.assertEqual(set(z.namelist()),{'META-INF/MANIFEST.MF','sieger/server/Bootstrap.class'})

 def test_bootstrap_uses_existing_callback_and_preserves_checksum(self):
  sources={
   'me/zed_0xff/zombie_buddy/Callbacks.java': 'package me.zed_0xff.zombie_buddy; public class Callbacks {public static final Callback onGameInitComplete=new Callback();public static class Callback {public Runnable r;public void register(Runnable r){this.r=r;}}}',
   'zombie/network/GameServer.java': 'package zombie.network;public class GameServer {public static boolean server=true;public static Thread mainThread=Thread.currentThread();}',
   'zombie/core/Core.java': 'package zombie.core;public class Core {public static Core getInstance(){return new Core();}public String getVersion(){return "42.21";}}',
   'se/krka/kahlua/vm/KahluaTable.java': 'package se.krka.kahlua.vm;public interface KahluaTable {void rawset(Object k,Object v);Object rawget(Object k);}',
   'zombie/Lua/LuaManager.java': 'package zombie.Lua;public class LuaManager {public static boolean checksumDone=true;public static String checksum="unchanged";public static Table env=new Table();public static Platform platform=new Platform();public static String path;public static Object RunLua(String p){path=p;env.rawset("SiegerServerModuleRevision","animals-v1");return null;}public static class Table implements se.krka.kahlua.vm.KahluaTable {private java.util.Map<Object,Object> m=new java.util.HashMap<Object,Object>();public void rawset(Object k,Object v){m.put(k,v);}public Object rawget(Object k){return m.get(k);}}public static class Platform {public Table newTable(){return new Table();}}}',
   'TestBootstrap.java': 'public class TestBootstrap {public static void main(String[] a)throws Exception{sieger.server.Bootstrap.premain("story_test",null);Runnable r=me.zed_0xff.zombie_buddy.Callbacks.onGameInitComplete.r;if(r==null)throw new AssertionError("no registration");r.run();if(!"/bootstrap/sieger-server/SiegerServer.lua".equals(zombie.Lua.LuaManager.path))throw new AssertionError("wrong module");if(!zombie.Lua.LuaManager.checksum.equals("unchanged"))throw new AssertionError("checksum mutated");for(String n:new String[]{"SiegerServerReady.txt","SiegerServerAnimalsRequest.txt","SiegerServerAnimalsResult.txt","SiegerServerAnimalsGuard.txt"}){java.nio.file.Path p=java.nio.file.Paths.get(System.getProperty("sieger.server.data"),n);if(!java.nio.file.Files.getPosixFilePermissions(p).equals(java.nio.file.attribute.PosixFilePermissions.fromString("rw-------")))throw new AssertionError("file privacy");}r.run();System.out.println("PASS: lifecycle callback only, fixed trusted module, unchanged checksum and private files");}}'
  }
  src=self.root/'src';classes=self.root/'classes';classes.mkdir()
  for name,text in sources.items():p=src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
  jar=ROOT/'server/runtime/SiegerServer.jar'
  subprocess.run(['javac','--release','8','-cp',str(jar),'-d',str(classes),*map(str,src.rglob('*.java'))],check=True)
  compiled=self.root/'compiled.jar'
  subprocess.run([sys.executable,str(ROOT/'scripts/server_tools_build.py'),'--output',str(compiled)],check=True)
  for i,artifact in enumerate((jar,compiled)):
   subprocess.run(['java','-Dsieger.server.data='+str(self.root/('data'+str(i))),'-cp',str(artifact)+os.pathsep+str(classes),'TestBootstrap'],check=True)

if __name__=='__main__':unittest.main()
