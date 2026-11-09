import hashlib,json,tempfile,unittest
from pathlib import Path
from merchant_preflight_abort import selection_closed_after_reconnect

class SelectionReconnectTests(unittest.TestCase):
 def test_only_closed_old_selection_with_three_exact_new_frames_is_reconciled(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t); p=root/'trade'/'one-trade.json'; p.parent.mkdir(); (root/'control').mkdir()
   book={'world_session':'old','complete':False,'pending':{'op':'merchant_select_trade','request_id':'req'},'receipts':[{'id':'req','player_uuid':'u','server':'s'}],'before':{'minecraft:iron_ingot':25,'minecraft:emerald':44}}
   p.write_text(json.dumps(book));frame={'world_session':'new','player_uuid':'u','server':'s','connected':True,'health':20,'screen':'','cursor_count':0,'supervision_lease':None,'inventory':book['before']}
   events=[{'request_id':'req','op':'merchant_select_trade','phase':'done','world_session':'old','inventory_delta':{}},{'op':'close_menu','phase':'done','world_session':'old','inventory_delta':{}},{'op':'material_job_pause','phase':'done','world_session':'old','inventory_delta':{}}]
   all_events=[events[0],events[1],{'op':'scan','phase':'done','world_session':'old'},events[2]]
   log=root/'control'/'events.jsonl';log.write_text(''.join(json.dumps(e)+'\n' for e in all_events))
   proof={'events_sha256':hashlib.sha256(log.read_bytes()).hexdigest(),'original_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'output_credit':0,'original_replayed':False,'old_events':events,'frames':[dict(frame,time=i)for i in (1,2,3)]}
   f=p.parent/'selection-closed-reconnect.json'
   def check():f.write_text(json.dumps(proof));return selection_closed_after_reconnect(p)
   self.assertTrue(check())
   proof['frames'][1]['inventory']={'minecraft:iron_ingot':22,'minecraft:emerald':45};self.assertFalse(check())
   proof['frames'][1]['inventory']=book['before'];proof['old_events'][1]['op']='slot_click';self.assertFalse(check())
   proof['old_events'][1]['op']='close_menu';proof['frames'][1]['world_session']='old';self.assertFalse(check())
