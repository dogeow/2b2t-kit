import copy,unittest
from village_fence_barrier import prepare

class Tests(unittest.TestCase):
 def fixture(self):
  rows={(x,66,15):{'state':'Block{minecraft:dark_oak_planks}'}for x in (-1,1)}
  v={'uuid':'v','type':'minecraft:villager','health':20,'is_baby':False,'bounds':{'min':[.2,65.5,14.4],'max':[.8,67.45,15.05]}}
  return rows,[v]
 def test_a_villager_overlapping_only_the_empty_part_of_the_cell_is_clear(self):
  rows,entities=self.fixture();r=prepare(rows,entities,[0,66,15],'v')
  self.assertGreater(entities[0]['bounds']['max'][2],15)
  self.assertEqual(15.375,r['collision_proxy']['min'][2])
 def test_real_shape_collision_or_wrong_side_is_rejected(self):
  for maximum in (15.4,16.9):
   rows,entities=self.fixture();entities[0]['bounds']['max'][2]=maximum
   with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v')
 def test_north_room_requires_resident_on_the_other_side(self):
  rows,entities=self.fixture();entities[0]['bounds']['min'][2]=15.9;entities[0]['bounds']['max'][2]=16.5
  prepare(rows,entities,[0,66,15],'v',inward=-1)
  with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v',inward=1)
 def test_unknown_connections_missing_wall_and_existing_block_are_rejected(self):
  for key in ((0,66,14),(0,66,16),(0,66,15),(-1,66,15)):
   rows,entities=self.fixture();rows[key]={'state':'Block{minecraft:stone}'}
   with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v')
 def test_rear_piston_extends_conservative_shape_and_expected_connection(self):
  rows,entities=self.fixture();rows[(0,66,16)]={'state':'Block{minecraft:piston}[extended=false,facing=north]'}
  r=prepare(rows,entities,[0,66,15],'v',rear_piston=True)
  self.assertEqual(16,r['collision_proxy']['max'][2]);self.assertEqual('true',r['expected_properties']['south'])
  with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v')
  for state in ('Block{minecraft:piston}[extended=true,facing=north]','Block{minecraft:piston}[extended=false,facing=south]','Block{minecraft:stone}'):
   rows[(0,66,16)]['state']=state
   with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v',rear_piston=True)
 def test_other_entities_and_unhealthy_or_missing_resident_are_protected(self):
  rows,entities=self.fixture();other=copy.deepcopy(entities[0]);other['uuid']='other';other['bounds']['min'][2]=15.4;other['bounds']['max'][2]=16
  with self.assertRaises(ValueError):prepare(rows,entities+[other],[0,66,15],'v')
  for mutation in ({'health':19},{'is_baby':True},{'uuid':'missing'}):
   rows,entities=self.fixture();entities[0].update(mutation)
   with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v')

if __name__=='__main__':unittest.main()
