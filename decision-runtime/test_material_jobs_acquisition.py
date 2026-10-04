import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.acquisition import (acquire, rock_choice, _travel,
    _wait_guard_clear, _resource_route_scope, blocks_route, Unavailable,
    _access_shaft, route_failure, record_route_failure)
from material_jobs.protocol import JobPaused


def block(pos, name, *, fluid=False, block_entity=False):
    return {'pos': list(pos), 'state': 'Block{minecraft:'+name+'}', 'solid': not fluid,
            'passable': False, 'fluid': fluid, 'block_entity': block_entity}


class FakeClient:
    world='world'
    def __init__(self, item='minecraft:cobbled_deepslate', before=0, gain=None, native_phase='done', resource='deepslate'):
        self.item=item;self.actions=[];self.gain=gain;self.native_phase=native_phase;self.still_active=False
        self.rev=7
        self.state={'world_session':self.world,'health':20,'food':20,'guard_armed':True,'guard_pve_only':True,
                    'pos':[.5,70.1,.5],'time':1,'quarry_protocol':1,'rock_quarry_protocol':1,'tree_survey_protocol':1,
                    'air_only_navigation_protocol':2,
                    'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(36)]}
        self.state['inventory'][0]={'slot':0,'item':'minecraft:diamond_pickaxe','count':1,'max_stack':1,'durability':1500}
        self.state['inventory'][1]={'slot':1,'item':'minecraft:diamond_shovel','count':1,'max_stack':1,'durability':1500}
        self.state['inventory'][2]={'slot':2,'item':'minecraft:diamond_axe','count':1,'max_stack':1,'durability':1500}
        self.state['inventory'][3]={'slot':3,'item':item,'count':before,'max_stack':64}
        self.rows=[block((x,y,z),resource) for x in range(2) for z in range(2) for y in range(63,68)]
        self.trees=[]
    def status(self):return copy.deepcopy(self.state)
    def checked(self,op,**params):
        result=self.request(op,**params)
        if result.get('phase')!='done':raise RuntimeError(result.get('detail','failure'))
        return result
    def request(self,op,**params):
        self.actions.append((op,copy.deepcopy(params)))
        if op=='scan':
            cells=math.prod(params['max'][i]-params['min'][i]+1 for i in range(3))
            self.last='scan-'+str(len(self.actions))
            return {'id':self.last,'phase':'done','world_session':self.world,'control_revision':self.rev,
                    'scan_start_revision':self.rev,'scan_end_revision':self.rev,
                    'scan_cells_read':cells,'scan_total_cells':cells,
                    'blocks':copy.deepcopy([r for r in self.rows if all(params['min'][i]<=r['pos'][i]<=params['max'][i] for i in range(3))])}
        if op=='scan_trees':return {'tree_survey':{'trees':copy.deepcopy(self.trees),'unloaded_columns':0}}
        if op=='select_item':self.state['selected_slot']=params['slot'];return {'phase':'done'}
        if op=='navigate':self.state['pos']=params['target'];return {'phase':'done'}
        if op in ('rock_quarry_batch','quarry_batch','chop'):
            if params.get('completion')=='clear':
                self.last='clear-'+str(len(self.actions))
                source={'minecraft:deepslate'} if self.item=='minecraft:cobbled_deepslate' else {'minecraft:stone'}
                taken=[r for r in self.rows if all(params['min'][i]<=r['pos'][i]<=params['max'][i] for i in range(3))]
                self.rows=[r for r in self.rows if r not in taken]
                self.state['inventory'][3]['count']+=sum(r['state'] in {'Block{'+name+'}' for name in source} for r in taken)
                return {'phase':'done','rock_quarry':{'id':self.last,'world_session':self.world,
                    'item':self.item,'min':params['min'],'max':params['max'],'active':False,'phase':'done',
                    'completion':'clear','area_cleared':True,'pending_blocks':0,'remaining_blocks':0}}
            count=params['target_count'] if self.gain is None else self.gain
            self.state['inventory'][3]['count']+=count
            self.state['borer_active']=self.still_active
            return {'phase':self.native_phase,'detail':'fake native receipt'}
        raise AssertionError(op)


class AcquisitionTest(unittest.TestCase):
    def test_guard_displaced_terminal_route_is_not_retried_or_called_a_solid_block(self):
        class Displaced(FakeClient):
            def request(self,op,**params):
                if op=='navigate':
                    self.actions.append((op,copy.deepcopy(params)))
                    self.state['pos']=[12.5,33,8.5]
                    self.state['guard_busy']=True
                    return {'phase':'waiting','detail':'air-only path changed; no blocks were excavated'}
                return super().request(op,**params)
        c=Displaced();c.state['pos']=[.5,145,.5];c.rows=[];trace=[]
        with patch('material_jobs.navigation.settled_state',side_effect=AssertionError('No settlement wait after terminal waiting')):
            with self.assertRaises(Unavailable) as stopped:
                _travel(c,[.5,-3.9,.5],lambda:None,trace)
        self.assertEqual('guard_displaced',stopped.exception.code)
        self.assertEqual('waiting',stopped.exception.phase)
        self.assertEqual('guard_displaced',trace[-1]['route_code'])
        self.assertFalse(stopped.exception.evidence['terminal_verified'])
        self.assertEqual(1,sum(op=='navigate' for op,_ in c.actions))

    def test_native_path_change_without_fresh_blocker_is_unknown_not_geometry(self):
        class Changed(FakeClient):
            task='materials-test'
            def __init__(self,obstacle):
                super().__init__();self.obstacle=obstacle;self.changed=False;self.scans=0
                self.state.update(flight=True,guard_busy=False,navigating=False,
                                  control_revision=7,entities=[],time=100,
                                  supervision_lease={'kind':'materials','job_session':self.task,
                                                     'world_session':self.world,'revision':7})
            def request(self,op,**params):
                if op=='scan':
                    self.scans+=1;self.last='scan-'+str(self.scans)
                    reply=super().request(op,**params)
                    return {**reply,'id':self.last,'world_session':self.world}
                if op=='navigate':
                    self.changed=True;self.last='nav-owned'
                    self.actions.append((op,copy.deepcopy(params)))
                    if self.obstacle:
                        # The first vertical request is now a bounded <=32
                        # leg. Only a blocker inside that exact leg is proof.
                        self.rows=[block((0,125,0),'stone')]
                    self.state.update(id=self.last,last_request=self.last,
                                      phase='waiting',guard_busy=False)
                    return {'id':self.last,'world_session':self.world,
                            'control_revision':7,'phase':'waiting',
                            'detail':'air-only path changed; no blocks were excavated'}
                return super().request(op,**params)
        for obstacle,expected in ((False,'route_uncertain'),
                                  (True,'route_geometry_blocked')):
            with self.subTest(obstacle=obstacle):
                c=Changed(obstacle);c.state['pos']=[.5,145,.5];c.rows=[];trace=[]
                with self.assertRaises(Unavailable) as stopped:
                    _travel(c,[.5,-3.9,.5],lambda:None,trace)
                self.assertEqual(expected,stopped.exception.code)
                self.assertEqual('nav-owned',stopped.exception.evidence['request_id'])
                self.assertEqual(1,sum(op=='navigate' for op,_ in c.actions))

    def test_proved_guard_stop_replans_from_current_position_to_same_target(self):
        class DisplacedThenSettled(FakeClient):
            task='materials-test'
            def __init__(self):
                super().__init__();self.failed=False
                self.state.update(flight=True,guard_busy=False,navigating=False,
                                  control_revision=7,entities=[],time=100,
                                  supervision_lease={'kind':'materials','job_session':self.task,
                                                     'world_session':self.world,'revision':7})
            def request(self,op,**params):
                if op=='navigate' and not self.failed:
                    self.failed=True;self.last='nav-first'
                    self.actions.append((op,copy.deepcopy(params)))
                    self.state.update(pos=[12.5,145,8.5],guard_busy=True,id=self.last,
                                      last_request=self.last,phase='waiting')
                    return {'id':self.last,'world_session':self.world,
                            'control_revision':7,'phase':'waiting',
                            'detail':'air-only path changed; no blocks were excavated'}
                return super().request(op,**params)
        c=DisplacedThenSettled();c.state['pos']=[.5,145,.5];c.rows=[];trace=[]
        def clear_guard(client,checkpoint,evidence):
            self.assertTrue(evidence['terminal_verified'])
            client.state['guard_busy']=False
            return client.status()
        with (patch('material_jobs.acquisition._wait_guard_clear',side_effect=clear_guard) as wait,
              patch('material_jobs.navigation.settled_state',
                    side_effect=lambda client,*args,**kwargs:client.status())):
            _travel(c,[.5,-3.9,.5],lambda:None,trace)
        wait.assert_called_once()
        self.assertEqual(1,sum(entry.get('event')=='same_target_replan_after_guard'
                               for entry in trace))
        self.assertEqual([.5,-3.9,.5],
                         [p['target'] for op,p in c.actions if op=='navigate'][-1])
        self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_guard_wait_allows_one_half_heart_regeneration_without_moving(self):
        c=FakeClient();c.task='materials-test'
        c.state.update(flight=True,guard_busy=True,navigating=False,entities=[],
                       control_revision=7,supervision_lease={
                           'kind':'materials','job_session':c.task,
                           'world_session':c.world,'revision':7})
        health=[18.5,18.5,19,19,19]
        def observed():
            index=min(observed.calls,len(health)-1);observed.calls+=1
            return {**c.state,'health':health[index],'guard_busy':index==0,
                    'time':100+index}
        observed.calls=0;c.status=observed
        with patch('material_jobs.acquisition.time.sleep'):
            result=_wait_guard_clear(c,lambda:None,{'terminal_verified':True},seconds=1)
        self.assertEqual(19,result['health'])
        self.assertFalse(any(op=='navigate' for op,_ in c.actions))

    def test_guard_wait_under_eighteen_health_fails_without_navigation(self):
        c=FakeClient();c.task='materials-test'
        c.state.update(health=17.5,flight=True,guard_busy=True,navigating=False,
                       entities=[],supervision_lease={'kind':'materials',
                       'job_session':c.task,'world_session':c.world,'revision':7},
                       control_revision=7)
        with self.assertRaises(Unavailable) as stopped:
            _wait_guard_clear(c,lambda:None,{'terminal_verified':True},seconds=1)
        self.assertEqual('waiting',stopped.exception.phase)
        self.assertFalse(any(op=='navigate' for op,_ in c.actions))

    def test_repeated_proved_guard_stops_retry_same_target_only_twice(self):
        class RepeatedDisplacement(FakeClient):
            task='materials-test'
            def __init__(self):
                super().__init__();self.attempt=0
                self.state.update(flight=True,guard_busy=False,navigating=False,
                                  control_revision=7,entities=[],time=100,
                                  supervision_lease={'kind':'materials','job_session':self.task,
                                                     'world_session':self.world,'revision':7})
            def request(self,op,**params):
                if op=='navigate':
                    self.attempt+=1;self.last='nav-'+str(self.attempt)
                    self.actions.append((op,copy.deepcopy(params)))
                    self.state.update(pos=[self.attempt+.5,145,.5],guard_busy=True,
                                      id=self.last,last_request=self.last,phase='waiting')
                    return {'id':self.last,'world_session':self.world,
                            'control_revision':7,'phase':'waiting',
                            'detail':'air-only path changed; no blocks were excavated'}
                return super().request(op,**params)
        c=RepeatedDisplacement();c.state['pos']=[.5,145,.5];c.rows=[];trace=[]
        def clear_guard(client,checkpoint,evidence):
            client.state['guard_busy']=False
            return client.status()
        with patch('material_jobs.acquisition._wait_guard_clear',side_effect=clear_guard) as wait:
            with self.assertRaises(Unavailable) as stopped:
                _travel(c,[.5,-3.9,.5],lambda:None,trace)
        self.assertEqual('guard_displaced',stopped.exception.code)
        self.assertEqual(2,stopped.exception.evidence['replans'])
        self.assertEqual(2,wait.call_count)
        self.assertEqual(3,c.attempt)
        self.assertTrue(all(op!='rock_quarry_batch' for op,_ in c.actions))

    def test_failed_shaft_entry_is_written_before_any_quarry_mutation_and_held_across_jobs(self):
        item='minecraft:cobbled_deepslate'
        region={'item':item,'min':[0,-18,0],'max':[1,-1,1],
                'source':'natural_survey','surface_y':10,
                'access_shaft':{'min':[0,0,0],'max':[1,10,1]}}
        profile={'server':'test','dimension':'minecraft:overworld','resource_regions':[region]}
        with tempfile.TemporaryDirectory() as folder:
            c=FakeClient();c.root=Path(folder)/'automation';c.root.mkdir()
            ledger={'schema':1,'world_session':c.world,'item':item,'visited':{}}
            local=Path(folder)/'acquisition.json'
            with patch('material_jobs.acquisition._scan',return_value=[]),\
                 patch('material_jobs.acquisition._rock_observation',return_value={'remaining':4}),\
                 patch('material_jobs.acquisition._tool',return_value={'item':'minecraft:diamond_pickaxe'}),\
                 patch('material_jobs.acquisition._travel',side_effect=Unavailable('guard moved actor','waiting','guard_displaced')):
                with self.assertRaises(Unavailable):
                    _access_shaft(c,region,{'max':[1,-1,1]},item,44,ledger,local,lambda:None,profile)
            saved=json.loads(local.read_text())
            self.assertEqual('route_hold',next(iter(saved['visited'].values()))['state'])
            self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))
            held=route_failure(c,profile,item,region)
            self.assertEqual('guard_displaced',held['code'])
            c.world='new-world'
            self.assertIsNone(route_failure(c,profile,item,region))

    def test_final_resource_route_failure_is_also_journaled_before_mining(self):
        item='minecraft:cobbled_deepslate'
        region={'item':item,'min':[0,63,0],'max':[1,67,1]}
        profile={'server':'test','dimension':'minecraft:overworld','resource_regions':[region]}
        with tempfile.TemporaryDirectory() as folder:
            c=FakeClient();c.root=Path(folder)/'automation';c.root.mkdir()
            out=Path(folder)/'acquisition'
            with patch('material_jobs.acquisition._travel',
                       side_effect=Unavailable('guard moved actor','waiting','guard_displaced')):
                receipt=acquire(c,item,12,profile,out,lambda:None)
            self.assertEqual(('waiting','guard_displaced'),(receipt['phase'],receipt['code']))
            ledger=json.loads((out/'acquisition-cobbled_deepslate.json').read_text())
            self.assertEqual('route_hold',next(iter(ledger['visited'].values()))['state'])
            self.assertEqual('guard_displaced',route_failure(c,profile,item,region)['code'])
            self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))
            second=acquire(c,item,12,profile,out,lambda:None)
            self.assertEqual(('waiting','guard_displaced'),
                             (second['phase'],second['code']))
            self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_later_region_guard_hold_preempts_all_other_regions_before_mining(self):
        item='minecraft:cobbled_deepslate'
        first={'item':item,'min':[0,63,0],'max':[1,67,1]}
        original={'item':item,'min':[10,63,0],'max':[11,67,1]}
        profile={'server':'test','dimension':'minecraft:overworld',
                 'resource_regions':[first,original]}
        with tempfile.TemporaryDirectory() as folder:
            c=FakeClient();c.root=Path(folder)/'automation';c.root.mkdir()
            record_route_failure(c,profile,item,original,'guard_displaced',
                                 'old combat stop',[10.5,70.1,.5])
            receipt=acquire(c,item,12,profile,Path(folder)/'job',lambda:None)
            self.assertEqual(('waiting','guard_displaced'),
                             (receipt['phase'],receipt['code']))
            self.assertFalse(any(op in ('rock_quarry_batch','navigate') for op,_ in c.actions))

    def test_real_checkpoint_pause_during_guard_wait_persists_original_region_hold(self):
        item='minecraft:cobbled_deepslate'
        region={'item':item,'min':[0,63,0],'max':[1,67,1]}
        profile={'server':'test','dimension':'minecraft:overworld',
                 'resource_regions':[region]}
        with tempfile.TemporaryDirectory() as folder:
            c=FakeClient();c.root=Path(folder)/'automation';c.root.mkdir()
            out=Path(folder)/'acquisition';paused={'now':False}
            def checkpoint():
                if paused['now']:
                    raise JobPaused('health fell below 18 during combat')
            def stopped_route(client,target,check,trace):
                paused['now']=True
                trace.append({'target':list(target),'actual':[.5,70.1,.5],
                              'phase':'waiting','route_code':'guard_displaced',
                              'terminal_verified':True,'request_id':'nav-owned',
                              'combat_confirmed':True,'observed_at':100})
                raise Unavailable('guard displaced','waiting','guard_displaced',
                                  {'request_id':'nav-owned','terminal_verified':True,
                                   'combat_confirmed':True})
            with (patch('material_jobs.acquisition._scan',return_value=[]),
                  patch('material_jobs.acquisition.rock_choice',
                        side_effect=lambda rows,lo,hi,*args:{
                            'min':lo,'max':hi,'available':4,'remaining':4}),
                  patch('material_jobs.acquisition._travel_once',
                        side_effect=stopped_route)):
                with self.assertRaises(JobPaused):
                    acquire(c,item,12,profile,out,checkpoint)
            ledger=json.loads((out/'acquisition-cobbled_deepslate.json').read_text())
            held=next(iter(ledger['visited'].values()))
            self.assertEqual(('route_hold','guard_displaced'),
                             (held['state'],held['route_code']))
            self.assertTrue(held['route_evidence']['checkpoint_paused'])
            self.assertEqual('guard_displaced',route_failure(c,profile,item,region)['code'])
            after=acquire(c,item,12,profile,out,lambda:None)
            self.assertEqual(('waiting','guard_displaced'),
                             (after['phase'],after['code']))
            self.assertFalse(any(op in ('navigate','rock_quarry_batch') for op,_ in c.actions))

    def test_wood_guard_route_holds_same_tree_across_next_acquisition(self):
        item='minecraft:oak_log'
        region={'item':item,'min':[0,63,0],'max':[20,90,20]}
        profile={'server':'test','dimension':'minecraft:overworld',
                 'resource_regions':[region]}
        with tempfile.TemporaryDirectory() as folder:
            c=FakeClient(item=item);c.root=Path(folder)/'automation';c.root.mkdir()
            c.trees=[{'pos':[0,65,0],'top':70,'natural_leaves':5},
                     {'pos':[10,65,0],'top':70,'natural_leaves':5}]
            c.rows=[block((0,65,0),'oak_log'),block((1,65,0),'oak_leaves')]
            out=Path(folder)/'acquisition'
            def stopped(client,target,checkpoint,trace,budget,route_scope=None):
                trace.append({'target':list(target),'actual':[.5,70.1,.5],
                              'route_code':'guard_displaced','terminal_verified':True,
                              'request_id':'nav-owned','combat_confirmed':True,
                              'observed_at':100})
                raise Unavailable('guard displaced','waiting','guard_displaced',
                                  {'terminal_verified':True,'combat_confirmed':True,
                                   'replans':2})
            with patch('material_jobs.acquisition.landing',return_value=[.5,72.1,.5]),\
                 patch('material_jobs.acquisition._travel',side_effect=stopped) as travel:
                first=acquire(c,item,10,profile,out,lambda:None)
                self.assertEqual(('waiting','guard_displaced'),
                                 (first['phase'],first['code']))
                second=acquire(c,item,10,profile,out,lambda:None)
                self.assertEqual(('waiting','guard_displaced'),
                                 (second['phase'],second['code']))
                self.assertEqual(1,travel.call_count)
            saved=json.loads((out/'acquisition-oak_log.json').read_text())
            self.assertEqual('route_hold',next(iter(saved['visited'].values()))['state'])
            self.assertFalse(any(op=='chop' for op,_ in c.actions))

    def test_wood_low_health_checkpoint_pause_records_original_tree(self):
        item='minecraft:oak_log'
        region={'item':item,'min':[0,63,0],'max':[20,90,20]}
        profile={'server':'test','dimension':'minecraft:overworld',
                 'resource_regions':[region]}
        with tempfile.TemporaryDirectory() as folder:
            c=FakeClient(item=item);c.root=Path(folder)/'automation';c.root.mkdir()
            c.trees=[{'pos':[0,65,0],'top':70,'natural_leaves':5}]
            c.rows=[block((0,65,0),'oak_log')]
            out=Path(folder)/'acquisition'
            def paused(client,target,checkpoint,trace,budget,route_scope=None):
                trace.append({'target':list(target),'actual':[.5,70.1,.5],
                              'route_code':'guard_displaced','terminal_verified':True,
                              'request_id':'nav-owned','combat_confirmed':True,
                              'observed_at':100})
                raise JobPaused('health below 18')
            with patch('material_jobs.acquisition.landing',return_value=[.5,72.1,.5]),\
                 patch('material_jobs.acquisition._travel',side_effect=paused):
                with self.assertRaises(JobPaused):
                    acquire(c,item,10,profile,out,lambda:None)
            saved=json.loads((out/'acquisition-oak_log.json').read_text())
            held=next(iter(saved['visited'].values()))
            self.assertEqual(('route_hold','guard_displaced'),
                             (held['state'],held['route_code']))
            self.assertTrue(held['route_evidence']['checkpoint_paused'])
            self.assertEqual(('waiting','guard_displaced'),
                             tuple(acquire(c,item,10,profile,out,lambda:None)[k]
                                   for k in ('phase','code')))
    def test_partial_chest_support_does_not_block_vertical_takeoff(self):
        state={'pos':[.5,64.875,.5],'on_ground':True}
        chest=block((0,64,0),'chest',block_entity=True);chest['solid']=False
        self.assertFalse(blocks_route(chest,state,[.5,100,.5]))
        self.assertTrue(blocks_route(chest,state,[10,64.875,.5]))
        self.assertTrue(blocks_route(dict(chest,solid=True),state,[.5,100,.5]))
        self.assertTrue(blocks_route(dict(chest,fluid=True),state,[.5,100,.5]))
        self.assertTrue(blocks_route(dict(chest,pos=[0,65,0]),state,[.5,100,.5]))

    def test_real_flight_on_chest_lid_takeoff_does_not_need_on_ground_flag(self):
        state={'pos':[761021.4973341001,64.875,797852.4999997583],
               'on_ground':False,'flight':True,'velocity':[0,0,0]}
        chest=block((761021,64,797852),'chest',block_entity=True);chest['solid']=False
        self.assertFalse(blocks_route(chest,state,[state['pos'][0],145,state['pos'][2]]))
        for name in ('trapped_chest','ender_chest'):
            self.assertFalse(blocks_route(dict(chest,state='Block{minecraft:'+name+'}'),state,
                                          [state['pos'][0],145,state['pos'][2]]))
        self.assertTrue(blocks_route(chest,state,[761032.5,64.875,797852.5]))
        self.assertTrue(blocks_route(chest,state,[state['pos'][0],64,state['pos'][2]]))

    def test_flying_partial_support_exception_requires_known_height_and_stationary_dry_storage(self):
        state={'pos':[.5,64.875,.5],'on_ground':False,'flight':True,'velocity':[0,0,0]}
        chest=block((0,64,0),'chest',block_entity=True);chest['solid']=False
        for changed in ({'flight':False},{'velocity':[0,-.078,0]},{'velocity':[.1,0,0]},
                        {'velocity':None},{'pos':[.5,64.8,.5]},{'pos':[.5,64.95,.5]}):
            self.assertTrue(blocks_route(chest,{**state,**changed},[.5,100,.5]))
        for changed in ({'solid':True},{'fluid':True},{'fluid':None},
                        {'state':'Block{minecraft:unknown_partial}'},{'pos':[0,65,0]}):
            self.assertTrue(blocks_route({**chest,**changed},state,[.5,100,.5]))

    def test_flight_departure_from_chest_uses_native_air_only_before_any_horizontal_move(self):
        c=FakeClient();c.state.update(pos=[.5,64.875,.5],on_ground=False,flight=True,velocity=[0,0,0])
        chest=block((0,64,0),'chest',block_entity=True);chest['solid']=False
        c.rows=[chest]+[block((5,y,0),'white_concrete')for y in range(70,81)];trace=[]
        _travel(c,[10.5,70.1,10.5],lambda:None,trace)
        moves=[p for op,p in c.actions if op=='navigate']
        self.assertTrue(moves);self.assertEqual([.5,.5],[moves[0]['target'][0],moves[0]['target'][2]])
        self.assertGreaterEqual(moves[0]['target'][1],83.1)
        self.assertTrue(all(p['air_only'] is True for p in moves))
        self.assertFalse(any(op in ('mine_block','chop','rock_quarry_batch') for op,_ in c.actions))

    def test_native_collision_rejection_still_stops_after_partial_support_filter_passes(self):
        from material_jobs.acquisition import Unavailable
        class RejectingClient(FakeClient):
            def request(self,op,**params):
                if op=='navigate':
                    self.actions.append((op,copy.deepcopy(params)))
                    return {'phase':'error','detail':'native collision shape blocked'}
                return super().request(op,**params)
        c=RejectingClient();c.state.update(pos=[.5,64.875,.5],on_ground=False,flight=True,velocity=[0,0,0])
        chest=block((0,64,0),'chest',block_entity=True);chest['solid']=False;c.rows=[chest]
        with self.assertRaises(Unavailable):_travel(c,[10.5,100,10.5],lambda:None,[])
        self.assertEqual(1,sum(op=='navigate' for op,_ in c.actions))
        self.assertEqual([.5,64.875,.5],c.status()['pos'])
        self.assertFalse(any(op in ('mine_block','chop','rock_quarry_batch') for op,_ in c.actions))

    def test_real_roof_above_flying_chest_still_blocks_without_moving_or_mining(self):
        from material_jobs.acquisition import Unavailable
        c=FakeClient();c.state.update(pos=[.5,64.875,.5],on_ground=False,flight=True,velocity=[0,0,0])
        chest=block((0,64,0),'chest',block_entity=True);chest['solid']=False
        c.rows=[chest,block((0,67,0),'stone_bricks')]
        with self.assertRaises(Unavailable):_travel(c,[10.5,70.1,10.5],lambda:None,[])
        self.assertFalse(any(op!='scan' for op,_ in c.actions))
        self.assertEqual([.5,64.875,.5],c.status()['pos'])

    def setUp(self):
        # These tests verify route geometry and mining receipts, not elapsed
        # settling time. Dedicated navigation tests exercise the real wait policy.
        wait=patch('material_jobs.navigation.settled_state',side_effect=lambda c,*args,**kwargs:c.status())
        wait.start();self.addCleanup(wait.stop)

    def test_flight_height_clears_observed_roof_before_crossing(self):
        c=FakeClient();c.state['pos']=[.5,70.1,.5]
        c.rows=[block((5,y,0),'white_concrete')for y in range(70,81)]
        trace=[]
        _travel(c,[10.5,70.1,10.5],lambda:None,trace)
        moves=[p['target'] for op,p in c.actions if op=='navigate']
        self.assertGreaterEqual(moves[0][1],83.1)
        self.assertTrue(all(p[1]>=83.1 for p in moves[:-1]))
        self.assertEqual([10.5,70.1,10.5],moves[-1])

    def test_approved_opposite_side_region_uses_two_fresh_same_target_segments(self):
        region={'item':'minecraft:snow','min':[248,64,0],'max':[253,80,5],
                'source':'natural_survey','surface_y':64}
        profile={'search_origin':[0,145,0],'search_radius':256,
                 'resource_regions':[region]}
        target=[250.5,67.1,.5]
        with tempfile.TemporaryDirectory() as folder:
            c=FakeClient();c.state['pos']=[-250.5,145,.5];c.rows=[]
            c.out=Path(folder);trace=[]
            _travel(c,target,lambda:None,trace,
                    route_scope=_resource_route_scope(profile,region))
            starts=[row for row in trace
                    if row.get('event')=='resource_route_segment_start']
            self.assertEqual(2,len(starts))
            self.assertTrue(all(row['final_target']==target for row in starts))
            points=[[-250.5,145,.5]]+[row['segment_target'] for row in starts]
            self.assertTrue(all(math.hypot(b[0]-a[0],b[2]-a[2])<=256
                                for a,b in zip(points,points[1:])))
            self.assertEqual(target,c.status()['pos'])
            saved=json.loads((Path(folder)/'resource-route-segments-latest.json').read_text())
            self.assertEqual(('done',target,2),
                             (saved['phase'],saved['final_target'],
                              sum(row.get('event')=='resource_route_segment_done'
                                  for row in saved['trace'])))

    def test_segment_scan_block_and_guard_failures_keep_original_final_target(self):
        region={'item':'minecraft:snow','min':[248,64,0],'max':[253,80,5],
                'source':'natural_survey','surface_y':64}
        profile={'search_origin':[0,145,0],'search_radius':256,
                 'resource_regions':[region]}
        scope=_resource_route_scope(profile,region);target=[250.5,67.1,.5]

        class ScanFailure(FakeClient):
            def request(self,op,**params):
                if op=='scan':
                    self.actions.append((op,copy.deepcopy(params)))
                    return {'detail':'chunk not loaded'}
                return super().request(op,**params)

        class GuardFailure(FakeClient):
            def request(self,op,**params):
                if op=='navigate':
                    self.actions.append((op,copy.deepcopy(params)))
                    self.state['pos']=[-249.5,145,.5]
                    self.state['guard_busy']=True
                    return {'phase':'waiting',
                            'detail':'air-only path changed; no blocks were excavated'}
                return super().request(op,**params)

        cases=[]
        scan=ScanFailure();cases.append(('route_uncertain',scan))
        blocked=FakeClient();blocked.rows=[block((-100,y,0),'stone')for y in range(145,319)]
        cases.append(('route_geometry_blocked',blocked))
        guard=GuardFailure();guard.rows=[];cases.append(('guard_displaced',guard))
        for expected,c in cases:
            with self.subTest(expected=expected),tempfile.TemporaryDirectory() as folder:
                c.state['pos']=[-250.5,145,.5];c.out=Path(folder);trace=[]
                with self.assertRaises(Unavailable) as stopped:
                    _travel(c,target,lambda:None,trace,route_scope=scope)
                self.assertEqual(expected,stopped.exception.code)
                self.assertEqual(target,stopped.exception.evidence['final_target'])
                final=next(row for row in reversed(trace)
                           if row.get('event')=='resource_route_segment_stopped')
                self.assertEqual((target,1,expected),
                                 (final['final_target'],final['segment'],final['route_code']))
                self.assertFalse(any(op in ('rock_quarry_batch','quarry_batch','chop')
                                     for op,_ in c.actions))
                saved=json.loads((Path(folder)/'resource-route-segments-latest.json').read_text())
                self.assertEqual(('stopped',target,expected),
                                 (saved['phase'],saved['final_target'],saved['route_code']))

    def profile(self,item,low=None,high=None):
        return {'resource_regions':[{'item':item,'min':low or [0,64,0],'max':high or [1,67,1]}]}
    def run_acquire(self,c,out,target=12,profile=None,checkpoint=lambda:None):
        c.root=Path(out)/'automation';c.root.mkdir(exist_ok=True)
        return acquire(c,c.item,target,profile or self.profile(c.item),out,checkpoint)

    def test_drives_rock_native_with_delta_and_confirms_absolute_target(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient(before=7);calls=[]
            result=self.run_acquire(c,out,checkpoint=lambda:calls.append('checkpoint'))
            self.assertEqual('done',result['phase']);self.assertEqual(12,result['after']);self.assertEqual(5,result['gained'])
            command=next(params for op,params in c.actions if op=='rock_quarry_batch')
            self.assertEqual(5,command['target_count']);self.assertEqual('collect',command['completion'])
            self.assertEqual([0,64,0],command['min']);self.assertEqual([1,67,1],command['max'])
            self.assertGreater(len(calls),len(c.actions)-1)

    def test_done_receipt_without_inventory_gain_is_not_completion_or_replayed(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient(gain=0)
            first=self.run_acquire(c,out);self.assertEqual('blocked',first['phase'])
            self.assertEqual('no_inventory_progress',first['code'])
            before=len(c.actions);second=self.run_acquire(c,out)
            self.assertEqual('blocked',second['phase']);self.assertEqual(before,len(c.actions))
            self.assertEqual(1,sum(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_partial_native_stop_returns_waiting_only_with_real_progress(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient(gain=3,native_phase='waiting')
            result=self.run_acquire(c,out)
            self.assertEqual('waiting',result['phase']);self.assertEqual(3,result['gained'])
            self.assertEqual(3,result['after'])

    def test_active_child_cannot_be_reported_done(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient();c.still_active=True
            result=self.run_acquire(c,out)
            self.assertEqual('blocked',result['phase'])
            journal=json.loads(next(Path(out).glob('acquisition-*.json')).read_text())
            self.assertEqual('inflight',next(iter(journal['visited'].values()))['state'])

    def test_building_or_wet_region_is_saved_and_not_rescanned(self):
        for replacement in (block((0,64,0),'white_concrete'),block((-3,64,0),'water',fluid=True)):
            with self.subTest(replacement=replacement),tempfile.TemporaryDirectory() as out:
                c=FakeClient();c.rows=[r for r in c.rows if r['pos']!=replacement['pos']]+[replacement]
                # Restrict vertical range so a smaller lower/upper slice cannot avoid the obstacle.
                profile=self.profile(c.item,[0,64,0],[1,65,1])
                first=self.run_acquire(c,out,profile=profile)
                self.assertEqual('blocked',first['phase']);self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))
                before=len(c.actions);self.run_acquire(c,out,profile=profile);self.assertEqual(before,len(c.actions))

    def test_unknown_reply_or_pause_never_reissues_the_batch(self):
        for failure in (RuntimeError('Native operation timed out; do not replay it'),JobPaused('pause')):
            with self.subTest(failure=str(failure)),tempfile.TemporaryDirectory() as out:
                c=FakeClient();original=c.request
                def request(op,**params):
                    if op=='rock_quarry_batch':c.actions.append((op,params));raise failure
                    return original(op,**params)
                c.request=request
                with self.assertRaises(type(failure)):self.run_acquire(c,out)
                before=len(c.actions);second=self.run_acquire(c,out)
                self.assertEqual('blocked',second['phase']);self.assertEqual(before,len(c.actions))

    def test_insufficient_tool_or_any_silk_pickaxe_is_explicitly_blocked(self):
        for kind in ('worn','silk'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as out:
                c=FakeClient()
                if kind=='worn':c.state['inventory'][0]['durability']=20
                else:c.state['inventory'][5]={'slot':5,'item':'minecraft:diamond_pickaxe','count':1,'durability':600,
                                            'enchantments':[{'id':'minecraft:silk_touch','level':1}]}
                result=self.run_acquire(c,out)
                self.assertEqual('blocked',result['phase']);self.assertEqual([],c.actions)

    def test_sand_uses_existing_quarry_choice_and_native_sand_op(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient(item='minecraft:sand',resource='sand',before=2)
            for row in c.rows:
                if row['pos'][1]==63:row['state']='Block{minecraft:stone}'
            result=self.run_acquire(c,out,target=6)
            self.assertEqual('done',result['phase']);self.assertEqual(6,result['after'])
            command=next(params for op,params in c.actions if op=='quarry_batch')
            self.assertEqual(4,command['target_count']);self.assertNotIn('completion',command)

    def test_iron_uses_ore_candidates_but_counts_actual_raw_iron(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient(item='minecraft:raw_iron',resource='deepslate_iron_ore',before=2)
            result=self.run_acquire(c,out,target=5)
            self.assertEqual('done',result['phase']);self.assertEqual(5,result['after'])
            self.assertEqual('minecraft:raw_iron',next(params for op,params in c.actions if op=='rock_quarry_batch')['item'])

    def raw_iron_block_client(self, **kwargs):
        c=FakeClient(item='minecraft:raw_iron_block',resource='raw_iron_block',**kwargs)
        for row in c.rows:row['pos'][1]-=96
        c.state['pos']=[.5,-26.9,.5]
        return c

    def test_deep_raw_iron_blocks_are_direct_targets_with_actual_block_delta(self):
        with tempfile.TemporaryDirectory() as out:
            c=self.raw_iron_block_client(before=2)
            result=self.run_acquire(c,out,target=5,profile=self.profile(c.item,[0,-32,0],[1,-29,1]))
            self.assertEqual(('done',5,3),(result['phase'],result['after'],result['gained']))
            batch=next(params for op,params in c.actions if op=='rock_quarry_batch')
            self.assertEqual(('minecraft:raw_iron_block',3,'collect'),
                             (batch['item'],batch['target_count'],batch['completion']))

    def test_surface_raw_iron_building_blocks_are_not_quarry_material_for_any_target(self):
        for item in ('minecraft:raw_iron_block','minecraft:raw_iron','minecraft:tuff'):
            with self.subTest(item=item),tempfile.TemporaryDirectory() as out:
                c=FakeClient(item=item,resource='raw_iron_block')
                c.rows[-1]['state']='Block{minecraft:tuff}' if item=='minecraft:tuff' else 'Block{minecraft:iron_ore}'
                result=self.run_acquire(c,out)
                self.assertEqual('blocked',result['phase'])
                self.assertFalse(any(op in ('navigate','rock_quarry_batch') for op,_ in c.actions))

    def test_raw_iron_block_rejects_wet_buffer_and_does_not_replay_missing_block_gain(self):
        with tempfile.TemporaryDirectory() as out:
            c=self.raw_iron_block_client(gain=0)
            profile=self.profile(c.item,[0,-32,0],[1,-29,1])
            result=self.run_acquire(c,out,profile=profile)
            self.assertEqual(('blocked','no_inventory_progress'),(result['phase'],result['code']))
            self.run_acquire(c,out,profile=profile)
            self.assertEqual(1,sum(op=='rock_quarry_batch' for op,_ in c.actions))
        with tempfile.TemporaryDirectory() as out:
            c=self.raw_iron_block_client()
            c.rows.append(block((-3,-32,0),'water',fluid=True))
            result=self.run_acquire(c,out,profile=self.profile(c.item,[0,-32,0],[1,-31,1]))
            self.assertEqual('blocked',result['phase'])
            self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_no_authorized_region_or_already_sufficient_inventory_makes_no_request(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient(before=20);self.assertEqual('done',self.run_acquire(c,out)['phase']);self.assertEqual([],c.actions)
            c=FakeClient();result=acquire(c,c.item,12,{'resource_regions':[]},out,lambda:None)
            self.assertEqual('blocked',result['phase']);self.assertEqual([],c.actions)

    def test_tree_survey_selects_natural_tree_and_one_bounded_native_chop(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient(item='minecraft:spruce_log',before=2,gain=4)
            c.state['pos']=[-6.5,71,.5]
            c.rows=[block((x,63,z),'grass_block') for x in range(-11,12) for z in range(-11,12)]
            c.rows += [block((0,y,0),'spruce_log') for y in range(64,68)]
            c.trees=[{'pos':[0,64,0],'top':68,'natural_leaves':8}]
            result=self.run_acquire(c,out,target=6,profile=self.profile(c.item,[-12,60,-12],[12,105,12]))
            self.assertEqual('done',result['phase']);self.assertEqual(6,result['after'])
            command=next(params for op,params in c.actions if op=='chop')
            self.assertEqual(1,command['tree_limit']);self.assertEqual(6,command['target_count'])

    def test_uncleared_overburden_is_not_tunneled_through(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient();c.rows.append(block((1,69,1),'stone'))
            result=self.run_acquire(c,out)
            self.assertEqual('blocked',result['phase'])
            self.assertFalse(any(op in ('quarry_batch','rock_quarry_batch','chop') for op,_ in c.actions))

    def test_authorized_natural_access_shaft_uses_bounded_clear_then_collect(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient();c.state['pos']=[.5,24.1,.5]
            c.rows=[block((x,y,z),'stone' if y>=0 else 'deepslate') for x in range(2) for z in range(2) for y in range(-5,22)]
            region={'item':c.item,'min':[0,-4,0],'max':[1,-1,1],'source':'natural_survey','surface_y':21,
                    'access_shaft':{'min':[0,0,0],'max':[1,21,1]}}
            result=self.run_acquire(c,out,target=12,profile={'resource_regions':[region]})
            self.assertEqual('done',result['phase']);self.assertEqual(12,result['after'])
            batches=[params for op,params in c.actions if op=='rock_quarry_batch']
            self.assertEqual(['clear','clear','collect'],[p['completion'] for p in batches])
            self.assertEqual([0,0,12],[p['target_count'] for p in batches])
            self.assertTrue(all(2<=p['max'][1]-p['min'][1]+1<=18 for p in batches))
            self.assertEqual(([0,4,0],[1,21,1]),(batches[0]['min'],batches[0]['max']))
            journal=json.loads(next(Path(out).glob('acquisition-*.json')).read_text())
            self.assertEqual(2,sum(r['state']=='clear_verified' for r in journal['visited'].values()))

    def test_wet_or_gravel_access_is_skipped_without_destructive_action(self):
        for hazard in ('gravel','water'):
            with self.subTest(hazard=hazard),tempfile.TemporaryDirectory() as out:
                c=FakeClient();c.state['pos']=[.5,24.1,.5]
                c.rows=[block((x,y,z),'stone' if y>=0 else 'deepslate') for x in range(2) for z in range(2) for y in range(-5,22)]
                c.rows=[r for r in c.rows if r['pos']!=[0,8,0]]+[block((0,8,0),hazard,fluid=hazard=='water')]
                region={'item':c.item,'min':[0,-4,0],'max':[1,-1,1],'source':'natural_survey','surface_y':21,
                        'access_shaft':{'min':[0,0,0],'max':[1,21,1]}}
                result=self.run_acquire(c,out,target=12,profile={'resource_regions':[region]})
                self.assertEqual('blocked',result['phase']);self.assertEqual('no_safe_candidate',result['code'])
                self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_known_stopped_shaft_records_actual_remaining_without_replay(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient();c.state['pos']=[.5,24.1,.5]
            c.rows=[block((x,y,z),'stone' if y>=0 else 'deepslate') for x in range(2) for z in range(2) for y in range(-5,22)]
            region={'item':c.item,'min':[0,-4,0],'max':[1,-1,1],'source':'natural_survey','surface_y':21,
                    'access_shaft':{'min':[0,0,0],'max':[1,21,1]}}
            original=c.request
            def stopped(op,**params):
                if op!='rock_quarry_batch':return original(op,**params)
                c.actions.append((op,params));c.last='clear-stopped'
                return {'phase':'waiting','rock_quarry':{'id':c.last,'world_session':c.world,
                    'min':params['min'],'max':params['max'],'item':c.item,'completion':'clear',
                    'active':False,'phase':'waiting','area_cleared':False,'pending_blocks':0,'remaining_blocks':72}}
            c.request=stopped
            first=self.run_acquire(c,out,target=12,profile={'resource_regions':[region]})
            self.assertEqual('blocked',first['phase']);self.assertEqual('native_clear_stopped',first['code'])
            journal=json.loads(next(Path(out).glob('acquisition-*.json')).read_text())
            self.assertEqual('clear_stopped',next(iter(journal['visited'].values()))['state'])
            second=self.run_acquire(c,out,target=12,profile={'resource_regions':[region]})
            self.assertEqual('native_clear_stopped',second['code'])
            self.assertEqual(1,sum(op=='rock_quarry_batch' for op,_ in c.actions))

    def shaft_fixture(self, *, bottom=0, surface=21):
        c=FakeClient();c.state['pos']=[.5,surface+3.1,.5]
        c.rows=[block((x,y,z),'stone' if y>=bottom else 'deepslate')
                for x in range(2) for z in range(2) for y in range(bottom-5,surface+1)]
        region={'item':c.item,'min':[0,bottom-4,0],'max':[1,bottom-1,1],
                'source':'natural_survey','surface_y':surface,
                'access_shaft':{'min':[0,bottom,0],'max':[1,surface,1]}}
        return c,{'resource_regions':[region]}

    def stopped_shaft(self,c,*,detail=None,changes=None):
        from material_jobs.acquisition import CLEAR_RESUPPLY_DETAIL, NATURAL, block_id
        original=c.request
        def stopped(op,**params):
            if op!='rock_quarry_batch':return original(op,**params)
            c.actions.append((op,copy.deepcopy(params)));c.last='clear-resupply'
            remaining=sum(block_id(r) in NATURAL and all(params['min'][i]<=r['pos'][i]<=params['max'][i]
                          for i in range(3)) for r in c.rows)
            receipt={'id':c.last,'world_session':c.world,'min':params['min'],'max':params['max'],
                     'item':c.item,'completion':'clear','active':False,'phase':'waiting',
                     'area_cleared':False,'pending_blocks':0,'remaining_blocks':remaining}
            receipt.update(changes or {})
            return {'phase':'waiting','detail':CLEAR_RESUPPLY_DETAIL if detail is None else detail,'rock_quarry':receipt}
        c.request=stopped
        return original

    def test_second_collection_reuses_fresh_empty_shaft_without_the_old_slice_floor(self):
        with tempfile.TemporaryDirectory() as out:
            c,profile=self.shaft_fixture()
            self.assertEqual('done',self.run_acquire(c,out,target=12,profile=profile)['phase'])
            path=next(Path(out).glob('acquisition-*.json'))
            old=json.loads(path.read_text())
            receipts={key:row['native'] for key,row in old['visited'].items() if key.startswith('access-')}
            self.assertFalse(any(r['pos'][1]==3 for r in c.rows))
            result=self.run_acquire(c,out,target=24,profile=profile)
            self.assertEqual('done',result['phase']);self.assertEqual(24,result['after'])
            batches=[params for op,params in c.actions if op=='rock_quarry_batch']
            self.assertEqual(['clear','clear','collect','collect'],[p['completion'] for p in batches])
            latest=json.loads(path.read_text())
            self.assertFalse(any(row['state']=='empty_or_unsafe' for row in latest['visited'].values()))
            for key,receipt in receipts.items():
                self.assertEqual('clear_verified',latest['visited'][key]['state'])
                self.assertEqual(receipt,latest['visited'][key]['native'])

    def test_cleared_shaft_still_rejects_fluids_falling_blocks_containers_and_obstructions(self):
        hazards=[block((0,8,0),'water',fluid=True),block((0,8,0),'gravel'),
                 block((0,8,0),'white_concrete'),block((3,8,0),'chest',block_entity=True),
                 block((0,8,0),'torch'),block((0,8,0),'fire')]
        for hazard in hazards:
            with self.subTest(hazard=hazard),tempfile.TemporaryDirectory() as out:
                c,profile=self.shaft_fixture()
                c.rows=[r for r in c.rows if r['pos'][1]<0]+[hazard]
                result=self.run_acquire(c,out,profile=profile)
                self.assertEqual('no_safe_candidate',result['code'])
                self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_nonempty_shaft_still_requires_every_floor_support_cell(self):
        with tempfile.TemporaryDirectory() as out:
            c,profile=self.shaft_fixture()
            c.rows=[r for r in c.rows if r['pos']!=[0,3,0]]
            result=self.run_acquire(c,out,profile=profile)
            self.assertEqual('no_safe_candidate',result['code'])
            self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_201_high_access_is_sliced_without_expanding_quarry_or_native_limits(self):
        from material_jobs.acquisition import _bounds, Unavailable
        with tempfile.TemporaryDirectory() as out:
            c,profile=self.shaft_fixture(bottom=-40,surface=160)
            result=self.run_acquire(c,out,target=12,profile=profile)
            self.assertEqual('done',result['phase'])
            batches=[params for op,params in c.actions if op=='rock_quarry_batch']
            clears=[p for p in batches if p['completion']=='clear']
            self.assertEqual(12,len(clears))
            self.assertEqual(201,sum(p['max'][1]-p['min'][1]+1 for p in clears))
            self.assertTrue(all(p['max'][0]-p['min'][0]==p['max'][2]-p['min'][2]==1 for p in clears))
            self.assertTrue(all(2<=p['max'][1]-p['min'][1]+1<=18 for p in batches))
            self.assertTrue(all((p['max'][0]-p['min'][0]+1)*(p['max'][1]-p['min'][1]+1)
                                *(p['max'][2]-p['min'][2]+1)<=648 for p in batches))
            for op,p in c.actions:
                if op=='scan':
                    self.assertLessEqual((p['max'][0]-p['min'][0]+1)*(p['max'][1]-p['min'][1]+1)
                                         *(p['max'][2]-p['min'][2]+1),50000)
            with self.assertRaises(Unavailable):
                _bounds({'min':[0,-40,0],'max':[1,160,1]})
            self.assertEqual(([0,-64,0],[1,319,1]),_bounds({'min':[0,-64,0],'max':[1,319,1]},shaft=True))

    def test_access_beyond_legal_world_height_is_rejected_before_native_mining(self):
        for bottom,surface in ((-65,21),(0,320)):
            with self.subTest(bottom=bottom,surface=surface),tempfile.TemporaryDirectory() as out:
                c,profile=self.shaft_fixture(bottom=bottom,surface=surface)
                result=self.run_acquire(c,out,profile=profile)
                self.assertEqual('blocked',result['phase'])
                self.assertIn('-64..319',result['detail'])
                self.assertFalse(any(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_exact_backpack_reserve_stop_rechecks_and_resumes_with_old_receipt_preserved(self):
        with tempfile.TemporaryDirectory() as out:
            c,profile=self.shaft_fixture();original=self.stopped_shaft(c)
            first=self.run_acquire(c,out,profile=profile)
            self.assertEqual(('waiting','quarry_backpack_reserve'),(first['phase'],first['code']))
            path=next(Path(out).glob('acquisition-*.json'));ledger=json.loads(path.read_text())
            key=next(key for key in ledger['visited'] if key.startswith('access-'))
            previous=copy.deepcopy(ledger['visited'][key])
            self.assertEqual('clear_resupply',previous['state'])
            self.assertEqual(72,previous['remaining']);self.assertEqual(0,previous['native']['pending_blocks'])
            c.request=original;action_start=len(c.actions)
            resumed=self.run_acquire(c,out,profile=profile)
            self.assertEqual('done',resumed['phase'])
            resumed_actions=c.actions[action_start:]
            first_native=next(i for i,(op,_) in enumerate(resumed_actions) if op=='rock_quarry_batch')
            self.assertTrue(any(op=='scan' and p['min']==[-3,2,-3] and p['max']==[4,23,4]
                                for op,p in resumed_actions[:first_native]))
            latest=json.loads(path.read_text())['visited'][key]
            self.assertEqual('clear_verified',latest['state'])
            self.assertEqual(previous,latest['previous_attempts'][0])
            self.assertNotEqual(previous['native']['id'],latest['native']['id'])

    def test_exact_resupply_stop_with_fresh_zero_remaining_is_not_permanently_blocked(self):
        from material_jobs.acquisition import CLEAR_RESUPPLY_DETAIL
        with tempfile.TemporaryDirectory() as out:
            c,profile=self.shaft_fixture();original=c.request
            def just_cleared(op,**params):
                reply=original(op,**params)
                if op=='rock_quarry_batch' and params.get('completion')=='clear':
                    reply.update(phase='waiting',detail=CLEAR_RESUPPLY_DETAIL)
                    reply['rock_quarry'].update(phase='waiting',area_cleared=False)
                return reply
            c.request=just_cleared
            first=self.run_acquire(c,out,profile=profile)
            self.assertEqual('quarry_backpack_reserve',first['code'])
            path=next(Path(out).glob('acquisition-*.json'));ledger=json.loads(path.read_text())
            key=next(iter(ledger['visited']));prior=copy.deepcopy(ledger['visited'][key]['native'])
            self.assertEqual(0,ledger['visited'][key]['remaining'])
            c.request=original
            self.assertEqual('done',self.run_acquire(c,out,profile=profile)['phase'])
            later=json.loads(path.read_text())['visited'][key]
            self.assertEqual('clear_verified',later['state']);self.assertEqual(prior,later['native'])
            self.assertEqual(2,sum(op=='rock_quarry_batch' and p.get('completion')=='clear' for op,p in c.actions))

    def test_resupply_remaining_match_does_not_override_new_fluid_in_actual_scan(self):
        with tempfile.TemporaryDirectory() as out:
            c,profile=self.shaft_fixture();self.stopped_shaft(c);stop=c.request
            def wet_stop(op,**params):
                reply=stop(op,**params)
                if op=='rock_quarry_batch':
                    c.rows=[r for r in c.rows if r['pos']!=[0,8,0]]+[block((0,8,0),'water',fluid=True)]
                    reply['rock_quarry']['remaining_blocks']-=1
                return reply
            c.request=wet_stop
            result=self.run_acquire(c,out,profile=profile)
            self.assertNotEqual('quarry_backpack_reserve',result.get('code'))
            ledger=json.loads(next(Path(out).glob('acquisition-*.json')).read_text())
            self.assertEqual('inflight',next(iter(ledger['visited'].values()))['state'])
            before=len(c.actions);self.run_acquire(c,out,profile=profile);self.assertEqual(before,len(c.actions))

    def test_similar_backpack_stop_reason_does_not_authorize_retry(self):
        from material_jobs.acquisition import CLEAR_RESUPPLY_DETAIL
        for detail in (CLEAR_RESUPPLY_DETAIL+' ',CLEAR_RESUPPLY_DETAIL.upper(),'rock quarry tool reserve exhausted'):
            with self.subTest(detail=detail),tempfile.TemporaryDirectory() as out:
                c,profile=self.shaft_fixture();self.stopped_shaft(c,detail=detail)
                result=self.run_acquire(c,out,profile=profile)
                self.assertEqual('native_clear_stopped',result['code'])
                self.assertEqual('native_clear_stopped',self.run_acquire(c,out,profile=profile)['code'])
                self.assertEqual(1,sum(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_resupply_reason_cannot_override_uncertain_receipt_or_actual_remaining(self):
        for changes in ({'id':'foreign'},{'pending_blocks':1},{'active':True},{'remaining_blocks':71}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as out:
                c,profile=self.shaft_fixture();self.stopped_shaft(c,changes=changes)
                first=self.run_acquire(c,out,profile=profile)
                self.assertNotEqual('quarry_backpack_reserve',first.get('code'))
                ledger=json.loads(next(Path(out).glob('acquisition-*.json')).read_text())
                self.assertEqual('inflight',next(iter(ledger['visited'].values()))['state'])
                before=len(c.actions)
                self.assertEqual('blocked',self.run_acquire(c,out,profile=profile)['phase'])
                self.assertEqual(before,len(c.actions))

    def test_empty_shaft_does_not_resolve_unknown_or_migrate_old_stopped_record(self):
        from material_jobs.acquisition import CLEAR_RESUPPLY_DETAIL
        for saved_state in ('inflight','clear_stopped'):
            with self.subTest(saved_state=saved_state),tempfile.TemporaryDirectory() as out:
                c,profile=self.shaft_fixture();self.stopped_shaft(c)
                self.run_acquire(c,out,profile=profile)
                path=next(Path(out).glob('acquisition-*.json'));ledger=json.loads(path.read_text())
                key=next(iter(ledger['visited']))
                ledger['visited'][key].update(state=saved_state,native_detail=CLEAR_RESUPPLY_DETAIL)
                path.write_text(json.dumps(ledger));c.rows=[r for r in c.rows if r['pos'][1]<0]
                first_native_count=sum(op=='rock_quarry_batch' for op,_ in c.actions)
                result=self.run_acquire(c,out,profile=profile)
                self.assertEqual('blocked',result['phase'])
                self.assertEqual(first_native_count,sum(op=='rock_quarry_batch' for op,_ in c.actions))
                self.assertEqual(saved_state,json.loads(path.read_text())['visited'][key]['state'])

    def stopped_collect(self,c,*,gain=0,detail=None,changes=None,mutate_rows=None):
        from material_jobs.acquisition import CLEAR_RESUPPLY_DETAIL, NATURAL, block_id
        original=c.request
        def stopped(op,**params):
            if op!='rock_quarry_batch' or params.get('completion')!='collect':return original(op,**params)
            c.actions.append((op,copy.deepcopy(params)));c.last='collect-resupply'
            removed=[r for r in c.rows if all(params['min'][i]<=r['pos'][i]<=params['max'][i]
                     for i in range(3))][:gain]
            c.rows=[r for r in c.rows if r not in removed]
            c.state['inventory'][3]['count']+=gain
            if mutate_rows:mutate_rows(c)
            remaining=sum(block_id(r) in NATURAL and all(params['min'][i]<=r['pos'][i]<=params['max'][i]
                          for i in range(3)) for r in c.rows)
            receipt={'id':c.last,'world_session':c.world,'min':params['min'],'max':params['max'],
                     'item':c.item,'completion':'collect','active':False,'phase':'waiting',
                     'pending_blocks':0,'remaining_blocks':remaining}
            receipt.update(changes or {})
            return {'phase':'waiting','detail':CLEAR_RESUPPLY_DETAIL if detail is None else detail,'rock_quarry':receipt}
        c.request=stopped
        return original

    def test_collect_backpack_reserve_zero_or_partial_gain_is_revalidated_progress_and_can_resume(self):
        for gain in (0,3):
            with self.subTest(gain=gain),tempfile.TemporaryDirectory() as out:
                c=FakeClient(before=2);original=self.stopped_collect(c,gain=gain)
                result=self.run_acquire(c,out,target=12)
                self.assertEqual(('waiting','quarry_backpack_reserve'),(result['phase'],result['code']))
                self.assertEqual(2+gain,result['after']);self.assertEqual(gain,result['gained'])
                self.assertEqual('scan',c.actions[-1][0])
                self.assertEqual(([0,64,0],[1,67,1]),(c.actions[-1][1]['min'],c.actions[-1][1]['max']))
                path=next(Path(out).glob('acquisition-*.json'));ledger=json.loads(path.read_text())
                key=next(iter(ledger['visited']));previous=copy.deepcopy(ledger['visited'][key])
                self.assertEqual('progress',previous['state']);self.assertEqual(16-gain,previous['remaining'])
                self.assertEqual('collect-resupply',previous['native']['id'])
                c.request=original
                resumed=self.run_acquire(c,out,target=12)
                self.assertEqual('done',resumed['phase']);self.assertEqual(12,resumed['after'])
                latest=json.loads(path.read_text())['visited'][key]
                self.assertEqual(previous,latest['previous_attempts'][0])
                self.assertEqual(2,sum(op=='rock_quarry_batch' for op,_ in c.actions))

    def test_collect_resupply_requires_exact_native_identity_scope_completion_and_terminal_state(self):
        variants=({'id':'foreign'},{'world_session':'old-world'},{'min':[1,64,0]},{'max':[1,66,1]},
                  {'item':'minecraft:stone'},{'completion':'clear'},{'active':True},{'pending_blocks':1},
                  {'pending_blocks':False},{'phase':'running'},{'remaining_blocks':None},{'remaining_blocks':-1})
        for changes in variants:
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as out:
                c=FakeClient();self.stopped_collect(c,gain=3,changes=changes)
                result=self.run_acquire(c,out)
                self.assertEqual('blocked',result['phase']);self.assertNotEqual('quarry_backpack_reserve',result.get('code'))
                path=next(Path(out).glob('acquisition-*.json'))
                self.assertEqual('inflight',next(iter(json.loads(path.read_text())['visited'].values()))['state'])
                before=len(c.actions);self.run_acquire(c,out);self.assertEqual(before,len(c.actions))

    def test_collect_resupply_requires_waiting_reply_even_when_native_snapshot_claims_waiting(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient();self.stopped_collect(c);stopped=c.request
            def wrong_phase(op,**params):
                reply=stopped(op,**params)
                if op=='rock_quarry_batch':reply['phase']='done'
                return reply
            c.request=wrong_phase
            self.assertEqual('blocked',self.run_acquire(c,out)['phase'])
            entry=next(iter(json.loads(next(Path(out).glob('acquisition-*.json')).read_text())['visited'].values()))
            self.assertEqual('inflight',entry['state'])

    def test_collect_resupply_checks_actual_remaining_and_refuses_new_hazards(self):
        for case in ('remaining-mismatch','water','container','building'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as out:
                c=FakeClient()
                def mutate(client):
                    if case=='remaining-mismatch':return
                    name={'water':'water','container':'chest','building':'white_concrete'}[case]
                    client.rows=[r for r in client.rows if r['pos']!=[0,64,0]]+[
                        block((0,64,0),name,fluid=case=='water',block_entity=case=='container')]
                self.stopped_collect(c,changes={'remaining_blocks':15} if case=='remaining-mismatch' else None,mutate_rows=mutate)
                result=self.run_acquire(c,out)
                self.assertEqual('blocked',result['phase'])
                entry=next(iter(json.loads(next(Path(out).glob('acquisition-*.json')).read_text())['visited'].values()))
                self.assertEqual('inflight',entry['state']);self.assertEqual('collect-resupply',entry['native']['id'])
                before=len(c.actions);self.run_acquire(c,out);self.assertEqual(before,len(c.actions))

    def test_collect_resupply_rechecks_no_active_controller_after_the_verification_scan(self):
        for controller in ('borer_active','chopping','navigating','native_material_busy'):
            with self.subTest(controller=controller),tempfile.TemporaryDirectory() as out:
                c=FakeClient();self.stopped_collect(c);stopped=c.request
                def reactivated(op,**params):
                    previous=getattr(c,'last',None)
                    reply=stopped(op,**params)
                    if op=='scan' and previous=='collect-resupply':c.state[controller]=True
                    return reply
                c.request=reactivated
                result=self.run_acquire(c,out)
                self.assertEqual('blocked',result['phase'])
                entry=next(iter(json.loads(next(Path(out).glob('acquisition-*.json')).read_text())['visited'].values()))
                self.assertEqual('inflight',entry['state'])

    def test_collect_resupply_pause_during_fresh_scan_keeps_native_receipt_and_never_replays(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient();self.stopped_collect(c)
            def checkpoint():
                if getattr(c,'last',None)=='collect-resupply':raise JobPaused('manual pause before evidence scan')
            with self.assertRaises(JobPaused):self.run_acquire(c,out,checkpoint=checkpoint)
            entry=next(iter(json.loads(next(Path(out).glob('acquisition-*.json')).read_text())['visited'].values()))
            self.assertEqual('inflight',entry['state']);self.assertEqual('collect-resupply',entry['native']['id'])
            before=len(c.actions);self.run_acquire(c,out);self.assertEqual(before,len(c.actions))

    def test_nonexact_collect_stop_keeps_original_gain_and_no_progress_behavior(self):
        from material_jobs.acquisition import CLEAR_RESUPPLY_DETAIL
        for gain in (0,3):
            with self.subTest(gain=gain),tempfile.TemporaryDirectory() as out:
                c=FakeClient();self.stopped_collect(c,gain=gain,detail=CLEAR_RESUPPLY_DETAIL+' ')
                result=self.run_acquire(c,out)
                self.assertEqual('waiting' if gain else 'blocked',result['phase'])
                self.assertNotEqual('quarry_backpack_reserve',result.get('code'))
                entry=next(iter(json.loads(next(Path(out).glob('acquisition-*.json')).read_text())['visited'].values()))
                self.assertEqual('progress' if gain else 'no_progress',entry['state'])

    def test_stale_or_busy_clear_receipts_remain_uncertain(self):
        from material_jobs.acquisition import _clear_receipt
        c=FakeClient();c.last='mine-owned';low=[0,4,0];high=[1,21,1]
        receipt={'id':c.last,'world_session':c.world,'min':low,'max':high,'item':c.item,
                 'completion':'clear','active':False,'phase':'waiting','pending_blocks':0}
        self.assertIsNotNone(_clear_receipt(c,c.item,low,high,{'phase':'waiting','rock_quarry':receipt},c.status()))
        for change in ({'id':'foreign'},{'world_session':'old'},{'min':[2,4,0]},
                       {'active':True},{'pending_blocks':1},{'phase':'running'}):
            with self.subTest(change=change):
                self.assertIsNone(_clear_receipt(c,c.item,low,high,{'phase':'waiting','rock_quarry':{**receipt,**change}},c.status()))
        self.assertIsNone(_clear_receipt(c,c.item,low,high,{'phase':'waiting','rock_quarry':receipt},{**c.status(),'borer_active':True}))

    def test_direct_andesite_target_is_supported_without_conversion(self):
        with tempfile.TemporaryDirectory() as out:
            c=FakeClient(item='minecraft:andesite',resource='andesite')
            result=self.run_acquire(c,out,target=8)
            self.assertEqual('done',result['phase']);self.assertEqual(8,result['after'])


if __name__=='__main__':unittest.main()
