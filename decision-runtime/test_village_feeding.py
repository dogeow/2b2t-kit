import unittest
import json,tempfile
from pathlib import Path
from unittest.mock import Mock
from village_feeding import bed_level_pose,settled_pose

class VillageFeedingTests(unittest.TestCase):
    def iron_door_shell(self):
        blocks=[{'pos':[x,y,z],'state':'Block{minecraft:dark_oak_planks}','solid':True,'fluid':False,'block_entity':False}
                for x in range(5)for y in range(63,68)for z in range(5)if x in(0,4)or z in(0,4)or y in(63,67)]
        for y,half in [(64,'lower'),(65,'upper')]:
            next(v for v in blocks if v['pos']==[0,y,2]).update(solid=False,state='Block{minecraft:iron_door}[facing=east,half='+half+',hinge=left,open=false,powered=false]')
        return {'scan_cells_read':125,'scan_total_cells':125,'blocks':blocks,'time':100}

    def test_complete_closed_iron_door_pair_with_full_frame_seals_the_room(self):
        from village_feeding import feeding_containment
        proof=feeding_containment(self.iron_door_shell(),[0,64,0],[4,67,4],[{'pos':[2.5,64,2.5]}])
        self.assertEqual(1,proof['closed_framed_iron_doors']);self.assertEqual('sealed_collision_shell',proof['kind'])

    def test_open_powered_unpaired_wooden_or_unframed_doors_do_not_seal(self):
        from village_feeding import feeding_containment
        for change in ('open','powered','unpaired','wood','hinge','facing','frame','roof'):
            scan=self.iron_door_shell();blocks=scan['blocks'];lower=next(v for v in blocks if v['pos']==[0,64,2]);upper=next(v for v in blocks if v['pos']==[0,65,2])
            if change=='open':lower['state']=lower['state'].replace('open=false','open=true')
            if change=='powered':lower['state']=lower['state'].replace('powered=false','powered=true')
            if change=='unpaired':blocks.remove(upper)
            if change=='wood':
                for v in(lower,upper):v['state']=v['state'].replace('iron_door','oak_door')
            if change=='hinge':upper['state']=upper['state'].replace('hinge=left','hinge=right')
            if change=='facing':
                for v in(lower,upper):v['state']=v['state'].replace('facing=east','facing=north')
            if change=='frame':blocks.remove(next(v for v in blocks if v['pos']==[0,64,1]))
            if change=='roof':blocks.remove(next(v for v in blocks if v['pos']==[0,66,2]))
            with self.subTest(change=change),self.assertRaisesRegex(RuntimeError,'outside'):
                feeding_containment(scan,[0,64,0],[4,67,4],[{'pos':[2.5,64,2.5]}])

    def test_solid_enclosure_accepts_zero_gates_and_rejects_real_escape_routes(self):
        from village_feeding import feeding_containment
        from copy import deepcopy
        low=[0,64,0];high=[4,67,4]
        blocks=[{'pos':[x,y,z],'state':'Block{minecraft:dark_oak_planks}',
                 'solid':True,'fluid':False}for x in range(5)for y in range(63,68)for z in range(5)
                if x in(0,4)or z in(0,4)or y in(63,67)]
        scan={'scan_cells_read':125,'scan_total_cells':125,'blocks':blocks,'time':100}
        people=[{'pos':[1.5,64,1.5]},{'pos':[2.5,64,2.5]}]
        proof=feeding_containment(scan,low,high,people)
        self.assertEqual('sealed_full_block_shell',proof['kind'])
        self.assertEqual(27,proof['reachable_cells'])
        for hole in ([0,64,2],[2,67,2],[2,63,2]):
            bad=deepcopy(scan);bad['blocks']=[r for r in blocks if r['pos']!=hole]
            with self.assertRaisesRegex(RuntimeError,'outside'):
                feeding_containment(bad,low,high,people)
        for change in ({'solid':False},{'fluid':True}):
            bad=deepcopy(scan)
            next(r for r in bad['blocks']if r['pos']==[0,64,2]).update(change)
            with self.assertRaisesRegex(RuntimeError,'outside'):
                feeding_containment(bad,low,high,people)

    def test_containment_requires_complete_scan_and_current_interior_origins(self):
        from village_feeding import feeding_containment
        empty={'scan_cells_read':125,'scan_total_cells':125,'blocks':[],'time':100}
        for scan in ({**empty,'scan_cells_read':124},{**empty,'scan_total_cells':124}):
            with self.assertRaisesRegex(RuntimeError,'Complete'):
                feeding_containment(scan,[0,64,0],[4,67,4],[{'pos':[2,64,2]}])
        with self.assertRaisesRegex(RuntimeError,'positions'):
            feeding_containment(empty,[0,64,0],[4,67,4],[])
        with self.assertRaisesRegex(RuntimeError,'outside'):
            feeding_containment(empty,[0,64,0],[4,67,4],[{'pos':[-1,64,2]}])

    def test_farmland_and_covered_water_support_a_closed_floor_without_claiming_full_cubes(self):
        from village_feeding import feeding_containment
        from copy import deepcopy
        blocks=[{'pos':[x,y,z],'state':'Block{minecraft:dark_oak_planks}',
                 'solid':True,'fluid':False,'block_entity':False}for x in range(5)for y in range(63,68)for z in range(5)
                if x in(0,4)or z in(0,4)or y in(63,67)]
        next(r for r in blocks if r['pos']==[1,63,1]).update(state='Block{minecraft:farmland}[moisture=7]',solid=False)
        next(r for r in blocks if r['pos']==[2,63,2]).update(state='Block{minecraft:dark_oak_slab}[type=top,waterlogged=true]',solid=False,fluid=True)
        scan={'scan_cells_read':125,'scan_total_cells':125,'blocks':blocks,'time':100}
        people=[{'pos':[1.5,63.9375,1.5]},{'pos':[2.5,64,2.5]}]
        proof=feeding_containment(scan,[0,64,0],[4,67,4],people)
        self.assertEqual('sealed_collision_shell',proof['kind'])
        self.assertEqual(2,proof['partial_floor_collision_surfaces'])
        for state,fluid in [('Block{minecraft:water}[level=0]',True),('Block{minecraft:farmland}[moisture=8]',False),('Block{minecraft:oak_trapdoor}[open=false]',False)]:
            bad=deepcopy(scan);next(r for r in bad['blocks']if r['pos']==[2,63,2]).update(state=state,fluid=fluid)
            with self.assertRaisesRegex(RuntimeError,'outside'):
                feeding_containment(bad,[0,64,0],[4,67,4],people)
        bad=deepcopy(scan);next(r for r in bad['blocks']if r['pos']==[0,64,2]).update(state='Block{minecraft:farmland}[moisture=7]',solid=False)
        with self.assertRaisesRegex(RuntimeError,'outside'):
            feeding_containment(bad,[0,64,0],[4,67,4],people)

    def test_sunken_workpoint_requires_its_observed_full_width_carpet_cover(self):
        from village_feeding import feeding_containment
        from copy import deepcopy
        blocks=[{'pos':[x,y,z],'state':'Block{minecraft:dark_oak_planks}',
                 'solid':True,'fluid':False,'block_entity':False}for x in range(5)for y in range(63,68)for z in range(5)
                if x in(0,4)or z in(0,4)or y in(63,67)]
        next(r for r in blocks if r['pos']==[2,63,2]).update(state='Block{minecraft:composter}[level=0]',solid=False)
        blocks.append({'pos':[2,64,2],'state':'Block{minecraft:light_gray_carpet}',
                       'solid':False,'fluid':False,'block_entity':False})
        scan={'scan_cells_read':125,'scan_total_cells':125,'blocks':blocks,'time':100}
        people=[{'pos':[2.5,64.0625,2.5]}]
        self.assertEqual(1,feeding_containment(scan,[0,64,0],[4,67,4],people)['partial_floor_collision_surfaces'])
        for cap in(None,{'pos':[2,64,2],'state':'Block{minecraft:air}','solid':False,'fluid':False,'block_entity':False}):
            bad=deepcopy(scan);bad['blocks']=[r for r in blocks if r['pos']!=[2,64,2]]
            if cap:bad['blocks'].append(cap)
            with self.assertRaisesRegex(RuntimeError,'outside'):
                feeding_containment(bad,[0,64,0],[4,67,4],people)

    def test_connected_fences_need_full_base_low_roof_and_reciprocal_connections(self):
        from village_feeding import feeding_containment
        from copy import deepcopy
        blocks=[{'pos':[x,y,z],'state':'Block{minecraft:dark_oak_planks}',
                 'solid':True,'fluid':False}for x in range(5)for y in range(63,68)for z in range(5)
                if x in(0,4)or z in(0,4)or y in(63,67)]
        for z in(1,2,3):
            next(r for r in blocks if r['pos']==[0,65,z]).update(solid=False,state='Block{minecraft:dark_oak_fence}[north=true,south=true,east=false,west=false,waterlogged=false]')
            blocks=[r for r in blocks if r['pos']!=[0,66,z]]
        scan={'scan_cells_read':125,'scan_total_cells':125,'blocks':blocks,'time':100}
        people=[{'pos':[2.5,64,2.5]}]
        proof=feeding_containment(scan,[0,64,0],[4,67,4],people)
        self.assertEqual('sealed_collision_shell',proof['kind'])
        self.assertEqual(3,proof['low_roof_connected_fences'])
        branch=deepcopy(scan)
        row=next(r for r in branch['blocks']if r['pos']==[0,65,2]);row['state']=row['state'].replace('west=false','west=true')
        self.assertEqual(3,feeding_containment(branch,[0,64,0],[4,67,4],people)['low_roof_connected_fences'])
        for hole in ([0,64,2],[0,67,2]):
            bad=deepcopy(scan);bad['blocks']=[r for r in blocks if r['pos']!=hole]
            with self.assertRaisesRegex(RuntimeError,'outside'):
                feeding_containment(bad,[0,64,0],[4,67,4],people)
        for old,new in [('north=true','north=false'),('waterlogged=false','waterlogged=true')]:
            bad=deepcopy(scan)
            row=next(r for r in bad['blocks']if r['pos']==[0,65,2]);row['state']=row['state'].replace(old,new)
            with self.assertRaisesRegex(RuntimeError,'outside'):
                feeding_containment(bad,[0,64,0],[4,67,4],people)

    def test_existing_closed_loading_gates_remain_supported_but_open_gate_is_refused(self):
        from village_feeding import feeding_containment
        gates=[{'pos':[0,64+i//3,i%3],'state':'Block{minecraft:dark_oak_fence_gate}[open=false]'}for i in range(6)]
        scan={'scan_cells_read':125,'scan_total_cells':125,'blocks':gates,'time':100}
        self.assertEqual('six_closed_loading_gates',feeding_containment(scan,[0,64,0],[4,67,4],[])['kind'])
        gates[0]['state']=gates[0]['state'].replace('false','true')
        with self.assertRaisesRegex(RuntimeError,'closed'):
            feeding_containment(scan,[0,64,0],[4,67,4],[])

    def test_quick_own_pickup_can_be_verified_after_a_single_debit_frame(self):
        from village_feeding import food_receipt_ready
        own=[{'collector':{'uuid':'player'}}];adult=[{'collector':{'uuid':'adult'}}]
        self.assertTrue(food_receipt_ready(own,'player',[100]))
        self.assertFalse(food_receipt_ready(adult,'player',[100]))
        self.assertTrue(food_receipt_ready(adult,'player',[100,200]))
        self.assertFalse(food_receipt_ready([],'player',[100,200]))
        self.assertFalse(food_receipt_ready(own+adult,'player',[100,200]))
    def test_repeated_interception_does_not_keep_targeting_the_same_adult(self):
        from village_feeding import choose_food_target
        required={'full':3,'intercepted':3,'other':3};delivered={'full':4,'intercepted':0,'other':1}
        receipts=[{'target':'intercepted','actual_collector':'full'}]*3
        self.assertEqual('other',choose_food_target(required,delivered,receipts))
        self.assertEqual('intercepted',choose_food_target(required,{**delivered,'other':3},receipts))
    def test_retreat_from_wall_edge_keeps_height_and_avoids_people_and_blocks(self):
        from village_feeding import food_retreat_pose,outside_food_pickup_box
        import math
        low=[0,64,0];high=[8,68,8];cells={(3,65,6):{'state':'stone'}}
        points=[[6.5,65,6.5]];people=[{'pos':[3.5,65,5.5]}]
        for y in(64,65):
            state={'pos':[5.25,y,6.77]};p=food_retreat_pose(low,high,cells,points,people,state)
            self.assertGreaterEqual(p[1],max(64.7,y));self.assertTrue(outside_food_pickup_box(p,points))
            self.assertNotEqual((3,6),(math.floor(p[0]),math.floor(p[2])))
            self.assertGreaterEqual(math.dist(p,people[0]['pos']),1)
    def test_retreat_avoids_both_initial_drop_and_forward_landing_area(self):
        from village_feeding import outside_food_pickup_box
        points=[[10,65.7,12.68],[10,64.56,13.29]]
        self.assertFalse(outside_food_pickup_box([10,64.7,14.5],points))
        self.assertTrue(outside_food_pickup_box([10,64.7,10.5],points))
        self.assertTrue(outside_food_pickup_box([7.5,64.7,12.5],points))
    def test_retreat_rejects_a_work_table_or_water_at_feet_despite_clear_headroom(self):
        from village_feeding import food_retreat_pose
        cells={(x,65,z):{'state':'stone'}for x in range(1,8)for z in range(1,8)if(x,z)!=(2,2)}
        for foot in ({'state':'Block{minecraft:fletching_table}','solid':True,'fluid':False},
                     {'state':'Block{minecraft:water}','solid':False,'fluid':True}):
            with self.subTest(foot=foot['state']):
                cells[2,64,2]=foot
                with self.assertRaisesRegex(RuntimeError,'No clear retreat'):
                    food_retreat_pose([0,64,0],[8,68,8],cells,[[6.5,64,6.5]],[],{'pos':[5.5,64,6.5]})
    def test_retreat_still_accepts_a_bed_surface_below_hover_height(self):
        from village_feeding import food_retreat_pose
        cells={(x,65,z):{'state':'stone'}for x in range(1,8)for z in range(1,8)if(x,z)!=(2,2)}
        cells[2,64,2]={'state':'Block{minecraft:white_bed}[facing=north,occupied=false,part=head]',
                       'solid':False,'fluid':False,'block_entity':True}
        pose=food_retreat_pose([0,64,0],[8,68,8],cells,[[6.5,64,6.5]],[],{'pos':[5.5,64,6.5]})
        self.assertEqual([2.5,64.7,2.5],pose)
    def test_retreat_does_not_hover_above_farmland_then_land_and_trample_it(self):
        from village_feeding import food_retreat_pose
        cells={(x,65,z):{'state':'stone'}for x in range(1,8)for z in range(1,8)if(x,z)!=(2,2)}
        cells[2,63,2]={'state':'Block{minecraft:farmland}[moisture=7]'}
        with self.assertRaisesRegex(RuntimeError,'No clear retreat'):
            food_retreat_pose([0,64,0],[8,68,8],cells,[[6.5,64,6.5]],[],{'pos':[5.5,64,6.5]})
    def test_food_pose_room_is_separate_from_whole_enclosure_and_cannot_escape_it(self):
        from village_feeding import feeding_pose_bounds
        low=[0,64,0];high=[32,67,15];bounds={'min':[0,64,3],'max':[8,67,12]}
        self.assertEqual((low,high),feeding_pose_bounds(low,high))
        self.assertEqual((bounds['min'],bounds['max']),feeding_pose_bounds(low,high,bounds))
        for bad in ({'min':[-1,64,3],'max':[8,67,12]},
                    {'min':[0,65,3],'max':[8,67,12]},
                    {'min':[False,64,3],'max':[8,67,12]}):
            with self.assertRaises(ValueError):feeding_pose_bounds(low,high,bad)
    def test_pose_only_resume_requires_no_drop_history_and_unchanged_real_stock(self):
        from village_feeding import feed
        proof={'classification':'pose_refused_before_any_bread_drop','world_session':'world',
               'no_bread_drop_intents':True,'original_request_replayed':False,'bread_before':1,'bread_after':1}
        base={'complete':False,'pending':None,'pending_food':None,'required':{'parent':1},
              'world_session':'world','pose_recoveries':[proof],'receipts':[],'delivered':{'parent':0}}
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'feed.json'
            variants=[{**base,'pending_food':{'unknown':True}},{**base,'receipts':[{}]},
                      {**base,'delivered':{'parent':1}},*[{**base,'pose_recoveries':[{**proof,**change}]}for change in
                      ({'no_bread_drop_intents':False},{'bread_before':True},{'bread_after':0},{'world_session':'other'})]]
            for book in variants:
                path.write_text(json.dumps(book));owner=Mock(world='world')
                with self.assertRaisesRegex(RuntimeError,'unresolved'):feed(owner,directory,{'parent':1},path,[0,0,0],[2,3,2])
                owner.native.assert_not_called()
            for count in(0,1):
                path.write_text(json.dumps(base));owner=Mock(world='world');owner.status.return_value={'inventory':[{'slot':0,'item':'minecraft:bread','count':count}]};owner.native.side_effect=RuntimeError('first scan')
                with self.assertRaisesRegex(RuntimeError,'stock changed'if count==0 else'first scan'):feed(owner,directory,{'parent':1},path,[0,0,0],[2,3,2])
                if count==0:owner.native.assert_not_called()
    def test_hover_gravity_needs_fresh_unchanged_positions_not_velocity_alone(self):
        from village_feeding import stable_hover
        frames=[{'time':t,'world_session':'w','flight':True,'navigating':False,
                 'velocity':[0,-.0784,0],'pos':[1,64.6,2]}for t in(100,250,400)]
        self.assertTrue(stable_hover(frames));self.assertFalse(stable_hover(frames[:2]))
        for changes in ({'pos':[1,64.5,2]},{'time':250},{'world_session':'other'},
                        {'velocity':[0,-.2,0]},{'navigating':True},{'manual_movement':True}):
            self.assertFalse(stable_hover(frames[:2]+[{**frames[2],**changes}]))
    def test_child_pickup_is_recorded_without_filling_an_adult_quota(self):
        from village_feeding import credit_collector
        book={'delivered':{'adult':0}}
        credit_collector(book,'adult',1);credit_collector(book,'child',1)
        self.assertEqual({'adult':1},book['delivered'])
        self.assertEqual({'child':1},book['other_villager_deliveries'])
        for amount in (True,0,2,-1):
            with self.assertRaises(RuntimeError):credit_collector(book,'adult',amount)
        self.assertEqual({'adult':1},book['delivered'])
    def test_resume_requires_proven_no_input_or_actual_player_recovery(self):
        from village_feeding import feed
        rejection={'classification':'pinned_food_guard_rejected_before_normal_Q','world_session':'world',
                   'host_jar_sha256':'d51d980dd68ea9f76e0d00c531d2b903657e3879d5ac5b91ff3a47d39ad9653a',
                   'original_request_replayed':False}
        base={'complete':False,'pending':None,'pending_food':None,'required':{'parent':1},
              'world_session':'world','preflight_rejections':[rejection]}
        invalid=[{**base,'pending_food':{'source':'unknown'}},{**base,'pending':{'op':'villager_bread_drop'}},
                 {**base,'world_session':'old'},{**base,'preflight_rejections':[]},
                 *[{**base,'preflight_rejections':[{**rejection,**change}]} for change in
                   ({'world_session':'old'},{'host_jar_sha256':'wrong'},{'original_request_replayed':True},
                    {'classification':'unknown_execution'})]]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'feeding.json'
            for book in invalid:
                owner=Mock(world='world');path.write_text(json.dumps(book))
                with self.assertRaisesRegex(RuntimeError,'unresolved'):
                    feed(owner,directory,{'parent':1},path,[0,0,0],[2,3,2])
                owner.native.assert_not_called()
            owner=Mock(world='world');owner.native.side_effect=RuntimeError('test first scan')
            path.write_text(json.dumps(base))
            with self.assertRaisesRegex(RuntimeError,'test first scan'):
                feed(owner,directory,{'parent':1},path,[0,0,0],[2,3,2])
            self.assertEqual('scan',owner.native.call_args.args[0])
    def test_grounded_gravity_velocity_does_not_prevent_feeding_but_hover_drift_does(self):
        s={'on_ground':True,'flight':False,'navigating':False,'velocity':[0,-.0784,0]}
        self.assertTrue(settled_pose(s));self.assertFalse(settled_pose({**s,'on_ground':False,'flight':True}))
        self.assertTrue(settled_pose({**s,'on_ground':False,'flight':True,'velocity':[0,0,0]}))
    def test_bed_occupant_gets_a_same_height_pose_on_the_other_half(self):
        cells={(1,64,2):{'state':'Block{minecraft:white_bed}[facing=north,occupied=true,part=head]'},
               (1,64,3):{'state':'Block{minecraft:white_bed}[facing=north,occupied=true,part=foot]'}}
        self.assertEqual([1.5,64.5625,3.5],bed_level_pose(cells,{'pos':[1.5,64.5625,2.5]}))
        self.assertEqual([1.5,64.6425,3.5],bed_level_pose(cells,{'pos':[1.5,64.5625,2.5]},sleeping=True))
        import math
        shifted={'pos':[1.55,64.5625,2.8]}
        distance=math.dist(bed_level_pose(cells,shifted,sleeping=True),shifted['pos'])
        self.assertGreaterEqual(distance,.4);self.assertLessEqual(distance,1.25)
        self.assertIsNone(bed_level_pose(cells,{'pos':[1.5,64,2.5]}))
        cells[1,66,3]={'state':'Block{minecraft:stone}'}
        self.assertIsNone(bed_level_pose(cells,{'pos':[1.5,64.5625,2.5]}))
    def test_one_drop_can_be_confirmed_by_a_real_collector_packet_seventeen_seconds_later(self):
        from unittest.mock import patch
        from village_feeding import feed
        class Clock:
            now=0
            def monotonic(self):return self.now
            def sleep(self,n):self.now+=n
        clock=Clock()
        class Owner:
            world='world'
            def __init__(self):
                self.bread=2;self.started=None;self.position=[1,64,1.5];self.calls=[];self.flight=False
            def status(self):
                person={'id':12,'uuid':'parent','pos':[1.8,64,1.5],'health':20,'is_baby':False,'visible':True}
                drop={'id':77,'uuid':'one-drop','type':'minecraft:item','pos':[1.5,64.5,1.5],
                      'stack':{'item':'minecraft:bread','count':1}}
                entities=[drop]if self.started is not None and clock.now-self.started<17 else[]
                return {'time':1000+int(clock.now*1000),'world_session':'world','runtime_generation':0,
                    'player_uuid':'player','pos':list(self.position),'velocity':[0,0,0],'on_ground':not self.flight,
                    'flight':self.flight,'navigating':False,'manual_movement':False,'health':20,
                    'hand':{'item':'minecraft:bread','count':self.bread},'entities':entities,
                    'inventory':[{'slot':0,'item':'minecraft:bread','count':self.bread}],
                    'loaded_villagers':{'villagers':[person]}}
            def native(self,op,**params):
                self.calls.append(op)
                if op=='scan':return {'blocks':[]}
                if op=='villager_bread_drop':self.started=clock.now;self.bread-=1
                if op=='navigate':self.position=params['target'];self.flight=True
                return {'id':'request-'+str(len(self.calls)),'phase':'done'}
        owner=Owner()
        def frame(root,state):
            events=[]
            if owner.started is not None and clock.now-owner.started>=17:
                events=[{'kind':'pickup_entities_unresolved','source_entity_id':77,'collector_entity_id':12,
                         'received_at':1000+int(owner.started*1000)+17000,'amount':1,
                         'collector':{'entity_id':12,'uuid':'parent','type':'minecraft:villager','pos':[1.8,64,1.5]}}]
            return {'world_session':'world','runtime_generation':0,'world_entered_at':0,'time':state['time'],
                    'events':events,'villagers':[{'uuid':'parent','sleeping':False}]}
        with tempfile.TemporaryDirectory()as tmp, \
                patch('village_feeding.time.monotonic',clock.monotonic), \
                patch('village_feeding.time.sleep',clock.sleep), \
                patch('village_feeding.read',side_effect=frame), \
                patch('village_feeding.feeding_containment',return_value={'verified':True}), \
                patch('village_feeding.food_retreat_pose',return_value=[4.5,64.7,4.5]):
            result=feed(owner,Path(tmp),{'parent':1},Path(tmp)/'food.json',[0,64,0],[5,67,5])
        self.assertTrue(result['complete']);self.assertEqual({'parent':1},result['delivered'])
        self.assertEqual(1,owner.calls.count('villager_bread_drop'))
        self.assertEqual(1,owner.bread);self.assertGreaterEqual(clock.now,17)
