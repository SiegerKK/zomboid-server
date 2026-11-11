import importlib.util,sys,unittest
from pathlib import Path
from unittest.mock import patch,mock_open
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('manual_deploy',ROOT/'ops/pz-codex-deploy.py')
deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)
class ManualTests(unittest.TestCase):
 def test_manual_mode_still_rejects_running_game_before_ci_or_checkout(self):
  for flags in (['--yes'],['--yes','--manual-reviewed']):
   with patch.object(deploy.os,'geteuid',return_value=0),patch.dict(deploy.os.environ,{'SUDO_USER':'codex-pz'}),patch.object(sys,'argv',['deploy','a'*40,*flags]),patch('builtins.open',mock_open()),patch.object(deploy.fcntl,'flock'),patch.object(deploy,'run',return_value='true')as run,patch.object(deploy.urllib.request,'urlopen')as request:
    with self.assertRaisesRegex(ValueError,'Game is running'):deploy.main()
    self.assertEqual(run.call_count,1);request.assert_not_called()
 def test_invalid_flags_never_reach_privileged_checks(self):
  with patch.object(deploy.os,'geteuid',return_value=0),patch.dict(deploy.os.environ,{'SUDO_USER':'codex-pz'}),patch.object(sys,'argv',['deploy','a'*40,'--manual-reviewed']),patch.object(deploy,'run')as run:
   with self.assertRaisesRegex(ValueError,'Usage'):deploy.main()
   run.assert_not_called()
if __name__=='__main__':unittest.main()
