import unittest
from unittest.mock import patch
from container_access import OutdoorChestChanged, open_grounded_chest,open_chest_from_pose
from copy import deepcopy
from unittest.mock import Mock


class FakeClient:
    def __init__(self, clock, blocked=False):
        self.clock=clock;self.blocked=blocked;self.opened_at=None;self.actions=[]
    def status(self):return {'hand':{'item':'minecraft:diamond_sword'}}
    def checked(self,op,**params):
        self.actions.append((op,params))
        if op=='interact':self.opened_at=self.clock[0]
        return {'phase':'done'}
    def request(self,op,**params):
        if op=='scan':
            rows=[{'pos':[1,64,2],'state':'Block{minecraft:chest}[facing=south]'}]
            if self.blocked:rows.append({'pos':[1,66,2],'state':'Block{minecraft:stone}'})
            return {'blocks':rows}
        opened=self.opened_at is not None and self.clock[0]-self.opened_at>=6
        return {'health':20,'on_ground':True,'velocity':[0,0,0],
                'menu':{'type':'ChestMenu' if opened else 'InventoryMenu','id':7,'cursor':{'count':0},
                        'slots':[{'item':'minecraft:stone','count':1}]+[{'count':0} for _ in range(36)]}}


class ContainerAccessTest(unittest.TestCase):
    def indoor_client(self):
        pose=[1.5,65,5.5];pos=[1,66,2]
        state={'world_session':'w','control_revision':7,'connected':True,'pos':pose,'velocity':[0,0,0],
               'flight':False,'on_ground':True,'under_water':False,'manual_movement':False,'screen':'',
               'health':20,'guard_busy':False,'guard_armed':True,'guard_pve_only':True,
               'hand':{'item':'minecraft:diamond_sword'},
               'supervision_lease':{'kind':'materials','world_session':'w','job_session':'t','revision':7},
               'menu':{'id':0,'type':'InventoryMenu','cursor':{'count':0}}}
        scan={'phase':'done','world_session':'w','control_revision':7,'scan_start_revision':7,'scan_end_revision':7,
              'scan_cells_read':1,'scan_total_cells':1,'blocks':[{'pos':pos,'state':'Block{minecraft:chest}[facing=south]','fluid':False}]}
        client=Mock();client.world='w';client.task='t';client.rev=7;client.status.side_effect=lambda:deepcopy(state)
        client.request.return_value=scan
        return client,state,scan,pos,pose

    def test_indoor_chest_opens_only_from_registered_grounded_pose_without_navigation(self):
        c,s,scan,pos,pose=self.indoor_client();opened={'menu':{'id':8,'type':'ChestMenu','cursor':{'count':0}}}
        with patch('container_access.wait_container_contents',return_value=opened)as wait, \
             patch('container_access.verify_opened_chest')as verify,patch('material_storage_index.bind_source')as bind:
            result=open_chest_from_pose(c,pos,pose,'south',allow_empty=True)
        c.checked.assert_called_once_with('interact',pos=pos,face='south',
             expected_state='Block{minecraft:chest}[facing=south]',expected_hand='minecraft:diamond_sword')
        wait.assert_called_once_with(c,'ChestMenu',require_nonempty=False)
        verify.assert_called_once_with(c,result['_verified_chest']);bind.assert_called_once_with(c,opened,pos,'minecraft:chest')

    def test_indoor_chest_refuses_flying_drifting_foreign_or_player_ui_before_scan_or_interaction(self):
        for change in ({'flight':True},{'pos':[1.5,66,5.5]},
                       {'pos':[float('nan'),65,5.5]},{'manual_movement':True},{'screen':'InventoryScreen'},
                       {'guard_busy':True},{'health':18},{'world_session':'other'}):
            with self.subTest(change=change):
                c,s,scan,pos,pose=self.indoor_client();s.update(change)
                with self.assertRaises(RuntimeError):open_chest_from_pose(c,pos,pose,'south')
                c.checked.assert_not_called();c.request.assert_not_called()

    def test_indoor_chest_observes_bounded_ground_settle_without_moving_or_opening_early(self):
        c,s,scan,pos,pose=self.indoor_client();clock=[0.0];s.update(on_ground=False,velocity=[.04,0,0])
        def observe(op,**params):
            if op=='snapshot':s.update(on_ground=True,velocity=[0,0,0]);return deepcopy(s)
            return scan
        c.request.side_effect=observe
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)), \
             patch('container_access.wait_container_contents',return_value={'menu':{'id':8}}), \
             patch('container_access.verify_opened_chest'),patch('material_storage_index.bind_source'):
            open_chest_from_pose(c,pos,pose,'south')
        self.assertEqual('snapshot',c.request.call_args_list[0].args[0]);self.assertEqual(1,c.checked.call_count)
        self.assertEqual('interact',c.checked.call_args.args[0])

    def test_indoor_chest_unsettled_pose_times_out_without_interaction(self):
        c,s,scan,pos,pose=self.indoor_client();clock=[0.0];s.update(on_ground=False,velocity=[.04,0,0])
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
            with self.assertRaises(RuntimeError):open_chest_from_pose(c,pos,pose,'south')
        self.assertGreaterEqual(clock[0],4);c.checked.assert_not_called()

    def test_indoor_chest_incomplete_changed_or_wet_scan_never_interacts(self):
        for change in ('waiting','unloaded','foreign','changed','wet'):
            with self.subTest(change=change):
                c,s,scan,pos,pose=self.indoor_client()
                if change=='waiting':scan['phase']='waiting'
                elif change=='unloaded':scan['scan_cells_read']=0
                elif change=='foreign':scan['scan_end_revision']=8
                elif change=='changed':scan['blocks'][0]['state']='Block{minecraft:air}'
                else:scan['blocks'][0]['fluid']=True
                with self.assertRaises(RuntimeError):open_chest_from_pose(c,pos,pose,'south')
                c.checked.assert_not_called()

    def test_indoor_chest_bad_registration_never_reads_or_interacts(self):
        c,s,scan,pos,pose=self.indoor_client()
        for point,stand,face in ([pos,[True,65,5.5],'south'],[pos,pose,'up'],[[True,66,2],pose,'south']):
            with self.assertRaises(ValueError):open_chest_from_pose(c,point,stand,face)
        c.checked.assert_not_called();c.request.assert_not_called()

    def test_owned_high_chest_approach_uses_verified_air_descent_before_supply_route(self):
        clock=[0.0];client=FakeClient(clock);client.task='task';client.world='world'
        client.status=lambda:{'hand':{'item':'minecraft:diamond_sword'},'pos':[1.5,85,2.5],
            'air_only_navigation_protocol':2,'supervision_lease':{'kind':'materials','job_session':'task','world_session':'world'}}
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
                patch('container_access.time.sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)), \
                patch('material_jobs.navigation.settled_state')as settled:
            open_grounded_chest(client,[1,64,2])
        self.assertEqual(['navigate','navigate','approach_block','walk','interact'],[op for op,_ in client.actions])
        self.assertEqual([1.5,65.8,2.5],client.actions[1][1]['target'])
        self.assertTrue(all(client.actions[n][1]['air_only']for n in (0,1)))
        settled.assert_called_once_with(client,[1.5,65.8,2.5],.4)

    def test_unknown_precise_descent_never_opens_or_repeats_the_chest(self):
        client=FakeClient([0]);client.task='task';client.world='world'
        client.status=lambda:{'hand':{'item':'minecraft:diamond_sword'},'pos':[1.5,85,2.5],
            'air_only_navigation_protocol':2,'supervision_lease':{'kind':'materials','job_session':'task','world_session':'world'}}
        def checked(op,**params):
            client.actions.append((op,params))
            if len(client.actions)==2:raise RuntimeError('unknown descent')
            return {'phase':'done'}
        client.checked=checked
        with self.assertRaisesRegex(RuntimeError,'unknown descent'):open_grounded_chest(client,[1,64,2])
        self.assertEqual(['navigate','navigate'],[op for op,_ in client.actions])

    def test_open_menu_waits_for_delayed_item_contents(self):
        clock=[0.0]
        class DelayedContents(FakeClient):
            def request(self,op,**params):
                result=super().request(op,**params)
                if op=='snapshot' and self.opened_at is not None and clock[0]-self.opened_at<9:
                    result['menu']['slots']=[{'count':0} for _ in range(63)]
                return result
        client=DelayedContents(clock)
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda duration:clock.__setitem__(0,clock[0]+duration)):
            result=open_grounded_chest(client,[1,64,2])
        self.assertGreaterEqual(clock[0],10)
        self.assertEqual(1,result['menu']['slots'][0]['count'])

    def test_late_server_open_is_awaited_without_leaving_the_chest(self):
        clock=[0.0];client=FakeClient(clock)
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda duration:clock.__setitem__(0,clock[0]+duration)):
            result=open_grounded_chest(client,[1,64,2])
        self.assertEqual('ChestMenu',result['menu']['type'])
        self.assertEqual({'pos':[1,64,2],'state':'Block{minecraft:chest}[facing=south]'},
                         result['_verified_chest'])
        self.assertEqual(7,client.owned_material_menu)
        self.assertEqual(['approach_block','walk','interact'],[name for name,_ in client.actions])
        self.assertFalse(client.actions[1][1]['restore_flight'])
        self.assertEqual(.65,client.actions[0][1]['stand_distance'])

    def test_obstructed_landing_is_rejected_before_movement(self):
        client=FakeClient([0],blocked=True)
        with self.assertRaisesRegex(RuntimeError,'obstructed'):open_grounded_chest(client,[1,64,2])
        self.assertEqual([],client.actions)

    def test_registered_chest_changed_records_exact_scan_without_approach(self):
        client=FakeClient([0])
        rows=[{'pos':[1,64,2],'state':'Block{minecraft:air}'},
              {'pos':[1,65,2],'state':'Block{minecraft:air}'}]
        client.request=lambda op,**params:{'blocks':rows}
        with self.assertRaises(OutdoorChestChanged) as caught:
            open_grounded_chest(client,[1,64,2])
        self.assertEqual({'pos':[1,64,2],'expected_block':'minecraft:chest',
                          'observed_state':'Block{minecraft:air}',
                          'scan':{'min':[1,64,2],'max':[1,70,2],'blocks':rows}},
                         caught.exception.evidence)
        self.assertEqual([],client.actions)

    def test_explicit_inventory_sweep_accepts_a_stable_empty_chest(self):
        clock=[0.0]
        class EmptyChest(FakeClient):
            def request(self,op,**params):
                result=super().request(op,**params)
                if op=='snapshot':result['menu']['slots']=[{'count':0} for _ in range(63)]
                return result
        client=EmptyChest(clock)
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda duration:clock.__setitem__(0,clock[0]+duration)):
            result=open_grounded_chest(client,[1,64,2],allow_empty=True)
        self.assertEqual('ChestMenu',result['menu']['type']);self.assertGreaterEqual(clock[0],7)
        self.assertEqual(0,sum(row['count'] for row in result['menu']['slots']))
