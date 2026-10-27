import copy,unittest
from librarian_workflow import seed_cycles
class WorkflowResumeTests(unittest.TestCase):
 def fixture(self):
  row={'slot':'EN07','pending':False,'station_restored':True,'native_sequence':2,'server_ack_sequence':2,'admission':{'world_session':'w','villager_uuid':'v'}}
  return {'complete':True,'pending':None,'open_roofs':[],'world_session':'w','cycles':[row]},[{'id':'EN07','occupant_uuid':'v'}]
 def test_only_complete_same_world_same_resident_acknowledged_cycles_resume(self):
  proof,layout=self.fixture();self.assertEqual(seed_cycles(proof,'w',layout)['EN07']['native_sequence'],2)
  for mode in ['pending','world','unconfirmed','missing_ack','new_resident','unfinished_quote','open_roof','unfinished_segment']:
   p=copy.deepcopy(proof);slots=copy.deepcopy(layout)
   if mode=='pending':p['pending']={'op':'mine_block'}
   if mode=='world':p['world_session']='other'
   if mode=='unconfirmed':p['cycles'][0]['pending']=True
   if mode=='missing_ack':p['cycles'][0]['server_ack_sequence']=-1
   if mode=='new_resident':slots[0]['occupant_uuid']='replacement'
   if mode=='unfinished_quote':p['public_quote_admissions']=[{'pending':True}]
   if mode=='open_roof':p['open_roofs']=[[1,2,3]]
   if mode=='unfinished_segment':p['complete']=False
   with self.subTest(mode=mode),self.assertRaises(RuntimeError):seed_cycles(p,'w',slots)
 def test_checkpoint_keeps_previous_cells_and_updates_only_confirmed_new_generation(self):
  p,layout=self.fixture();p['last_cycles']={'EN07':copy.deepcopy(p['cycles'][0])};p['cycles'][0]['native_sequence']=3;p['cycles'][0]['server_ack_sequence']=3
  self.assertEqual(seed_cycles(p,'w',layout)['EN07']['native_sequence'],3);self.assertEqual(p['last_cycles']['EN07']['native_sequence'],2)

class SleepingSupplierTests(unittest.TestCase):
 def test_only_a_new_awake_observation_unparks_the_candidate(self):
  from librarian_workflow import wake_sleeping_candidates
  blocked={'A','B'};sleeping={'A':'keeper'}
  self.assertEqual(wake_sleeping_candidates(blocked,sleeping,{}),[])
  self.assertEqual(wake_sleeping_candidates(blocked,sleeping,{'keeper':{'sleeping':True}}),[])
  self.assertEqual(wake_sleeping_candidates(blocked,sleeping,{'keeper':{'sleeping':False}}),['A'])
  self.assertEqual(blocked,{'B'});self.assertEqual(sleeping,{})

class PriorityRecheckTests(unittest.TestCase):
 def test_priority_requires_current_owned_same_resident_quote(self):
  from librarian_workflow import priority_quote_changed
  seed={'complete':True,'world_session':'w','stop_reason':'preserved_wanted_quote_changed','priority_slot':'ES08','priority_enchantment':'minecraft:smite','priority_level':5}
  slot={'id':'ES08','occupant_uuid':'npc'}
  quote={'world_session':'w','menu':{'merchant':{'protocol':1,'owned':True,'villager_uuid':'npc','trader_xp':0,'offers':[{'result':{'item':'minecraft:bookshelf'}}]}}}
  self.assertTrue(priority_quote_changed(seed,quote,slot))
  for mode in ['world','owner','resident','paid','still_wanted','pending']:
   s=copy.deepcopy(seed);q=copy.deepcopy(quote);m=q['menu']['merchant']
   if mode=='world':q['world_session']='old'
   if mode=='owner':m['owned']=False
   if mode=='resident':m['villager_uuid']='other'
   if mode=='paid':m['trader_xp']=1
   if mode=='pending':s['pending']={'op':'merchant_buy_one'}
   if mode=='still_wanted':m['offers']=[{'result':{'item':'minecraft:enchanted_book','count':1,'stored_enchantments':[{'id':'minecraft:smite','level':5}]}}]
   with self.subTest(mode=mode),self.assertRaises(RuntimeError):priority_quote_changed(s,q,slot)

class ReachDeferralTests(unittest.TestCase):
 def fixture(self):
  slot={'id':'ES02','occupant_uuid':'v','work_block':[20,65,30]}
  return {'ES02'}, {'ES02':{'uuid':'v','pos':[20.5,65.,33.5],'deferred_at':10}}, {'v':{'pos':[20.5,65.,31.5],'villager':{'profession':'minecraft:librarian','entity_xp':0}}}, {'v':{'sleeping':False}}, {'ES02':slot}, {}
 def test_only_moved_near_awake_unpaid_resident_can_return(self):
  from librarian_workflow import wake_reachable_candidates
  blocked,d,a,f,s,c=self.fixture()
  self.assertEqual(wake_reachable_candidates(blocked,d,a,f,s,31,c),['ES02'])
  self.assertFalse(blocked);self.assertEqual(c,{'ES02':1});self.assertFalse(d)
 def test_limits_do_not_unpark_duplicate_blocks_or_unknown_or_sleeping_sources(self):
  from librarian_workflow import wake_reachable_candidates
  for mode in ['time','unchanged','far','paid','unclaimed','sleeping','missing_flag','limit','other_block']:
   blocked,d,a,f,s,c=self.fixture();now=31
   if mode=='time':now=20
   if mode=='unchanged':d['ES02']['pos']=a['v']['pos'][:]
   if mode=='far':a['v']['pos']=[20.5,65.,33.5]
   if mode=='paid':a['v']['villager']['entity_xp']=1
   if mode=='unclaimed':a['v']['villager']['profession']='minecraft:none'
   if mode=='sleeping':f['v']['sleeping']=True
   if mode=='missing_flag':f={}
   if mode=='limit':c['ES02']=3
   if mode=='other_block':d={}
   with self.subTest(mode=mode):self.assertEqual(wake_reachable_candidates(blocked,d,a,f,s,now,c),[]);self.assertEqual(blocked,{'ES02'})

class PaidKeeperDeferralTests(unittest.TestCase):
 def fixture(self):
  return {'candidate'},{'candidate':{'uuid':'paid','work':[10,65,20],'pos':[10.5,65.,23.5],'deferred_at':0,'refresh_key':'key','paid_history_verified':True}},{'paid':{'health':20,'is_baby':False,'pos':[10.5,65.,21.5],'villager':{'profession':'minecraft:librarian'}}},{'paid':{'sleeping':False}},{},{'key':2}
 def test_actual_paid_supplier_movement_only_reopens_its_bounded_read_attempt(self):
  from librarian_workflow import wake_paid_keeper_candidates
  b,d,a,f,c,attempts=self.fixture();self.assertEqual(wake_paid_keeper_candidates(b,d,a,f,21,c,attempts),['candidate']);self.assertFalse(b);self.assertFalse(d);self.assertEqual(c,{'key':1});self.assertNotIn('key',attempts)
 def test_sleeping_unpaid_far_unchanged_or_early_source_cannot_unpark_a_candidate(self):
  from librarian_workflow import wake_paid_keeper_candidates
  for mode in ['sleeping','unpaid','far','unchanged','early','injured','baby']:
   b,d,a,f,c,t=self.fixture();now=21
   if mode=='sleeping':f['paid']['sleeping']=True
   if mode=='unpaid':d['candidate']['paid_history_verified']=False
   if mode=='far':a['paid']['pos']=[10.5,65,23.5]
   if mode=='unchanged':d['candidate']['pos']=a['paid']['pos'][:]
   if mode=='early':now=10
   if mode=='injured':a['paid']['health']=19
   if mode=='baby':a['paid']['is_baby']=True
   with self.subTest(mode=mode):self.assertEqual(wake_paid_keeper_candidates(b,d,a,f,now,c,t),[]);self.assertEqual(b,{'candidate'});self.assertEqual(t,{'key':2})
 def test_exhausted_or_unchanged_near_source_requests_attention_instead_of_waiting_forever(self):
  from librarian_workflow import wake_paid_keeper_candidates
  for mode in ['limit','unchanged']:
   b,d,a,f,c,t=self.fixture()
   if mode=='limit':c['key']=3
   else:d['candidate']['pos']=a['paid']['pos'][:]
   self.assertEqual(wake_paid_keeper_candidates(b,d,a,f,100,c,t),[]);self.assertFalse(d);self.assertTrue(b)

class KeeperApproachFlagTests(unittest.TestCase):
 def test_far_supplier_is_approached_before_flag_read(self):
  from librarian_workflow import keeper_flag_after_approach
  from types import SimpleNamespace
  order=[];keeper=SimpleNamespace(uid='paid')
  def walk(room):self.assertIs(room,keeper);order.append('walk')
  def frame():self.assertEqual(order,['walk']);order.append('frame');return {'villagers':[{'uuid':'paid','sleeping':False}]}
  self.assertFalse(keeper_flag_after_approach(keeper,walk,frame)['sleeping']);self.assertEqual(order,['walk','frame'])
 def test_missing_or_ambiguous_supplier_is_not_stop_iteration_or_another_flag(self):
  from librarian_workflow import keeper_flag_after_approach
  from types import SimpleNamespace
  for flags in ([],[{'uuid':'other','sleeping':False}],[{'uuid':'paid','sleeping':False}]*2):
   self.assertIsNone(keeper_flag_after_approach(SimpleNamespace(uid='paid'),lambda _:None,lambda:{'villagers':flags}))

class KeeperWakeBeforeQuoteTests(unittest.TestCase):
 def test_exact_sleeping_keeper_is_woken_once_then_observed_again(self):
  from librarian_workflow import keeper_flag_after_approach
  from types import SimpleNamespace
  events=[];sleeping=[True]
  def frame():events.append('frame');return {'villagers':[{'uuid':'paid','sleeping':sleeping[0]}]}
  def wake():events.append('wake');sleeping[0]=False
  flag=keeper_flag_after_approach(SimpleNamespace(uid='paid'),lambda _:events.append('walk'),frame,wake=wake);self.assertFalse(flag['sleeping']);self.assertEqual(['walk','frame','wake','frame'],events)
 def test_awake_missing_or_other_keeper_never_triggers_a_bed_use(self):
  from librarian_workflow import keeper_flag_after_approach
  from types import SimpleNamespace
  for flags in ([],[{'uuid':'other','sleeping':True}],[{'uuid':'paid','sleeping':False}]):
   def wake():raise AssertionError('Do not wake an unobserved or awake keeper')
   keeper_flag_after_approach(SimpleNamespace(uid='paid'),lambda _:None,lambda:{'villagers':flags},wake=wake)
 def test_unconfirmed_wake_propagates_without_another_input(self):
  from librarian_workflow import keeper_flag_after_approach
  from types import SimpleNamespace
  calls=[]
  def wake():calls.append('wake');raise RuntimeError('original wake unconfirmed')
  with self.assertRaises(RuntimeError):keeper_flag_after_approach(SimpleNamespace(uid='paid'),lambda _:None,lambda:{'villagers':[{'uuid':'paid','sleeping':True}]},wake=wake)
  self.assertEqual(['wake'],calls)
