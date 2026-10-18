#!/usr/bin/env python3
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import radio_loudness_prepare as n
class LoudnessTests(unittest.TestCase):
 def test_common_target_respects_worst_true_peak_without_compressor(self):
  data={'quiet':{'input_i':-30,'input_tp':-15},'crest':{'input_i':-20,'input_tp':-1}}
  target=n.common_target(data)
  self.assertLessEqual(target,-20.5)
  for row in data.values():self.assertLessEqual(float(row['input_tp'])+target-float(row['input_i']),-1.5)
 def test_no_peak_constraint_never_boosts_target_above_preferred(self):
  self.assertLessEqual(n.common_target({'a':{'input_i':-10,'input_tp':0}}),-18)
if __name__=='__main__':unittest.main(verbosity=2)
