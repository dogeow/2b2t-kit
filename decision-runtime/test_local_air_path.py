from pathlib import Path
from types import SimpleNamespace
import json
import math
import tempfile
import unittest
from unittest.mock import Mock,patch

from material_jobs.local_air_path import plan,move,move_replanning_once
from material_jobs.protocol import JobBlocked


class LocalAirPathTests(unittest.TestCase):
    def test_low_air_route_rises_before_crossing_magma_column(self):
        rows=[{'pos':[1,61,0],'state':'Block{minecraft:magma_block}','solid':True,'fluid':False}]
        route=plan(rows,[.5,63.1,.5],[2.5,63.1,.5],[0,60,0],[2,69,0],foot_offset=.1)
        self.assertTrue(any(p[1]>=65 for p in route))
        for a,b in zip(route,route[1:]):
            if min(a[0],b[0])<=1.5<=max(a[0],b[0]):self.assertGreaterEqual(min(a[1],b[1]),65)
    def test_current_recorded_magma_column_is_not_an_air_destination(self):
        rows=[{'pos':[1,61,0],'state':'Block{minecraft:magma_block}','solid':True,'fluid':False}]
        with self.assertRaises(JobBlocked):plan(rows,[.5,63.1,.5],[1.5,63.1,.5],[0,60,0],[2,69,0],foot_offset=.1)
    def test_completed_full_floor_shields_air_route_from_deeper_magma(self):
        rows=[{'pos':[1,61,0],'state':'Block{minecraft:magma_block}','solid':True,'fluid':False},
              {'pos':[1,62,0],'state':'Block{minecraft:cobblestone}','solid':True,'fluid':False}]
        route=plan(rows,[.5,63.1,.5],[2.5,63.1,.5],[0,60,0],[2,69,0],foot_offset=.1)
        self.assertTrue(all(p[1]==63.1 for p in route))
    def test_high_hover_recenters_before_entering_two_block_ceiling(self):
        position=[.5,.25,.5];ceiling=[{'pos':[x,2,0],'state':'Block{minecraft:stone}'}for x in(1,2)]
        c=SimpleNamespace(world='w',last='nav',status=lambda:{'pos':list(position)})
        def scan(c,lo,hi):return[r for r in ceiling if all(lo[i]<=r['pos'][i]<=hi[i]for i in range(3))]
        def nav(c,point,seconds,*,arrival):position[:]=[point[0],point[1]+.05,point[2]]
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',side_effect=scan),\
             patch('material_jobs.local_air_path._air_move',side_effect=nav)as movement:
            proof=move(c,[2.5,.1,.5],d,foot_offset=.1)
        self.assertTrue(proof['complete']);self.assertEqual([.5,.1,.5],movement.call_args_list[0].args[1])
        self.assertEqual(.08,movement.call_args_list[0].kwargs['arrival'])
        self.assertEqual(2,movement.call_count)

    def test_dry_cone_edge_keeps_native_air_only_collision_admission(self):
        cone={'pos':[0,0,0],'state':'Block{minecraft:pointed_dripstone}[thickness=base,vertical_direction=up,waterlogged=false]',
              'fluid':False,'block_entity':False}
        for rejected in (False,True):
            with self.subTest(rejected=rejected),tempfile.TemporaryDirectory()as d:
                position=[1.5,.2,.5];calls=[]
                def request(op,**kwargs):
                    calls.append((op,kwargs));self.assertEqual('navigate',op);self.assertIs(True,kwargs['air_only'])
                    if rejected:return {'phase':'error','detail':'native real shape collision'}
                    position[:]=kwargs['target'];return {'phase':'done'}
                c=SimpleNamespace(world='w',last='native',status=lambda:{'pos':list(position)},request=request)
                def scan(c,lo,hi):return [cone]if all(lo[i]<=cone['pos'][i]<=hi[i]for i in range(3))else[]
                with patch('material_jobs.local_air_path._air_scan',side_effect=scan),\
                     patch('material_jobs.navigation.settled_state',side_effect=lambda *a,**k:c.status()):
                    if rejected:
                        with self.assertRaisesRegex(JobBlocked,'native real shape collision'):
                            move(c,[1.2,.2,.5],d,foot_offset=.2,exact_target=True,allow_dry_cone_edge=True)
                        self.assertEqual([1.5,.2,.5],position)
                    else:
                        proof=move(c,[1.2,.2,.5],d,foot_offset=.2,exact_target=True,allow_dry_cone_edge=True)
                        self.assertTrue(proof['complete']);self.assertEqual([1.2,.2,.5],position)
                self.assertEqual(1,len(calls))
    def test_cone_edge_never_admits_water_containers_cactus_or_other_terrain(self):
        dry={'pos':[0,0,0],'state':'Block{minecraft:pointed_dripstone}[thickness=base,vertical_direction=up,waterlogged=false]',
             'fluid':False,'block_entity':False}
        for change in ({'fluid':True},{'block_entity':True},{'state':'Block{minecraft:cactus}[age=0]'},
                       {'state':'Block{minecraft:stone}'},{'state':dry['state'].replace('waterlogged=false','waterlogged=true')}):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as d:
                c=SimpleNamespace(world='w',last='scan',status=lambda:{'pos':[1.5,.2,.5]})
                with patch('material_jobs.local_air_path._air_scan',return_value=[{**dry,**change}]),\
                     patch('material_jobs.local_air_path._air_move')as nav,self.assertRaises(JobBlocked):
                    move(c,[1.2,.2,.5],d,foot_offset=.2,exact_target=True,allow_dry_cone_edge=True)
                nav.assert_not_called()
    def test_new_growth_before_a_leg_gets_one_new_route_from_actual_rest(self):
        position=[.5,.2,.5];grown=False;wall={'pos':[3,0,0],'state':'Block{minecraft:stone}'}
        c=SimpleNamespace(world='w',last='scan',status=lambda:{'pos':list(position),'world_session':'w'})
        def scan(c,low,high):
            nonlocal grown
            if low==[2,0,0] and high==[4,1,0]:grown=True
            return [wall]if grown and all(low[i]<=wall['pos'][i]<=high[i]for i in range(3))else[]
        def nav(c,point,*args,**kwargs):position[:]=point
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',side_effect=scan),\
             patch('material_jobs.local_air_path._air_move',side_effect=nav):
            result=move_replanning_once(c,[4.5,.2,.5],d,max_straight=2,foot_offset=.2)
            first=json.loads((Path(d)/'attempt-0/local-air-path.json').read_text())
            second=json.loads((Path(d)/'attempt-1/local-air-path.json').read_text())
        self.assertTrue(result['complete']);self.assertIsNone(first['pending']);self.assertFalse(first['complete'])
        self.assertEqual([2.5,.2,.5],second['start']);self.assertEqual(1,len(first['moves']))
        self.assertTrue(any(p[1]>=1 for p in second['path']))
    def test_unknown_movement_never_triggers_the_observed_growth_replanner(self):
        c=SimpleNamespace(world='w',last='unknown',status=lambda:{'pos':[.5,.2,.5],'world_session':'w'})
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',return_value=[]),\
             patch('material_jobs.local_air_path._air_move',side_effect=RuntimeError('unknown'))as movement:
            with self.assertRaisesRegex(RuntimeError,'unknown'):
                move_replanning_once(c,[4.5,.2,.5],d,max_straight=2,foot_offset=.2)
            self.assertFalse((Path(d)/'attempt-1').exists())
            self.assertIsNotNone(json.loads((Path(d)/'attempt-0/local-air-path.json').read_text())['pending'])
        self.assertEqual(1,movement.call_count)
    def test_explicit_known_volume_can_exit_around_a_wall_beyond_default_padding(self):
        position=[.5,.2,.5];wall=[{'pos':[x,2,z]}for x in range(-3,5)for z in range(-3,4)]
        c=SimpleNamespace(world='w',status=lambda:{'pos':list(position)},last='nav')
        def scan(c,low,high):return[r for r in wall if all(low[i]<=r['pos'][i]<=high[i]for i in range(3))]
        def nav(c,p,*args,**kwargs):position[:]=p
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',side_effect=scan),\
             patch('material_jobs.local_air_path._air_move',side_effect=nav):
            with self.assertRaises(JobBlocked):move(c,[.5,5.2,.5],Path(d)/'narrow',foot_offset=.2)
            proof=move(c,[.5,5.2,.5],Path(d)/'full',foot_offset=.2,scan_bounds={'min':[-3,0,-3],'max':[6,8,3]})
        self.assertTrue(proof['complete']);self.assertFalse(proof['mining_sent'])
        self.assertTrue(any(p[0]>=5.5 for p in proof['path']))
    def test_explicit_volume_cannot_weaken_body_coverage_or_scan_size_limits(self):
        c=SimpleNamespace(world='w',status=lambda:{'pos':[.5,.2,.5]},last=None)
        for bounds in ({'min':[1,0,0],'max':[4,6,4]}, {'min':[-30,0,-30],'max':[30,60,30]}):
            with self.subTest(bounds=bounds),tempfile.TemporaryDirectory()as d,\
                 patch('material_jobs.local_air_path._air_scan')as scan,self.assertRaises(JobBlocked):
                move(c,[.5,5.2,.5],d,foot_offset=.2,scan_bounds=bounds)
            scan.assert_not_called()
    def test_fractional_endpoint_is_not_silently_rounded_back_to_cell_center(self):
        position=[.5,.2,1.5];target=[.32,.2,1.32]
        c=SimpleNamespace(world='w',status=lambda:{'pos':list(position)},last='nav')
        def nav(c,point,seconds,*,arrival):position[:]=[point[0],point[1]-.14,point[2]]
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',return_value=[]),\
             patch('material_jobs.local_air_path._air_move',side_effect=nav)as movement:
            proof=move(c,target,d,foot_offset=.2,exact_target=True)
        self.assertEqual(target,movement.call_args.args[1]);self.assertEqual(.08,movement.call_args.kwargs['arrival'])
        self.assertEqual(target,proof['path'][-1]);self.assertTrue(proof['exact_target']);self.assertTrue(proof['complete'])
    def test_fence_collision_extends_into_the_air_voxel_above_it(self):
        fence={'pos':[1,0,0],'state':'Block{minecraft:oak_fence}[east=true,north=false,south=false,waterlogged=false,west=true]'}
        with self.assertRaises(JobBlocked):
            plan([fence],[.5,1.2,.5],[2.5,1.2,.5],[0,0,0],[2,2,0],foot_offset=.2)
        path=plan([fence],[.5,1.2,.5],[2.5,1.2,.5],[0,0,0],[2,5,0],foot_offset=.2)
        self.assertTrue(any(p[1]>=2 for p in path))
    def test_mud_surface_starts_above_its_verified_fourteen_pixel_collision_top(self):
        mud={'pos':[0,71,0],'state':'Block{minecraft:mud}','solid':False,'fluid':False,'block_entity':False}
        position=[.5,71.875,.5]
        c=SimpleNamespace(world='w',status=lambda:{'pos':list(position)},last='nav')
        def scan(c,low,high):return [mud]if all(low[i]<=mud['pos'][i]<=high[i]for i in range(3))else[]
        def nav(c,point,seconds,*,arrival):position[:]=[point[0],point[1]-.14,point[2]]
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',side_effect=scan),\
             patch('material_jobs.local_air_path._air_move',side_effect=nav)as movement:
            proof=move(c,[1.5,72.2,.5],d,foot_offset=.2)
        self.assertTrue(proof['complete']);self.assertEqual([.5,72.2,.5],movement.call_args_list[0].args[1])
    def test_mud_below_shape_top_or_full_clay_is_never_an_air_start(self):
        for state,solid in [('Block{minecraft:mud}',False),('Block{minecraft:clay}',True)]:
            row={'pos':[0,71,0],'state':state,'solid':solid,'fluid':False,'block_entity':False}
            with self.subTest(state=state),self.assertRaises(JobBlocked):
                plan([row],[.5,71.8,.5],[1.5,72.2,.5],[-1,70,-1],[2,75,1],foot_offset=.2)
    def test_registered_water_route_can_extend_only_with_an_explicit_bounded_limit(self):
        position=[.5,62.2,.5]
        c=SimpleNamespace(world='w',status=lambda:{'pos':list(position)},last='nav')
        def nav(c,point,seconds,*,arrival):position[:]=point
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',return_value=[]),\
             patch('material_jobs.local_air_path._air_move',side_effect=nav):
            with self.assertRaises(JobBlocked):move(c,[14.5,72.2,.5],Path(d)/'default')
            proof=move(c,[14.5,72.2,.5],Path(d)/'registered',foot_offset=.2,max_horizontal=24)
            self.assertTrue(proof['complete']);self.assertFalse(proof['mining_sent'])
            with self.assertRaises(JobBlocked):move(c,[14.5,72.2,.5],Path(d)/'bad-limit',max_horizontal=25)
    def test_off_center_pickup_pose_is_centered_before_rising_past_neighbor_wall(self):
        position=[1.265,68.2,.5];wall=[{'pos':[0,70,0]}]
        def scan(c,low,high):return[r for r in wall if all(low[i]<=r['pos'][i]<=high[i]for i in range(3))]
        def nav(c,point,seconds,*,arrival):position[:]=[point[0],point[1]-.14,point[2]]
        c=SimpleNamespace(world='w',status=lambda:{'pos':list(position)},last='known-nav')
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',side_effect=scan),\
             patch('material_jobs.local_air_path._air_move',side_effect=nav)as movement:
            proof=move(c,[1.5,72.2,.5],d,foot_offset=.2)
        self.assertTrue(proof['complete']);self.assertEqual([1.5,68.2,.5],movement.call_args_list[0].args[1])
        self.assertGreaterEqual(movement.call_count,2)
    def test_settled_supported_start_does_not_add_a_second_centering_move(self):
        position=[.5,62.045,.5]
        c=SimpleNamespace(world='w',status=lambda:{'pos':list(position)},last='known-nav')
        def navigate(c,point,seconds,*,arrival):position[:]=[point[0],point[1]-.155,point[2]]
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',return_value=[]),\
             patch('material_jobs.local_air_path._air_move',side_effect=navigate)as native:
            proof=move(c,[1.5,62.2,.5],d,foot_offset=.2)
        self.assertTrue(proof['complete']);self.assertEqual(1,native.call_count)
        self.assertEqual([1.5,62.2,.5],native.call_args.args[1])

    def test_route_creates_its_nested_journal_directory_before_dispatch(self):
        c=SimpleNamespace(world='w',status=lambda:{'pos':[.5,0,.5]},last=None)
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',return_value=[]),\
             patch('material_jobs.local_air_path._air_move')as navigate:
            nested=Path(d)/'new'/'route'
            proof=move(c,[.5,0,.5],nested)
            self.assertTrue(proof['complete'])
            self.assertTrue((nested/'local-air-path.json').is_file())
            navigate.assert_not_called()
    def test_existing_vertical_detour_avoids_low_roof_without_excavating(self):
        rows=[{'pos':[1,1,0]},{'pos':[1,2,0]}]
        path=plan(rows,[.5,0,.5],[2.5,0,.5],[0,0,0],[2,5,0])
        self.assertEqual([2.5,0,.5],path[-1]);self.assertTrue(any(p[1]>=3 for p in path))
        for p in path:
            self.assertFalse(p[0]==1.5 and p[1]in (0,1,2))

    def test_flying_exit_from_hanging_growth_platform_needs_no_ground_floor(self):
        roof=[{'pos':[x,4,z]}for x in range(-1,2)for z in range(-1,2)]
        roof.append({'pos':[0,3,0]})
        path=plan(roof,[.5,1.2,.5],[3.5,8.2,.5],[-2,0,-2],[5,12,2],max_straight=8,foot_offset=.2)
        self.assertEqual([3.5,8.2,.5],path[-1])
        self.assertTrue(any(p[0]>=2.5 or abs(p[2]-.5)>=2 for p in path if p[1]>=4))

    def test_one_block_head_gap_is_not_an_air_corridor(self):
        with self.assertRaises(JobBlocked):plan([{'pos':[1,1,0]}],[.5,0,.5],[2.5,0,.5],[0,0,0],[2,1,0])

    def test_straight_stretches_remain_bounded_native_moves(self):
        path=plan([],[.5,0,.5],[.5,60,.5],[0,0,0],[0,63,0])
        self.assertEqual([.5,60,.5],path[-1])
        self.assertTrue(all(math.dist(a,b)<=16 for a,b in zip(path,path[1:])))

    def test_unknown_native_move_is_saved_and_not_replayed(self):
        c=SimpleNamespace(world='w',status=lambda:{'pos':[.5,0,.5]},last='unknown-nav')
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',return_value=[]),\
             patch('material_jobs.local_air_path._air_move',side_effect=RuntimeError('unknown'))as navigate:
            with self.assertRaises(RuntimeError):move(c,[2.5,0,.5],Path(d))
            raw=(Path(d)/'local-air-path.json').read_bytes();book=json.loads(raw)
            self.assertIsNotNone(book['pending']);self.assertFalse(book['complete']);self.assertFalse(book['mining_sent'])
            with self.assertRaises(JobBlocked):move(c,[2.5,0,.5],Path(d))
            self.assertEqual(raw,(Path(d)/'local-air-path.json').read_bytes());self.assertEqual(1,navigate.call_count)

    def test_supported_margin_keeps_next_sweep_above_floor_after_flight_settles(self):
        floor=[{'pos':[x,61,0]}for x in range(4)]
        position=[.5,62.06,.5]
        def scan(low,high):
            return [r for r in floor if all(low[i]<=r['pos'][i]<=high[i]for i in range(3))]
        def navigate(c,point,seconds,*,arrival=.25):
            self.assertEqual(.2,arrival)
            position[:]=[point[0],point[1]-.14,point[2]]
        c=SimpleNamespace(world='w',status=lambda:{'pos':list(position)},last='known-nav')
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',side_effect=lambda c,lo,hi:scan(lo,hi)),\
             patch('material_jobs.local_air_path._air_move',side_effect=navigate):
            proof=move(c,[3.5,62.2,.5],Path(d),max_straight=2,foot_offset=.2)
        self.assertTrue(proof['complete'])
        self.assertGreater(position[1],62)
        self.assertLessEqual(max(p[1]+1.8 for p in proof['path']),64)

    def test_margin_cannot_extend_body_beyond_two_verified_air_cells(self):
        for margin in (-.01,.201,float('nan'),True):
            with self.assertRaises(JobBlocked):
                plan([], [.5,62,.5],[2.5,62,.5],[0,62,0],[3,64,0],foot_offset=margin)


class SurfaceLiftRouteTests(unittest.TestCase):
    def run_case(self, *, unknown=False, enabled=True, target_y=64.15, liquid='water'):
        position=[1.5,62.9875,3.5]
        row={'pos':[1,62,3],'state':'Block{minecraft:'+liquid+'}[level=1]',
             'fluid':True,'solid':False,'block_entity':False}
        # Match the real flowing surface above its falling-water cell.
        rows=[row,{**row,'pos':[1,61,3]}]
        client=SimpleNamespace(world='w',last='scan',status=lambda:{'pos':list(position)},
                               unconfirmed_native_request='original'if unknown else None)
        scans=[];moves=[]
        def scan(c,low,high):
            scans.append((list(position),low,high))
            return [r for r in rows if all(low[i]<=r['pos'][i]<=high[i]for i in range(3))]
        def navigate(c,target,*args,**kwargs):
            self.assertGreaterEqual(position[1],63.5,'Air-only routing must follow the verified water exit')
            moves.append(target);position[:]=target
        def lift(c,state):position[:]=[1.5,64.1,3.5]
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.local_air_path._air_scan',side_effect=scan),\
             patch('material_jobs.local_air_path._air_move',side_effect=navigate),\
             patch('material_jobs.construction_breathing.lift_surface_feet',side_effect=lift)as recover:
            if unknown or not enabled or target_y<63.5 or liquid!='water':
                with self.assertRaises(JobBlocked):
                    move(client,[1.5,target_y,3.5],d,exact_target=True,foot_offset=.15,allow_surface_lift=enabled)
                recover.assert_not_called();self.assertEqual([],moves)
                return
            result=move(client,[1.5,target_y,3.5],d,exact_target=True,foot_offset=.15)
            recover.assert_called_once()
            self.assertTrue(result['complete']);self.assertTrue(result['replaced_after_verified_surface_lift'])
            self.assertTrue(any(p[0][1]>=63.5 for p in scans))
            self.assertTrue(json.loads(Path(result['replacement_route']).read_text())['complete'])
            self.assertEqual([1.5,target_y,3.5],position)

    def test_pre_send_foot_water_uses_one_verified_lift_then_rescans(self):self.run_case()
    def test_unknown_request_is_not_recovered_or_replayed(self):self.run_case(unknown=True)
    def test_water_recovery_can_be_disabled_without_weakening_air_checks(self):self.run_case(enabled=False)
    def test_original_target_without_dry_margin_is_not_silently_changed(self):self.run_case(target_y=63.15)
    def test_lava_is_never_admitted_as_water(self):self.run_case(liquid='lava')


if __name__=='__main__':unittest.main()
