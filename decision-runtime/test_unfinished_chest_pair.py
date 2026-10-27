import unittest,copy
from village_projection import unfinished_chest_pair
class ChestPairTests(unittest.TestCase):
 def fixture(self):
  left='Block{minecraft:chest}[facing=east,type=left,waterlogged=false]';right=left.replace('type=left','type=right');single=left.replace('type=left','type=single');r=dict(pos=[0,0,0],kind='state_only',expected=left,actual=single);table=dict(expected=[dict(pos=[0,0,0],state=left),dict(pos=[0,0,1],state=right)]);m=[r,dict(pos=[0,0,1],kind='missing',actual='Block{minecraft:air}')];return r,table,m
 def test_only_a_known_single_chest_with_the_exact_missing_partner_is_admitted(self):
  r,t,m=self.fixture();self.assertTrue(unfinished_chest_pair(r,t,m))
  for kind in ['facing','water','present','wrong_partner','not_single','foreign_block']:
   r,t,m=self.fixture()
   if kind=='facing':r['actual']=r['actual'].replace('east','west')
   if kind=='water':r['actual']=r['actual'].replace('false','true')
   if kind=='present':m[1]['kind']='state_only'
   if kind=='wrong_partner':t['expected'][1]['state']=t['expected'][1]['state'].replace('right','left')
   if kind=='not_single':r['actual']=r['actual'].replace('single','right')
   if kind=='foreign_block':r['actual']='Block{minecraft:barrel}[facing=east,open=false]'
   with self.subTest(kind=kind):self.assertFalse(unfinished_chest_pair(r,t,m))
if __name__=='__main__':unittest.main()
