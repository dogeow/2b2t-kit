"""A stock reader must prove egress before descending and never replay unknowns."""
import copy
import math
from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

import warehouse_audit_cli as stock
from test_warehouse_audit_cli import FakeClient,FakeSurvey,state


class NativeCore(FakeClient):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.state['velocity']=[0,0,0];self.response_changes={};self.raise_op=None
        self.state['last_request']=None;self.owned_material_menu=None

    def request(self,op,**params):
        if op==self.raise_op:raise RuntimeError('No local request was dispatched')
        if op in ('scan','snapshot','close_menu','material_job_park'):
            reply=super().request(op,**params)
        else:
            self.calls.append((op,copy.deepcopy(params)));self.sequence+=1
            self.last='warehouse-request-'+str(self.sequence)
            if op=='navigate':
                self.assert_step=math.dist(self.state['pos'],params['target'])
                if self.assert_step>31.00001:raise AssertionError('Unbounded native step')
                self.rev+=1;self.state['control_revision']=self.rev
                self.state['supervision_lease']['revision']=self.rev
                self.state['pos']=list(params['target']);self.state['flight']=True
            elif op=='interact':
                self.state['screen']='ContainerScreen'
                self.state['menu']=copy.deepcopy(self.contents[tuple(params['pos'])])
                self.owned_material_menu=self.state['menu']['id']
            elif op!='select_item'and op!='approach_block':raise AssertionError(op)
            reply=self.status()|{'phase':'done','id':self.last}
        self.state['last_request']=self.last
        reply['last_request']=self.last
        reply.update(self.response_changes.get(op,{}))
        return reply


class WarehouseExitTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)/'root';self.out=Path(tmp.name)/'out'
        self.core=NativeCore(self.root,self.out,server='example.test:25565',park_target=state()['pos'])
        (self.out/'receipts').mkdir()
        self.report={'pending':None}
        self.session=stock._Session(self.core,state(),self.report,self.out)
        self.pos=[20,64,20]
        self.core.put_chest(self.pos,[],kind='minecraft:hopper',properties='[enabled=true,facing=down]',size=5)
        self.core.contents[tuple(self.pos)]['type']='HopperMenu'

    def follow(self,*args):
        return patch('material_jobs.navigation.settled_state',side_effect=lambda client,*a,**k:client.status())

    def test_machine_open_side_is_preproved_and_returns_before_finish(self):
        origin=self.core.state['pos'][:]
        with self.follow():
            face=stock._side_access(self.session,self.pos,self.core.scans[tuple(self.pos)]['state'])
            self.assertEqual('west',face)
            self.assertEqual([19.5,64.02,20.5],self.core.state['pos'])
            self.assertEqual('proved_before_entry',self.report['storage_return']['state'])
            stock._exit_storage(self.session,{})
        self.assertEqual(origin,self.core.state['pos']);self.assertEqual([],self.session.return_points)
        self.assertEqual('returned_to_original_verified_start',self.report['storage_return']['state'])
        self.assertTrue(all(op!='approach_block'for op,_ in self.core.calls))
        self.assertEqual(0,self.core.finish_calls)

    def test_roofed_all_side_columns_refuse_before_any_descent(self):
        for dx,dz in ((-1,0),(0,-1),(0,1),(1,0),(-2,0),(0,-2),(0,2),(2,0)):
            pos=[20+dx,70,20+dz]
            self.core.scans[tuple(pos)]={'pos':pos,'state':'Block{minecraft:white_concrete}',
                                      'passable':False,'fluid':False,'solid':True,'block_entity':False}
        with self.assertRaisesRegex(stock.StockBlocked,'remain outside'):
            stock._side_access(self.session,self.pos,self.core.scans[tuple(self.pos)]['state'])
        self.assertEqual(state()['pos'],self.core.state['pos'])
        self.assertFalse(any(op=='navigate'for op,_ in self.core.calls))
        self.assertEqual([],self.session.return_points)

    def test_house_returns_to_original_inside_pose_before_registered_door_exit(self):
        self.core.state['pos']=[20.5,65,24.5];self.session.in_house=True
        origin=self.core.state['pos'][:];self.pos=[20,65,20]
        self.core.put_chest(self.pos,[])
        visited=[]
        def exit_route(route,name):visited.append((name,self.core.state['pos'][:]))
        with self.follow(),patch.object(stock._RegisteredRoute,'route',exit_route):
            stock._side_access(self.session,self.pos,self.core.scans[tuple(self.pos)]['state'],house=True)
            stock._exit_storage(self.session,{})
        self.assertEqual([('workbench_exit',origin)],visited)
        self.assertFalse(self.session.in_house)
        self.assertTrue(all(abs(params['target'][1]-65)<1e-6 for op,params in self.core.calls if op=='navigate'))

    def test_house_high_barrel_refuses_before_entry_or_staging(self):
        pos=[20,71,20];self.core.put_chest(pos,[],kind='minecraft:barrel',properties='[facing=west,open=false]')
        self.core.scans[(20,72,20)]={'pos':[20,72,20],'state':'Block{minecraft:oak_planks}'}
        profile={'workbench':[20,65,22],'workbench_entry':[{'kind':'walk','target':[20.5,65,24.5]}],
                 'workbench_exit':[{'kind':'walk','target':[20.5,65,24.5]}],
                 'workbench_staging':[20.5,90,24.5]}
        with patch.object(stock._RegisteredRoute,'route')as route,patch.object(stock,'_side_access')as side, \
                self.assertRaisesRegex(stock.StockBlocked,'same-level'):
            stock._open_container(self.session,pos,self.core.scans[tuple(pos)]['state'],profile)
        route.assert_not_called();side.assert_not_called();self.assertFalse(self.session.in_house)

    def test_exact_terminal_blocked_approach_clears_pending_for_safety_exit(self):
        self.core.response_changes['approach_block']={'phase':'error','detail':'No visible collision-free depot approach'}
        reply=self.session.request('approach_block',pos=self.pos,face='west',expected_state='block')
        self.assertEqual('error',reply['phase']);self.assertIsNone(self.report['pending'])
        self.assertEqual('approach_block',self.report['known_read_terminals'][0]['op'])

    def test_terminal_foreign_id_world_revision_busy_or_inflight_stays_unresolved(self):
        changes=({'id':'foreign'},{'world_session':'foreign'},{'control_revision':99})
        for change in changes:
            with self.subTest(change=change):
                self.setUp();self.core.response_changes['approach_block']={'phase':'error',**change}
                with self.assertRaises(stock.StockBlocked):self.session.request('approach_block',pos=self.pos)
                self.assertIsNotNone(self.report['pending'])
        for kind in ('busy','inflight'):
            with self.subTest(kind=kind):
                self.setUp();self.core.response_changes['approach_block']={'phase':'waiting'}
                if kind=='busy':self.core.state['native_material_busy']=True
                else:self.core.native_inflight={'request_id':'unknown'}
                with self.assertRaises(stock.StockBlocked):self.session.request('approach_block',pos=self.pos)
                self.assertIsNotNone(self.report['pending'])

    def test_unknown_pending_never_closes_menu_returns_or_finishes(self):
        self.report['pending']={'request_id':'unknown-interact'}
        self.session.return_points=[[20.5,140,20.5]];self.session.in_house=True
        self.core.state['screen']='ContainerScreen'
        with patch.object(stock._RegisteredRoute,'route')as route,self.assertRaisesRegex(stock.StockBlocked,'unresolved'):
            stock._exit_storage(self.session,{})
        with self.assertRaisesRegex(stock.StockBlocked,'unresolved'):self.session.request('snapshot')
        route.assert_not_called();self.assertEqual([],self.core.calls);self.assertEqual(0,self.core.finish_calls)

    def test_unknown_interact_terminal_cannot_be_cleared_as_read_only(self):
        self.core.response_changes['interact']={'phase':'error','detail':'ambiguous server result'}
        with self.assertRaises(stock.StockBlocked):
            self.session.request('interact',pos=self.pos,expected_hand='minecraft:diamond_sword')
        self.assertIsNotNone(self.report['pending'])

    def test_exact_native_interact_preflight_rejection_allows_safe_exit(self):
        self.core.response_changes['interact']={'phase':'error','detail':'Target interaction face is occluded or out of reach'}
        self.session.request('interact',pos=self.pos,expected_hand='minecraft:diamond_sword')
        self.assertIsNone(self.report['pending'])

    def test_proved_local_no_dispatch_failure_does_not_invent_unknown_request(self):
        self.core.raise_op='scan'
        with self.assertRaises(RuntimeError):self.session.request('scan',min=self.pos,max=self.pos)
        self.assertIsNone(self.report['pending'])
        self.assertFalse(self.report['known_local_preflights'][0]['request_dispatched'])

    def test_changed_return_corridor_never_moves_through_new_roof(self):
        with self.follow():stock._side_access(self.session,self.pos,self.core.scans[tuple(self.pos)]['state'])
        self.core.scans[(19,70,20)]={'pos':[19,70,20],'state':'Block{minecraft:white_concrete}',
                                    'passable':False,'fluid':False,'solid':True,'block_entity':False}
        before=len([op for op,_ in self.core.calls if op=='navigate'])
        with self.follow(),self.assertRaisesRegex(stock.StockBlocked,'changed'):
            stock._exit_storage(self.session,{})
        self.assertEqual(before,len([op for op,_ in self.core.calls if op=='navigate']))
        self.assertTrue(self.session.return_points)

    def run_machine(self,*,changed=False):
        result_core=[]
        out=self.out/'run'
        def factory(root,directory,**kwargs):
            core=NativeCore(root,directory,**kwargs)
            core.put_chest(self.pos,[{'item':'minecraft:raw_iron','count':9}],
                           kind='minecraft:hopper',properties='[enabled=true,facing=down]',size=5)
            core.contents[tuple(self.pos)]['type']='HopperMenu'
            if changed:
                original=core.request
                def request(op,**params):
                    reply=original(op,**params)
                    if op=='interact':core.scans[tuple(self.pos)]['state']='Block{minecraft:hopper}[enabled=true,facing=north]'
                    return reply
                core.request=request
            result_core.append(core);return core
        with patch.object(stock,'_travel_to'),self.follow():
            result=stock.run(self.root/'game',out,[self.pos],client_factory=factory,survey_factory=FakeSurvey,
                             snapshot_reader=lambda *a,**k:state(),sleeper=lambda seconds:None)
        return result,result_core[0]

    def test_full_machine_run_returns_high_before_exact_native_finish(self):
        result,core=self.run_machine()
        self.assertTrue(result['complete']);self.assertEqual({'minecraft:raw_iron':9},result['loose_counts'])
        self.assertEqual(state()['pos'],core.state['pos']);self.assertEqual(1,core.finish_calls)
        self.assertEqual('returned_to_original_verified_start',result['storage_return']['state'])

    def test_known_post_read_block_change_returns_high_and_finishes_without_claiming_stock(self):
        result,core=self.run_machine(changed=True)
        self.assertFalse(result['complete']);self.assertEqual([],result['containers'])
        self.assertEqual(state()['pos'],core.state['pos']);self.assertEqual(1,core.finish_calls)
        self.assertIn('finish_proof',result);self.assertIsNone(result['pending'])

    def test_house_normal_and_known_error_both_follow_original_exit_before_finish(self):
        for changed in (False,True):
            with self.subTest(changed=changed):
                self.setUp();pos=[20,65,20];cores=[];exits=[]
                profile={'server':'example.test:25565','dimension':'minecraft:overworld',
                         'workbench':[20,65,22],
                         'workbench_entry':[{'kind':'walk','target':[20.5,65,24.5]}],
                         'workbench_exit':[{'kind':'walk','target':[20.5,65,28.5]}]}
                def factory(root,directory,**kwargs):
                    core=NativeCore(root,directory,**kwargs);cores.append(core)
                    core.put_chest(pos,[{'item':'minecraft:raw_iron_block','count':9}],
                                   properties='[facing=west,type=single,waterlogged=false]')
                    for ground in ([20,70,20],[20,64,28]):
                        core.scans[tuple(ground)]={'pos':ground,'state':'Block{minecraft:oak_planks}',
                            'fluid':False,'passable':False,'solid':True,'block_entity':False}
                    if changed:
                        request=core.request
                        def altered(op,**params):
                            reply=request(op,**params)
                            if op=='interact':core.scans[tuple(pos)]['state']='Block{minecraft:chest}[facing=north,type=single,waterlogged=false]'
                            return reply
                        core.request=altered
                    return core
                def route(adapter,name):
                    if name=='workbench_entry':adapter.session.core.state['pos']=[20.5,65,24.5]
                    else:
                        exits.append((name,adapter.session.core.state['pos'][:]))
                        adapter.session.core.state['pos']=[20.5,65,28.5]
                with patch.object(stock,'_travel_to'),self.follow(),patch.object(stock._RegisteredRoute,'route',route):
                    result=stock.run(self.root/'game',self.out/'house',[pos],profile,client_factory=factory,
                                    survey_factory=FakeSurvey,snapshot_reader=lambda *a,**k:state(),sleeper=lambda seconds:None)
                self.assertEqual([('workbench_exit',[20.5,65,24.5])],exits)
                self.assertEqual(1,cores[0].finish_calls);self.assertEqual(not changed,result['complete'])
                self.assertEqual('original_registered_exit_completed',result['house_exit'])
                self.assertEqual([20.5,89,28.5],cores[0].state['pos'])


if __name__=='__main__':unittest.main()
