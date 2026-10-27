import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from village_queue import VillageQueue
from kit_runtime.journal import write_json

class ExchangeShortageTests(unittest.TestCase):
 def setup_case(self,directory):
  q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'};q.prefix='observe';q.index=0;q.closing_menu=None
  d=q.out/'old';d.mkdir();(q.out/'control').mkdir();write_json(q.out/'command.json',{'id':'old','action':'exchange','withdraw':{'minecraft:iron_block':1,'minecraft:cherry_button':4}})
  result={'complete':False,'remaining_deposit':{},'remaining_withdraw':{'minecraft:cherry_button':4},'visited':[{'after':{'minecraft:iron_block':1}}]};write_json(d/'result.json',result)
  event={'request_id':'last','op':'close_menu','phase':'done','world_session':'w','revision_after':4,'params':{'task_session':'t'},'inventory_delta':{},'health_after':20};state={'last_request':'last','control_revision':4,'screen':'','health':20,'manual_movement':False,'inventory':[{'slot':0,'item':'minecraft:iron_block','count':1}]};q.status=lambda **kw:state
  (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,d,event,state,result
 def test_partial_receipt_retained_and_only_snapshot_dispatched(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e,s,r=self.setup_case(directory);original=(d/'result.json').read_bytes();sent=[]
   with self.assertRaises(RuntimeError):q._send('native',op='snapshot',params={})
   def owner(path,value):
    write_json(path,value)
    if Path(path).name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_exchange_shortage()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(original,(d/'result.json').read_bytes());self.assertIsNone(q._exchange_shortage_read)
 def test_rejects_unknown_changed_inventory_owner_or_active_action(self):
  for change in ['unknown','inventory','owner','revision','active','health','manual','screen','event','deposit']:
   with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
    q,d,e,s,r=self.setup_case(directory)
    if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if change=='inventory':s['inventory'][0]['count']=2
    if change=='owner':e['params']['task_session']='other'
    if change=='revision':s['control_revision']=5
    if change=='active':s['native_material_busy']=True
    if change=='health':s['health']=19
    if change=='manual':s['manual_movement']=True
    if change=='screen':s['screen']='ContainerScreen'
    if change=='event':e['op']='interact'
    if change=='deposit':r['remaining_deposit']={'minecraft:iron_block':1}
    write_json(d/'result.json',r);(q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
    with self.assertRaises(RuntimeError):q.observe_exchange_shortage()
    self.assertFalse((q.out/'observe-001').exists())
 def test_partial_deposit_observes_exact_kept_totals_without_replaying(self):
  with tempfile.TemporaryDirectory()as directory:
   q,d,e,s,r=self.setup_case(directory);command=json.loads((q.out/'command.json').read_text());command['deposit']={'minecraft:acacia_planks':1};write_json(q.out/'command.json',command)
   s['inventory'].append({'slot':1,'item':'minecraft:acacia_planks','count':3});r['visited'][-1]['after']['minecraft:acacia_planks']=3;r['remaining_deposit']={'minecraft:acacia_planks':2};write_json(d/'result.json',r);raw=(d/'result.json').read_bytes();sent=[]
   def owner(path,value):
    write_json(path,value)
    if path.name=='command.json':
     sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done'})
   with patch('village_queue.write_json',side_effect=owner):q.observe_exchange_shortage()
   self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(raw,(d/'result.json').read_bytes())
 def test_recorded_storage_exit_walk_keeps_partial_transfer_and_only_observes(self):
  for change in ['none','position','moving','airborne','missing_close','intermediate_delta','wrong_owner','unknown']:
   with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
    q,d,close,s,r=self.setup_case(directory);command=json.loads((q.out/'command.json').read_text());command['profile']='known-storage.json';write_json(q.out/'command.json',command)
    close['request_id']='close';walk=dict(close,request_id='last',op='walk',position_after=[.5,65,.5]);s.update(pos=[.7,64.125,.8],on_ground=True,flight=False,movement_keys={'forward':False})
    if change=='position':s['pos'][0]=2
    if change=='moving':s['movement_keys']['forward']=True
    if change=='airborne':s['on_ground']=False
    if change=='intermediate_delta':close['inventory_delta']={'minecraft:iron_block':1}
    if change=='wrong_owner':close['params']={'task_session':'other'}
    if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    events=[walk]if change=='missing_close'else[close,walk];(q.out/'control/events.jsonl').write_text(''.join(json.dumps(v)+'\n'for v in events));sent=[];original=(d/'result.json').read_bytes()
    def owner(path,value):
     write_json(path,value)
     if path.name=='command.json':
      sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done'})
    with patch('village_queue.write_json',side_effect=owner):
     if change=='none':q.observe_exchange_shortage()
     else:
      with self.assertRaises(RuntimeError):q.observe_exchange_shortage()
    self.assertEqual(['snapshot']if change=='none'else[],[v['op']for v in sent]);self.assertEqual(original,(d/'result.json').read_bytes())

 def test_air_only_exit_is_observation_only_and_preserves_partial_receipt(self):
  for changed in ['none','ground_route','delta','owner','position','unknown']:
   with self.subTest(changed=changed),tempfile.TemporaryDirectory()as directory:
    q,d,close,state,r=self.setup_case(directory);command=json.loads((q.out/'command.json').read_text());command['profile']='known-storage.json';write_json(q.out/'command.json',command)
    close['request_id']='close';event=dict(close,request_id='last',op='navigate',position_after=[.5,89,.5],params={'task_session':'t','air_only':True});state.update(pos=[.5,88.9,.5],flight=True,on_ground=False,movement_keys={'forward':False})
    if changed=='ground_route':event['params']['air_only']=False
    if changed=='delta':close['inventory_delta']={'minecraft:diamond':1}
    if changed=='owner':event['params']['task_session']='other'
    if changed=='position':state['pos'][0]=3
    if changed=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    (q.out/'control/events.jsonl').write_text(json.dumps(close)+'\n'+json.dumps(event)+'\n');sent=[];original=(d/'result.json').read_bytes()
    def owner(path,value):
     write_json(path,value)
     if path.name=='command.json':
      sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done'})
    with patch('village_queue.write_json',side_effect=owner):
     if changed=='none':q.observe_exchange_shortage()
     else:
      with self.assertRaises(RuntimeError):q.observe_exchange_shortage()
    self.assertEqual(['snapshot']if changed=='none'else[],[v['op']for v in sent]);self.assertEqual(original,(d/'result.json').read_bytes())

if __name__=='__main__':unittest.main()
