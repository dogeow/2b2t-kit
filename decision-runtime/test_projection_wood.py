import unittest
from projection_wood import log_target,anchors,use_with_margin
from unittest.mock import patch
class WoodTest(unittest.TestCase):
 def row(self,actual='Block{minecraft:air}'):
  return {'pos':[2,3,4],'expected':'Block{minecraft:stripped_spruce_log}[axis=x]','actual':actual,'kind':'missing','fluid':False,'adjacent_fluid':False,'block_entity':False}
 def test_same_axis_raw_logs_can_be_stripped_but_wrong_axis_is_preserved(self):
  self.assertTrue(log_target(self.row('Block{minecraft:spruce_log}[axis=x]'))['strip'])
  self.assertIsNone(log_target(self.row('Block{minecraft:spruce_log}[axis=z]')))
 def test_only_axis_correct_non_container_support_is_used(self):
  rows=[{'pos':[1,3,4],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False},{'pos':[2,2,4],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False}]
  self.assertEqual([x[0] for x in anchors([2,3,4],'x',rows)],['east'])
  rows[0]['block_entity']=True;self.assertEqual(anchors([2,3,4],'x',rows),[])
 def test_fluid_or_existing_player_block_is_not_modified(self):
  r=self.row();r['adjacent_fluid']=True;self.assertIsNone(log_target(r));self.assertIsNone(log_target(self.row('Block{minecraft:oak_log}[axis=x]')))
 def test_only_known_pre_use_failure_gets_one_closer_attempt(self):
  class Client:
   calls=0
   def request(self,*a,**kw):
    self.calls+=1
    return {'phase':'error','detail':'Target interaction face is occluded or out of reach'} if self.calls==1 else {'phase':'done'}
  c=Client();checks=[]
  with patch('projection_wood.approach_faces',return_value='east') as approach:
   use_with_margin(c,[1,2,3],'Block{minecraft:stone}','minecraft:spruce_log',['east'],lambda:checks.append(True))
   self.assertEqual([v.kwargs['stand_distance'] for v in approach.call_args_list],[2.4,1.8])
  self.assertEqual(c.calls,2);self.assertEqual(len(checks),2)
 def test_uncertain_mutation_is_never_replayed(self):
  class Client:
   calls=0
   def request(self,*a,**kw):self.calls+=1;return {'phase':'waiting','detail':'server acknowledgement timed out'}
  c=Client()
  with patch('projection_wood.approach_faces',return_value='east'):
   with self.assertRaises(RuntimeError):use_with_margin(c,[1,2,3],'Block{minecraft:stone}','minecraft:spruce_log',['east'])
  self.assertEqual(c.calls,1)
if __name__=='__main__':unittest.main()
