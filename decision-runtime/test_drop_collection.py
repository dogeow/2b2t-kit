import copy,unittest
from unittest.mock import patch
from drop_collection import collect_drop
DROP={'type':'minecraft:item','uuid':'same','pos':[1,2,3],'stack':{'item':'minecraft:cobblestone','count':1}}
class Tests(unittest.TestCase):
 def test_stack_merge_refreshes_count_before_any_collection_started(self):
  class C:
   count=1;taken=0;requests=[]
   def status(self):
    d=copy.deepcopy(DROP);d['stack']['count']=self.count
    return {'inventory':[{'slot':0,'item':'minecraft:cobblestone','count':self.taken}], 'entities':[d] if not self.taken else []}
   def request(self,op,**args):
    self.requests.append(args)
    if len(self.requests)==1:self.count=2;return {'phase':'error','detail':'Drop identity or stack changed'}
    self.taken=2;return {'phase':'done'}
  c=C()
  with patch('drop_collection.time.sleep'):self.assertTrue(collect_drop(c,DROP,observation=c.status()))
  self.assertEqual([r['expected_count'] for r in c.requests],[1,2]);self.assertEqual(c.taken,2)
 def test_retired_uuid_can_reselect_a_recent_nearby_ordinary_material_stack(self):
  class C:
   old=True;calls=[]
   def status(self):
    d=copy.deepcopy(DROP)
    if not self.old:d['uuid']='merged';d['stack']['count']=3
    return {'time':1000,'inventory':[],'entities':[d]}
   def request(self,op,**args):
    self.calls.append(args)
    if self.old:self.old=False;return {'phase':'error','detail':'Drop is no longer loaded; observe again'}
    return {'phase':'done'}
  c=C()
  with patch('drop_collection.time.sleep'):self.assertTrue(collect_drop(c,DROP,observation=c.status()))
  self.assertEqual([v['expected_uuid'] for v in c.calls],['same','merged']);self.assertEqual(c.calls[-1]['expected_count'],3)
 def test_white_concrete_merge_refreshes_to_new_uuid_with_exact_count(self):
  original=copy.deepcopy(DROP);original['stack']['item']='minecraft:white_concrete'
  class C:
   old=True;calls=[]
   def status(self):
    d=copy.deepcopy(original)
    if not self.old:d['uuid']='merged';d['stack']['count']=2
    return {'time':1000,'inventory':[],'entities':[d]}
   def request(self,op,**args):
    self.calls.append(args)
    if self.old:self.old=False;return {'phase':'error','detail':'Drop is no longer loaded; observe again'}
    return {'phase':'done'}
  c=C()
  with patch('drop_collection.time.sleep'):self.assertTrue(collect_drop(c,original,observation=c.status()))
  self.assertEqual([v['expected_uuid'] for v in c.calls],['same','merged'])
 def test_unconfirmed_movement_is_never_replayed(self):
  class C:
   calls=0
   def status(self):return {'inventory':[],'entities':[DROP]}
   def request(self,*a,**k):self.calls+=1;return {'phase':'waiting','detail':'Drop disappeared without inventory confirmation'}
  c=C();self.assertFalse(collect_drop(c,DROP));self.assertEqual(c.calls,1)
 def test_already_collected_requires_actual_inventory_gain(self):
  class C:
   def status(self):return {'inventory':[{'slot':0,'item':'minecraft:cobblestone','count':1}], 'entities':[]}
   def request(self,*a,**k):raise AssertionError('No click should be needed')
  self.assertTrue(collect_drop(C(),DROP,observation={'inventory':[]}))
if __name__=='__main__':unittest.main()
