import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from stopped_air_pickup import observable
class StoppedPickupTests(unittest.TestCase):
 def case(self):
  item='minecraft:sugar_cane';inventory=lambda n:[{'slot':0,'item':item,'count':n}];source={'id':4,'uuid':'drop','type':'minecraft:item','pos':[2,62.5,3],'stack':{'item':item,'count':1}}
  command={'action':'native','op':'navigate','params':{'air_only':True,'target':[2,63.1,3]}};previous={'action':'native','op':'snapshot'}
  prior={'phase':'done','world_session':'w','control_revision':1,'pos':[0,64,3],'inventory':inventory(1),'entities':[source],'time':1000,'runtime_generation':0}
  reply={'phase':'waiting','detail':'air-only path changed; no blocks were excavated','world_session':'w','id':'r','control_revision':2,'pos':[2,62.95,3],'inventory':inventory(2)}
  state={**copy.deepcopy(reply),'last_request':'r','pos':[2,62.9,3],'health':20,'connected':True,'manual_movement':False,'screen':'','flight':True,'movement_keys':{'forward':False},'player_uuid':'player','entities':[]}
  event={'request_id':'r','op':'navigate','phase':'waiting','detail':reply['detail'],'world_session':'w','params':{'task_session':'t','target':command['params']['target']},'revision_before':1,'revision_after':2,'position_before':prior['pos'],'position_after':reply['pos'],'health_before':20,'health_after':20,'inventory_delta':{item:1}}
  frame={'world_session':'w','runtime_generation':0,'world_entered_at':0,'time':2000,'events':[{'kind':'pickup_entities_unresolved','received_at':1500,'amount':1,'source_entity_id':4,'collector_entity_id':5,'collector':{'entity_id':5,'uuid':'player','type':'minecraft:player','pos':[2,63.2,3]}}]}
  return command,reply,previous,prior,event,state,frame,'w','t','drop'
 def test_exact_joined_server_collector_allows_observation(self):self.assertTrue(observable(*self.case()))
 def test_mismatched_or_unknown_receipts_do_not_allow_observation(self):
  for change in ['other_collector','old_packet','two_packets','generation','world','different_stock','other_delta','moving','drift','hurt','wrong_previous','running','missing_source','source_remains','ambiguous_source']:
   with self.subTest(change=change):
    args=list(copy.deepcopy(self.case()));command,reply,previous,prior,event,state,frame=args[:7]
    if change=='other_collector':frame['events'][0]['collector']['uuid']='other'
    if change=='old_packet':frame['events'][0]['received_at']=900
    if change=='two_packets':frame['events'].append(copy.deepcopy(frame['events'][0]))
    if change=='generation':frame['runtime_generation']=1
    if change=='world':reply['world_session']='other'
    if change=='different_stock':state['inventory'][0]['count']=3
    if change=='other_delta':event['inventory_delta']={'minecraft:emerald':-1}
    if change=='moving':state['movement_keys']['forward']=True
    if change=='drift':state['pos'][0]+=1
    if change=='hurt':state['health']=19
    if change=='wrong_previous':previous['op']='interact'
    if change=='running':reply['phase']='running'
    if change=='missing_source':prior['entities']=[]
    if change=='source_remains':state['entities']=copy.deepcopy(prior['entities'])
    if change=='ambiguous_source':prior['entities'].append({**copy.deepcopy(prior['entities'][0]),'uuid':'other','id':6})
    self.assertFalse(observable(*args))
 def test_pruned_packet_does_not_erase_conserved_native_inventory_evidence(self):
  args=list(self.case());args[6]=None;self.assertTrue(observable(*args))
  args[6]={'world_session':'w','runtime_generation':0,'events':[]};self.assertTrue(observable(*args))
 def test_raw_native_snapshot_has_no_phase_but_requires_connected_identity(self):
  args=list(self.case());args[3].pop('phase');args[3].update(id='snapshot',connected=True);self.assertTrue(observable(*args))
  args[3]['connected']=False;self.assertFalse(observable(*args))
 def test_queue_reads_once_retains_original_stop_and_rejects_unknown_native_request(self):
  from village_queue import VillageQueue
  for unknown in [False,True]:
   with self.subTest(unknown=unknown),tempfile.TemporaryDirectory()as directory:
    command,reply,previous,prior,event,state,frame,world,task,uid=self.case();q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.root=q.out;q.world=world;q.lease={'job_session':task};q.status=lambda:state;sent=[];q.native=lambda op:sent.append(op)
    command['id']='route-002';previous['id']='route-001';(q.out/'control').mkdir();(q.out/'command.json').write_text(json.dumps(command));d=q.out/command['id'];d.mkdir();p=q.out/previous['id'];p.mkdir();(d/'result.json').write_text(json.dumps(reply));(p/'result.json').write_text(json.dumps(prior));(p/'intent.json').write_text(json.dumps(previous));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');original=(d/'result.json').read_bytes()
    if unknown:(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    with patch('villager_events.read',return_value=frame):
     if unknown:
      with self.assertRaises(RuntimeError):q.observe_stopped_air_pickup(uid)
     else:q.observe_stopped_air_pickup(uid)
    self.assertEqual(sent,[]if unknown else['snapshot']);self.assertEqual(original,(d/'result.json').read_bytes())
if __name__=='__main__':unittest.main()
