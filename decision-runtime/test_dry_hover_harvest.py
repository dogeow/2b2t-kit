import unittest,tempfile
from types import SimpleNamespace
from unittest.mock import patch,Mock
from material_jobs.dry_hover_harvest import offers,pickup_offers,pickup,run,visible_face,rejected_without_mining,harvest_context

def row(pos,name,**kw):return {'pos':pos,'state':'Block{minecraft:'+name+'}','fluid':False,'block_entity':False,'solid':True,**kw}
class DryHoverHarvestTest(unittest.TestCase):
    def test_known_removal_without_unique_drop_keeps_zero_credit_and_continues(self):
        for stack_count,inflight,ack in ((2,None,True),(1,None,True),(2,{'id':'unknown-move'},True),(2,None,False)):
            with self.subTest(stack_count=stack_count,inflight=inflight,ack=ack):
                state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
                       'pos':[1.5,4.2,.5],'entities':[],
                       'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
                state['inventory'][0].update(item='minecraft:dripstone_block',count=4)
                state['inventory'][1].update(item='minecraft:diamond_pickaxe',count=1,durability=100,max_durability=1561)
                proof={'id':'r','world_session':'w','phase':'done','server_confirmed':ack,'outcome_pending':False,
                       'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack','server_update_seen':True,
                       'server_observed_state':'Block{minecraft:air}','native_sequence':3,'server_ack_sequence':3,'mining_target':[0,4,0]}
                def mine(*a,**kw):
                    state['entities']=[{'uuid':'merged','type':'minecraft:item','pos':[.5,4.125,.5],
                        'stack':{'item':'minecraft:dripstone_block','count':stack_count}}]
                    return proof
                c=SimpleNamespace(world='w',status=lambda:state,last='r',request=Mock(side_effect=mine),native_inflight=inflight)
                region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,8,3]}
                choice={'target':[0,4,0],'state':'Block{minecraft:dripstone_block}','station':[1.5,4.2,.5],'face':'east'}
                with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',side_effect=[[row([0,4,0],'dripstone_block')],[row([0,4,0],'dripstone_block')],[]]),\
                     patch('material_jobs.dry_hover_harvest.offers',side_effect=[[choice],[]]),\
                     patch('material_jobs.dry_hover_harvest._protected',return_value=False),patch('material_jobs.dry_hover_harvest._choose_tool'),\
                     patch('material_jobs.dry_hover_harvest.move'),patch('material_jobs.dry_hover_harvest.pickup',return_value=True)as pickup:
                    if inflight is not None or not ack:
                        with self.assertRaises(RuntimeError):run(c,{},region,64,d,lambda:None,max_blocks=2)
                    elif stack_count==2:
                        result=run(c,{},region,64,d,lambda:None,max_blocks=2)
                        self.assertEqual(4,result['verified_count']);self.assertIsNone(result['pending'])
                        self.assertEqual(0,result['receipts'][0]['inventory_credit'])
                        self.assertTrue(result['unreceived_drops'][0]['drop_identity_unconfirmed']);pickup.assert_not_called()
                    else:
                        # The ordinary single-drop path still requires a real
                        # inventory gain; a successful return alone cannot credit it.
                        with self.assertRaisesRegex(RuntimeError,'exact backpack gain'):run(c,{},region,64,d,lambda:None,max_blocks=2)
                    self.assertEqual(1,c.request.call_count)

    def test_failed_ledge_pickup_uses_proved_lower_air_before_repeating_edges(self):
        import itertools,json
        from pathlib import Path
        clock=itertools.count(0,.2);position=[1.5,.2,1.5];received=False;moves=[]
        drop={'uuid':'ledge-original','type':'minecraft:item','pos':[.849,1.,.989],
              'stack':{'item':'minecraft:pointed_dripstone','count':1}}
        rows=[row([x,y,z],'stone')for x in range(-3,5)for y in range(-3,6)for z in range(-3,5)
              if (x,z)!=(1,1)or y not in(-1,0,1)]
        def state():return {'pos':list(position),'entities':[]if received else[drop],
                           'inventory':[{'slot':0,'item':'minecraft:pointed_dripstone','count':6 if received else 5}]}
        def movement(c,point,out,**kwargs):
            nonlocal received
            moves.append(list(point));position[:]=point
            if len(moves)==1:self.assertEqual([1.5,.2,1.5],point)
            else:
                self.assertEqual([1.5,-.8,1.5],point);self.assertNotIn('allow_dry_cone_edge',kwargs)
                received=True
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',return_value=rows),\
             patch('material_jobs.dry_hover_harvest.move',side_effect=movement),\
             patch('material_jobs.dry_hover_harvest.time.sleep'),\
             patch('material_jobs.dry_hover_harvest.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(pickup(SimpleNamespace(world='w'),drop,5,d,state,item='minecraft:pointed_dripstone'))
            book=json.loads((Path(d)/'pickup.json').read_text())
        self.assertEqual(2,len(moves));self.assertTrue(book['confirmed']);self.assertEqual(6,book['after'])

    def test_reached_centre_without_pickup_uses_a_new_safe_edge_and_actual_inventory_proof(self):
        import itertools,json
        from pathlib import Path
        clock=itertools.count(0,.2);position=[1.5,.2,1.5];received=False;moves=[]
        drop={'uuid':'same-acknowledged-drop','type':'minecraft:item','pos':[.873,1.,1.027],
              'stack':{'item':'minecraft:pointed_dripstone','count':1}}
        rows=[row([x,y,z],'stone')for x in range(-3,5)for y in range(-3,6)for z in range(-3,5)
              if (x,z)!=(1,1)or y not in(0,1)]
        def state():return {'pos':list(position),'entities':[]if received else[drop],
                           'inventory':[{'slot':0,'item':'minecraft:pointed_dripstone','count':5 if received else 4}]}
        def movement(c,point,out,**kwargs):
            nonlocal received
            moves.append(list(point));position[:]=point
            if len(moves)==1:
                self.assertEqual([1.5,.2,1.5],point)
            else:
                self.assertTrue(kwargs['exact_target']);self.assertNotIn('allow_dry_cone_edge',kwargs)
                self.assertGreaterEqual(point[0]-.3,1);self.assertGreaterEqual(point[2]-.3,1)
                received=True
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',return_value=rows),\
             patch('material_jobs.dry_hover_harvest.move',side_effect=movement),\
             patch('material_jobs.dry_hover_harvest.time.sleep'),\
             patch('material_jobs.dry_hover_harvest.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(pickup(SimpleNamespace(world='w'),drop,4,d,state,item='minecraft:pointed_dripstone'))
            book=json.loads((Path(d)/'pickup.json').read_text())
        self.assertEqual(2,len(moves));self.assertNotEqual(moves[0],moves[1])
        self.assertEqual([4,5],[a['after']for a in book['attempts']])
        self.assertTrue(book['confirmed']);self.assertFalse(book['collect_item_sent'])

    def native_cone_pocket(self):
        rows=[row([x,y,z],'stone')for x in range(-3,4)for y in range(-1,6)for z in range(-2,3)
              if (x,z)!=(1,0)or y not in range(5)]
        rows=[r for r in rows if r['pos']not in ([0,0,0],[0,1,0])]
        for y,thickness in ((0,'base'),(1,'frustum')):
            rows.append({'pos':[0,y,0],'state':'Block{minecraft:pointed_dripstone}[thickness='+thickness+',vertical_direction=up,waterlogged=false]',
                         'fluid':False,'block_entity':False,'solid':False})
        return rows
    def test_larger_cone_edge_is_only_an_opt_in_candidate_for_native_shape_validation(self):
        rows=self.native_cone_pocket();args=(rows,[-3,-1,-2],[3,5,2],[1.5,3.2,.5],[-.104,0,.5])
        self.assertEqual([],pickup_offers(*args))
        points=pickup_offers(*args,allow_cone_edges=True);self.assertEqual([[1.2,.2,.5]],points)
        for r in rows:
            if r['pos']==[0,0,0]:r['state']='Block{minecraft:stone}'
        self.assertEqual([],pickup_offers(*args,allow_cone_edges=True))
    def test_confirmed_cone_edge_pickup_returns_to_a_full_air_cell(self):
        import itertools,json
        from pathlib import Path
        rows=self.native_cone_pocket();position=[1.5,3.2,.5];received=False;clock=itertools.count(0,.2)
        drop={'uuid':'cone-pocket-original','type':'minecraft:item','pos':[-.104,0,.5],
              'stack':{'item':'minecraft:pointed_dripstone','count':1}}
        def state():return {'pos':list(position),'entities':[]if received else[drop],
                          'inventory':[{'slot':0,'item':'minecraft:pointed_dripstone','count':1 if received else 0}]}
        def movement(c,point,out,**kwargs):
            nonlocal received
            self.assertEqual([1.2,.2,.5],point);self.assertTrue(kwargs['allow_dry_cone_edge']);self.assertTrue(kwargs['exact_target'])
            position[:]=point;received=True
        def scan(c,lo,hi):return [r for r in rows if all(lo[i]<=r['pos'][i]<=hi[i]for i in range(3))]
        def restore(c,point,*args,**kwargs):
            self.assertEqual([1.5,.2,.5],point);self.assertEqual(.08,kwargs['arrival']);position[:]=point
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',return_value=rows),\
             patch('material_jobs.dry_hover_harvest.move',side_effect=movement),\
             patch('material_jobs.navigation._air_scan',side_effect=scan),\
             patch('material_jobs.navigation._air_move',side_effect=restore)as back,\
             patch('material_jobs.dry_hover_harvest.time.sleep'),\
             patch('material_jobs.dry_hover_harvest.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(pickup(SimpleNamespace(world='w'),drop,0,d,state,item='minecraft:pointed_dripstone',allow_cone_edges=True))
            book=json.loads((Path(d)/'pickup.json').read_text())
        self.assertTrue(book['confirmed']);self.assertEqual(1,book['after']);self.assertIsNone(book['return_to_air_cell_pending'])
        self.assertEqual(1,back.call_count);self.assertEqual([1.5,.2,.5],position)
    def test_cone_pocket_can_be_picked_from_an_edge_inside_an_adjoining_full_air_cell(self):
        rows=[row([x,y,z],'stone')for x in range(-2,3)for y in range(-1,7)for z in range(-2,4)
              if (x,z)!=(0,1)]
        points=pickup_offers(rows,[-2,-1,-2],[2,6,3],[.5,4.2,1.5],[.125,0,.029])
        self.assertTrue(points);self.assertEqual([.32,.2,1.32],points[0])
        self.assertGreaterEqual(points[0][2]-.31,1)
        rows.append(row([0,1,1],'stone'))
        self.assertEqual([],pickup_offers(rows,[-2,-1,-2],[2,6,3],[.5,4.2,1.5],[.125,0,.029]))
    def test_scan_updates_falling_item_height_before_any_new_movement(self):
        import itertools
        received=False;clock=itertools.count(0,.2)
        drop={'uuid':'original','pos':[.5,69.2,.5],'type':'minecraft:item','stack':{'item':'minecraft:pointed_dripstone','count':1}}
        def state():return {'pos':[1.5,67.2,.5],'entities':[]if received else[drop],
                          'inventory':[{'slot':0,'item':'minecraft:pointed_dripstone','count':4 if received else 3}]}
        def scan(*args):drop['pos']=[.125,64.,.029];return[]
        def arrivals(rows,low,high,player,current_drop):
            nonlocal received
            self.assertEqual([.125,64.,.029],current_drop);received=True;return[]
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',side_effect=scan),\
             patch('material_jobs.dry_hover_harvest.pickup_offers',side_effect=arrivals),\
             patch('material_jobs.dry_hover_harvest.move')as movement,patch('material_jobs.dry_hover_harvest.time.sleep'),\
             patch('material_jobs.dry_hover_harvest.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(pickup(SimpleNamespace(world='w'),drop,3,d,state,item='minecraft:pointed_dripstone'))
        movement.assert_not_called()
    def test_exact_four_ball_stack_is_confirmed_without_mining_or_collect_replay(self):
        import itertools,json
        from pathlib import Path
        received=False;clock=itertools.count(0,.2)
        drop={'uuid':'four-original','pos':[.5,71.125,.5],'type':'minecraft:item','stack':{'item':'minecraft:clay_ball','count':4}}
        def state():return {'pos':[1.5,72.2,.5],'entities':[]if received else[drop],
                          'inventory':[{'slot':0,'item':'minecraft:clay_ball','count':20 if received else 16}]}
        def arrivals(*a):
            nonlocal received
            received=True;return[]
        c=SimpleNamespace(world='w')
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',return_value=[]),\
             patch('material_jobs.dry_hover_harvest.pickup_offers',side_effect=arrivals),\
             patch('material_jobs.dry_hover_harvest.move')as movement,patch('material_jobs.dry_hover_harvest.time.sleep'),\
             patch('material_jobs.dry_hover_harvest.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(pickup(c,drop,16,d,state,item='minecraft:clay_ball',expected_count=4))
            book=json.loads((Path(d)/'pickup.json').read_text());self.assertEqual(20,book['after']);self.assertEqual(4,book['expected_count'])
            movement.assert_not_called()
    def test_known_removal_with_no_air_pickup_keeps_zero_credit_and_never_remines(self):
        for inflight,error,late in ((None,'No actual air body position near the current settled drop',False),
                               (None,'New normal-air item pickup unconfirmed; no remine',False),
                               (None,'New normal-air item pickup unconfirmed; no remine',True),
                               (None,'Original mined item vanished without actual inventory gain',False),
                               (None,'Current mined item stack changed',False),
                               (None,'Unknown movement receipt',False),
                               ({'request_id':'unknown-move'},'New normal-air item pickup unconfirmed; no remine',False)):
            with self.subTest(inflight=inflight,error=error,late=late):
                drop={'uuid':'new-drop','type':'minecraft:item','pos':[.5,4.125,.5],'stack':{'item':'minecraft:dripstone_block','count':1}}
                state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
                       'pos':[1.5,4.2,.5],'entities':[],
                       'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
                state['inventory'][0].update(item='minecraft:dripstone_block',count=4)
                state['inventory'][1].update(item='minecraft:diamond_pickaxe',count=1,durability=100,max_durability=1561)
                proof={'id':'r','world_session':'w','phase':'done','server_confirmed':True,'outcome_pending':False,
                       'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack','server_update_seen':True,
                       'server_observed_state':'Block{minecraft:air}','native_sequence':3,'server_ack_sequence':3,'mining_target':[0,4,0]}
                def mine(*a,**kw):state['entities']=[drop];return proof
                c=SimpleNamespace(world='w',status=lambda:state,last='r',request=Mock(side_effect=mine),native_inflight=inflight)
                region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,8,3]}
                choice={'target':[0,4,0],'state':'Block{minecraft:dripstone_block}','station':[1.5,4.2,.5],'face':'east'}
                def delayed_pickup(*args,**kwargs):
                    if late:state['inventory'][0]['count']=5;state['entities']=[]
                    raise RuntimeError(error)
                with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',side_effect=[[row([0,4,0],'dripstone_block')],[row([0,4,0],'dripstone_block')],[]]),\
                     patch('material_jobs.dry_hover_harvest.offers',side_effect=[[choice],[]]),\
                     patch('material_jobs.dry_hover_harvest._protected',return_value=False),patch('material_jobs.dry_hover_harvest._choose_tool'),\
                     patch('material_jobs.dry_hover_harvest.move'),patch('material_jobs.dry_hover_harvest.pickup',side_effect=delayed_pickup):
                    if inflight is None and error!='Unknown movement receipt':
                        result=run(c,{},region,64,d,lambda:None,max_blocks=2)
                        self.assertIsNone(result['pending']);self.assertEqual(5 if late else 4,result['verified_count'])
                        if late:self.assertTrue(result['receipts'][0]['late_pickup_verified']);self.assertEqual(1,result['receipts'][0]['actual_gain'])
                        else:self.assertEqual(0,result['unreceived_drops'][0]['inventory_credit']);self.assertEqual(0,result['receipts'][0]['actual_gain'])
                    else:
                        with self.assertRaises(RuntimeError):run(c,{},region,64,d,lambda:None,max_blocks=2)
                        import json
                        from pathlib import Path
                        self.assertEqual('r',json.loads((Path(d)/'harvest.json').read_text())['pending']['request_id'])
                    self.assertEqual(1,c.request.call_count)

    def test_overlapping_original_drop_can_arrive_after_no_air_station_without_new_movement(self):
        import itertools,json
        from pathlib import Path
        received=False;clock=itertools.count(0,.2)
        drop={'uuid':'original-drop','pos':[.5,3.125,.5],'type':'minecraft:item','stack':{'item':'minecraft:dripstone_block','count':1}}
        def state():
            return {'pos':[1.5,4.2,.5],'entities':[]if received else[drop],
                    'inventory':[{'slot':0,'item':'minecraft:dripstone_block','count':5 if received else 4}]}
        def no_station(*a):
            nonlocal received
            received=True;return[]
        c=SimpleNamespace(world='w')
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',return_value=[]),\
             patch('material_jobs.dry_hover_harvest.pickup_offers',side_effect=no_station),\
             patch('material_jobs.dry_hover_harvest.move')as movement,\
             patch('material_jobs.dry_hover_harvest.time.sleep'),patch('material_jobs.dry_hover_harvest.time.monotonic',side_effect=lambda:next(clock)):
            self.assertTrue(pickup(c,drop,4,d,state));book=json.loads((Path(d)/'pickup.json').read_text())
            self.assertTrue(book['confirmed']);self.assertEqual('original-drop',book['uuid']);movement.assert_not_called()

    def test_real_cone_direction_preserves_support_without_mistaking_hanging_tip_for_floor_support(self):
        for direction,y,support in [('down',3,True),('up',5,True),('down',5,False),('up',3,False)]:
            cone=row([0,y,0],'pointed_dripstone',solid=False)
            cone['state']+='[vertical_direction='+direction+',waterlogged=false,thickness=tip]'
            self.assertEqual(not support,harvest_context([row([0,4,0],'dripstone_block'),cone],[0,4,0]))

    def test_rejected_without_send_replans_but_an_unknown_send_keeps_pending(self):
        for sequence in (-1,0):
            with self.subTest(sequence=sequence):
                state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
                       'pos':[1.5,4.2,.5],'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
                state['inventory'][0].update(item='minecraft:dripstone_block',count=4)
                state['inventory'][1].update(item='minecraft:diamond_pickaxe',count=1,durability=100,max_durability=1561)
                reply={'id':'r','world_session':'w','op':'mine_block','mining_target':[0,4,0],
                       'phase':'waiting','detail':'mining target is occluded','native_sequence':sequence,
                       'server_ack_sequence':-1,'server_update_seen':False,'server_confirmed':False,'outcome_pending':False}
                def mining_reply(*a,**kw):
                    if sequence==0:state['inventory'][0]['count']=6
                    return reply
                c=SimpleNamespace(world='w',status=lambda:state,last='r',request=Mock(side_effect=mining_reply))
                region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,8,3]}
                choice={'target':[0,4,0],'state':'Block{minecraft:dripstone_block}','station':[1.5,4.2,.5],'face':'east'}
                with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',return_value=[row([0,4,0],'dripstone_block')]),\
                     patch('material_jobs.dry_hover_harvest.offers',return_value=[choice]),patch('material_jobs.dry_hover_harvest._protected',return_value=False),\
                     patch('material_jobs.dry_hover_harvest._choose_tool'),patch('material_jobs.dry_hover_harvest.move'):
                    if sequence==-1:
                        result=run(c,{},region,64,d,lambda:None,max_blocks=2)
                        self.assertIsNone(result['pending']);self.assertEqual(0,result['rejected_before_mining'][0]['inventory_credit'])
                        self.assertEqual([],result['receipts'])
                    else:
                        with self.assertRaisesRegex(RuntimeError,'exact server confirmation'):run(c,{},region,64,d,lambda:None,max_blocks=2)
                        import json
                        from pathlib import Path
                        book=json.loads((Path(d)/'harvest.json').read_text());self.assertEqual('r',book['pending']['request_id'])
                    self.assertEqual(1,c.request.call_count)

    def test_buried_top_face_is_not_offered_even_when_adjacent_body_is_air(self):
        rows=[row([0,4,0],'dripstone_block'),row([0,5,0],'stone')]
        self.assertFalse(visible_face(rows,[1.5,5.2,.5],[0,4,0],'up'))
        self.assertFalse(any(r['target']==[0,4,0]and r['face']=='up'for r in offers(rows,[-3,1,-3],[3,8,3],[1.5,5.2,.5])))

    def test_only_exact_negative_sequences_prove_occlusion_before_any_mining(self):
        proof={'id':'r','world_session':'w','op':'mine_block','mining_target':[0,4,0],
               'phase':'waiting','detail':'mining target is occluded','native_sequence':-1,
               'server_ack_sequence':-1,'server_update_seen':False,'server_confirmed':False,'outcome_pending':False}
        self.assertTrue(rejected_without_mining(proof,'r','w',[0,4,0]))
        for k,v in [('id','other'),('world_session','old'),('mining_target',[1,4,0]),
                    ('native_sequence',0),('native_sequence',False),('server_ack_sequence',2),
                    ('server_update_seen',True),('outcome_pending',True)]:
            self.assertFalse(rejected_without_mining({**proof,k:v},'r','w',[0,4,0]))
    def test_ceiling_is_reachable_from_two_air_cells_below_without_entering_roof(self):
        rows=[row([x,6,z],'dripstone_block')for x in range(-3,4)for z in range(-3,4)]
        got=offers(rows,[-4,1,-4],[4,9,4],[.5,4.2,.5])
        target=[r for r in got if r['target']==[0,6,0]]
        self.assertTrue(target)
        self.assertEqual('down',target[0]['face'])
        self.assertEqual([.5,4.2,.5],target[0]['station'])

    def test_missing_local_target_updates_cached_geology_without_repeating_whole_region_scan(self):
        state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
               'pos':[1.5,4.2,.5],'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
        state['inventory'][0].update(item='minecraft:dripstone_block',count=3)
        c=SimpleNamespace(world='w',status=lambda:state,last='current-local-read',checked=Mock())
        region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,7,3]}
        choice={'target':[0,4,0],'state':'Block{minecraft:dripstone_block}','station':[1.5,4.2,.5],'face':'east'}
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',side_effect=[[row([0,4,0],'dripstone_block')],[]])as scan,\
             patch('material_jobs.dry_hover_harvest.offers',side_effect=[[choice],[]])as offered,\
             patch('material_jobs.dry_hover_harvest._protected',return_value=False),patch('material_jobs.dry_hover_harvest.move'):
            result=run(c,{},region,64,d,lambda:None,max_blocks=2)
        self.assertEqual(2,scan.call_count);self.assertEqual([],offered.call_args_list[-1].args[0])
        c.checked.assert_not_called();self.assertEqual(3,result['verified_count'])

    def test_changed_local_target_never_mines_from_cached_state(self):
        state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
               'pos':[1.5,4.2,.5],'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
        state['inventory'][0].update(item='minecraft:dripstone_block',count=3)
        c=SimpleNamespace(world='w',status=lambda:state,last='current-local-read',checked=Mock())
        region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,7,3]}
        choice={'target':[0,4,0],'state':'Block{minecraft:dripstone_block}','station':[1.5,4.2,.5],'face':'east'}
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',side_effect=[[row([0,4,0],'dripstone_block')],[row([0,4,0],'chest',block_entity=True)]]),\
             patch('material_jobs.dry_hover_harvest.offers',return_value=[choice]),\
             patch('material_jobs.dry_hover_harvest._protected',return_value=False),patch('material_jobs.dry_hover_harvest.move'):
            with self.assertRaisesRegex(RuntimeError,'Natural target'):run(c,{},region,64,d,lambda:None,max_blocks=1)
        c.checked.assert_not_called()

    def test_target_removed_before_mining_rescans_without_dispatch_or_ascent(self):
        state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
               'pos':[1.5,4.2,.5],'inventory':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
        state['inventory'][0].update(item='minecraft:dripstone_block',count=3)
        c=SimpleNamespace(world='w',status=lambda:state,last='fresh-scan')
        region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,7,3]}
        choice={'target':[0,4,0],'state':'Block{minecraft:dripstone_block}','station':[1.5,4.2,.5],'face':'east'}
        with tempfile.TemporaryDirectory()as d,patch('material_jobs.dry_hover_harvest._scan',side_effect=[[row([0,4,0],'dripstone_block')],[]]),patch('material_jobs.dry_hover_harvest.offers',return_value=[choice]),patch('material_jobs.dry_hover_harvest._protected',return_value=False),patch('material_jobs.dry_hover_harvest.move')as move:
            result=run(c,{},region,64,d,lambda:None,max_blocks=1)
        self.assertEqual(3,result['verified_count']);self.assertEqual([],result['receipts'])
        self.assertIsNone(result['pending']);self.assertEqual('current_target_already_air',result['skipped_before_mining'][0]['reason'])
        self.assertEqual([1.5,4.2,.5],move.call_args.args[1]);self.assertEqual(1,move.call_count)
    def test_floor_target_uses_adjacent_air_above_it_not_its_own_footing(self):
        rows=[row([x,4,z],'dripstone_block')for x in range(-2,3)for z in range(-2,3)]
        result=offers(rows,[-3,1,-3],[3,8,3],[1.5,5.2,.5])
        target=[r for r in result if r['target']==[0,4,0]]
        self.assertTrue(target);self.assertTrue(all(r['station'][1]==5.2 for r in target))
        self.assertTrue(all(r['face']=='up'for r in target))
        self.assertFalse(any(r['station'][0]==.5 and r['station'][2]==.5 for r in target))
    def test_already_carried_goal_returns_without_new_mining_or_drop_observation(self):
        state={'health':20,'food':20,'flight':True,'guard_armed':True,'guard_pve_only':True,
               'inventory':[{'slot':0,'item':'minecraft:dripstone_block','count':1}]}
        c=SimpleNamespace(world='w',status=lambda:state)
        region={'authorized':True,'source':'natural_survey','min':[-3,1,-3],'max':[3,7,3]}
        with tempfile.TemporaryDirectory()as d:
            result=run(c,{},region,1,d,lambda:None)
        self.assertTrue(result['full_target_reached']);self.assertEqual([],result['receipts'])
    def test_pickup_tracks_actual_item_height_instead_of_old_mining_plane(self):
        points=pickup_offers([],[-3,1,-3],[3,8,3],[1.5,6.2,.5],[.45,3.125,.45])
        self.assertTrue(points);self.assertEqual([.5,3.2,.5],points[0])
    def test_pickup_does_not_enter_blocked_item_cell_or_one_high_gap(self):
        points=pickup_offers([row([0,4,0],'stone')],[-3,1,-3],[3,8,3],[1.5,5.2,.5],[.5,3.125,.5])
        self.assertNotIn([.5,3.2,.5],points)
    def test_existing_torch_and_its_natural_support_remain(self):
        rows=[row([0,4,0],'dripstone_block'),row([0,5,0],'torch',solid=False,passable=True)]
        self.assertEqual([],offers(rows,[-3,1,-3],[3,7,3],[1.5,4.2,.5]))
    def test_actual_air_route_can_hover_without_inventing_a_floor(self):
        got=offers([row([0,4,0],'dripstone_block')],[-3,1,-3],[3,7,3],[1.5,4.2,.5])
        self.assertTrue(got);self.assertEqual([0,4,0],got[0]['target'])
    def test_liquid_structures_or_uncovered_target_prevent_harvest(self):
        base=[row([0,4,0],'dripstone_block')]
        for extra in(row([1,5,1],'water',fluid=True),row([1,4,1],'chest',block_entity=True)):
            self.assertEqual([],offers(base+[extra],[-3,1,-3],[3,7,3],[1.5,4.2,.5]))
        self.assertEqual([],offers(base,[-1,1,-1],[1,7,1],[1.5,4.2,.5]))
    def test_dry_neighboring_cone_does_not_disqualify_unrelated_block_but_stays_outside_body_route(self):
        rows=[row([0,4,0],'dripstone_block'),row([0,5,1],'pointed_dripstone')]
        got=offers(rows,[-3,1,-3],[3,7,3],[1.5,4.2,.5])
        self.assertTrue(got)
        self.assertFalse(any(p['station'][0]==.5 and p['station'][2]==1.5
                             and p['station'][1]in(4.2,5.2)for p in got))
    def test_stalactite_and_stalagmite_support_blocks_are_never_mined(self):
        for y in (3,5):
            rows=[row([0,4,0],'dripstone_block'),row([0,y,0],'pointed_dripstone')]
            self.assertEqual([],offers(rows,[-3,1,-3],[3,7,3],[1.5,4.2,.5]))
    def test_waterlogged_neighboring_cone_remains_a_fluid_hazard(self):
        rows=[row([0,4,0],'dripstone_block'),row([0,5,1],'pointed_dripstone',fluid=True)]
        self.assertEqual([],offers(rows,[-3,1,-3],[3,7,3],[1.5,4.2,.5]))
    def test_air_pocket_must_connect_to_the_current_player(self):
        rows=[row([0,4,0],'dripstone_block')]+[row([1,y,z],'stone')for y in range(1,8)for z in range(-3,4)]
        self.assertEqual([],offers(rows,[-3,1,-3],[4,7,3],[3.5,4.2,.5]))
if __name__=='__main__':unittest.main()
