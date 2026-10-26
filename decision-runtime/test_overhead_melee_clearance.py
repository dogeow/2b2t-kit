import unittest
from overhead_melee_clearance import separated
class OverheadTest(unittest.TestCase):
 def mob(self,kind='creeper',pos=None):
  p=pos or [385.5,64,985.5]
  return {'type':'minecraft:'+kind,'alive':True,'hostile':True,'pos':p,'bounds':{'max':[p[0]+.3,p[1]+(.9 if kind=='spider' else 1.7),p[2]+.3]}}
 def test_unreachable_melee_can_remain_recorded_for_high_work(self):
  self.assertTrue(separated([self.mob(),self.mob('spider',[378.7,65,990.8])],[[394.5,74.1,990.5],[396,74.1,992]]))
 def test_ranged_close_or_insufficient_height_and_unknown_data_block_work(self):
  for mob,pose in [(self.mob('skeleton'),[394.5,74.1,990.5]),(self.mob('bogged'),[394.5,74.1,990.5]),(self.mob(),[385.5,74.1,985.5]),(self.mob('spider'),[394.5,72.1,990.5]),({},[394.5,74.1,990.5])]:
   self.assertFalse(separated([mob],[pose]))
  self.assertFalse(separated([self.mob()],[]))
  self.assertFalse(separated([self.mob()],[[394.5,float('nan'),990.5]]))

 def test_high_melee_zombie_does_not_become_a_ranged_threat(self):
  self.assertTrue(separated([self.mob('zombie',[396,62,992])],[[396,74.1,992]]))
  self.assertFalse(separated([self.mob('zombie',[396,66,992])],[[396,74.1,992]]))
  self.assertFalse(separated([self.mob('drowned',[396,62,992])],[[396,74.1,992]]))

 def test_distant_creeper_is_outside_blast_range_even_on_higher_terrain(self):
  self.assertTrue(separated([self.mob('creeper',[373.46,70,996.38])],[[396,74.1,992]]))
  self.assertFalse(separated([self.mob('creeper',[390,70,992])],[[396,74.1,992]]))

 def test_distant_slime_is_retained_and_close_slime_blocks_low_work(self):
  self.assertTrue(separated([self.mob('slime',[20,64,0])],[[.5,64.1,.5]]))
  self.assertFalse(separated([self.mob('slime',[6,64,0])],[[.5,64.1,.5]]))
