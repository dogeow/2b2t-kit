import unittest
from renewable_cane import suitable,harvest_targets,single_block_harvest_order

def row(p,name,**kw):return dict(pos=p,state='Block{'+name+'}',**kw)
class RenewableCaneTest(unittest.TestCase):
 def setUp(self):self.rows=[row([0,62,0],'minecraft:dirt',solid=True,fluid=False,block_entity=False),row([1,62,0],'minecraft:water',fluid=True)]
 def test_requires_water_at_the_support_level(self):
  self.assertTrue(suitable(self.rows,[0,63,0]));self.rows[1]['pos'][1]=63;self.assertFalse(suitable(self.rows,[0,63,0]))
 def test_never_replaces_crops_or_containers(self):
  for name in ['minecraft:wheat','minecraft:chest','minecraft:short_grass']:
   self.assertFalse(suitable(self.rows+[row([0,63,0],name)],[0,63,0]))
  self.rows[0]['block_entity']=True;self.assertFalse(suitable(self.rows,[0,63,0]))
 def test_requires_three_air_cells(self):self.assertFalse(suitable(self.rows+[row([0,65,0],'minecraft:stone')],[0,63,0]))
 def test_harvest_leaves_roots_and_ignores_unregistered_stalks(self):
  rows=[row([0,y,0],'minecraft:sugar_cane')for y in [63,64,65]]+[row([2,63,0],'minecraft:sugar_cane'),row([2,64,0],'minecraft:sugar_cane')]
  self.assertEqual([[0,64,0]],harvest_targets(rows,[[0,63,0]]));self.assertEqual([],harvest_targets(rows,[[3,63,0]]))
 def test_single_drop_collection_breaks_top_first_and_keeps_root(self):
  rows=[row([0,y,0],'minecraft:sugar_cane')for y in [63,64,65]]
  self.assertEqual([[0,65,0],[0,64,0]],single_block_harvest_order(rows,[[0,63,0]]))
 def test_single_drop_order_refuses_taller_artificial_stack_or_missing_root(self):
  rows=[row([0,y,0],'minecraft:sugar_cane')for y in [63,64,65,66]]
  self.assertEqual([],single_block_harvest_order(rows,[[0,63,0]]));self.assertEqual([],single_block_harvest_order(rows[1:],[[0,63,0]]))
 def test_lone_root_is_not_harvested(self):self.assertEqual([],harvest_targets([row([0,63,0],'minecraft:sugar_cane')],[[0,63,0]]))
if __name__=='__main__':unittest.main()
