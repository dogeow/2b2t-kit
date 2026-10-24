from copy import deepcopy
from collections import Counter
from types import SimpleNamespace
import unittest
from test_librarian_reset_enclosure import ResetEnclosureTests
from service_opening import recover_pair,require_guard
class Stub:
 def __init__(self,ack=True):
  self.scene,_=ResetEnclosureTests().fixture();self.scene['world_session']='w';
  for row in self.scene['blocks']:row.setdefault('fluid',False)
  self.scene['scan_entities'][0]['alive']=True;self.q=SimpleNamespace(world='w');self.book={};self.calls=[];self.stock=Counter();self.hand='minecraft:diamond_pickaxe';self.ack=ack
  self.scene['blocks'] += [{'pos':[100,y,101],'state':'Block{'+item+'}','solid':True,'fluid':False,'block_entity':False}for y,item in [(65,'minecraft:cobblestone'),(66,'minecraft:cobbled_deepslate')]]
 def check(self):return {'inventory':[{'slot':i,'item':k,'count':v}for i,(k,v)in enumerate(self.stock.items())],'hand':{'item':self.hand}}
 def scan(self,*a):return deepcopy(self.scene),{tuple(r['pos']):r for r in self.scene['blocks']}
 def save(self):pass
 def n(self,op,**p):
  self.calls.append((op,p))
  if op=='select_item':self.hand=p['item'];return {}
  if op=='mine_block':
   row=next(r for r in self.scene['blocks']if r['pos']==p['pos']);self.stock[row['state'][6:-1]]+=1;self.scene['blocks'].remove(row);return {'id':str(len(self.calls)),'server_confirmed':self.ack,'native_sequence':len(self.calls),'server_ack_sequence':len(self.calls)if self.ack else-1}
class Tests(unittest.TestCase):
 def args(self):return ([{'pos':[100,65,101],'item':'minecraft:cobblestone'},{'pos':[100,66,101],'item':'minecraft:cobbled_deepslate'}],{'front':[100,65,100],'inward':-1,'depth':3,'uuid':'keeper'})
 def test_two_acknowledged_distinct_mines_and_materials_before_completion(self):
  b=Stub();r=recover_pair(b,*self.args());self.assertFalse(r['pending']);self.assertEqual(2,len(r['mines']));self.assertEqual(1,b.stock['minecraft:cobblestone']);self.assertEqual(1,b.stock['minecraft:cobbled_deepslate'])
 def test_missing_first_ack_never_sends_second_mine(self):
  b=Stub(ack=False)
  with self.assertRaises(RuntimeError):recover_pair(b,*self.args())
  self.assertEqual(1,sum(op=='mine_block'for op,p in b.calls));self.assertTrue(b.book['service_openings'][0]['pending'])
 def test_never_mine_the_retained_barrier_or_a_quarantined_cell(self):
  for protected,targets in [([[100,65,101]],self.args()[0]),([],[{'pos':[100,y,100],'item':'minecraft:cobblestone'}for y in (65,66)])]:
   b=Stub()
   with self.assertRaises(ValueError):recover_pair(b,targets,self.args()[1],protected)
   self.assertEqual([],b.calls)
 def test_open_retained_shell_blocks_all_mining(self):
  b=Stub();b.scene['blocks']=[r for r in b.scene['blocks']if r['pos']not in [[100,66,100],[100,67,100]]]
  with self.assertRaises(ValueError):recover_pair(b,*self.args())
  self.assertEqual([],b.calls)
 def test_containers_and_nonvertical_batches_are_refused(self):
  for target in ({'pos':[100,65,101],'item':'minecraft:chest'},{'pos':[101,65,101],'item':'minecraft:cobblestone'}):
   b=Stub();targets,guard=self.args();targets[0]=target
   with self.assertRaises(ValueError):recover_pair(b,targets,guard)
   self.assertEqual([],b.calls)
 def test_other_or_injured_resident_is_not_a_retained_guard(self):
  for key,value in [('uuid','other'),('health',19),('is_baby',True)]:
   b=Stub();b.scene['scan_entities'][0][key]=value
   with self.assertRaises(ValueError):recover_pair(b,*self.args())
   self.assertEqual([],b.calls)
if __name__=='__main__':unittest.main()
