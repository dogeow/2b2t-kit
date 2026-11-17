import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from test_village_queue import VillageQueueTests
from kit_runtime.journal import write_json

class WalkStepRefusalTests(unittest.TestCase):
    def test_only_exact_conserved_refusal_permits_snapshot(self):
        for bad in (None,'inventory','revision','position','held','airborne','health','world','unknown','detail'):
            with self.subTest(bad=bad), tempfile.TemporaryDirectory() as directory:
                q,d,event,state=VillageQueueTests().stopped_walk(directory)
                reply=json.loads((d/'result.json').read_text()); detail='Ordinary walking requires a supported step within 1.1 blocks; Flight was not disabled'
                reply.update(phase='error',detail=detail);event.update(phase='error',detail=detail,revision_before=8);state.update(health=20,on_ground=True,flight=False)
                if bad=='inventory': event['inventory_delta']={'minecraft:stone':1}
                if bad=='revision': event['revision_before']=7
                if bad=='position': state['pos']=[4,2,3]
                if bad=='held': state['movement_keys']['forward']=True
                if bad=='airborne': state['on_ground']=False
                if bad=='health': state['health']=19
                if bad=='world': event['world_session']='other'
                if bad=='unknown': (q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if bad=='detail': reply['detail']='other'
                write_json(d/'result.json',reply);(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');sent=[]
                def owner(path,value):
                    write_json(path,value)
                    if Path(path).name=='command.json':
                        sent.append(value);new=q.out/value['id'];new.mkdir();write_json(new/'result.json',{'phase':'done','world_session':'w'})
                with patch('village_queue.write_json',side_effect=owner):
                    if bad:
                        with self.assertRaises(RuntimeError):q.observe_stopped_walk()
                    else:q.observe_stopped_walk()
                self.assertEqual([] if bad else ['snapshot'],[v['op'] for v in sent])
    def test_small_grounded_coast_requires_two_identical_fresh_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            q,d,event,state=VillageQueueTests().stopped_walk(directory)
            detail='Ordinary walking requires a supported step within 1.1 blocks; Flight was not disabled'
            reply=json.loads((d/'result.json').read_text());reply.update(phase='error',detail=detail);event.update(phase='error',detail=detail,revision_before=8)
            state.update(pos=[2.01,2,3],health=20,on_ground=True,flight=False,time=1)
            (d/'result.json').write_text(json.dumps(reply));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
            states=iter([state,{**state,'time':2}]);q.status=lambda **kw:next(states);sent=[];q.native=lambda op:sent.append(op)
            q.observe_stopped_walk();self.assertEqual(sent,['snapshot'])
if __name__=='__main__':unittest.main()
