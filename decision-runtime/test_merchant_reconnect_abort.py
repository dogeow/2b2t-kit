import hashlib,json,tempfile,unittest
from pathlib import Path
from merchant_preflight_abort import settled,DETAIL
class ReconnectAbortTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'one-trade.json'
  params={'slot':2,'kind':'pickup','button':0,'menu_id':2,'expected_item':'minecraft:emerald'}
  book={'world_session':'old','complete':False,'pending':{'request_id':'r1','op':'slot_click','params':params},'before':{'minecraft:iron_ingot':40}}
  self.path.write_text(json.dumps(book))
  event={'request_id':'r1','phase':'error','detail':DETAIL,'op':'slot_click','world_session':'old','params':params,'inventory_delta':{},'revision_before':5,'revision_after':5,'position_before':[1,2,3],'position_after':[1,2,3],'health_before':20,'health_after':20}
  self.proof={'abort_settled':True,'purchase_credit':0,'original_sha256':hashlib.sha256(self.path.read_bytes()).hexdigest(),'refusal_event':event,'refusal_reply':{'id':'r1','phase':'error','detail':DETAIL,'world_session':'old','player_uuid':'player','server':'s','time':10},'reconnect_snapshot':{'connected':True,'health':20,'world_session':'new','player_uuid':'player','server':'s','time':20,'inventory':[{'slot':0,'item':'minecraft:iron_ingot','count':40}]},'reconnect_result':{'server':'s','world_session':'new','connected':True,'request_replayed':False,'inventory_credit':0},'return_observation':{'original_request':'r1','native_outcome':'rejected_no_packet_sent','inventory_equals_before':True,'original_replayed':False,'frames':[21,22,23]}}
 def write(self): (self.path.parent/'reconnect-abort.json').write_text(json.dumps(self.proof))
 def test_positive(self): self.write();self.assertTrue(settled(self.path))
 def test_rejections(self):
  for section,key,value in [('refusal_event','detail','unknown'),('refusal_event','inventory_delta',{'minecraft:iron_ingot':-1}),('refusal_reply','player_uuid','other'),('reconnect_snapshot','health',19),('reconnect_snapshot','world_session','old'),('reconnect_result','request_replayed',True),('return_observation','inventory_equals_before',False),('return_observation','frames',[21,21,23])]:
   with self.subTest(section=section,key=key):
    original=self.proof[section][key];self.proof[section][key]=value;self.write();self.assertFalse(settled(self.path));self.proof[section][key]=original
 def test_modified_journal(self): self.write();self.path.write_text(self.path.read_text()+' ');self.assertFalse(settled(self.path))
 def test_missing_proof(self): self.assertFalse(settled(self.path))
if __name__=='__main__':unittest.main()
