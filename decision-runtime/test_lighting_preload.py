"""Distant lighting loads current server chunks through one owned short-leg route."""
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lighting_regions_cli import NativeBatch, RegionsPaused, RegionsWorker
from potato_farm import ENTITY_SCOPE
from test_lighting_regions_cli import profile, state


class LightingPreloadTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.current=state()
        self.current.update(pos=[1.5,95,1.5],phase='parking',guard_busy=False,air_only_navigation_protocol=2)
        self.calls=[];self.created=[];self.fail_navigation=False;self.ground=63
        settings=profile();settings['movement_bounds']['max']=[260,140,260]
        settings['regions']=[{'name':'remote','min':[151,60,151],'max':[155,110,155]}]
        self.owner=RegionsWorker(self.root,settings,observer=lambda:deepcopy(self.current))
        case=self

        class Survey:
            def __init__(self,root,out,server,**kwargs):
                self.root=Path(root);self.out=Path(out);self.world=case.current['world_session']
                self.out.mkdir(parents=True,exist_ok=True)
            def status(self):return deepcopy(case.current)
            def request(self,op,**params):
                case.calls.append((op,deepcopy(params),deepcopy(case.current['pos'])))
                if op!='scan':raise AssertionError('Read-only survey must only scan')
                low,high=params['min'],params['max']
                self.last='scan-'+str(len(case.calls))
                if math.hypot(low[0]-case.current['pos'][0],low[2]-case.current['pos'][2])>48:
                    raise AssertionError('Distant server column was scanned before preload')
                blocks=([{'pos':[low[0],case.ground,low[2]],'state':'Block{minecraft:grass_block}',
                          'fluid':False,'passable':False}]
                        if low[1]<=case.ground<=high[1] else [])
                return {'id':self.last,'phase':'done','world_session':self.world,
                        'control_revision':case.current['control_revision'],
                        'scan_start_revision':case.current['control_revision'],'scan_end_revision':case.current['control_revision'],
                        'scan_cells_read':math.prod(high[i]-low[i]+1 for i in range(3)),
                        'scan_total_cells':math.prod(high[i]-low[i]+1 for i in range(3)),
                        'scan_entity_scope':ENTITY_SCOPE,
                        'scan_entities':[],'blocks':blocks}

        class Material(Survey):
            def __init__(self,root,out,server,remote_finish,park_target,record_experience):
                super().__init__(root,out,server)
                case.created.append(self);self.task='owned-task';self.rev=case.current['control_revision']
                self.park_target=deepcopy(park_target);self.initial_park=deepcopy(park_target)
                self.last=None;self.native_inflight=None
                self.heartbeat=type('Beat',(),{'id':'owned-lease','close':lambda self:None})()
                case.current['supervision_lease']={'id':self.heartbeat.id,'kind':'materials',
                    'job_session':self.task,'world_session':self.world,'revision':self.rev,'remote_finish':'guard'}
            def raw(self,*args,**kwargs):return deepcopy(case.current)
            def status(self):return self.raw()
            def request(self,op,**params):
                if op=='scan':return super().request(op,**params)
                if op!='navigate':raise AssertionError('Unexpected game operation')
                case.calls.append((op,deepcopy(params),deepcopy(case.current['pos'])))
                self.last='native-route-'+str(len(case.calls))
                self.native_inflight={'request_id':self.last,'op':'navigate','world_session':self.world,
                    'task_session':self.task,'lease_id':self.heartbeat.id,'base_revision':self.rev,
                    'expected_revision':self.rev+1,'request_revision':self.rev}
                case.current.update(id=self.last,last_request=self.last,op='navigate',phase='running')
                case.owner.gate(self.status(),self)
                if case.fail_navigation:raise RuntimeError('Original native navigation outcome unknown')
                self.rev+=1;case.current['control_revision']=self.rev
                case.current['supervision_lease']['revision']=self.rev
                case.current.update(pos=list(params['target']),phase='done')
                self.native_inflight=None
                return {'phase':'done','id':self.last}
            def finish(self):raise AssertionError('Generic finish must not run after unknown travel')
            def start_progress(self,*args,**kwargs):pass

        class Runner:
            def __init__(self,c,low,high,budget,out,initial,**kwargs):
                self.c=c;self.out=Path(out);self.report={'placed':[],'progress':{'eligible_candidates':0},
                    'remaining_unprotected_risk':0,'park_native_confirmed':False}
                case.calls.append(('lighting_start',{},deepcopy(case.current['pos'])))
            def work(self):pass
            def scan(self,low,high,name):return self.c.request('scan',min=list(low),max=list(high),details=True)
            def park(self):
                self.report['park_native_confirmed']=True
                case.current['supervision_lease']['kind']='parking'
                (self.out/'final-snapshot.json').write_text(json.dumps(case.current))

        def travel(c,target,checkpoint,trace,*args,**kwargs):
            checkpoint();before=c.status()['pos'];c.request('navigate',target=target,air_only=True)
            trace.append({'from':before,'target':list(target),'request_id':c.last})

        self.patches=[patch('material_client.Client',Survey),patch('material_client.MaterialClient',Material),
                      patch('material_jobs.acquisition._travel',side_effect=travel),
                      patch('lighting_regions_cli.LightingRun',Runner),
                      patch.object(NativeBatch,'high_work_preflight',return_value={'eligible_remaining':1})]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def dispatch(self):return self.owner.dispatch(0,self.owner.profile['regions'][0],audit=False)

    def test_remote_column_follows_single_client_and_short_current_loaded_legs(self):
        result=self.dispatch()
        self.assertTrue(result['park_native_confirmed']);self.assertEqual(1,len(self.created))
        self.assertEqual([1.5,95,1.5],self.created[0].initial_park)
        first=self.calls[0];self.assertEqual('scan',first[0])
        self.assertEqual([1,-64,1],first[1]['min'])
        remote=next(i for i,row in enumerate(self.calls) if row[0]=='scan' and row[1]['min'][0]==153)
        self.assertTrue(any(row[0]=='navigate' for row in self.calls[:remote]))
        self.assertLessEqual(math.hypot(self.calls[remote][2][0]-153.5,self.calls[remote][2][2]-153.5),16)
        directory=Path(result['directory'])
        route=json.loads((directory/'preload-route.json').read_text())
        self.assertTrue(route['arrived_near']);self.assertGreater(len(route['legs']),1)
        for leg in route['legs']:
            self.assertLessEqual(math.dist(leg['from'],leg['target']),32)
            self.assertEqual('done',leg['state']);self.assertTrue(leg['request_id'])
        self.assertIsNone(self.owner.book['pending'])
        arrival=next(row for row in self.calls[remote+1:] if row[0]=='navigate'and row[1]['target'][1]==65.5)
        self.assertEqual(65.5,arrival[1]['target'][1])

    def test_nearby_region_keeps_original_column_then_low_flight_without_preload(self):
        self.current['pos']=[152.5,95,152.5]
        result=self.dispatch();directory=Path(result['directory'])
        self.assertEqual([153,-64,153],self.calls[0][1]['min'])
        self.assertFalse((directory/'preload-route.json').exists())
        self.assertEqual([153.5,95,153.5],self.created[0].initial_park)

    def test_audit_arrives_at_current_high_park_and_keeps_full_region_scan(self):
        self.current['pos']=[152.5,95,152.5]
        result=self.owner.dispatch(0,self.owner.profile['regions'][0],audit=True)
        self.assertTrue(result['park_native_confirmed']);self.assertEqual(1,len(self.created))
        navigations=[row for row in self.calls if row[0]=='navigate']
        self.assertEqual([95],[row[1]['target'][1]for row in navigations])
        plan=json.loads((Path(result['directory'])/'arrival-height-plan.json').read_text())
        self.assertEqual('audit_high_guarded_arrival',plan['mode'])
        self.assertEqual([153.5,95,153.5],plan['arrival']);self.assertEqual(plan['arrival'],plan['safe_park'])
        self.assertTrue(any(row[0]=='scan'and row[1]['min']==[151,60,151]
            and row[1]['max']==[155,110,155]for row in self.calls))

    def test_audit_raises_to_actual_solid_top_plus_24_without_ground_visit(self):
        batch=NativeBatch(self.owner);column={'blocks':[{'pos':[153,90,153],'passable':False,'fluid':False}]}
        plan=batch.arrival_height_plan(column,self.current,[153.5,108,153.5],audit=True)
        self.assertEqual(115,plan['arrival'][1]);self.assertEqual(plan['arrival'],plan['safe_park'])
        work=batch.arrival_height_plan(column,self.current,[153.5,108,153.5],audit=False)
        self.assertEqual(92.5,work['arrival'][1]);self.assertEqual(115,work['safe_park'][1])

    def test_audit_refuses_unbounded_height_or_obstruction_without_low_fallback(self):
        batch=NativeBatch(self.owner)
        for column,current in (
            ({'blocks':[{'pos':[153,120,153],'passable':False}]},self.current),
            ({'blocks':[{'pos':[153,63,153],'passable':False},
                        {'pos':[153,95,153],'passable':True,'fluid':False}]},self.current),
            ({'blocks':[]},self.current)):
            with self.subTest(column=column),self.assertRaises(RegionsPaused):
                batch.arrival_height_plan(column,current,[153.5,108,153.5],audit=True)

    def test_audit_column_covers_full_body_at_block_boundary_center(self):
        self.current['pos']=[152.5,95,152.5]
        self.owner.profile['regions'][0]['max'][0]=154
        self.owner.dispatch(0,self.owner.profile['regions'][0],audit=True)
        self.assertEqual([152,-64,153],self.calls[0][1]['min'])
        self.assertEqual([153,319,153],self.calls[0][1]['max'])

    def test_actual_travel_plans_only_short_loaded_corridors_before_remote_scan(self):
        self.patches[2].stop()
        with patch('material_jobs.navigation.settled_state',side_effect=lambda c,*args:c.status()):
            result=self.dispatch()
        route=json.loads((Path(result['directory'])/'preload-route.json').read_text())
        self.assertTrue(route['arrived_near'])
        for leg in route['legs']:
            for step in leg['route']:
                self.assertLessEqual(math.dist(step['target'],step['actual']),.55)
        remote=next(i for i,row in enumerate(self.calls) if row[0]=='scan' and row[1]['min']==[153,-64,153])
        for op,params,here in self.calls[:remote]:
            if op=='navigate':self.assertLessEqual(math.dist(here,params['target']),32.000001)
            if op=='scan':
                self.assertLessEqual(params['max'][0]-params['min'][0],36)
                self.assertLessEqual(params['max'][2]-params['min'][2],36)

    def test_unverified_current_clearance_never_acquires_control_or_moves(self):
        self.current['pos'][1]=80
        with self.assertRaisesRegex(RegionsPaused,'twenty-block'):self.dispatch()
        self.assertFalse(self.created)
        self.assertEqual(['scan'],[row[0] for row in self.calls])
        self.assertEqual('before_native_control',self.owner.book['pending']['stage'])

    def test_unknown_preload_keeps_original_pending_request_and_does_not_finish_or_resurvey(self):
        self.fail_navigation=True
        with patch.object(NativeBatch,'wait_unresolved') as wait:
            with self.assertRaisesRegex(RuntimeError,'Original native'):self.dispatch()
        wait.assert_called_once_with(self.created[0])
        pending=self.owner.book['pending']
        self.assertEqual('travel',pending['stage']);self.assertEqual('preload',pending['travel_stage'])
        self.assertEqual(pending['native_request'],pending['uncertain_request'])
        self.assertEqual(self.created[0].last,pending['native_request']['request_id'])
        self.assertEqual(['scan','navigate'],[row[0] for row in self.calls])
        route=json.loads((Path(pending['directory'])/'preload-route.json').read_text())
        self.assertEqual('pending',route['legs'][0]['state'])
        with self.assertRaisesRegex(RegionsPaused,'pending batch'):self.owner.run(resume=True)

    def test_manual_health_and_world_changes_stop_preload_before_next_leg(self):
        for change in ({'manual_movement':True},{'health':19},{'world_session':'other'}):
            with self.subTest(change=change):
                self.current=state();self.current.update(pos=[1.5,95,1.5],phase='parking',guard_busy=False)
                self.calls=[];self.created=[]
                # Each independent invocation gets a new pending directory, but
                # never rewrites a prior native result or runs another controller.
                directory=self.owner.out/('safety-'+str(len(change))+next(iter(change)))
                directory.mkdir();self.owner.book['pending']={'stage':'before_native_control'}
                self.owner.opening=True
                import material_client
                c=material_client.MaterialClient(self.root,directory,self.owner.profile['server'],
                    'guard',[1.5,95,1.5],False)
                self.owner.opening=False
                self.current.update(change)
                with self.assertRaises(RegionsPaused):NativeBatch(self.owner).preload_region(c,[153.5,108,153.5],directory)
                self.assertFalse(self.calls)

    def test_preload_body_bounds_stop_before_short_leg_submission(self):
        directory=self.owner.out/'bounded';directory.mkdir()
        self.owner.book['pending']={'stage':'before_native_control'};self.owner.opening=True
        import material_client
        c=material_client.MaterialClient(self.root,directory,self.owner.profile['server'],
                                        'guard',[1.5,95,1.5],False)
        self.owner.opening=False
        with self.assertRaisesRegex(RegionsPaused,'movement box'):
            NativeBatch(self.owner).preload_region(c,[-100,95,1.5],directory)
        self.assertFalse(self.calls)


if __name__=='__main__':unittest.main()
