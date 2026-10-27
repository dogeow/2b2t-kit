import unittest
from copy import deepcopy
from village_enchantment_plan import bind_required_books

class EnchantmentPlanTest(unittest.TestCase):
 def fixture(self):
  layout={'slots':[{'id':'A','occupant_uuid':'locked','trade_verified':True,'role':{'kind':'librarian','block':'minecraft:lectern'}},{'id':'B','occupant_uuid':'b','role':{'kind':'librarian','enchantment':'minecraft:feather_falling','level':4}},{'id':'C','occupant_uuid':None,'role':{'kind':'armorer','block':'minecraft:blast_furnace'}}],'outside':'preserved'}
  return layout,{'minecraft:sweeping_edge':3,'minecraft:mending':1,'minecraft:unbreaking':3},{'minecraft:sweeping_edge':{'level':3,'villager_uuid':'locked','proof':'actual.json'}}
 def test_excluded_book_and_profession_placeholder_become_missing_maximum_books(self):
  l,t,k=self.fixture();old=deepcopy(l);result,changes=bind_required_books(l,t,k);self.assertEqual(l,old);self.assertEqual({r['role']['enchantment']:r['role']['level']for r in result['slots']},t);self.assertEqual(result['slots'][0]['role']['enchantment'],'minecraft:sweeping_edge');self.assertTrue(result['slots'][0]['trade_verified']);self.assertNotIn('trade_verified',result['slots'][1]);self.assertEqual(result['outside'],'preserved');self.assertEqual(len(changes),3)
 def test_valid_original_priority_is_preserved_and_locked_type_not_duplicated(self):
  l,t,k=self.fixture();l['slots'][1]['role']={'kind':'librarian','enchantment':'minecraft:unbreaking','level':3};l['slots'][2]['role']={'kind':'librarian','enchantment':'minecraft:sweeping_edge','level':3};r,_=bind_required_books(l,t,k);self.assertEqual(r['slots'][1]['role']['enchantment'],'minecraft:unbreaking');self.assertEqual(r['slots'][2]['role']['enchantment'],'minecraft:mending')
 def test_insufficient_capacity_and_ambiguous_locks_fail_closed(self):
  for mode in ['capacity','weak','missing_uuid','missing_proof','duplicate_resident']:
   l,t,k=self.fixture()
   if mode=='capacity':l['slots'].pop()
   elif mode=='weak':k['minecraft:sweeping_edge']['level']=2
   elif mode=='missing_uuid':k['minecraft:sweeping_edge']['villager_uuid']='elsewhere'
   elif mode=='missing_proof':k['minecraft:sweeping_edge']['proof']=''
   else:l['slots'][1]['occupant_uuid']='locked'
   with self.subTest(mode=mode),self.assertRaises(ValueError):bind_required_books(l,t,k)
 def test_repeated_planning_does_not_shuffle_desired_books(self):
  l,t,k=self.fixture();r,_=bind_required_books(l,t,k);r2,changes=bind_required_books(r,t,k);self.assertEqual(r,r2);self.assertEqual(changes,[])
if __name__=='__main__':unittest.main()
