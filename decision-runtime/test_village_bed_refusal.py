import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from village_queue import VillageQueue
from kit_runtime.journal import write_json

class BedRefusalTests(unittest.TestCase):
 def case(self,directory):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.prefix='observe';q.index=0;q.closing_menu=None
  d=q.out/'old';d.mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',{'id':'old','action':'place_bed','foot':[3,1,3],'facing':'west'})
  error={'error':'An entity intersects the new bed; no placement','last_request':'scan','native_inflight':None,'unconfirmed_native_request':None};write_json(d/'error.json',error)
  event={'request_id':'scan','op':'scan','phase':'done','world_session':'w','revision_after':4,'position_before':[0,1,0],'position_after':[0,1,0],'inventory_delta':{},'health_before':20,'health_after':20,'params':{'min':[1,0,2],'max':[5,3,4],'task_session':'t'}};(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');q.status=lambda **kw:{'last_request':'scan','control_revision':4,'screen':''};return q,d,event
 def test_only_read_and_original_error_preserved(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e=self.case(directory);old=(d/'error.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if Path(path).name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_bed_entity_refusal()
   self.assertEqual(['snapshot'],[x['op']for x in sent]);self.assertEqual(old,(d/'error.json').read_bytes())
 def test_unknown_or_placement_or_other_scene_stays_fenced(self):
  for change in ['unknown','placement','bounds','owner','world','movement']:
   with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
    q,d,e=self.case(directory)
    if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if change=='placement':(d/'actual-directional-bed').mkdir()
    if change=='bounds':e['params']['min']=[0,0,0]
    if change=='owner':e['params']['task_session']='other'
    if change=='world':e['world_session']='other'
    if change=='movement':e['position_after']=[1,1,0]
    (q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
    with self.assertRaises(RuntimeError):q.observe_bed_entity_refusal()
    self.assertFalse((q.out/'observe-001').exists())
 def test_initial_space_refusal_only_observes_original_survey(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e=self.case(directory);error=json.loads((d/'error.json').read_text());error['error']='Bed halves and standing cell need empty body space over dry solid floors';write_json(d/'error.json',error);raw=(d/'error.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_bed_space_refusal()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(raw,(d/'error.json').read_bytes())
 def test_space_observer_rejects_other_error_or_started_placement(self):
  for mode in ['error','placement']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,e=self.case(directory)
    if mode=='placement':
     error=json.loads((d/'error.json').read_text());error['error']='Bed halves and standing cell need empty body space over dry solid floors';write_json(d/'error.json',error);(d/'actual-directional-bed').mkdir()
    with self.assertRaises(RuntimeError):q.observe_bed_space_refusal()
 def landing_case(self,directory):
  q,d,e=self.case(directory);d.rename(q.out/'bed-002');d=q.out/'bed-002';command=json.loads((q.out/'command.json').read_text());command['id']='bed-002';write_json(q.out/'command.json',command);err=json.loads((d/'error.json').read_text());err['error']='Bed halves and standing cell need empty body space over dry solid floors';write_json(d/'error.json',err)
  old=q.out/'bed-001';old.mkdir();params={'target':[0,1,0],'restore_flight':False};write_json(old/'intent.json',{'action':'native','op':'walk','params':params});write_json(old/'result.json',{'id':'walk','world_session':'w','phase':'done','pos':[0,1.1,0]});prior={'request_id':'walk','op':'walk','phase':'done','world_session':'w','params':{'task_session':'t',**params},'position_after':[0,1.1,0],'revision_after':4,'health_before':20,'health_after':20,'inventory_delta':{}}
  e.update(position_before=[0,1.1,0],revision_before=4);s={'last_request':'scan','control_revision':4,'screen':'','pos':[0,1,0],'health':20,'on_ground':True,'flight':False,'movement_keys':{'forward':False}};q.status=lambda **kw:s;return q,d,e,prior,s
 def test_completed_small_landing_only_allows_a_read(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e,prior,s=self.landing_case(directory);(q.out/'control/events.jsonl').write_text('\n'.join(map(json.dumps,[prior,e]))+'\n');sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_bed_space_refusal()
   self.assertEqual(['snapshot'],[v['op']for v in sent])
 def test_active_or_unexplained_landing_stays_fenced(self):
  for mode in ['keys','flight','missing_walk','horizontal','fall']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,e,prior,s=self.landing_case(directory)
    if mode=='keys':s['movement_keys']['forward']=True
    if mode=='flight':s['flight']=True
    if mode=='missing_walk':(q.out/'bed-001/result.json').unlink()
    if mode=='horizontal':e['position_after']=[.1,1,0];s['pos']=e['position_after']
    if mode=='fall':e['position_before']=[0,1.5,0]
    (q.out/'control/events.jsonl').write_text('\n'.join(map(json.dumps,[prior,e]))+'\n')
    with self.assertRaises(RuntimeError):q.observe_bed_space_refusal()
if __name__=='__main__':unittest.main()
