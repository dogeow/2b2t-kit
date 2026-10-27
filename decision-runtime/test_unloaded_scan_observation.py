import copy,json,tempfile,unittest
from pathlib import Path
from unloaded_scan_observation import observable
from village_queue import VillageQueue
class UnloadedScanTests(unittest.TestCase):
 def fixture(self):
  p={'min':[1,2,3],'max':[2,3,4],'details':True};c=dict(id='cmd',action='native',op='scan',params=p);detail='scan stopped; partial records retained: Server chunk is not loaded: 1 3'
  r=dict(id='read',op='scan',phase='waiting',detail=detail,world_session='w',scan_coherent=False,scan_total_cells=8,scan_cells_read=3,pos=[4,5,6],scan_start_revision=7,scan_end_revision=7)
  e=dict(request_id='read',world_session='w',op='scan',phase='waiting',detail=detail,params=dict(p,task_session='t'),inventory_delta={},health_before=20,health_after=20,position_before=[4,5,6],position_after=[4,5,6],revision_before=7,revision_after=7)
  s=dict(connected=True,world_session='w',manual_movement=False,screen='',health=20,pos=[4,5,6],control_revision=7,last_request='read')
  return c,r,e,s
 def test_partial_cells_remain_unproved_and_only_allow_current_observation(self):
  c,r,e,s=self.fixture();self.assertTrue(observable(c,r,e,s,'w','t'));self.assertEqual(r['scan_cells_read'],3)
 def test_mutation_changed_scope_or_live_read_refuses(self):
  for which,change in [('c',{'op':'mine_block'}),('r',{'scan_cells_read':8}),('r',{'scan_coherent':True}),('r',{'phase':'running'}),('r',{'scan_end_revision':8}),('e',{'inventory_delta':{'minecraft:cobblestone':1}}),('e',{'position_after':[5,5,6]}),('s',{'world_session':'old'}),('s',{'manual_movement':True}),('s',{'pending_scan':True}),('s',{'health':19})]:
   c,r,e,s=self.fixture();{'c':c,'r':r,'e':e,'s':s}[which].update(change)
   with self.subTest(which=which,change=change):self.assertFalse(observable(c,r,e,s,'w','t'))
 def test_queue_keeps_original_read_and_never_replays_scan_or_world_input(self):
  c,r,e,s=self.fixture()
  with tempfile.TemporaryDirectory()as directory:
   q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.status=lambda:s;d=q.out/c['id'];d.mkdir();(q.out/'control').mkdir();(q.out/'command.json').write_text(json.dumps(c));original=json.dumps(r);(d/'result.json').write_text(original);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n');sent=[];q.native=lambda op:sent.append(op)
   q.observe_unloaded_scan();self.assertEqual(sent,['snapshot']);self.assertEqual((d/'result.json').read_text(),original)
   (q.out/'control/unconfirmed-native-request.json').write_text('{}')
   with self.assertRaises(RuntimeError):q.observe_unloaded_scan()
if __name__=='__main__':unittest.main()
