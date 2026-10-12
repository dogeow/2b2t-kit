import unittest
from owned_placement_repair import observed_errors,recover_drops,repair
from unittest.mock import patch

class Tests(unittest.TestCase):
 def test_two_distant_drops_are_collected_before_leaving_each_site(self):
  from pathlib import Path
  errors=[{'pos':[x,64,0],'expected':'Block{minecraft:black_concrete}','wrong_state':'Block{minecraft:tuff}'}for x in(0,25)]
  class Client:
   root=Path('/tmp');world='w'
   def __init__(self):self.pos=[0,66,0];self.stock=3;self.drops={};self.removed=[]
   def status(self):
    return{'pos':self.pos,'inventory':[{'slot':0,'item':'minecraft:tuff','count':self.stock}],
     'entities':[{'uuid':k,'type':'minecraft:item','pos':p,'stack':{'item':'minecraft:tuff','count':1}}
                 for k,p in self.drops.items()if abs(p[0]-self.pos[0])<8]}
   def checked(self,op,**args):
    if op=='mine_block':
     p=args['pos'];self.removed.append(p);self.drops[str(p)]=p
    return{'phase':'done'}
   def request(self,op,**args):
    if op=='projection_audit':return{'projection_audit':{'placement_key':'same','mismatches':[
      {'pos':e['pos'],'expected':e['expected'],'actual':'Block{minecraft:air}'if e['pos']in self.removed else e['wrong_state'],
       'neighbors_loaded':True,'adjacent_fluid':False,'block_entity':False,'fluid':False}for e in errors]}}
    assert op=='scan';return{'world_session':'w','phase':'done','blocks':[]}
  c=Client()
  def approach(client,pos,*a,**k):client.pos=[pos[0],66,pos[2]];return'up'
  def collect(client,drop,**kwargs):del client.drops[drop['uuid']];client.stock+=1;return True
  with patch('owned_placement_repair.require_unlocked'),patch('owned_placement_repair.time.sleep'),\
       patch('owned_placement_repair.approach_faces',side_effect=approach),\
       patch('owned_placement_repair.collect_drop',side_effect=collect):
   r=repair(c,'same',errors,item='minecraft:tuff',tool='minecraft:diamond_pickaxe',faces=('up',))
  self.assertEqual(2,r['items_recovered']);self.assertEqual(5,c.stock);self.assertFalse(c.drops)

 def test_stone_repair_uses_pickaxe_and_top_access_and_rejects_unknown_empty_read(self):
  from pathlib import Path
  error={'pos':[18,69,33],'expected':'Block{minecraft:black_concrete}','wrong_state':'Block{minecraft:tuff}'}
  class Client:
   world='w';root=Path('/tmp');bad=False;removed=False;actions=[]
   def status(self):return{'inventory':[{'slot':0,'item':'minecraft:tuff','count':3+int(self.removed)}],'entities':[]}
   def checked(self,op,**args):
    self.actions.append((op,args))
    if op=='mine_block':self.removed=True
    return{'phase':'done'}
   def request(self,op,**args):
    if op=='projection_audit':return{'projection_audit':{'placement_key':'same','mismatches':[{
      'pos':error['pos'],'expected':error['expected'],'actual':error['wrong_state'],
      'neighbors_loaded':True,'adjacent_fluid':False,'block_entity':False,'fluid':False}]}}
    assert op=='scan';return{'world_session':'w','phase':'error'if self.bad else'done','blocks':[]}
  for bad in(False,True):
   c=Client();c.actions=[];c.bad=bad
   with patch('owned_placement_repair.require_unlocked'),patch('owned_placement_repair.time.sleep'),\
        patch('owned_placement_repair.approach_faces',return_value='up')as access:
    if bad:
     with self.assertRaisesRegex(RuntimeError,'not observed'):repair(c,'same',[error],item='minecraft:tuff',tool='minecraft:diamond_pickaxe',faces=('up',))
    else:
     self.assertEqual(1,repair(c,'same',[error],item='minecraft:tuff',tool='minecraft:diamond_pickaxe',faces=('up',))['items_recovered'])
   self.assertEqual(('select_item',{'item':'minecraft:diamond_pickaxe'}),c.actions[0]);self.assertEqual(('up',),access.call_args.args[3])
 def audit(self, actual, expected='Block{minecraft:barrel}[facing=west,open=false]'):
  return {'placement_key':'same','mismatches':[{'pos':[18,69,33],'actual':actual,'expected':expected}]}
 def test_only_newly_observed_wrong_blocks_are_repair_candidates(self):
  self.assertEqual(len(observed_errors(self.audit('Block{minecraft:air}'),self.audit('Block{minecraft:oak_planks}'),'Block{minecraft:oak_planks}')),1)
  self.assertFalse(observed_errors(self.audit('Block{minecraft:stone}'),self.audit('Block{minecraft:oak_planks}'),'Block{minecraft:oak_planks}'))
 def test_changed_design_or_placement_does_not_authorize_removal(self):
  self.assertFalse(observed_errors(self.audit('Block{minecraft:air}'),self.audit('Block{minecraft:oak_planks}','Block{minecraft:chest}'),'Block{minecraft:oak_planks}'))
  after=self.audit('Block{minecraft:oak_planks}');after['placement_key']='new'
  with self.assertRaises(ValueError):observed_errors(self.audit('Block{minecraft:air}'),after,'Block{minecraft:oak_planks}')
 def test_a_later_session_collects_prior_drops_even_without_new_mining(self):
  class Client:
   picked=False;calls=0
   def status(self):
    return {'pos':[17,67,34],'inventory':[{'slot':0,'item':'minecraft:oak_planks','count':14 if self.picked else 8}],
            'entities':[] if self.picked else [{'uuid':'drop','type':'minecraft:item','pos':[18,69,34],'stack':{'item':'minecraft:oak_planks','count':6}}]}
   def request(self,op,**args):
    assert op=='collect_item' and args['expected_uuid']=='drop' and args['expected_count']==6
    self.picked=True;self.calls+=1;return {'phase':'done'}
  c=Client()
  with patch('owned_placement_repair.time.sleep'):
   self.assertTrue(recover_drops(c,'minecraft:oak_planks',8,0,[[18,69,33]]))
  self.assertEqual(c.calls,1)

if __name__=='__main__':unittest.main()
