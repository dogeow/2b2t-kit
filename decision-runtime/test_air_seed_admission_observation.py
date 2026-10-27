import json,tempfile,unittest
from pathlib import Path
from village_queue import VillageQueue
class AdmissionObservationTest(unittest.TestCase):
 def test_only_snapshots_a_known_unmoved_unconsumed_seed_refusal(self):
  for mutation in [None,'unknown','moved','consumed','foreign','later_error','hurt']:
   with self.subTest(mutation=mutation),tempfile.TemporaryDirectory()as tmp:
    q=VillageQueue.__new__(VillageQueue);q.out=Path(tmp);q.world='w';q.lease={'job_session':'t'};(q.out/'control').mkdir();(q.out/'c-001').mkdir();detail='Air seed requires the current healthy idle guarded material lease';command={'id':'c-001','action':'native','op':'projection_air_seed','params':{'target':[1,64,2]}};reply={'id':'n','world_session':'w','phase':'error','detail':detail};event={'request_id':'n','world_session':'w','op':'projection_air_seed','phase':'error','detail':detail,'inventory_delta':{},'position_before':[1.5,67.1,2.5],'position_after':[1.5,67.1,2.5],'revision_before':4,'revision_after':4,'params':{'task_session':'t'}};state={'health':20,'manual_movement':False,'screen':'','last_request':'n'}
    if mutation=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
    if mutation=='moved':event['position_after']=[2,67,2]
    if mutation=='consumed':event['inventory_delta']={'minecraft:cobblestone':-1}
    if mutation=='foreign':reply['world_session']='other'
    if mutation=='later_error':reply['detail']='Air seed target is occluded'
    if mutation=='hurt':state['health']=19
    (q.out/'command.json').write_text(json.dumps(command));(q.out/'c-001/result.json').write_text(json.dumps(reply));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');sent=[];q.status=lambda:state;q.native=lambda op:sent.append(op)
    if mutation:
     with self.assertRaises(RuntimeError):q.observe_refused_air_seed()
    else:q.observe_refused_air_seed()
    self.assertEqual([]if mutation else['snapshot'],sent)
