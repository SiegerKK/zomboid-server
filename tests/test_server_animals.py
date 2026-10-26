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
  self.req=self.root/'SiegerServerAnimals.request';self.result=self.root/'SiegerServerAnimals.json'
 def args(self,cmd='snapshot',**kw):
  return argparse.Namespace(command=cmd,world='story_test',player='admin',radius=100,yes=True,output=None,**kw)
 def test_queue_typed_expiring_boot_bound_request(self):
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
  code=(ROOT/'server/src/sieger/server/Animals.java').read_text();self.assertNotIn('setHealth',code);self.assertNotIn('setX(',code);self.assertNotIn('RunLua',code)
  self.assertIn('checksumDone',code);self.assertNotIn('checksumDone=',code)
 def test_own_jar_has_no_engine_classes(self):
  with zipfile.ZipFile(ROOT/'server/runtime/SiegerServer.jar')as z:
   self.assertTrue(all(n.startswith('sieger/server/')or n=='META-INF/MANIFEST.MF' for n in z.namelist()))
 def test_jvm_scanner_and_reproducible_build(self):
  asm=os.environ.get('SIEGER_ASM_JAR')
  if not asm:self.skipTest('Set SIEGER_ASM_JAR to audited ZombieBuddy or ByteBuddy 1.18.8')
  out=self.root/'agent.jar'
  subprocess.run([sys.executable,str(ROOT/'scripts/server_tools_build.py'),'--asm-jar',asm,'--output',str(out)],check=True)
  self.assertEqual(out.read_bytes(),(ROOT/'server/runtime/SiegerServer.jar').read_bytes())
  sources={
   'zombie/network/GameServer.java':'''package zombie.network; public class GameServer {public static boolean server=true; public static Thread mainThread=Thread.currentThread(); public static Object getPlayerByUserName(String n){return n.equals("admin")?new Anchor():null;} public static class Anchor {public float getX(){return 10;}public float getY(){return 20;}public float getZ(){return 0;}}}''',
   'zombie/Lua/LuaManager.java':'package zombie.Lua; public class LuaManager {public static boolean checksumDone=true;}',
   'zombie/iso/IsoWorld.java':'''package zombie.iso; public class IsoWorld {public static IsoWorld instance=new IsoWorld();public Object getCell(){return new Cell();}public static class Cell {public java.util.List<Object> getAnimals(){return java.util.List.of(new Animal(),new Animal());}}public static class Animal {public Object getSquare(){return this;}public float getX(){return 13;}public float getY(){return 24;}public float getZ(){return 0;}public int getAnimalID(){return 7;}public String getAnimalType(){return "cow";}public float getHealth(){return 1;}public int getAge(){return 20;}public boolean isDead(){return false;}public boolean isBaby(){return false;}}}''',
   'sieger/server/Test.java':'''package sieger.server; public class Test {public static void main(String[] a)throws Exception{Animals.world="story_test";Animals.tick();var dir=Animals.DIR;String id="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";java.nio.file.Files.writeString(dir.resolve("SiegerServerAnimals.request"),"v1\\t"+id+"\\tstory_test\\tadmin\\t10\\t"+(System.currentTimeMillis()+30000)+"\\t"+Animals.BOOT+"\\n");Animals.nextPoll=0;Animals.tick();for(int n=0;n<20&&Animals.source!=null;n++)Animals.tick();String first=java.nio.file.Files.readString(dir.resolve("SiegerServerAnimals.json"));if(!first.contains("\\\"count\\\":2")||!first.contains("\\\"distance_tiles_2d\\\":5.0")||!first.contains("complete"))throw new AssertionError(first);Animals.nextPoll=0;Animals.tick();if(!first.equals(java.nio.file.Files.readString(dir.resolve("SiegerServerAnimals.json"))))throw new AssertionError("replay");try{Agent.instrument(new byte[8]);throw new AssertionError("bad class accepted");}catch(IllegalArgumentException expected){}System.out.println("PASS: JVM fixture counts/distance/replay/hash guard");}}'''}
  src=self.root/'src';classes=self.root/'classes';classes.mkdir()
  for name,text in sources.items():p=src/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
  subprocess.run(['javac','--release','17','-cp',str(out)+os.pathsep+asm,'-d',str(classes),*map(str,src.rglob('*.java'))],check=True)
  data=self.root/'data'
  subprocess.run(['java','-Dsieger.server.data='+str(data),'-cp',os.pathsep.join([str(out),str(classes),asm]),'sieger.server.Test'],check=True)
  result=json.loads((data/'SiegerServerAnimals.json').read_text());self.assertEqual(result['count'],2);self.assertEqual(result['errors'],0)
if __name__=='__main__':unittest.main()
