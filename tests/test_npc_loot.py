import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'story'))
from npclootctl import patch_condition
class NpcLootTests(unittest.TestCase):
 def test_only_weapon_condition_changes(self):
  old='SandboxVars = {\n ALife = {\n  Drops_WeaponCondition = 1,\n  Drops_WeaponChance = 5,\n  Raid_MinDay = 14,\n },\n Other = { value = 8, },\n}\n'
  new,value=patch_condition(old)
  self.assertEqual(value,1);self.assertEqual(new,old.replace('Drops_WeaponCondition = 1','Drops_WeaponCondition = 8'))
  self.assertEqual(patch_condition(new),(new,8))
 def test_absent_key_added_inside_existing_block(self):
  s='SandboxVars = {\n ALife = {\n  Raid_MinDay = 14,\n },\n}\n'
  new,old=patch_condition(s);self.assertIsNone(old);self.assertIn('Drops_WeaponCondition = 8,',new);self.assertIn('Raid_MinDay = 14,',new)
 def test_ambiguous_or_missing_block_rejected(self):
  for s in ['SandboxVars = {}',' ALife = {\n Drops_WeaponCondition = 1,\n Drops_WeaponCondition = 2,\n }']:
   with self.assertRaises(ValueError):patch_condition(s)
if __name__=='__main__':unittest.main()
