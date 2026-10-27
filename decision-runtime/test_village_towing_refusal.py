import json
from pathlib import Path
import tempfile
import unittest
from village_queue import VillageQueue


class TowingRefusalTests(unittest.TestCase):
    def fixture(self, directory):
        q=VillageQueue.__new__(VillageQueue);q.out=Path(directory);q.world='w';q.lease={'job_session':'t'}
        state={'connected':True,'world_session':'w','health':20,'pos':[1,2,3],'id':'r','last_request':'r',
               'phase':'error','detail':'Air-only navigation requires the current material lease and a loaded clear dry path',
               'movement_keys':{'forward':False},'manual_movement':False,'screen':''}
        q.status=lambda:state
        (q.out/'command.json').write_text(json.dumps({'id':'old','action':'tow_villager_boat'}))
        d=q.out/'old';(d/'actual-villager-towing').mkdir(parents=True);(q.out/'control').mkdir()
        error={'error':'Original towing leg did not complete; retain it without replay','native_inflight':None,'unconfirmed_native_request':None,'last_request':'r'}
        (d/'error.json').write_text(json.dumps(error))
        path=d/'actual-villager-towing/tow.json'
        path.write_text(json.dumps({'world_session':'w','pending':{'op':'navigate','request_id':'r','from':[1,2,3],'target':[1,4,3]},'complete':False,'legs':[]}))
        event={'request_id':'r','world_session':'w','op':'navigate','phase':'error','detail':state['detail'],
               'position_before':[1,2,3],'position_after':[1,2,3],'inventory_delta':{},'revision_before':4,'revision_after':4,
               'params':{'task_session':'t','target':[1,4,3]}}
        (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
        return q,state,path,d/'error.json',event

    def test_only_snapshot_and_retains_refused_leg_without_credit(self):
        with tempfile.TemporaryDirectory()as directory:
            q,state,path,error,event=self.fixture(directory);original=error.read_bytes();calls=[]
            q.native=lambda op: calls.append(op)or{'id':'read','world_session':'w','pos':[1,2,3],'health':20}
            result=q.observe_refused_towing_air_path();book=json.loads(path.read_text())
            self.assertEqual(calls,['snapshot']);self.assertIsNone(book['pending']);self.assertEqual(book['legs'],[])
            self.assertEqual(result['movement_credit'],0);self.assertEqual(error.read_bytes(),original)
            self.assertEqual(book['refused_legs'][0]['original_pending']['request_id'],'r')

    def test_unknown_movement_or_changed_revision_preserves_pending(self):
        for kind in('unknown','position','revision'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory()as directory:
                q,state,path,error,event=self.fixture(directory);original=path.read_bytes();q.native=lambda _:self.fail('no read authorized')
                if kind=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if kind=='position':state['pos']=[2,2,3]
                if kind=='revision':event['revision_after']=5;(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
                with self.assertRaises(RuntimeError):q.observe_refused_towing_air_path()
                self.assertEqual(path.read_bytes(),original)


if __name__=='__main__':unittest.main()
