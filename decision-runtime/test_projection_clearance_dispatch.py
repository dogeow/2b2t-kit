import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from contextlib import nullcontext
from types import SimpleNamespace

from test_material_jobs import FakeBackend
from material_jobs import MaterialJob
from material_jobs.protocol import JobBlocked
from material_jobs.projection_clearance import capture, possible, verified_progress


def terrain(air=False):
    return {'pos':[1,64,1], 'actual':'Block{minecraft:dirt}',
            'expected':'Block{minecraft:air}' if air else 'Block{minecraft:cobblestone}',
            'kind':'enclosed_air_candidate' if air else 'occupied',
            'block_entity':False, 'fluid':False, 'adjacent_fluid':False, 'neighbors_loaded':True}


class ClearanceBackend(FakeBackend):
    def __init__(self, air=False, lie=False):
        super().__init__(object(), held={'minecraft:cobblestone':1}, projection={} if air else {'minecraft:cobblestone':1})
        if air:
            self.total=self.matched=1
        self.air,self.lie,self.terrain,self.tick=air,lie,True,1000

    def observe(self):
        s=super().observe();self.tick+=1
        row=terrain(self.air)
        s.update(time=self.tick,flight=True,screen='',projection_selection={'key':'ship','min':[0,60,0],'max':[8,70,8]})
        a=s['projection_audit'];a.update(audit_schema=2,server='example.test',dimension='minecraft:overworld',observed_at=self.tick,
                                       mismatches=([row] if self.terrain else [] if self.matched==self.total else [{**row,'actual':'Block{minecraft:air}','kind':'missing'}]) if not self.air else [],
                                       enclosed_air_conflicts=[row] if self.air and self.terrain else [])
        return s

    def has_projection_clearance(self, state):
        return self.terrain

    def build(self,key):
        if not self.terrain:
            return super().build(key)
        self.calls.append(('clear',key))
        if not self.lie:
            self.terrain=False;self.held['minecraft:dirt']+=1
        return {'phase':'done','clearance_confirmations':[{'pos':[1,64,1], 'old_state':'Block{minecraft:dirt}',
                'request_id':'native-one','world_session':'world','server_confirmed':True,'native_sequence':1,'server_ack_sequence':1}]}


def request():
    return {'schema':1,'id':'clear-job','mode':'projection','targets':{},'projection_key':'ship',
            'context':{'server':'example.test','dimension':'minecraft:overworld','world_session':'world',
                       'expected_revision':1,'start_pos':[0,64,0]},'created_at':1000}


class ProjectionClearanceDispatchTests(unittest.TestCase):
    def test_real_backend_clears_without_an_unnecessary_outside_round_trip(self):
        from material_jobs_backend import Backend
        f=ClearanceBackend();state=f.observe();state['pos']=[2.5,65,2.5]
        before=copy.deepcopy(state['projection_audit']);f.terrain=False;after=f.observe()['projection_audit']
        c=SimpleNamespace(status=lambda:copy.deepcopy(state))
        with tempfile.TemporaryDirectory()as d:
            b=object.__new__(Backend);b.root=Path(d);b.audit=before;b.request=request()
            b.action=Mock(return_value=nullcontext((c,Path(d))));b.ensure_client=Mock(return_value=c)
            b.refresh_audit=Mock(side_effect=[before,after]);b.prepare_travel=Mock()
            proof={'pos':[1,64,1],'old_state':'Block{minecraft:dirt}','request_id':'one','world_session':'world',
                   'server_confirmed':True,'native_sequence':1,'server_ack_sequence':1}
            with patch('material_jobs.construction_access.recover_pending'),patch('projection_terrain.candidates',return_value=[terrain()]),\
                 patch('projection_terrain.clear_batch',return_value={'removed':[terrain()],'confirmed_removals':[proof]}),\
                 patch('goal_workflow.build_phase')as printer:
                result=b.build('ship')
            self.assertEqual([proof],result['clearance_confirmations'])
            b.prepare_travel.assert_not_called();printer.assert_not_called()

    def test_one_worker_clears_then_prints_existing_stock_without_agent_or_extra_supply(self):
        b=ClearanceBackend()
        with tempfile.TemporaryDirectory()as d:
            result=MaterialJob(request(),d,b).run()
            self.assertEqual('completed',result['state']);self.assertEqual(0,result['ai_calls'])
            self.assertEqual(['clear','build'],[v[0]for v in b.calls]);self.assertEqual(1,b.finish_count)
            self.assertFalse((Path(d)/'inflight.json').exists())

    def test_internal_air_cleanup_is_scheduled_before_false_completion(self):
        b=ClearanceBackend(air=True)
        with tempfile.TemporaryDirectory()as d:
            result=MaterialJob(request(),d,b).run()
        self.assertEqual('completed',result['state']);self.assertEqual([('clear','ship')],b.calls)

    def test_unchanged_terrain_receipts_do_not_keep_a_stuck_worker_alive(self):
        b=ClearanceBackend(lie=True)
        with tempfile.TemporaryDirectory()as d:
            result=MaterialJob(request(),d,b).run()
        self.assertEqual('blocked',result['state']);self.assertEqual(2,len(b.calls));self.assertTrue(b.terrain)

    def test_progress_needs_fresh_changed_world_and_matching_native_receipt(self):
        b=ClearanceBackend();before=capture(b.observe()['projection_audit']);receipt=b.build('ship');after=b.observe()['projection_audit']
        self.assertTrue(verified_progress(before,after,receipt,'world'))
        for field,value in [('server_confirmed',False),('server_ack_sequence',2),('world_session','other'),('pos',[9,9,9])]:
            r=copy.deepcopy(receipt);r['clearance_confirmations'][0][field]=value
            self.assertFalse(verified_progress(before,after,r,'world'))
        a=copy.deepcopy(after);a['observed_at']=before['observed_at'];self.assertFalse(verified_progress(before,a,receipt,'world'))
        a=copy.deepcopy(after);a['mismatches']=[terrain()];self.assertFalse(verified_progress(before,a,receipt,'world'))

    def test_shared_pending_receipt_is_filtered_even_after_world_reconnect(self):
        b=ClearanceBackend();state=b.observe();audit=state['projection_audit'];state.update(server='example.test',dimension='minecraft:overworld')
        with tempfile.TemporaryDirectory()as d:
            self.assertTrue(possible(audit,state,d))
            folder=Path(d)/'projection-terrain-intents';folder.mkdir()
            (folder/'old.json').write_text(json.dumps({'scope':{'server':'example.test','dimension':'minecraft:overworld','projection_key':'ship','pos':[1,64,1]},'world_session':'old-world','pending':{'request_id':'uncertain'}}))
            self.assertFalse(possible(audit,state,d))

    def test_old_projection_claim_still_protects_the_same_world_cell(self):
        b=ClearanceBackend();state=b.observe();audit=state['projection_audit']
        with tempfile.TemporaryDirectory()as d:
            folder=Path(d)/'projection-terrain-intents';folder.mkdir()
            (folder/'old.json').write_text(json.dumps({'scope':{'server':'example.test','dimension':'minecraft:overworld','projection_key':'previous-project','pos':[1,64,1]},'pending':{'request_id':'uncertain'}}))
            self.assertFalse(possible(audit,state,d))

    def test_foreign_audit_and_unreadable_claim_never_authorize_clearance(self):
        b=ClearanceBackend();state=b.observe();audit=state['projection_audit']
        with tempfile.TemporaryDirectory()as d:
            a=copy.deepcopy(audit);a['server']='other.test';self.assertFalse(possible(a,state,d))
            folder=Path(d)/'projection-terrain-intents';folder.mkdir();(folder/'broken.json').write_text('{')
            with self.assertRaises(JobBlocked):possible(audit,state,d)

    def test_wet_or_unloaded_hints_do_not_enable_ordinary_dry_clearance(self):
        b=ClearanceBackend();state=b.observe();audit=state['projection_audit']
        with tempfile.TemporaryDirectory()as d:
            audit['mismatches'][0]['adjacent_fluid']=True;self.assertFalse(possible(audit,state,d))
            audit['mismatches'][0]['adjacent_fluid']=False;audit['loaded_chunks_verified']=False;self.assertFalse(possible(audit,state,d))
