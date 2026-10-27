import copy,unittest
from librarian_duplicate_reset import OPTIONAL_MAXIMA, reset_allowed
class DuplicateResetTest(unittest.TestCase):
 def fixture(self,name='minecraft:aqua_affinity',level=1):
  book={'item':'minecraft:enchanted_book','count':1,'stored_enchantments':[{'id':name,'level':level}]};m={'protocol':1,'owned':True,'owner_task':'t','villager_uuid':'candidate','level':1,'trader_xp':0,'offers':[{'uses':0,'result':book}]};locked={name:{'villager_uuid':'keeper','level':level,'server_history_verified':True}};proof={name:{'complete':True,'pending':None,'open_roofs':[],'world_session':'w','keeper_uuid':'keeper','merchant':{'villager_uuid':'keeper','trader_xp':1,'offers':[{'result':copy.deepcopy(book)}]}}};state={'connected':True,'world_session':'w','health':20,'manual_movement':False,'supervision_lease':{'job_session':'t'},'loaded_villagers':{'villagers':[{'uuid':'keeper','health':20,'is_baby':False,'villager':{'profession':'minecraft:librarian'}}]}};return m,{name:level},locked,proof,state
 def test_verified_locked_other_resident_keeps_the_required_type(self):self.assertTrue(reset_allowed(*self.fixture()))
 def test_missing_dead_changed_world_or_untraded_keeper_is_not_a_duplicate_certificate(self):
  for mode in ['missing','health','world','untraded','wrong_book','pending','same_uid']:
   a=self.fixture();name='minecraft:aqua_affinity'
   if mode=='missing':a[4]['loaded_villagers']['villagers']=[]
   elif mode=='health':a[4]['loaded_villagers']['villagers'][0]['health']=19
   elif mode=='world':a[3][name]['world_session']='other'
   elif mode=='untraded':a[3][name]['merchant']['trader_xp']=0
   elif mode=='wrong_book':a[3][name]['merchant']['offers'][0]['result']['stored_enchantments'][0]['id']='minecraft:lure'
   elif mode=='pending':a[3][name]['pending']='unknown'
   else:a[0]['villager_uuid']='keeper'
   with self.subTest(mode=mode):self.assertFalse(reset_allowed(*a))
 def test_unowned_maximum_or_used_quote_is_never_reset(self):
  a=self.fixture();a[2].clear();self.assertFalse(reset_allowed(*a))
  for mode in ['xp','uses','task']:
   a=self.fixture()
   if mode=='xp':a[0]['trader_xp']=1
   elif mode=='uses':a[0]['offers'][0]['uses']=1
   else:a[0]['owner_task']='other'
   with self.subTest(mode=mode):self.assertFalse(reset_allowed(*a))
 def test_native_keeper_requires_native_protection_even_with_a_planner_certificate(self):self.assertFalse(reset_allowed(*self.fixture('minecraft:looting',3)))
 def native_fixture(self):
  args=self.fixture('minecraft:unbreaking',3);m,targets,locked,proof,state=args;state.update(time=10000);state['supervision_lease'].update(id='lease',world_session='w',kind='materials');quote=proof['minecraft:unbreaking']['merchant'];quote.update(protocol=1,owned=True,owner_task='t',observation_scope='current_server_received_merchant_menu_not_trade_completion');reply={'connected':True,'health':20,'manual_movement':False,'world_session':'w','time':9500,'supervision_lease':dict(state['supervision_lease']),'menu':{'material_owned':True,'merchant':copy.deepcopy(quote)}};return args,{'minecraft:unbreaking':reply}
 def test_fresh_other_paid_native_quote_only_permits_host_duplicate_request(self):
  args,attested=self.native_fixture();self.assertTrue(reset_allowed(*args,native_attestations=attested));self.assertFalse(reset_allowed(*args))
 def test_expired_foreign_changed_or_unpaid_native_attestation_is_rejected(self):
  for mode in['age','task','world','quote','xp','lease']:
   args,a=self.native_fixture();r=a['minecraft:unbreaking']
   if mode=='age':r['time']=-16000
   if mode=='task':r['menu']['merchant']['owner_task']='other'
   if mode=='world':r['world_session']='other'
   if mode=='quote':r['menu']['merchant']['offers']=[]
   if mode=='xp':r['menu']['merchant']['trader_xp']=0
   if mode=='lease':r['supervision_lease']['id']='other'
   with self.subTest(mode=mode):self.assertFalse(reset_allowed(*args,native_attestations=a))
 def test_ordinary_unwanted_quote_needs_no_duplicate_certificate(self):
  a=self.fixture();a[0]['offers'][0]['result']['stored_enchantments'][0]['id']='minecraft:lure';self.assertTrue(reset_allowed(*a))
 def test_optional_maxima_are_preserved_without_becoming_required(self):
  for name,level in OPTIONAL_MAXIMA.items():
   a=self.fixture(name,level);a[1].clear();a[2].clear();a[3].clear()
   with self.subTest(name=name):self.assertFalse(reset_allowed(*a))
 def test_optional_lower_levels_do_not_stop_required_book_search(self):
  for name,level in OPTIONAL_MAXIMA.items():
   if level==1:continue
   a=self.fixture(name,level-1);a[1].clear();a[2].clear();a[3].clear()
   with self.subTest(name=name):self.assertTrue(reset_allowed(*a))
 def test_optional_duplicate_requires_an_independent_keeper_certificate(self):
  a=self.fixture('minecraft:channeling',1);a[1].clear()
  self.assertTrue(reset_allowed(*a))
  a[3].clear();self.assertFalse(reset_allowed(*a))
 def test_optional_duplicate_does_not_reuse_candidate_as_its_own_keeper(self):
  a=self.fixture('minecraft:multishot',1);a[1].clear();a[0]['villager_uuid']='keeper'
  self.assertFalse(reset_allowed(*a))
class NativeKeeperAgeBoundaryTests(unittest.TestCase):
 def test_returning_from_far_counter_is_allowed_only_within_twenty_seconds(self):
  args,attested=DuplicateResetTest().native_fixture();args[-1]['time']=29500
  self.assertTrue(reset_allowed(*args,native_attestations=attested))
  args[-1]['time']=29501
  self.assertFalse(reset_allowed(*args,native_attestations=attested))
if __name__=='__main__':unittest.main()
