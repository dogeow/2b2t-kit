import copy,unittest
from sleeping_merchant_observation import observable_paid_reopen
from test_sleeping_merchant_observation import SleepingMerchantObservationTests

class Tests(unittest.TestCase):
 def fixture(self):
  c,e,o,event,s,f=SleepingMerchantObservationTests().fixture()
  c={'action':'merchant_lock_wanted','targets':{'minecraft:mending':1}}
  wanted={'result':{'stored_enchantments':[{'id':'minecraft:mending','level':1}]}}
  offer={'cost_a':{'item':'minecraft:paper','count':24},'cost_b':{'item':'minecraft:air','count':0},'result':{'item':'minecraft:emerald','count':1}}
  purchase={'world_session':'w','uuid':'v','complete':True,'pending':None,'offer':offer,'before':{'minecraft:paper':48},'after':{'minecraft:paper':24,'minecraft:emerald':1},'expected_after':{'minecraft:paper':24,'minecraft:emerald':1}}
  lock={'world_session':'w','uuid':'v','pending':'reopen_after_purchase','locked':False,'selected':{'enchantment':'minecraft:mending','level':1,'offer':wanted},'quote':{'villager_uuid':'v','offers':[wanted]},'purchase':purchase}
  s['inventory']=[{'slot':0,'item':'minecraft:paper','count':24},{'slot':1,'item':'minecraft:emerald','count':1}];f['villagers'][0]['entity_id']=4
  return c,e,lock,o,event,s,f,'w','t'
 def test_paid_reopen_range_refusal_requires_audited_host_and_conserved_payment(self):
  from sleeping_merchant_observation import REACH_HOST_SHA256S
  args=list(self.fixture());args[1]['error']='Entity out of reach';args[4].update(phase='error',detail='Entity out of reach')
  self.assertTrue(observable_paid_reopen(*args,host_sha256=next(iter(REACH_HOST_SHA256S))))
  self.assertFalse(observable_paid_reopen(*args,host_sha256='unknown'))
  args[5]['inventory'][0]['count']=23
  self.assertFalse(observable_paid_reopen(*args,host_sha256=next(iter(REACH_HOST_SHA256S))))
 def test_completed_payment_only_admits_observation_not_repeat_purchase(self):
  self.assertTrue(observable_paid_reopen(*self.fixture()))
 def test_unknown_payment_changed_inventory_and_other_openings_stay_fenced(self):
  for mode in ['pending','incomplete','stock','expected','unconfirmed','other_uuid','other_entity','target','payment','no_payment','wrong_stage','opened']:
   args=copy.deepcopy(self.fixture());c,e,l,o,event,s,f,w,t=args
   if mode=='pending':l['purchase']['pending']='click'
   if mode=='incomplete':l['purchase']['complete']=False
   if mode=='stock':s['inventory'][0]['count']=23
   if mode=='expected':l['purchase']['expected_after']['minecraft:paper']=23
   if mode=='unconfirmed':e['unconfirmed_native_request']={'id':'unknown'}
   if mode=='other_uuid':l['purchase']['uuid']='other'
   if mode=='other_entity':f['villagers'][0]['entity_id']=99
   if mode=='target':c['targets']={}
   if mode=='payment':l['purchase']['offer']['cost_a']['count']=23
   if mode=='no_payment':l['purchase']['before']=dict(l['purchase']['after'])
   if mode=='wrong_stage':l['pending']='purchase'
   if mode=='opened':s['screen']='MerchantScreen'
   with self.subTest(mode=mode):self.assertFalse(observable_paid_reopen(*args))

if __name__=='__main__':unittest.main()
