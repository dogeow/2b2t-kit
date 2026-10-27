import unittest,json,hashlib,tempfile
from copy import deepcopy
from pathlib import Path
from merchant_preflight_abort import observable,settled,DETAIL
class MerchantPreflightAbortTest(unittest.TestCase):
 def setUp(self):
  p={'menu_id':69,'slot':2,'kind':'pickup','button':0,'expected_trade_index':1}
  self.command={'action':'merchant_buy_one','index':1};self.error={'error':DETAIL,'last_request':'r','native_inflight':None,'unconfirmed_native_request':None}
  self.book={'world_session':'w','uuid':'u','complete':False,'pending':{'op':'slot_click','params':p,'request_id':'r'},'before':{'minecraft:potato':166,'minecraft:emerald':9},'receipts':[{'id':'select'}]}
  self.state={'world_session':'w','phase':'error','last_request':'r','control_revision':3,'pos':[1,2,3],'health':20,'movement_keys':{},'supervision_lease':{'job_session':'t'},'inventory':[{'slot':0,'item':'minecraft:potato','count':64},{'slot':1,'item':'minecraft:potato','count':38},{'slot':2,'item':'minecraft:emerald','count':9}], 'menu':{'type':'MerchantMenu','material_owned':True,'id':69,'cursor':{'count':0},'slots':[{'item':'minecraft:potato','count':64},{'count':0}],'merchant':{'owned':True,'owner_task':'t','villager_uuid':'u'}}}
  self.event={'world_session':'w','request_id':'r','phase':'error','op':'slot_click','detail':DETAIL,'params':dict(p,task_session='t'),'inventory_delta':{},'revision_after':3,'position_before':[1,2,3],'position_after':[1,2,3],'health_before':20,'health_after':20}
  self.selection={'world_session':'w','request_id':'select','op':'merchant_select_trade','phase':'done','inventory_delta':{},'params':{'index':1,'menu_id':69,'expected_villager_uuid':'u','task_session':'t'}}
 def check(self):return observable(self.command,self.error,self.book,self.state,self.event,self.selection,'w','t')
 def test_exact_no_packet_refusal_is_observable(self):self.assertTrue(self.check())
 def test_no_refusal_or_unknown_input_cannot_be_aborted(self):
  self.error['unconfirmed_native_request']='unknown';self.assertFalse(self.check());self.error['unconfirmed_native_request']=None
  self.event['detail']='timeout';self.assertFalse(self.check())
 def test_any_debit_or_cursor_change_prevents_abort(self):
  self.state['inventory'][0]['count']=63;self.assertFalse(self.check());self.state['inventory'][0]['count']=64
  self.state['menu']['cursor']['count']=1;self.assertFalse(self.check())
 def test_prior_purchase_or_foreign_owner_is_rejected(self):
  self.book['receipts'].append({'id':'purchase'});self.assertFalse(self.check());self.book['receipts'].pop()
  self.state['menu']['merchant']['owner_task']='other';self.assertFalse(self.check())
 def test_non_output_pickup_is_rejected(self):self.book['pending']['params']['slot']=0;self.assertFalse(self.check())
 def test_terminal_abort_preserves_incomplete_original_and_requires_hash_and_two_frames(self):
  with tempfile.TemporaryDirectory()as d:
   path=Path(d)/'one-trade.json';path.write_text(json.dumps(self.book));frames=[{'time':n,'world_session':'w','health':20,'screen':'','cursor_count':0,'inventory':self.book['before']}for n in [1,2]]
   proof={'abort_settled':True,'purchase_credit':0,'original_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'refusal':self.event,'close_receipt':{'id':'close','phase':'done','op':'settle','world_session':'w'},'close_event':{'request_id':'close','phase':'done','op':'close_menu','world_session':'w','params':{'task_session':'t'}},'settled_frames':frames,'world_session':'w','uuid':'u'};p=Path(d)/'prepurchase-abort.json';p.write_text(json.dumps(proof));self.assertTrue(settled(path));self.assertFalse(json.loads(path.read_text())['complete']);proof['settled_frames'][1]['time']=1;p.write_text(json.dumps(proof));self.assertFalse(settled(path))
   proof['settled_frames'][1]['time']=2;p.write_text(json.dumps(proof));path.write_text(path.read_text()+' ');self.assertFalse(settled(path))
if __name__=='__main__':unittest.main()
