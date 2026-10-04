"""High-only empty work is native-read evidence, never placement or a replay."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lighting_regions_cli import NativeBatch, RegionsWorker, RegionsPaused
from potato_farm import ENTITY_SCOPE_AT_SCAN_END
from test_lighting_regions_cli import profile, state


class HighPreflightTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.calls=[];self.work_calls=0;self.park_calls=0;self.clients=[]
        self.positive=False;self.failure=None;self.park_proven=True;self.waits=[]
        self.current=state()|{'pos':[2.5,95,2.5],'recent_hurt_at':1,'guard_busy':False,
            'player_uuid':'same-player','game_mode':'survival',
            'projection_selection':{'key':'same','min':[0,64,0],'max':[4,64,4]}}
        settings=profile();settings['regions']=settings['regions'][:1]
        settings['movement_bounds']['max'][1]=140
        self.owner=RegionsWorker(self.root,settings,observer=lambda:deepcopy(self.current))
        case=self
        def row(pos, *, dark=False):
            return {'pos':pos,'state':'Block{minecraft:grass_block}[snowy=false]',
                    'solid':True,'passable':False,'replaceable':False,'fluid':False,'block_entity':False,
                    'zombie_spawn_floor':dark,'zombie_block_light_risk':dark,
                    'spawn_block_light':0,'monster_spawn_block_light_limit':0}
        class Survey:
            def __init__(self,root,out,server,**kwargs):
                self.root=Path(root);self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True)
                self.world=case.current['world_session'];self.last=None
            def status(self):return deepcopy(case.current)
            def request(self,op,**params):
                case.calls.append((op,deepcopy(params),deepcopy(case.current['pos'])))
                assert op=='scan'
                low,high=params['min'],params['max'];self.last='scan-'+str(len(case.calls))
                blocks=[row([low[0],63,low[2]])]if low[1]==-64 else [row([0,63,0],dark=True)]
                if low[1]!=-64 and not case.positive:
                    blocks.append({**row([0,66,0]),'state':'Block{minecraft:stone}'})
                reply=deepcopy(case.current)|{'id':self.last,'phase':'done','blocks':blocks,
                    'scan_cells_read':math.prod(b-a+1 for a,b in zip(low,high)),
                    'scan_total_cells':math.prod(b-a+1 for a,b in zip(low,high)),
                    'scan_start_revision':case.current['control_revision'],
                    'scan_end_revision':case.current['control_revision'],'scan_started_at':1000,'scan_ended_at':1001,
                    'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END,'scan_entities':[]}
                if low[1]!=-64:
                    if case.failure=='partial':reply['scan_cells_read']-=1
                    elif case.failure=='foreign':reply['world_session']='foreign'
                    elif case.failure=='revision':reply['scan_end_revision']+=1
                    elif case.failure=='unloaded':reply.update(phase='waiting',scan_cells_read=0,detail='Server chunk is not loaded')
                    elif case.failure=='guard':case.current['guard_busy']=True
                    elif case.failure=='identity':case.current['projection_selection']['key']='foreign'
                    elif case.failure=='unknown':
                        self.native_inflight={'request_id':self.last,'op':'scan','world_session':self.world,
                            'task_session':self.task,'lease_id':self.heartbeat.id,'base_revision':self.rev,
                            'expected_revision':self.rev}
                        case.owner.gate(self.status(),self)
                        raise RuntimeError('Original native scan outcome unknown')
                    elif isinstance(case.failure,str)and case.failure.startswith('missing-detail:'):
                        reply['blocks'][0].pop(case.failure.split(':',1)[1])
                    elif case.failure=='contradictory-risk':reply['blocks'][0]['zombie_block_light_risk']=False
                    elif case.failure=='malformed-detail':reply['blocks'][0]['passable']=0
                return reply
        class Material(Survey):
            def __init__(self,root,out,server,park_target,**kwargs):
                super().__init__(root,out,server);self.task='owned-task';self.rev=case.current['control_revision']
                self.park_target=deepcopy(park_target);self.initial_park=deepcopy(park_target);self.native_inflight=None
                self.heartbeat=type('Beat',(),{'id':'owned-lease','close':lambda self:None})()
                case.clients.append(self)
                case.current['supervision_lease']={'id':'owned-lease','kind':'materials','world_session':self.world,
                    'job_session':self.task,'revision':self.rev,'remote_finish':'guard','park_target':deepcopy(park_target)}
            def raw(self,*args,**kwargs):return self.status()
            def request(self,op,**params):
                if op=='scan':return super().request(op,**params)
                case.calls.append((op,deepcopy(params),deepcopy(case.current['pos'])))
                self.last='native-'+str(len(case.calls))
                if op=='navigate':
                    case.current['pos']=list(params['target']);self.rev+=1
                    case.current['control_revision']=self.rev;case.current['supervision_lease']['revision']=self.rev
                elif op=='material_job_park':
                    case.current['supervision_lease']['park_target']=deepcopy(params['park_target'])
                    if case.failure=='anchor':case.current['supervision_lease']['id']='foreign'
                    if case.failure=='anchor_unknown':
                        self.native_inflight={'request_id':self.last,'op':op,'world_session':self.world,
                            'task_session':self.task,'lease_id':self.heartbeat.id,'base_revision':self.rev,
                            'expected_revision':self.rev}
                        case.owner.gate(self.status(),self)
                        raise RuntimeError('Original native anchor setter unknown')
                else:raise AssertionError('Unexpected interaction or cleanup operation '+op)
                return deepcopy(case.current)|{'phase':'done','id':self.last}
            def checked(self,op,**params):return self.request(op,**params)
            def park_near(self,s):return math.dist(s['pos'],self.park_target)<=2
            def start_progress(self,*args,**kwargs):pass
            def finish(self):raise AssertionError('No generic finish should run after uncertainty')
        class Runner:
            def __init__(self,c,low,high,limit,out,initial,**kwargs):
                self.c=c;self.out=Path(out);self.hurt=initial['recent_hurt_at']
                self.report={'placed':[],'progress':{},'park_native_confirmed':False}
            def save(self):(self.out/'report.json').write_text(json.dumps(self.report))
            def work(self):
                case.work_calls+=1
                self.report.update(placed=[{'real_fixture_placement':True}],remaining_unprotected_risk=0)
                self.report['progress']['eligible_candidates']=0
            def park(self):
                case.park_calls+=1;self.report['park_native_confirmed']=case.park_proven
                case.current['supervision_lease']['kind']='parking'
                (self.out/'final-snapshot.json').write_text(json.dumps(case.current));self.save()
            def scan(self,*args,**kwargs):raise AssertionError('High scan must retain raw terminal replies before validation')
        def travel(c,target,checkpoint,trace,**kwargs):
            checkpoint();before=c.status()['pos'];reply=c.request('navigate',target=target,air_only=True)
            trace.append({'from':before,'target':list(target),'request_id':c.last});return reply
        patches=[patch('material_client.Client',Survey),patch('material_client.MaterialClient',Material),
                 patch('lighting_regions_cli.LightingRun',Runner),
                 patch('material_jobs.acquisition._travel',side_effect=travel),
                 patch.object(NativeBatch,'wait_unresolved',side_effect=lambda c:case.waits.append(c.last))]
        for item in patches:item.start();self.addCleanup(item.stop)

    def dispatch(self):return self.owner.dispatch(0,self.owner.profile['regions'][0],audit=False)

    def test_empty_current_high_scan_records_actual_darkness_without_descent_or_credit(self):
        before=deepcopy(self.current['inventory']);result=self.dispatch()
        self.assertEqual(result['placed_verified'],0);self.assertEqual(result['unprotected_dark_floor'],1)
        self.assertEqual(self.work_calls,0);self.assertEqual(self.park_calls,1)
        self.assertTrue(result['park_native_confirmed']);self.assertIsNone(self.owner.book['pending'])
        self.assertEqual(self.current['inventory'],before)
        self.assertTrue(all(params['target'][1]>=95 for op,params,_ in self.calls if op=='navigate'))
        self.assertFalse(any(op=='interact'for op,_,_ in self.calls))
        directory=Path(result['directory']);report=json.loads((directory/'report.json').read_text())
        self.assertEqual(report['progress']['dark_floor_observation_stage'],'single_high_preflight_scan')
        self.assertNotIn('after',report);self.assertNotIn('before',report)
        self.assertEqual(report['high_work_preflight']['placement_credit'],0)
        self.assertFalse(report['high_work_preflight']['goal_complete'])
        client=self.clients[0];native=json.loads((directory/'high-preflight-native-anchor.json').read_text())
        self.assertEqual(client.park_target,native['supervision_lease']['park_target'])
        self.assertGreaterEqual(client.park_target[1],95)

    def test_positive_high_prediction_keeps_original_low_work_and_reported_verification(self):
        self.positive=True;result=self.dispatch()
        self.assertEqual(self.work_calls,1);self.assertEqual(result['placed_verified'],1)
        self.assertTrue(any(params['target'][1]==65.5 for op,params,_ in self.calls if op=='navigate'))
        directory=Path(result['directory'])
        self.assertTrue((directory/'low-work-arrival-route.json').exists())
        self.assertTrue((directory/'high-preflight-region.json').exists())
        anchor=json.loads((directory/'high-preflight-native-anchor.json').read_text())['supervision_lease']['park_target']
        low_plan=json.loads((directory/'low-work-arrival-height-plan.json').read_text())
        self.assertEqual(low_plan['safe_park'],anchor)
        self.assertEqual(self.clients[0].park_target,anchor)

    def test_partial_unloaded_foreign_unknown_guard_or_identity_never_descend_or_count_zero(self):
        for failure in ('partial','unloaded','foreign','revision','unknown','guard','identity','anchor','anchor_unknown'):
            with self.subTest(failure=failure):
                self.failure=failure;self.calls.clear();self.work_calls=0;self.park_calls=0
                self.current.update(guard_busy=False,projection_selection={'key':'same','min':[0,64,0],'max':[4,64,4]})
                self.current['supervision_lease']={};self.owner.book['pending']=None
                self.owner.book['last_revision']=None;self.owner.book['parking_lease']=None
                with self.assertRaises(RuntimeError):self.dispatch()
                pending=deepcopy(self.owner.book['pending'])
                self.assertIsNotNone(pending);self.assertEqual(self.work_calls,0);self.assertEqual(self.park_calls,0)
                self.assertEqual(self.owner.book['batches'],[])
                self.assertTrue(all(params['target'][1]>=95 for op,params,_ in self.calls if op=='navigate'))
                self.assertFalse(any(op=='interact'for op,_,_ in self.calls))
                if failure in ('unknown','anchor_unknown'):
                    self.assertEqual(pending['native_request']['op'],'scan'if failure=='unknown'else'material_job_park')
                    self.assertTrue(pending['native_request']['request_id'])
                    self.assertEqual(pending['uncertain_request'],pending['native_request'])

    def test_empty_scan_without_real_parking_proof_preserves_original_pending(self):
        self.park_proven=False
        with self.assertRaisesRegex(RegionsPaused,'parking unproven'):self.dispatch()
        self.assertIsNotNone(self.owner.book['pending']);self.assertEqual(self.owner.book['batches'],[])
        self.assertEqual(self.work_calls,0)

    def test_missing_or_contradictory_native_details_never_become_zero_candidate_credit(self):
        missing=('solid','fluid','passable','replaceable','block_entity','zombie_spawn_floor',
                 'zombie_block_light_risk','spawn_block_light','monster_spawn_block_light_limit')
        for failure in [*('missing-detail:'+key for key in missing),'contradictory-risk','malformed-detail']:
            with self.subTest(failure=failure):
                self.setUp();self.failure=failure
                with self.assertRaisesRegex(RuntimeError,'native lighting details'):self.dispatch()
                self.assertIsNotNone(self.owner.book['pending']);self.assertEqual([],self.owner.book['batches'])
                self.assertEqual(0,self.work_calls);self.assertEqual(0,self.park_calls)
                self.assertFalse(any(op=='interact'for op,_,_ in self.calls))
                self.assertTrue(all(params['target'][1]>=95 for op,params,_ in self.calls if op=='navigate'))
                self.assertTrue(self.waits)


if __name__=='__main__':unittest.main()
