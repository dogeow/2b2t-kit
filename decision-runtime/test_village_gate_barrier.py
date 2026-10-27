import copy,unittest
from village_gate_barrier import prepare
class GateTests(unittest.TestCase):
 def fixture(self,opened=True):
  rows={(0,66,15):{'state':'Block{minecraft:acacia_fence_gate}[facing=south,in_wall=false,open='+str(opened).lower()+',powered=false]'}}
  v={'uuid':'v','type':'minecraft:villager','is_baby':False,'health':20,'bounds':{'min':[.2,65.5,14.4],'max':[.8,67.45,15.05]}}
  return rows,[v]
 def test_close_allows_only_empty_portion_of_cell_to_overlap(self):
  rows,entities=self.fixture();self.assertIn('open=false',prepare(rows,entities,[0,66,15],'v',opening=False)['after'])
 def test_body_in_real_gate_plane_cannot_be_closed_on(self):
  rows,entities=self.fixture();entities[0]['bounds']['max'][2]=15.4
  with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v',opening=False)
 def test_opening_clears_collision_even_if_body_is_in_gate(self):
  rows,entities=self.fixture(False);entities[0]['bounds']['max'][2]=16
  self.assertIn('open=true',prepare(rows,entities,[0,66,15],'v',opening=True)['after'])
 def test_no_repeated_toggle_when_already_in_requested_state(self):
  rows,entities=self.fixture()
  with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v',opening=True)
 def test_other_entity_is_protected(self):
  rows,entities=self.fixture();other=copy.deepcopy(entities[0]);other.update(uuid='other');other['bounds']['min'][2]=15.4;other['bounds']['max'][2]=16
  with self.assertRaises(ValueError):prepare(rows,entities+[other],[0,66,15],'v',opening=False)
 def test_wrong_axis_powered_gate_and_unhealthy_resident_rejected(self):
  for old,new in [('facing=south','facing=east'),('powered=false','powered=true'),('in_wall=false','in_wall=true')]:
   rows,entities=self.fixture();rows[(0,66,15)]['state']=rows[(0,66,15)]['state'].replace(old,new)
   with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v',opening=False)
  rows,entities=self.fixture();entities[0]['health']=19
  with self.assertRaises(ValueError):prepare(rows,entities,[0,66,15],'v',opening=False)
class ClosingTransitionTests(unittest.TestCase):
 def test_resident_moving_during_item_selection_prevents_interaction(self):
  from village_gate_barrier import toggle
  class Builder:
   def __init__(self):self.book={};self.scans=0;self.calls=[]
   def check(self):return {'pos':[.5,65.1,12.5]}
   def save(self):pass
   def scan(self,low,high):
    self.scans+=1;rows,entities=GateTests().fixture()
    if self.scans==2:entities[0]['bounds']['max'][2]=15.6
    return {'scan_entities':entities},rows
   def n(self,op,**params):self.calls.append(op);return {}
  b=Builder()
  with self.assertRaises(ValueError):toggle(b,[0,66,15],'v',opening=False)
  self.assertEqual(['select_item'],b.calls)
  self.assertFalse(b.book['trader_gate_operations'][0]['pending'])

if __name__=='__main__':unittest.main()
