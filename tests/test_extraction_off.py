import importlib.util,sqlite3,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'story'))
import extractionoffctl,npclootctl
spec=importlib.util.spec_from_file_location('world_guard',ROOT/'scripts/world-config-guard.py');guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
class OffTests(unittest.TestCase):
 def test_radio_settings_preserve_other_sandbox(self):
  s='SandboxVars = {\n TarkovTraders = {\n  TraderAccess = 1,\n  TaskSource = 1,\n  RadioHideoutOnly = true,\n  BuyMultiplier = 1.0,\n },\n ALife = { Drops_WeaponCondition = 8, },\n}\n'
  n=extractionoffctl.set_block(s,'TarkovTraders',{'TraderAccess':'3','TaskSource':'2','RadioHideoutOnly':'false'})
  self.assertEqual(n,s.replace('TraderAccess = 1','TraderAccess = 3').replace('TaskSource = 1','TaskSource = 2').replace('RadioHideoutOnly = true','RadioHideoutOnly = false'))
 def test_map_guard_keeps_config_and_replaces_generated_regions(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);server=p/'Server';server.mkdir();maps=p/'maps';maps.mkdir()
   towns=['Muldraugh','West Point','Riverside','Rosewood','March Ridge','Echo Creek','Fallas Lake','Ekron','Irvington','Brandenburg','Valley Station']
   for town in towns:
    folder=maps/(town+', KY');folder.mkdir();(folder/'spawnpoints.lua').write_text('function SpawnPoints() return {} end')
   ini=server/'SiegerZomboid.ini';ini.write_text('Map=ExtractionMap;Muldraugh, KY\nMods=ZombieBuddy;TarkovTraders\nRCONPassword=fixture-not-secret\n')
   guard.configure(server,maps)
   self.assertIn('RCONPassword=fixture-not-secret',ini.read_text());self.assertIn('Map=Muldraugh, KY',ini.read_text())
   regions=(server/'SiegerZomboid_spawnregions.lua').read_text();self.assertEqual(regions.count('spawnpoints.lua'),11);self.assertNotIn('ExtractionMap',regions)
 def test_saved_character_in_hideout_is_detected_read_only(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);mod=root/'package/3785397275/maps';mod.mkdir(parents=True);(mod/'90_75.lotheader').write_bytes(b'fixture')
   dbfile=root/'data/Saves/Multiplayer/SiegerZomboid/players.db';dbfile.parent.mkdir(parents=True)
   with sqlite3.connect(dbfile)as db:
    db.execute('CREATE TABLE networkPlayers(x REAL,y REAL,z REAL,isDead INTEGER)');db.execute('INSERT INTO networkPlayers VALUES(23160,19340,0,0)')
   with patch.object(npclootctl,'snapshot',return_value=root/'package'):
    self.assertEqual(extractionoffctl.players_in_hideout(root),{'characters_checked':1,'inside_extraction_map':1})
if __name__=='__main__':unittest.main()
