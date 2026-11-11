import argparse,datetime,hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'story'))
import alifectl,scanctl,livectl,adminmode,workshopctl
class InstallTests(unittest.TestCase):
 def test_profile_has_exact_alife_identity_and_no_conflicting_processors(self):
  body=(ROOT/'config/mods.alife.env').read_text()
  self.assertIn('3803984183',body);self.assertIn('ProjectALifeNPCs',body)
  self.assertNotIn('ZomboidForge',body);self.assertNotIn('TLOU_',body);self.assertNotIn('SiegerRadio',body)
 def test_stopped_install_and_failed_download_preserve_previous_config(self):
  self.install(False)
 def test_success_changes_profile_and_disables_radio_without_touching_save(self):
  self.install(True)
 def install(self,success):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);slot=root/'worlds/story_test';(slot/'data').mkdir(parents=True);(slot/'story').mkdir()
   (slot/'data/keep.bin').write_bytes(b'save sentinel')
   (slot/'profile').write_text('mp-test\n');(slot/'mods.env').write_bytes((ROOT/'config/mods.mp-test.env').read_bytes())
   (slot/'story/radio.enabled').write_text('on\n');(slot/'workshop-snapshot').write_text('old-snapshot\n')
   backups=root/'backups/worlds/story_test';backups.mkdir(parents=True)
   b=backups/'world-fixture.tar.gz';b.write_bytes(b'fixture');Path(str(b)+'.sha256').write_text(hashlib.sha256(b.read_bytes()).hexdigest()+'  '+b.name+'\n')
   info={'State':{'Running':True,'FinishedAt':'2026-01-01T00:00:00Z'},'Mounts':[{'Destination':'/root/Zomboid','Source':str(slot/'data')}]}
   def inspect(*a,**kw):return subprocess.CompletedProcess([],0,stdout=json.dumps([info]))
   def download(a):
    self.assertEqual((slot/'profile').read_text(),'alife\n');self.assertFalse((slot/'story/radio.enabled').exists())
    if not success:raise ValueError('download failed')
    (slot/'workshop-snapshot').write_text('new-snapshot\n')
    p=root/'mod-snapshots/new-snapshot/workshop/content/108600/3803984183/mods/ProjectALifeNPCs/42.20/mod.info';p.parent.mkdir(parents=True);p.write_text('id=ProjectALifeNPCs\nmodversion=1.5.1\n')
    j=root/'mod-snapshots/new-snapshot/workshop/content/108600/3806944055/mods/ProjectALifeJimmy/42/mod.info';j.parent.mkdir(parents=True);j.write_text('id=ProjectALifeJimmy\nrequire=\\ProjectALifeNPCs\nmodversion=0.8.0\n')
   a=argparse.Namespace(world='story_test',yes=True)
   with patch.object(scanctl,'slot',return_value=slot),patch.object(scanctl,'STORE',root),patch.object(scanctl,'active_world',return_value='story_test'),patch.object(livectl,'STORE',root),patch.object(adminmode,'disabled',return_value=True),patch.object(alifectl.subprocess,'run',side_effect=inspect),patch.object(workshopctl,'run',side_effect=download):
    with self.assertRaisesRegex(ValueError,'Stop game'):alifectl.run(a)
    info['State']['Running']=False
    if success:alifectl.run(a)
    else:
     with self.assertRaisesRegex(ValueError,'download failed'):alifectl.run(a)
   self.assertEqual((slot/'data/keep.bin').read_bytes(),b'save sentinel')
   self.assertEqual((slot/'profile').read_text(),'alife\n'if success else'mp-test\n')
   self.assertEqual((slot/'workshop-snapshot').read_text(),'new-snapshot\n'if success else'old-snapshot\n')
   self.assertEqual((slot/'story/radio.enabled').exists(),not success)
if __name__=='__main__':unittest.main()
