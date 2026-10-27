import copy,unittest
from village_cell_containment import ready_resident
class CellContainmentTests(unittest.TestCase):
 def setUp(self):self.v=dict(uuid='a',type='minecraft:villager',alive=True,is_baby=False,health=20,bounds={'min':[.2,64,.2],'max':[.8,65.95,.8]})
 def test_exact_single_adult_is_ready(self):self.assertEqual(ready_resident([self.v],{'a'},0,0,3)['uuid'],'a')
 def test_two_residents_or_neighbour_at_front_never_seal(self):
  self.assertIsNone(ready_resident([self.v,{**self.v,'uuid':'b'}],{'a','b'},0,0,3))
 def test_actual_body_at_front_cannot_be_sealed_even_when_centre_inside(self):
  v=copy.deepcopy(self.v);v['bounds']['max'][2]=3.01;self.assertIsNone(ready_resident([v],{'a'},0,0,3))
 def test_unknown_baby_injured_or_unmeasured_resident_is_rejected(self):
  for changes in ({'uuid':'other'},{'is_baby':True},{'health':19},{'alive':False},{'bounds':{}}, {'bounds':{'min':[.2,64,.2],'max':[float('nan'),66,.8]}}):
   self.assertIsNone(ready_resident([{**self.v,**changes}],{'a'},0,0,3))
 def test_an_item_is_not_a_second_resident(self):self.assertIsNotNone(ready_resident([self.v,{'type':'minecraft:item'}],{'a'},0,0,3))
if __name__=='__main__':unittest.main()
