import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_village_queue
from kit_runtime.journal import write_json

class UnstartedMineTests(unittest.TestCase):
 def case(self,directory):
  q,d,event,state=test_village_queue.VillageQueueTests().stopped_walk(directory)
  command={'id':'old','action':'native','op':'mine_block','params':{'pos':[4,2,3],'expected_state':'Block{minecraft:cobblestone}','seconds':10}}
  reply={'id':'native-old','world_session':'w','op':'mine_block','phase':'waiting','detail':'mining target is occluded','pos':state['pos'],'mining_target':[4,2,3],'native_sequence':-1,'server_ack_sequence':-1,'server_update_seen':False,'server_confirmed':False,'outcome_pending':False}
  event.update(op='mine_block',detail=reply['detail'],position_before=state['pos'],params={'task_session':'t',**command['params']})
  write_json(q.out/'command.json',command);write_json(d/'result.json',reply);(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,d,event,state,reply
 def test_observes_only_preserving_original_mining_receipt(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,event,state,reply=self.case(directory);original=(d/'result.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_unstarted_occluded_mine()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(original,(d/'result.json').read_bytes())
 def test_started_unknown_pending_changed_target_or_owner_stays_fenced(self):
  for mode in ['started','pending','ack','unknown','target','moved','health','task','revision']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,event,state,reply=self.case(directory)
    if mode=='started':reply['native_sequence']=0
    if mode=='pending':reply['outcome_pending']=True
    if mode=='ack':reply['server_ack_sequence']=0
    if mode=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mode=='target':reply['mining_target']=[9,2,3]
    if mode=='moved':event['position_before']=[1,2,3]
    if mode=='health':event['health_after']=19
    if mode=='task':event['params']['task_session']='other'
    if mode=='revision':state['control_revision']=9
    write_json(d/'result.json',reply);(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
    with self.assertRaises(RuntimeError):q.observe_unstarted_occluded_mine()
    self.assertFalse((q.out/'walk-observe-001').exists())

class AirPreflightDriftTests(unittest.TestCase):
 def case(self,directory):
  q,d,event=test_village_queue.VillageQueueTests().air_refusal(directory);d.rename(q.out/'route-002');d=q.out/'route-002'
  write_json(q.out/'command.json',{'id':'route-002','action':'native','op':'navigate','params':{'air_only':True}})
  old=q.out/'route-001';old.mkdir();write_json(old/'intent.json',{'id':'route-001','action':'native','op':'walk','params':{'target':[1,2,3]}})
  done={'id':'walk-native','world_session':'w','phase':'done','pos':[1,2,3]};write_json(old/'result.json',done)
  prior={'request_id':'walk-native','world_session':'w','op':'walk','phase':'done','inventory_delta':{},'health_before':20,'health_after':20,'position_before':[0,2,3],'position_after':[1,2,3],'time':100,'revision_after':4,'params':{'task_session':'t','target':[1,2,3]}}
  event['time']=101;event['position_after']=[1.25,2,3];reply=json.loads((d/'result.json').read_text());reply.update(pos=[1.25,2,3],control_revision=4);write_json(d/'result.json',reply)
  state={'screen':'','last_request':'native-old','pos':[1.26,2,3],'control_revision':4,'health':20,'flight':False,'movement_keys':{'forward':False}};q.status=lambda **kw:state
  return q,d,event,prior,state,old
 def test_only_observes_known_small_horizontal_drift_after_completed_walk(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,event,prior,state,old=self.case(directory);(q.out/'control/events.jsonl').write_text('\n'.join(map(json.dumps,[prior,event]))+'\n');sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_refused_air_path()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertTrue((d/'result.json').exists())
 def test_unexplained_movement_or_changed_walk_stays_fenced(self):
  for mode in ['no_walk','task','active','vertical','revision','large']:
   with self.subTest(mode=mode),tempfile.TemporaryDirectory()as directory:
    q,d,event,prior,state,old=self.case(directory)
    if mode=='no_walk':(old/'result.json').unlink()
    if mode=='task':prior['params']['task_session']='other'
    if mode=='active':state['movement_keys']['forward']=True
    if mode=='vertical':event['position_after'][1]=2.1
    if mode=='revision':state['control_revision']=5
    if mode=='large':state['pos']=[2,2,3]
    (q.out/'control/events.jsonl').write_text('\n'.join(map(json.dumps,[prior,event]))+'\n')
    with self.assertRaises(RuntimeError):q.observe_refused_air_path()
    self.assertFalse((q.out/'observe-001').exists())

if __name__=='__main__':unittest.main()
