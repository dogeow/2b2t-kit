import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from types import SimpleNamespace

from material_jobs.navigation import leave_quarry, quarry_exit_candidates, shaft_path, settled_state, leave_projection
from material_jobs.protocol import JobBlocked


class FakeClient:
    def __init__(self,root):
        self.out=root;self.world='w';self.pos=[4.5,10.,2.5];self.calls=[];self.blocks={};self.protocol=2
        self.scan_phase='done';self.bad_arrival=False
        for x in range(-2,8):
            for z in range(-2,8):
                if not (0<=x<=1 and 0<=z<=1):
                    self.blocks[(x,12,z)]={'pos':[x,12,z],'passable':False,'state':'Block{minecraft:stone}'}

    def status(self):
        return {'pos':list(self.pos),'world_session':self.world,'air_only_navigation_protocol':self.protocol}

    def request(self,op,**kw):
        self.calls.append((op,kw))
        if op=='scan':
            rows=[copy.deepcopy(row) for p,row in self.blocks.items() if all(kw['min'][i]<=p[i]<=kw['max'][i] for i in range(3))]
            return {'phase':self.scan_phase,'world_session':self.world,'blocks':rows}
        if op=='navigate':
            assert kw['air_only'] and kw['arrival']==.25
            self.pos=list(kw['target'])
            if self.bad_arrival:self.pos[0]+=.7
            return {'phase':'done','world_session':self.world}
        raise AssertionError('Exit navigation may not dig or interact: '+op)


class Clock:
    def __init__(self):self.now=0.;self.sleeps=[]
    def monotonic(self):return self.now
    def sleep(self,seconds):self.sleeps.append(seconds);self.now+=seconds


class SettledStateTest(unittest.TestCase):
    """Exercise the real wait policy with elapsed time supplied by a fake clock."""
    def test_grounded_gravity_impulse_is_not_mistaken_for_position_drift(self):
        clock=Clock();state={'pos':[1.,64.875,1.],'velocity':[0,-.0784,0],'on_ground':True}
        client=SimpleNamespace(status=lambda:dict(state))
        with patch('material_jobs.navigation.time.monotonic',side_effect=clock.monotonic), \
                patch('material_jobs.navigation.time.sleep',side_effect=clock.sleep):
            self.assertEqual(state,settled_state(client,seconds=1))
        self.assertGreaterEqual(clock.now,.4)

    def test_airborne_vertical_speed_still_prevents_parking(self):
        clock=Clock();client=SimpleNamespace(status=lambda:{'pos':[1.,80.,1.],'velocity':[0,-.0784,0],'on_ground':False})
        with patch('material_jobs.navigation.time.monotonic',side_effect=clock.monotonic), \
                patch('material_jobs.navigation.time.sleep',side_effect=clock.sleep):
            with self.assertRaises(JobBlocked):settled_state(client,seconds=1)

    def test_arrival_receipt_does_not_hide_continuing_velocity(self):
        clock=Clock()
        client=SimpleNamespace(status=Mock(return_value={'pos':[1.,10.,1.],'velocity':[.12,0,0]}))
        with patch('material_jobs.navigation.time.monotonic',side_effect=clock.monotonic), \
                patch('material_jobs.navigation.time.sleep',side_effect=clock.sleep):
            with self.assertRaisesRegex(JobBlocked,'漂移'):
                settled_state(client,[1.,10.,1.],seconds=1)
        self.assertGreaterEqual(clock.now,1)

    def test_stable_window_restarts_after_an_intervening_motion_sample(self):
        clock=Clock()
        def status():
            return {'pos':[1.,10.,1.],'velocity':[.12 if .29<=clock.now<.44 else 0,0,0],
                    'sample_time':clock.now}
        client=SimpleNamespace(status=status)
        with patch('material_jobs.navigation.time.monotonic',side_effect=clock.monotonic), \
                patch('material_jobs.navigation.time.sleep',side_effect=clock.sleep):
            result=settled_state(client,[1.,10.,1.],seconds=2)
        # Quiet samples before 0.3 cannot be added to the later stable period.
        self.assertGreaterEqual(result['sample_time'],.85)
        self.assertLess(result['sample_time'],1.1)

    def test_changing_position_cannot_pass_even_when_velocity_reports_zero(self):
        clock=Clock()
        client=SimpleNamespace(status=lambda:{'pos':[clock.now*2,10.,1.],'velocity':[0,0,0]})
        with patch('material_jobs.navigation.time.monotonic',side_effect=clock.monotonic), \
                patch('material_jobs.navigation.time.sleep',side_effect=clock.sleep):
            with self.assertRaisesRegex(JobBlocked,'漂移'):settled_state(client,seconds=1)
        self.assertGreaterEqual(clock.now,1)

    def test_quiet_but_outside_arrival_tolerance_never_passes(self):
        clock=Clock()
        client=SimpleNamespace(status=lambda:{'pos':[1.7,10.,1.],'velocity':[0,0,0]})
        with patch('material_jobs.navigation.time.monotonic',side_effect=clock.monotonic), \
                patch('material_jobs.navigation.time.sleep',side_effect=clock.sleep):
            with self.assertRaisesRegex(JobBlocked,'实际位置未到达'):
                settled_state(client,[1.,10.,1.],tolerance=.45,seconds=1)


class QuarryExitTest(unittest.TestCase):

    def setUp(self):
        # Geometry fixtures have instantaneous movement. The real settling
        # policy is independently verified above; _air_move still checks distance.
        wait=patch('material_jobs.navigation.settled_state',side_effect=lambda c,*args,**kwargs:c.status())
        wait.start();self.addCleanup(wait.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.directory=self.root/'acquisition';self.directory.mkdir()
        self.path=self.directory/'acquisition-cobbled_deepslate.json'
        self.ledger={'schema':1,'world_session':'w','item':'minecraft:cobbled_deepslate',
                     'resource_regions':[{'source':'natural_survey','min':[0,8,0],'max':[5,14,5],
                     'surface_y':20,'access_shaft':{'min':[0,15,0],'max':[1,20,1]}}],
                     'visited':{'access-a':{'state':'clear_verified','min':[0,15,0],'max':[1,20,1]}}}
        self.save();self.client=FakeClient(self.root)

    def save(self):self.path.write_text(json.dumps(self.ledger))

    def test_moves_through_observed_air_to_old_shaft_before_rising(self):
        self.assertTrue(leave_quarry(self.client,self.directory))
        moves=[args['target'] for op,args in self.client.calls if op=='navigate']
        self.assertTrue(all(p[1]==10 for p in moves[:-1]))
        self.assertEqual([1.5,10.,1.5],moves[-2]);self.assertEqual([1.5,23.,1.5],moves[-1])
        self.assertTrue(list(self.root.glob('quarry-exit-*.json')))

    def stone(self,x,y,z):
        return {'pos':[x,y,z],'state':'Block{minecraft:stone}','passable':False,
                'fluid':False,'block_entity':False}

    def partial_shaft(self, clear_column=(0,0)):
        self.client.pos=[.57,10.,.43]
        for x in (0,1):
            for z in (0,1):
                if (x,z)!=clear_column:
                    for y in range(12,21):self.client.blocks[(x,y,z)]=self.stone(x,y,z)

    def test_partial_2x2_shaft_exits_in_current_clear_body_column_without_recentering(self):
        self.partial_shaft();before=copy.deepcopy(self.client.blocks)
        self.assertTrue(leave_quarry(self.client,self.directory))
        moves=[params['target'] for op,params in self.client.calls if op=='navigate']
        self.assertEqual([[.57,23.,.43]],moves)
        scans=[params for op,params in self.client.calls if op=='scan']
        self.assertEqual(2,len(scans))
        for params in scans:
            self.assertEqual([0,10,0],params['min']);self.assertEqual([0,25,0],params['max'])
        self.assertEqual(before,self.client.blocks)
        self.assertEqual({'scan','navigate'},{op for op,_ in self.client.calls})

    def test_blocked_current_column_moves_through_observed_level_air_to_another_clear_column(self):
        self.partial_shaft(clear_column=(1,0));self.client.pos=[.5,10.,.5]
        before=copy.deepcopy(self.client.blocks)
        self.assertTrue(leave_quarry(self.client,self.directory))
        moves=[params['target'] for op,params in self.client.calls if op=='navigate']
        self.assertEqual([[1.5,10.,.5],[1.5,23.,.5]],moves)
        self.assertEqual(before,self.client.blocks)
        navigation_indices=[index for index,(op,_) in enumerate(self.client.calls) if op=='navigate']
        for index in navigation_indices:
            self.assertEqual('scan',self.client.calls[index-1][0])
        horizontal_scan=self.client.calls[navigation_indices[0]-1][1]
        self.assertEqual(([0,10,0],[1,11,0]),(horizontal_scan['min'],horizontal_scan['max']))
        vertical_scan=self.client.calls[navigation_indices[1]-1][1]
        self.assertEqual(([1,10,0],[1,25,0]),(vertical_scan['min'],vertical_scan['max']))

    def test_all_owned_columns_blocked_does_not_exit_through_unowned_open_sky(self):
        self.client.pos=[.5,10.,.5]
        # Everything outside the four authorized columns is now clear sky.
        # It cannot be substituted for an owned shaft exit.
        self.client.blocks={(x,16,z):self.stone(x,16,z) for x in (0,1) for z in (0,1)}
        with self.assertRaisesRegex(JobBlocked,'现在有方块或水'):
            leave_quarry(self.client,self.directory)
        self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))
        self.assertFalse(list(self.root.glob('quarry-exit-*.json')))

    def test_full_body_overlap_with_blocked_neighbor_must_recenter_before_rising(self):
        self.partial_shaft();self.client.pos=[.8,10.,.5]
        self.assertTrue(leave_quarry(self.client,self.directory))
        moves=[params['target'] for op,params in self.client.calls if op=='navigate']
        self.assertEqual([[.5,10.,.5],[.5,23.,.5]],moves)
        first_scan=self.client.calls[0][1]
        self.assertEqual(0,first_scan['min'][0]);self.assertEqual(1,first_scan['max'][0])
        self.assertTrue(all(point[0]==.5 for point in moves))

    def test_new_block_after_lateral_arrival_prevents_ascent_in_selected_column(self):
        self.partial_shaft(clear_column=(1,0));self.client.pos=[.5,10.,.5]
        original=self.client.request
        def changed(op,**params):
            reply=original(op,**params)
            if op=='navigate' and params['target'][1]==10:
                self.client.blocks[(1,18,0)]=self.stone(1,18,0)
            return reply
        self.client.request=changed
        with self.assertRaisesRegex(JobBlocked,'上升空间发生变化'):
            leave_quarry(self.client,self.directory)
        moves=[params['target'] for op,params in self.client.calls if op=='navigate']
        self.assertEqual([[1.5,10.,.5]],moves)
        self.assertFalse(list(self.root.glob('quarry-exit-*.json')))

    def test_direct_column_requires_complete_current_world_scan(self):
        original=self.client.request
        for changes in ({'phase':'error'},{'world_session':'old-world'},{'blocks':None}):
            with self.subTest(changes=changes):
                self.client.pos=[.5,10.,.5];self.client.calls=[]
                def uncertain(op,**params):
                    reply=original(op,**params)
                    if op=='scan':reply.update(changes)
                    return reply
                self.client.request=uncertain
                with self.assertRaisesRegex(JobBlocked,'尚未完整确认'):
                    leave_quarry(self.client,self.directory)
                self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_real_read_only_scan_reply_does_not_need_action_phase(self):
        self.client.scan_phase=None
        self.assertTrue(leave_quarry(self.client,self.directory))

    def test_a_wall_is_walked_around_without_digging_or_going_up_early(self):
        for z in range(1,6):
            for y in (10,11):self.client.blocks[(3,y,z)]={'pos':[3,y,z],'passable':False}
        self.assertTrue(leave_quarry(self.client,self.directory))
        moves=[args['target'] for op,args in self.client.calls if op=='navigate']
        self.assertTrue(any(p[2]==.5 for p in moves[:-2]))
        self.assertEqual({'scan','navigate'},{op for op,_ in self.client.calls})

    def test_all_shaft_columns_with_new_solid_or_water_refuse_before_any_movement(self):
        for row in ({'passable':False},{'passable':True,'fluid':True}):
            for x in (0,1):
                for z in (0,1):self.client.blocks[(x,16,z)]={**row,'pos':[x,16,z]}
            self.client.calls=[]
            with self.assertRaisesRegex(JobBlocked,'现在有方块或水'):leave_quarry(self.client,self.directory)
            self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_retained_torch_and_collision_free_surface_grass_allow_exit(self):
        for pos,name in (([0,16,0],'wall_torch'),([1,22,1],'tall_grass')):
            self.client.blocks[tuple(pos)]={'pos':pos,'state':'Block{minecraft:'+name+'}',
                'passable':True,'fluid':False,'block_entity':False}
        self.assertTrue(leave_quarry(self.client,self.directory))
        self.assertEqual({'scan','navigate'},{op for op,_ in self.client.calls})

    def test_noncolliding_hazards_and_unconfirmed_grass_remain_blocking(self):
        for name,extras in (('fire',{}),('wither_rose',{}),('water',{'fluid':True}),
                            ('tall_grass',{'passable':False}),('tall_grass',{'block_entity':True})):
            with self.subTest(name=name,extras=extras):
                self.client.calls=[]
                for x in (0,1):
                    for z in (0,1):
                        self.client.blocks[(x,16,z)]={'pos':[x,16,z],'state':'Block{minecraft:'+name+'}',
                            'passable':True,'fluid':False,'block_entity':False,**extras}
                with self.assertRaisesRegex(JobBlocked,'现在有方块或水'):leave_quarry(self.client,self.directory)
                self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_wrong_world_or_no_clearance_evidence_never_uses_old_route(self):
        self.ledger['world_session']='old';self.save()
        self.assertFalse(leave_quarry(self.client,self.directory));self.assertFalse(self.client.calls)
        self.ledger['world_session']='w';self.ledger['visited']['access-a']['state']='inflight';self.save()
        self.assertFalse(leave_quarry(self.client,self.directory));self.assertFalse(self.client.calls)

    def test_current_position_outside_recorded_quarry_is_untouched(self):
        self.client.pos=[100.5,10,100.5]
        self.assertFalse(leave_quarry(self.client,self.directory));self.assertFalse(self.client.calls)

    def test_incomplete_scan_cannot_be_interpreted_as_air(self):
        self.client.scan_phase='error'
        with self.assertRaisesRegex(JobBlocked,'尚未完整确认'):leave_quarry(self.client,self.directory)
        self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_old_host_cannot_silently_ignore_air_only_requirement(self):
        self.client.protocol=0
        with self.assertRaisesRegex(JobBlocked,'尚不支持'):leave_quarry(self.client,self.directory)
        self.assertFalse(self.client.calls)

    def test_unconfirmed_actual_position_stops_before_vertical_ascent(self):
        self.client.bad_arrival=True
        with self.assertRaisesRegex(JobBlocked,'实际位置未到达'):leave_quarry(self.client,self.directory)
        self.assertTrue(all(args['target'][1]==10 for op,args in self.client.calls if op=='navigate'))

    def test_closed_air_route_preserves_blocks(self):
        for x,z in ((3,2),(5,2),(4,1),(4,3)):
            for y in (10,11):self.client.blocks[(x,y,z)]={'pos':[x,y,z],'passable':False}
        with self.assertRaisesRegex(JobBlocked,'没有连到原入口'):leave_quarry(self.client,self.directory)
        self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_feet_and_head_are_both_required_to_be_clear(self):
        shaft={'min':[0,15,0],'max':[1,20,1]}
        row={'pos':[4,11,2],'passable':False}
        with self.assertRaises(JobBlocked):shaft_path([row],self.client.pos,shaft,[-2,10,-2],[7,11,7])

    def test_exit_already_above_surface_has_no_more_navigation(self):
        self.client.pos=[1,23,1]
        self.assertFalse(leave_quarry(self.client,self.directory));self.assertFalse(self.client.calls)


class ProjectionExitTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.client=FakeClient(self.root)
        self.client.blocks={};self.client.pos=[.5,64.,.5]
        self.selection={'key':'courtyard-with-protected-holes','min':[-1,60,-1],'max':[1,70,1]}
        original=self.client.status
        self.client.status=lambda:{**original(),'projection_selection':self.selection,
                                   'flight':True,'on_ground':False,'velocity':[0,0,0]}
        waiter=patch('material_jobs.navigation.settled_state',side_effect=lambda c,*args,**kwargs:c.status())
        waiter.start();self.addCleanup(waiter.stop)

    def chest(self,x,y,z,**extra):
        return {'pos':[x,y,z],'state':'Block{minecraft:chest}[facing=south,type=single,waterlogged=false]',
                'solid':False,'passable':False,'fluid':False,'block_entity':True,**extra}

    def test_full_courtyard_protected_warehouse_chest_top_exits_vertically_with_airborne_flight(self):
        self.selection.update(min=[760982,61,797819],max=[761023,70,797865])
        self.client.pos=[761021.4973341001,64.875,797852.4999999573]
        for x in (761020,761021,761022):self.client.blocks[(x,64,797852)]=self.chest(x,64,797852)
        before=copy.deepcopy(self.client.blocks);start=list(self.client.pos)
        with patch('material_jobs.navigation.horizontal_exit') as horizontal:
            leave_projection(self.client)
        horizontal.assert_not_called()
        moves=[params for op,params in self.client.calls if op=='navigate']
        self.assertEqual(1,len(moves));self.assertTrue(moves[0]['air_only'])
        self.assertEqual([start[0],73.,start[2]],moves[0]['target'])
        self.assertEqual(before,self.client.blocks)
        self.assertEqual({'scan','navigate'},{op for op,_ in self.client.calls})
        receipt=json.loads(next(self.root.glob('exit-*.json')).read_text())
        self.assertEqual('verified_open_sky_column',receipt['mode']);self.assertTrue(receipt['confirmed'])

    def test_open_air_cell_inside_projection_bounds_can_rise_without_fake_interior_path(self):
        self.client.scan_phase=None
        self.client.blocks[(0,63,0)]={'pos':[0,63,0],'state':'Block{minecraft:grass_block}[snowy=false]',
            'solid':True,'passable':False,'fluid':False,'block_entity':False}
        with patch('material_jobs.navigation.horizontal_exit') as horizontal:
            leave_projection(self.client)
        horizontal.assert_not_called()
        self.assertEqual([.5,73.,.5],self.client.pos)
        self.assertEqual(319,self.client.calls[0][1]['max'][1])

    def test_open_sky_scan_starts_from_settled_position(self):
        waits=[]
        def settle(client,*args,**kwargs):
            waits.append(list(client.pos))
            if len(waits)==1:client.pos=[1.5,64.,.5]
            return client.status()
        with patch('material_jobs.navigation.settled_state',side_effect=settle):
            leave_projection(self.client)
        scans=[params for op,params in self.client.calls if op=='scan']
        self.assertEqual([1,64,0],scans[0]['min'])
        self.assertEqual([1.5,73.,.5],self.client.pos)

    def test_open_sky_drift_rescans_new_body_column_before_rising(self):
        self.selection['max'][0]=5
        original=self.client.request;columns=[]
        def request(op,**params):
            reply=original(op,**params)
            if op=='scan' and params['max'][1]==319:
                columns.append(params['min'])
                if len(columns)==1:self.client.pos=[1.5,64.,.5]
            return reply
        self.client.request=request
        leave_projection(self.client)
        self.assertEqual([[0,64,0],[1,64,0]],columns)
        moves=[params['target'] for op,params in self.client.calls if op=='navigate']
        self.assertEqual([[1.5,73.,.5]],moves)

    def test_open_sky_repeated_drift_stops_without_ascent(self):
        self.selection['max'][0]=5
        original=self.client.request;columns=[]
        def request(op,**params):
            reply=original(op,**params)
            if op=='scan' and params['max'][1]==319:
                columns.append(params['min'])
                self.client.pos=[len(columns)+.5,64.,.5]
            return reply
        self.client.request=request
        with self.assertRaisesRegex(JobBlocked,'露天退出核验期间位置或投影改变'):
            leave_projection(self.client)
        self.assertEqual([[0,64,0],[1,64,0]],columns)
        self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_open_sky_projection_change_during_scan_stops_without_retry(self):
        original=self.client.request
        def request(op,**params):
            reply=original(op,**params)
            if op=='scan':self.selection['key']='another-projection'
            return reply
        self.client.request=request
        with self.assertRaisesRegex(JobBlocked,'露天退出核验期间位置或投影改变'):
            leave_projection(self.client)
        self.assertEqual(1,sum(op=='scan' for op,_ in self.client.calls))
        self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_open_sky_control_change_during_scan_stops_without_retry(self):
        original_status=self.client.status;revision=[7]
        self.client.status=lambda:{**original_status(),'control_revision':revision[0]}
        original_request=self.client.request
        def request(op,**params):
            reply=original_request(op,**params)
            if op=='scan':revision[0]=8
            return reply
        self.client.request=request
        with self.assertRaisesRegex(JobBlocked,'露天退出核验期间位置或投影改变'):
            leave_projection(self.client)
        self.assertEqual(1,sum(op=='scan' for op,_ in self.client.calls))
        self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_real_roof_even_above_projection_height_uses_horizontal_exit_and_sealed_room_stays_blocked(self):
        from hull_escape import horizontal_exit
        for roof_y,sealed in ((68,False),(80,False),(68,True)):
            with self.subTest(roof_y=roof_y,sealed=sealed):
                self.client.pos=[.5,64.,.5];self.client.calls=[]
                self.client.blocks={(0,roof_y,0):{'pos':[0,roof_y,0],'passable':False,'state':'Block{minecraft:stone}'}}
                if sealed:
                    for x,z in ((-1,0),(1,0),(0,-1),(0,1)):
                        for y in (64,65):self.client.blocks[(x,y,z)]={'pos':[x,y,z],'passable':False,'state':'Block{minecraft:stone}'}
                with patch('material_jobs.navigation.horizontal_exit',wraps=horizontal_exit) as horizontal:
                    if sealed:
                        with self.assertRaisesRegex(RuntimeError,'No observed horizontal exit'):leave_projection(self.client)
                    else:leave_projection(self.client)
                horizontal.assert_called_once()
                moves=[params['target'] for op,params in self.client.calls if op=='navigate']
                self.assertEqual([],moves) if sealed else self.assertTrue(moves)
                self.assertTrue(all(point[1]==64 for point in moves))

    def test_open_sky_scan_must_be_complete_and_from_current_world(self):
        original=self.client.request
        for change in ({'phase':'error'},{'world_session':'old'},{'blocks':None}):
            with self.subTest(change=change):
                self.client.calls=[]
                def request(op,**params):
                    reply=original(op,**params)
                    if op=='scan':reply.update(change)
                    return reply
                self.client.request=request
                with self.assertRaisesRegex(JobBlocked,'尚未完整确认'):leave_projection(self.client)
                self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))

    def test_roof_over_neighbor_intersecting_body_footprint_cannot_be_ignored(self):
        from hull_escape import horizontal_exit
        self.client.pos=[.85,64.,.5]
        self.client.blocks[(1,66,0)]={'pos':[1,66,0],'passable':False,'state':'Block{minecraft:stone}'}
        with patch('material_jobs.navigation.horizontal_exit',wraps=horizontal_exit) as horizontal:
            leave_projection(self.client)
        horizontal.assert_called_once()
        self.assertEqual(1,self.client.calls[0][1]['max'][0])
        self.assertTrue(all(params['target'][1]==64 for op,params in self.client.calls if op=='navigate'))

    def test_chest_exception_does_not_accept_wet_unknown_or_above_feet_container(self):
        for feet,row in ((64.8,self.chest(0,64,0)),(64.875,self.chest(0,64,0,fluid=True)),
                         (64.875,self.chest(0,64,0,solid=True)),(64.875,self.chest(0,65,0))):
            with self.subTest(feet=feet,row=row):
                self.client.pos=[.5,feet,.5];self.client.calls=[]
                self.client.blocks={tuple(row['pos']):row}
                with self.assertRaises(RuntimeError):leave_projection(self.client)
                self.assertFalse(any(op=='navigate' for op,_ in self.client.calls))


if __name__=='__main__':unittest.main()
