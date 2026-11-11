import argparse,json,re,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'story'))
import walkingdeadctl, scanctl, workshopctl

class WalkingDeadTests(unittest.TestCase):
 def test_reviewed_balance_and_extraction_options(self):
  s=(ROOT/'config/presets/WalkingDead_ThreeMonths.lua').read_text()
  for k,v in {'StartMonth':'11','StartDay':'15','StartTime':'1','PopulationMultiplier':'0.56','AmmoLootNew':'3.0','Transmission':'3','HordeSize':'70','AmbientSprinterPercentWeek2':'0','HordeSprinterPercent':'0','NPCProvider':'3'}.items():
   self.assertRegex(s,rf'\b{k}\s*=\s*{re.escape(v)}\s*,')
  rules=(ROOT/'config/server-rules/walkingdead-coop.env').read_text()
  for line in ('SLEEP_ALLOWED=true','SLEEP_NEEDED=false','PVP=true','PING_LIMIT=0'):self.assertIn(line,rules)
  mods=(ROOT/'config/mods.walkingdead.env').read_text()
  for name in ('ProjectALifeNPCs','ProjectALifeJimmy','TacticalGridInventory','ExtractionMode'):self.assertIn(name,mods)
  self.assertNotRegex(mods,r'MODS=.*(?:SiegerAdmin|SiegerRadio|ZomboidForge|TLOU)')
 def test_preflight_refuses_running_or_wrong_world(self):
  with patch.object(scanctl,'active_world',return_value='other'):
   with self.assertRaisesRegex(ValueError,'previous active'):walkingdeadctl.preflight()
  info={'State':{'Running':True}}
  with patch.object(scanctl,'active_world',return_value='story_test'),patch.object(walkingdeadctl.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps([info]))):
   with self.assertRaisesRegex(ValueError,'Stop game'):walkingdeadctl.preflight()
 def test_new_world_may_not_overwrite_existing_data(self):
  with tempfile.TemporaryDirectory() as d:
   slot=Path(d);(slot/'profile').write_text('walkingdead\n');(slot/'data/db').mkdir(parents=True)
   with patch.object(walkingdeadctl,'preflight'),patch.object(scanctl,'slot',return_value=slot),patch.object(workshopctl,'run')as download:
    with self.assertRaisesRegex(ValueError,'Existing game data'):walkingdeadctl.prepare()
    download.assert_not_called()
 def test_snapshot_retains_installed_manifest_and_downloads_only_additions(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);slot=root/'worlds/walking_dead';slot.mkdir(parents=True)
   (slot/'mods.env').write_text((ROOT/'config/mods.walkingdead.env').read_text())
   previous=root/'worlds/story_test';previous.mkdir(parents=True)
   marker='workshop-20260101T000000Z';(previous/'workshop-snapshot').write_text(marker+'\n')
   seed=root/'mod-snapshots'/marker/'workshop';seed.mkdir(parents=True)
   (seed.parent/'verified.json').write_text('{}')
   (seed/'appworkshop_108600.acf').write_text('retained fixture manifest')
   old_ids=['3619862853','3378285185','3809306528','3817413313','3803984183','3806944055']
   for wid in old_ids:
    file=seed/'content/108600'/wid/'mods/example/mod.info';file.parent.mkdir(parents=True);file.write_text('id=example')
   jar=seed/'content/108600/3619862853/mods/ZombieBuddy/libs/ZombieBuddy.jar';jar.parent.mkdir(parents=True)
   with zipfile.ZipFile(jar,'w')as z:
    z.writestr('me/zed_0xff/zombie_buddy/Callbacks.class',b'fixture, not runtime')
    z.writestr('META-INF/MANIFEST.MF','Premain-Class: me.zed_0xff.zombie_buddy.Agent')
   def docker(cmd,**kw):
    if cmd[:2]==['docker','inspect']:return subprocess.CompletedProcess(cmd,0,stdout='false')
    if cmd[:2]==['docker','run']:
     target=next(p for p in (root/'mod-snapshots').iterdir() if p.name!=marker)
     self.assertEqual(json.loads((target/'request.json').read_text()),['3810674933','3785397275'])
     cache=target/'workshop'
     self.assertEqual((cache/'appworkshop_108600.acf').read_text(),'retained fixture manifest')
     for wid in ['3810674933','3785397275']:
      file=cache/'content/108600'/wid/'mods/example/mod.info';file.parent.mkdir(parents=True);file.write_text('id=example')
    return subprocess.CompletedProcess(cmd,0)
   with patch.object(scanctl,'STORE',root),patch.object(scanctl,'slot',side_effect=lambda name:root/'worlds'/name),patch.object(workshopctl.subprocess,'run',side_effect=docker):
    workshopctl.run(argparse.Namespace(world='walking_dead',yes=True))
   self.assertEqual((seed/'appworkshop_108600.acf').read_text(),'retained fixture manifest')

 def test_spawn_generator_is_python_syntax_and_has_only_hideout(self):
  compile(walkingdeadctl.SPAWNS,'spawn-preparation','exec')
  self.assertIn("'name':'Hideout'",walkingdeadctl.SPAWNS)
  self.assertIn('Map=ExtractionMap;Muldraugh, KY',walkingdeadctl.SPAWNS)

if __name__=='__main__':unittest.main()
