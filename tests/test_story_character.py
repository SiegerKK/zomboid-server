#!/usr/bin/env python3
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"story"))
import characterctl
class CharacterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  patcher=patch.object(characterctl.scanctl,"lua_dir",return_value=Path(self.tmp.name));patcher.start();self.addCleanup(patcher.stop)
 def test_receipt_must_match_exact_target_and_request(self):
  rid="1"*32;request=["v1",rid,"story_test","owner","joel-arrival-v1"]
  with patch.object(characterctl,"read",side_effect=[request,request+["waiting","client_ack_required"]]):
   self.assertEqual(characterctl.status("story_test")["status"],"waiting")
  with patch.object(characterctl,"read",side_effect=[request,["v1","2"*32]+request[2:]+["complete","client_applied"]]):
   self.assertEqual(characterctl.status("story_test")["status"],"pending")
  with patch.object(characterctl,"read",side_effect=[request,request+["complete","client_applied"]]):
   self.assertEqual(characterctl.status("story_test")["status"],"complete")
 def test_symlink_and_oversize_refused(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);target=root/"target";target.write_text("x"*513)
   with patch.object(characterctl.scanctl,"lua_dir",return_value=root):
    (root/characterctl.REQ).symlink_to(target)
    with self.assertRaises(ValueError):characterctl.read("story_test",characterctl.REQ)
    with self.assertRaises(ValueError):characterctl.read("story_test","target")
 def test_b42_stats_and_profile_safety_contract(self):
  client=(ROOT/"mods/SiegerRadio/42/media/lua/client/SiegerStoryCharacterClient.lua").read_text()
  server=(ROOT/"story/runtime/SiegerStoryCharacter.lua").read_text()
  self.assertNotIn("SyncXp(",client)
  self.assertNotIn("sendPlayerStatsChange(",client)
  self.assertIn("addXpNoMultiplier(player,Perks.Strength,0)",server)
  self.assertNotIn("ai:updateXpChecker()",server)
  self.assertIn('pending.phase="server_commit"',server)
  self.assertIn("setScratched(true,true)",client)
  self.assertIn("stats:get(CharacterStat[name])",client)
  self.assertIn('md.SiegerCharacterProfile={id=args.id,state="error"}',client)
  self.assertIn('read(GUARD)==req.id',server)
  self.assertIn('player:getUsername()~=pending.username',server)
  for term in ("loadstring(","setGodMod(","setAccessLevel(","SetInfected(false"):
   self.assertNotIn(term,client+server)
if __name__=="__main__":unittest.main()
