import copy,unittest
from material_client import Client
from terminal_confirmation import verified
class TerminalTest(unittest.TestCase):
 def mine(self):return {'id':'r','world_session':'w','phase':'done','server_confirmed':True,'outcome_pending':False,'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack','server_update_seen':True,'server_observed_state':'Block{minecraft:air}','native_sequence':3,'server_ack_sequence':3,'mining_target':[1,2,3]}
 def test_legacy_done_is_not_checked_success(self):
  c=object.__new__(Client);c.world='w';c.last='r';c.request=lambda *a,**k:{'id':'r','world_session':'w','phase':'done'}
  for op in ['mine_block','professional_print','recover_shulker']:
   with self.subTest(op=op),self.assertRaisesRegex(RuntimeError,'server confirmation'):c.checked(op,pos=[1,2,3])
 def test_exact_mine_accepts_but_foreign_stale_or_missing_proof_refuses(self):
  base=self.mine();p={'pos':[1,2,3]};self.assertTrue(verified('mine_block',base,'w','r',p))
  for key,value in [('id','other'),('world_session','old'),('server_confirmed',False),('native_sequence',True),('server_ack_sequence',2),('server_observed_state','Block{minecraft:stone}'),('mining_target',[9,9,9]),('outcome_pending',True)]:
   r=copy.deepcopy(base);r[key]=value
   with self.subTest(key=key):self.assertFalse(verified('mine_block',r,'w','r',p))
 def test_underwater_allows_only_pure_water_removal(self):
  r=self.mine();r['server_observed_state']='Block{minecraft:water}[level=0]'
  self.assertFalse(verified('mine_block',r,'w','r',{'pos':[1,2,3]}))
  self.assertTrue(verified('mine_block',r,'w','r',{'pos':[1,2,3],'underwater_gravel':True}))
  r['server_observed_state']='Block{minecraft:oak_fence}[waterlogged=true]'
  self.assertFalse(verified('mine_block',r,'w','r',{'pos':[1,2,3],'underwater_gravel':True}))
 def test_print_can_only_prove_its_unique_bounded_mask(self):
  r={'id':'r','world_session':'w','server_confirmed':True,'outcome_pending':False,'confirmation_scope':'current_bounded_mask_distinct_exact_final_server_updates','full_projection_confirmed':False,'bounded_targets':[[1,2,3],[4,5,6]],'bounded_target_count':2,'placement_key':'p'}
  self.assertTrue(verified('professional_print',r,'w','r',{}))
  for key,value in [('full_projection_confirmed',True),('bounded_target_count',0),('bounded_targets',[[1,2,3],[1,2,3]]),('placement_key','')]:
   v=copy.deepcopy(r);v[key]=value
   with self.subTest(key=key):self.assertFalse(verified('professional_print',v,'w','r',{}))
