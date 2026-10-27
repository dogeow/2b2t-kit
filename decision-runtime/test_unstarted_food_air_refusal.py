import unittest,copy
from food_approach_observation import unmoved_air_refusal
class Tests(unittest.TestCase):
 def fixture(self):
  detail='Air-only navigation requires the current material lease and a loaded clear dry path';params={'target':[1,65,2],'air_only':True,'arrival':.1,'seconds':20};command={'action':'feed_village_founders','quotas':{'a':3,'b':3}};error={'type':'RuntimeError','error':detail,'native_inflight':None,'unconfirmed_native_request':None,'last_request':'r'};book={'world_session':'w','complete':False,'required':command['quotas'].copy(),'delivered':{'a':0,'b':0},'receipts':[],'pending_food':None,'pending':{'op':'navigate','params':params},'error':repr(RuntimeError(detail))};event={'world_session':'w','request_id':'r','op':'navigate','phase':'error','detail':detail,'params':dict(params,task_session='t'),'position_before':[0,64,0],'position_after':[0,64,0],'revision_before':3,'revision_after':3,'inventory_delta':{},'health_before':20,'health_after':20};state={'world_session':'w','phase':'error','last_request':'r','pos':[0,64,0],'control_revision':3,'health':20,'supervision_lease':{'job_session':'t','world_session':'w','kind':'materials'},'inventory':[{'item':'minecraft:bread','count':8,'slot':1}],'connected':True,'manual_movement':False,'screen':'','menu':{'cursor':{'count':0}},'movement_keys':{'forward':False}};return command,error,book,event,state,'w','t',8
 def test_exact_refusal_is_observable(self):self.assertTrue(unmoved_air_refusal(*self.fixture()))
 def test_food_intent_or_receipt_remains_fenced(self):
  for mode in ['intent','receipt','credit','debit','unknown']:
   a=copy.deepcopy(self.fixture())
   if mode=='intent':a[2]['pending_food']={'target':'a'}
   elif mode=='receipt':a[2]['receipts']=[{'drop':'r'}]
   elif mode=='credit':a[2]['delivered']['a']=1
   elif mode=='debit':a[4]['inventory'][0]['count']=7
   else:a[1]['unconfirmed_native_request']='r'
   with self.subTest(mode=mode):self.assertFalse(unmoved_air_refusal(*a))
 def test_moved_changed_owner_or_revision_refused(self):
  for mode in ['move','owner','world','revision','target']:
   a=copy.deepcopy(self.fixture())
   if mode=='move':a[3]['position_before']=[1,64,0]
   elif mode=='owner':a[4]['supervision_lease']['job_session']='other'
   elif mode=='world':a[3]['world_session']='other'
   elif mode=='revision':a[3]['revision_before']=2
   else:a[3]['params']['target']=[9,65,2]
   with self.subTest(mode=mode):self.assertFalse(unmoved_air_refusal(*a))
 def test_player_health_and_manual_control_remain_required(self):
  a=copy.deepcopy(self.fixture());a[4]['health']=19;self.assertFalse(unmoved_air_refusal(*a));a=copy.deepcopy(self.fixture());a[4]['manual_movement']=True;self.assertFalse(unmoved_air_refusal(*a))
 def test_incomplete_event_fails_closed(self):
  a=list(copy.deepcopy(self.fixture()));a[3]=None;self.assertFalse(unmoved_air_refusal(*a))
