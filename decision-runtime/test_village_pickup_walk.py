import json,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
import test_village_queue as base

class PickupWalkTests(unittest.TestCase):
    def case(self,directory):
        q,d,event,state=base.VillageQueueTests().stopped_walk(directory)
        d.rename(q.out/'walk-002');d=q.out/'walk-002'
        command=json.loads((q.out/'command.json').read_text());command['id']='walk-002'
        (q.out/'command.json').write_text(json.dumps(command))
        inventory=lambda n:[{'slot':0,'item':'minecraft:dark_oak_slab','count':n}]
        reply=json.loads((d/'result.json').read_text());reply.update(phase='stopped',detail='脚本任务达到时间上限',control_revision=8,inventory=inventory(2))
        (d/'result.json').write_text(json.dumps(reply))
        p=q.out/'walk-001';p.mkdir();prior={'phase':'done','world_session':'w','pos':event['position_before'],'control_revision':7,'inventory':inventory(1)}
        (p/'intent.json').write_text(json.dumps({'action':'native','op':'scan'}));(p/'result.json').write_text(json.dumps(prior))
        event.update(phase=reply['phase'],detail=reply['detail'],revision_before=7,inventory_delta={'minecraft:dark_oak_slab':1})
        state.update(world_session='w',health=20,screen='',on_ground=True,flight=False,phase='waiting',detail='time limit reached; inspect progress before resuming',pos=[2.05,1.875,3],inventory=inventory(2))
        (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
        return q,d,event,state,reply,p

    def test_conserved_pickup_only_snapshots_and_preserves_original_receipt(self):
        from kit_runtime.journal import write_json as real_write
        with tempfile.TemporaryDirectory()as directory:
            q,d,event,state,reply,p=self.case(directory);original=(d/'result.json').read_bytes();sent=[]
            def owner(path,value):
                real_write(path,value)
                if Path(path).name=='command.json':
                    sent.append(value);new=q.out/value['id'];new.mkdir();real_write(new/'result.json',{'phase':'done','world_session':'w'})
            with patch('village_queue.write_json',side_effect=owner):q.observe_stopped_pickup_walk('minecraft:dark_oak_slab',1)
            self.assertEqual(['snapshot'],[v['op']for v in sent]);self.assertEqual(original,(d/'result.json').read_bytes())

    def test_unknown_debit_changed_pickup_motion_or_nonread_prior_stay_fenced(self):
        for change in ('unknown','debit','pickup','inventory','health','active','rising','far','revision','prior_input','reason'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
                q,d,event,state,reply,p=self.case(directory)
                if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if change=='debit':event['inventory_delta']={'minecraft:dark_oak_slab':-1}
                if change=='pickup':event['inventory_delta']={'minecraft:dark_oak_slab':2}
                if change=='inventory':state['inventory']=[{'item':'minecraft:dark_oak_slab','count':3}]
                if change=='health':event['health_after']=19
                if change=='active':state['movement_keys']['forward']=True
                if change=='rising':state['pos']=[2,2.01,3]
                if change=='far':state['pos']=[2.3,2,3]
                if change=='revision':state['control_revision']=9
                if change=='prior_input':(p/'intent.json').write_text(json.dumps({'action':'native','op':'interact'}))
                if change=='reason':reply['detail']='another stop';(d/'result.json').write_text(json.dumps(reply))
                (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
                with self.assertRaises(RuntimeError):q.observe_stopped_pickup_walk('minecraft:dark_oak_slab',1)
                self.assertEqual(0,q.index)

class LecternPreflightTests(unittest.TestCase):
    def case(self,directory):
        q,d,event=base.VillageQueueTests().air_refusal(directory)
        command={'id':'old','action':'native','op':'mine_block','params':{'reset_empty_lectern':True,'expected_villager_uuid':'v','expected_quote_opening':'quote','expected_offers_fingerprint':'fingerprint','expected_state':'Block{minecraft:lectern}[has_book=false]'}}
        (q.out/'command.json').write_text(json.dumps(command))
        detail='Lectern reset requires an empty lectern beside the same freshly quoted untraded librarian without a requested book'
        reply=json.loads((d/'result.json').read_text());reply['detail']=detail;(d/'result.json').write_text(json.dumps(reply));event.update(op='mine_block',detail=detail)
        (q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n');return q,d,event,reply
    def test_initial_lectern_policy_refusal_only_reads(self):
        with tempfile.TemporaryDirectory()as directory:
            q,d,event,reply=self.case(directory);sent=[];q.native=lambda op,**kw:sent.append(op)
            q.observe_refused_lectern_reset();self.assertEqual(['snapshot'],sent)
    def test_active_or_changed_policy_stop_is_not_initial_refusal(self):
        for change in ('waiting','inventory','revision','unknown','book'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as directory:
                q,d,event,reply=self.case(directory)
                if change=='waiting':reply['phase']='waiting';event['phase']='waiting'
                if change=='inventory':event['inventory_delta']={'minecraft:lectern':1}
                if change=='revision':event['revision_after']=5
                if change=='unknown':(q.out/'control/unconfirmed-native-request.json').write_text('{}')
                if change=='book':
                    p=q.out/'command.json';v=json.loads(p.read_text());v['params']['expected_state']='Block{minecraft:lectern}[has_book=true]';p.write_text(json.dumps(v))
                (d/'result.json').write_text(json.dumps(reply));(q.out/'control/events.jsonl').write_text(json.dumps(event)+'\n')
                with self.assertRaises(RuntimeError):q.observe_refused_lectern_reset()

class RetainedLecternTests(unittest.TestCase):
    def test_retained_target_blocks_floor_and_side_anchors_but_keeps_observation(self):
        from village_queue import VillageQueue
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);out=root/'owner';out.mkdir();q=VillageQueue.__new__(VillageQueue);q.world='w';q.out=out;q.status=lambda **kw:{'screen':'','hand':{'item':'minecraft:lectern'}};q.closing_menu=None
            (root/'unresolved-lectern-placement-870.json').write_text(json.dumps({'outcome_unresolved':True,'target':[4,2,3]}))
            q._dispatch=lambda *args:{'phase':'done'}
            for pos,face in [([4,1,3],'up'),([3,2,3],'east'),([4,2,3],'north')]:
                with self.assertRaisesRegex(RuntimeError,'Original lectern placement is unresolved'):
                    q._send('native',op='interact',params={'pos':pos,'face':face,'expected_hand':'minecraft:lectern'})
            self.assertEqual('done',q._send('native',op='snapshot',params={})['phase'])
            self.assertEqual('done',q._send('native',op='interact',params={'pos':[8,1,3],'face':'up','expected_hand':'minecraft:lectern'})['phase'])

if __name__=='__main__':unittest.main()
