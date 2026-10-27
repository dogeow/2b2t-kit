import copy,unittest
from food_guard_observation import rejected_without_q,HOST_SHA256,DETAIL,APPROVED_HOSTS
class FoodGuardObservationTests(unittest.TestCase):
 def fixture(self):
  params={'entity_id':4,'expected_uuid':'a','expected_count':7};cmd={'action':'feed_village_founders','quotas':{'a':3,'b':3}};err={'error':DETAIL,'native_inflight':None,'unconfirmed_native_request':None,'last_request':'native'};f={'world_session':'w','complete':False,'receipts':[],'delivered':{'a':0,'b':0},'required':cmd['quotas'],'pending':{'op':'villager_bread_drop','params':params},'pending_food':{'target':'a','before_bread':7}};s={'last_request':'native','pos':[1,64,1],'control_revision':8,'health':20,'screen':'','manual_movement':False,'movement_keys':{},'hand':{'item':'minecraft:bread','count':7},'inventory':[{'slot':0,'item':'minecraft:bread','count':7}]};e={'request_id':'native','world_session':'w','op':'villager_bread_drop','phase':'error','detail':DETAIL,'params':{'task_session':'t',**params},'position_before':s['pos'],'position_after':s['pos'],'inventory_delta':{},'revision_before':8,'revision_after':8,'health_before':20,'health_after':20};return cmd,err,f,e,s
 def test_pinned_unchanged_preflight_is_observable_without_food_credit(self):self.assertTrue(rejected_without_q(*self.fixture(),'w','t',HOST_SHA256))
 def test_partial_server_confirmed_delivery_keeps_credit_but_releases_only_rejected_Q(self):
  for unsafe in (None,'missing_event','wrong_task','wrong_collector','fake_total','duplicate'):
   with self.subTest(unsafe=unsafe):
    cmd,err,f,e,s=copy.deepcopy(self.fixture());f['delivered']['a']=1
    packet=dict(kind='pickup_entities_unresolved',amount=1,source_entity_id=10,collector_entity_id=4,
                collector=dict(uuid='a',entity_id=4,type='minecraft:villager',is_baby=False,client_health=20),
                source_join='fresh_same_world_generation_item_id_uuid',joined_source=dict(id=10,stack=dict(item='minecraft:bread',count=1)))
    f['receipts']=[dict(native_request='prior',target='a',actual_collector='a',server_receipt=packet)]
    prior=dict(request_id='prior',world_session='w',op='villager_bread_drop',phase='done',params=dict(task_session='t',expected_uuid='a'),inventory_delta={'minecraft:bread':-1},health_before=20,health_after=20);events=[prior]
    if unsafe=='missing_event':events=[]
    if unsafe=='wrong_task':prior['params']['task_session']='other'
    if unsafe=='wrong_collector':packet['collector']['uuid']='b'
    if unsafe=='fake_total':f['delivered']['a']=2
    if unsafe=='duplicate':f['receipts']*=2;f['delivered']['a']=2
    self.assertEqual(rejected_without_q(cmd,err,f,e,s,'w','t',HOST_SHA256,prior_events=events),unsafe is None)
 def test_translation_only_host_with_identical_guard_classes_is_explicitly_pinned(self):
  for host in APPROVED_HOSTS:self.assertTrue(rejected_without_q(*self.fixture(),'w','t',host))
 def test_unknown_debited_sent_or_moved_outcome_is_never_released(self):
  for mode in ['unknown','debit','sent','revision','receipt','position','health','hand','host','task']:
   with self.subTest(mode=mode):
    cmd,err,f,e,s=copy.deepcopy(self.fixture());h=HOST_SHA256
    if mode=='unknown':err['native_inflight']={'id':'x'}
    if mode=='debit':s['inventory'][0]['count']=6
    if mode=='sent':f['pending_food']['native_request']='native'
    if mode=='revision':e['revision_after']=9;s['control_revision']=9
    if mode=='receipt':f['receipts']=[{'amount':1}]
    if mode=='position':s['pos']=[2,64,1]
    if mode=='health':s['health']=19
    if mode=='hand':s['hand']['count']=6
    if mode=='host':h='unverified'
    if mode=='task':e['params']['task_session']='other'
    self.assertFalse(rejected_without_q(cmd,err,f,e,s,'w','t',h))
if __name__=='__main__':unittest.main()
