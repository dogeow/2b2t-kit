import unittest
from types import SimpleNamespace
from village_merchant_bridge import VillageMerchantBridge
class VillageMerchantBridgeTest(unittest.TestCase):
 def test_known_terminal_request_id_survives_a_queue_wrapper_exception(self):
  import json,tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory()as directory:
   c,s,calls=self.make();q=c.queue;q.out=Path(directory);(q.out/'control').mkdir();(q.out/'new').mkdir();(q.out/'command.json').write_text(json.dumps({'id':'old'}))
   def refused(op,**params):
    command={'id':'new','action':'native','op':op,'params':params}
    for path,value in [(q.out/'command.json',command),(q.out/'new/intent.json',command),(q.out/'new/result.json',{'id':'refused','phase':'error','world_session':'w'})]:path.write_text(json.dumps(value))
    event={'request_id':'refused','phase':'error','world_session':'w','op':op,'params':dict(params,task_session='t')}
    (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');raise RuntimeError('known native refusal')
   q.native=refused
   with self.assertRaisesRegex(RuntimeError,'known native refusal'):c.checked('slot_click',slot=2,kind='pickup')
   self.assertEqual(c.last,'refused')
 def make(self):
  state={'world_session':'w','supervision_lease':{'job_session':'t'},'health':20,'server':'server','last_request':'old'};calls=[]
  q=SimpleNamespace(root='root',world='w',lease={'job_session':'t'},out='out',status=lambda **kw:state,native=lambda op,**kw:(calls.append((op,kw))or{'id':'new','phase':'done'}));return VillageMerchantBridge(q),state,calls
 def test_uses_only_original_queue(self):
  c,s,calls=self.make();c.checked('merchant_select_trade',index=1);self.assertEqual([('merchant_select_trade',{'index':1})],calls);self.assertEqual('new',c.last)
 def test_snapshot_observes_same_world_without_requiring_a_mutation_phase(self):
  c,s,calls=self.make();c.queue.native=lambda op:(calls.append((op,{}))or{'id':'read','world_session':'w','phase':None})
  self.assertEqual(c.request('snapshot')['id'],'read');self.assertEqual(c.last,'read')
  self.assertEqual(calls,[('snapshot',{})])
  with self.assertRaises(ValueError):c.request('snapshot',target=[1,2,3])
 def test_owner_change_or_non_trade_action_sends_nothing(self):
  c,s,calls=self.make();s['supervision_lease']['job_session']='other'
  with self.assertRaises(RuntimeError):c.checked('close_menu')
  self.assertEqual([],calls)
  with self.assertRaises(ValueError):c.checked('mine_block')
if __name__=='__main__':unittest.main()
