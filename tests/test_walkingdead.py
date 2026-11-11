import json, re, subprocess, sys, tempfile, unittest
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
 def test_spawn_generator_is_python_syntax_and_has_only_hideout(self):
  compile(walkingdeadctl.SPAWNS,'spawn-preparation','exec')
  self.assertIn("'name':'Hideout'",walkingdeadctl.SPAWNS)
  self.assertIn('Map=ExtractionMap;Muldraugh, KY',walkingdeadctl.SPAWNS)

if __name__=='__main__':unittest.main()
