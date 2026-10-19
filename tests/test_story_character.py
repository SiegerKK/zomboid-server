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
 def test_server_owned_inventory_contract(self):
  client=(ROOT/"mods/SiegerAdmin/42/media/lua/client/SiegerStoryCharacterClient.lua").read_text()
  server=(ROOT/"story/runtime/SiegerStoryCharacter.lua").read_text()
  for forbidden in ("instanceItem(",":AddItem(","SyncXp(","sendPlayerStatsChange(","setPerkLevelDebug(","setScratched("):
   self.assertNotIn(forbidden,client)
  self.assertIn("sendAddItemToContainer(inv,placed)",server)
  self.assertIn('journal(req,"server_mutation_started"',server)
  self.assertIn('firstLine("SiegerInventoryRepair-"',server)
  self.assertIn('player:getUsername()~=req.username',server)
  self.assertIn('legacy_apply_disabled',server)
  for forbidden in ("loadstring(","setGodMod(","setAccessLevel(","SetInfected(false"):
   self.assertNotIn(forbidden,client+server)
 def test_cli_repair_preview_and_legacy_block(self):
  import subprocess
  script=ROOT/"story/characterctl.py"
  result=subprocess.run([sys.executable,str(script),"repair","story_test","example","--profile","joel-arrival-v1","--item","Base.308Bullets"],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr);self.assertIn("PREVIEW ONLY",result.stdout)
  result=subprocess.run([sys.executable,str(script),"apply","story_test","example","--profile","joel-arrival-v1","--yes"],capture_output=True,text=True)
  self.assertNotEqual(result.returncode,0);self.assertIn("disabled",result.stderr)

if __name__=="__main__":unittest.main()
