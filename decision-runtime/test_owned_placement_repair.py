import unittest
from owned_placement_repair import observed_errors,recover_drops
from unittest.mock import patch

class Tests(unittest.TestCase):
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
