from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import math
from roof_double_completion import run
from roof_double_slab_plan import DOUBLE,SLAB

class NativeDouble:
 def __init__(self,half=False,extra=False,no_update=False):
  self.client=self;self.pos=[1.5,74.1,.5];self.stock=5;self.t=0;self.calls=[];self.extra=extra;self.no_update=no_update;self.rows={(-1,72,0):{'pos':[-1,72,0],'state':SLAB,'fluid':False,'block_entity':False}}
  if half:self.rows[(0,72,0)]={'pos':[0,72,0],'state':SLAB,'fluid':False,'block_entity':False}
 def check(self):return {'world_session':'world','health':20,'pos':self.pos,'inventory':[{'slot':0,'item':'minecraft:cobblestone_slab','count':self.stock}]}
 def n(self,op,**kw):
  self.calls.append((op,kw));self.t+=1
  if op=='scan':
   lo,hi=kw['min'],kw['max'];total=math.prod(b-a+1 for a,b in zip(lo,hi));return {**self.check(),'id':str(self.t),'phase':'done','time':self.t,'scan_cells_read':total,'scan_total_cells':total,'scan_start_revision':1,'scan_end_revision':1,'blocks':[dict(v)for p,v in self.rows.items()if all(a<=n<=b for a,n,b in zip(lo,p,hi))]}
  if op=='navigate':self.pos=kw['target']
  if op=='interact'and not self.no_update:
   state=SLAB if tuple(kw['pos'])==(-1,72,0)else DOUBLE;self.rows[(0,72,0)]={'pos':[0,72,0],'state':state,'fluid':False,'block_entity':False};self.stock-=1
   if self.extra and state==DOUBLE:self.rows[(-1,72,0)]['state']=DOUBLE
  return {'phase':'done','id':str(self.t)}

class DoubleCompletionExecutionTest(TestCase):
 model={'placement_key':'model','expected':[{'pos':[-1,72,0],'state':SLAB},{'pos':[0,72,0],'state':DOUBLE}]}
 def execute(self,b,path,protected=()):return run(b,self.model,path,low=[-3,70,-2],high=[3,83,2],protected=protected,limit=1)
 def test_air_target_uses_exact_nonreserved_support_then_self(self):
  with TemporaryDirectory()as d:
   b=NativeDouble();r=self.execute(b,Path(d)/'proof');uses=[p for op,p in b.calls if op=='interact'];self.assertEqual([[-1,72,0],[0,72,0]],[x['pos']for x in uses]);self.assertEqual(['east','up'],[x['face']for x in uses]);self.assertEqual(3,b.stock);self.assertEqual(1,r['verified_repairs'])
 def test_real_completed_double_support_stays_unchanged(self):
  with TemporaryDirectory()as d:
   from copy import deepcopy
   b=NativeDouble();b.rows[(-1,72,0)]['state']=DOUBLE;self.model=deepcopy(self.model);self.model['expected'][0]['state']=DOUBLE;r=self.execute(b,Path(d)/'proof');self.assertEqual(1,r['verified_repairs']);self.assertEqual(DOUBLE,b.rows[(-1,72,0)]['state']);self.assertEqual(3,b.stock)
 def test_existing_half_only_gets_the_new_merge_use(self):
  with TemporaryDirectory()as d:
   b=NativeDouble(half=True);r=self.execute(b,Path(d)/'proof');self.assertEqual(1,len([op for op,p in b.calls if op=='interact']));self.assertEqual(4,b.stock);self.assertEqual(1,r['verified_repairs'])
 def test_pending_target_or_only_support_is_never_interacted_with(self):
  for protected in [[[0,72,0]],[[-1,72,0]]]:
   with TemporaryDirectory()as d:
    b=NativeDouble();r=self.execute(b,Path(d)/'proof',protected);self.assertEqual(0,r['verified_repairs']);self.assertNotIn('interact',[op for op,p in b.calls])
 def test_unconfirmed_use_is_not_sent_again(self):
  with TemporaryDirectory()as d:
   b=NativeDouble(no_update=True)
   with patch('roof_double_completion.time.monotonic',side_effect=[0,10]):
    with self.assertRaisesRegex(RuntimeError,'without replay'):self.execute(b,Path(d)/'proof')
   self.assertEqual(1,len([op for op,p in b.calls if op=='interact']))
 def test_extra_anchor_mutation_is_not_counted_as_completed(self):
  with TemporaryDirectory()as d:
   b=NativeDouble(extra=True)
   with self.assertRaisesRegex(RuntimeError,'surroundings'):self.execute(b,Path(d)/'proof')
   self.assertEqual(2,len([op for op,p in b.calls if op=='interact']))
