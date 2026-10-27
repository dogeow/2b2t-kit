import copy,unittest
from merchant_preflight_abort import observable_selection,DETAIL
class SelectionRefusalTests(unittest.TestCase):
 def fixture(self):
  params={'menu_id':3,'index':0,'expected_villager_uuid':'v','expected_offers_fingerprint':'old'};pending={'op':'merchant_select_trade','params':params,'request_id':'r'};book={'complete':False,'pending':pending,'world_session':'w','uuid':'v','before':{}};state={'world_session':'w','last_request':'r','control_revision':4,'pos':[1,2,3],'health':20,'connected':True,'manual_movement':False,'supervision_lease':{'job_session':'t'},'inventory':[],'menu':{'id':3,'type':'MerchantMenu','material_owned':True,'cursor':{'count':0},'slots':[{'count':0}]*3,'merchant':{'owned':True,'owner_task':'t','villager_uuid':'v','offers_fingerprint':'restocked'}}};event={'request_id':'r','world_session':'w','op':'merchant_select_trade','phase':'error','detail':DETAIL,'params':{'task_session':'t',**params},'inventory_delta':{},'revision_before':4,'revision_after':4,'position_before':[1,2,3],'position_after':[1,2,3],'health_before':20,'health_after':20};error={'last_request':'r','error':DETAIL,'native_inflight':None,'unconfirmed_native_request':None};return {'action':'merchant_buy_one','index':0},error,book,state,event,'w','t'
 def test_changed_offer_is_observable_only_when_selection_was_explicitly_unissued(self):self.assertTrue(observable_selection(*self.fixture()))
 def test_any_completed_selection_payment_delta_foreign_owner_or_pending_output_rejects(self):
  for mode in ['receipt','payment','owner','phase','output','cursor']:
   a=list(copy.deepcopy(self.fixture()))
   if mode=='receipt':a[2]['receipts']=[{'id':'selected'}]
   if mode=='payment':a[4]['inventory_delta']={'minecraft:paper':-24}
   if mode=='owner':a[3]['menu']['merchant']['owned']=False
   if mode=='phase':a[4]['phase']='done'
   if mode=='output':a[2]['pending']['op']='slot_click'
   if mode=='cursor':a[3]['menu']['cursor']['count']=1
   with self.subTest(mode=mode):self.assertFalse(observable_selection(*a))

class SelectionSettlementTests(unittest.TestCase):
 def test_aborted_selection_remains_incomplete_and_needs_immutable_source_and_two_conserved_frames(self):
  import tempfile,json,hashlib
  from pathlib import Path
  from merchant_preflight_abort import selection_settled,settled
  command,error,book,state,event,world,task=SelectionRefusalTests().fixture()
  with tempfile.TemporaryDirectory()as directory:
   path=Path(directory)/'one-trade.json';path.write_text(json.dumps(book));proof={'abort_settled':True,'purchase_credit':0,'original_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'original_error':error,'refusal':event,'close_receipt':{'id':'close','phase':'done','world_session':'w'},'close_event':{'request_id':'close','op':'close_menu','phase':'done','world_session':'w','params':{'task_session':'t'}},'settled_frames':[{'time':i,'world_session':'w','health':20,'screen':'','cursor_count':0,'inventory':{}}for i in [1,2]]};dest=path.parent/'preselection-abort.json';dest.write_text(json.dumps(proof));self.assertTrue(selection_settled(path));self.assertTrue(settled(path));self.assertFalse(json.loads(path.read_text())['complete'])
   proof['settled_frames'][1]['inventory']={'minecraft:paper':1};dest.write_text(json.dumps(proof));self.assertFalse(settled(path))
