import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from material_client import MaterialClient,Handoff


class FakeClient(MaterialClient):
    def __init__(self,directory,health=18.9,food=20):
        self.root=self.out=Path(directory);self.remote_finish='guard'
        self.park_target=[1,110,2];self.owned_material_menu=None
        self.actions=[];self.calls=[];self.world='world';self.rev=1;self.heal=False;self.task='task';self.last='request'
        self.scan_blocks=[];self.navigate_phase='done'
        self.state={'health':health,'food':food,'pos':[1,67,2],
            'guard_armed':True,'guard_pve_only':True,'guard_busy':False,'entities':[],
            'flight':True,'time':100,'air_supply':300,
            'connected':True,'control_revision':1,'world_session':'world',
            'last_request':'request','phase':'done',
            'supervision_lease':{'kind':'materials','job_session':'task','revision':1},
            'server':'simpcraft.com','inventory':[{'slot':3,'item':'minecraft:cooked_porkchop','count':2}],
            'menu':{'id':0,'type':'InventoryMenu','cursor':{'count':0},'slots':[]}}
        client=self
        class Heartbeat:
            id='test';closed=False
            def close(self):
                self.closed=True
                (client.root/'supervision-receipt-test.json').write_text(json.dumps({'action':'KEEP_PVE_GUARD'}))
        self.heartbeat=Heartbeat()
    def advise(self,*args,**kwargs):return {'id':'test','choice':'wait'}
    def status(self):
        if not self.state.get('connected') or self.state.get('manual_movement'):
            raise Handoff('Control or world changed')
        return self.state.copy()
    def raw(self):return self.status()
    def request(self,op,**params):
        self.actions.append(op)
        self.calls.append((op,params))
        if (self.root/'material-health-hold.json').exists():
            raise AssertionError('The escape/logout must finish before the hold blocks requests')
        if op=='scan':
            low,high=params['min'],params['max']
            return {'world_session':self.world,'blocks':[row for row in self.scan_blocks
                    if all(low[i]<=row['pos'][i]<=high[i] for i in range(3))]}
        if op=='navigate':
            if self.navigate_phase=='done':
                self.state['pos']=params['target']
                if self.state.get('under_water') and params['target'][1]>=70:
                    self.state['under_water']=False;self.state['air_supply']=300
            return {'phase':self.navigate_phase}
        if op=='use_item':
            self.state['food']=20
            if self.heal:self.state['health']=20
        return {'phase':'done'}


class MaterialHealthExitTest(unittest.TestCase):
    def finish(self,client):
        # Advance bounded recovery without slowing the regression suite.
        with patch('material_cleanup.run',return_value=[]),patch('craft_recovery.clear_owned_workbench'),patch('material_client.time.sleep'),patch('material_client.time.monotonic',side_effect=range(0,10000,10)):
            client.finish()

    def test_minor_injury_rises_and_stays_guarded_without_logout_or_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory)
            self.finish(client)
            self.assertEqual(['scan','navigate'],client.actions)
            self.assertTrue(client.heartbeat.closed)
            self.assertFalse((client.root/'material-health-hold.json').exists())
            self.assertTrue((client.out/'stock-safety.json').exists())

    def test_dry_y63_paving_hole_routes_to_high_park_without_water_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.state.update(pos=[1,63.15,2],under_water=False,air_supply=300)
            self.finish(client)
            self.assertEqual([entry[0] for entry in client.calls],['scan','navigate'])
            self.assertEqual(client.calls[1][1]['target'],[1,110,2])
            self.assertTrue(client.calls[1][1]['air_only'])
            self.assertTrue((client.out/'stock-safety.json').exists())
            self.assertFalse((client.out/'park-fallback.json').exists())

    def test_distant_high_park_is_reached_by_vertical_then_horizontal_air_only_legs(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.park_target=[10.5,110,20.5]
            self.finish(client)
            self.assertEqual(['scan','navigate','navigate'],client.actions)
            self.assertEqual(client.calls[1][1]['target'],[1,110,2])
            self.assertEqual(client.calls[2][1]['target'],client.park_target)
            self.assertTrue(client.calls[1][1]['air_only'] and client.calls[2][1]['air_only'])
            self.assertTrue((client.out/'stock-safety.json').exists())

    def test_unconfirmed_vertical_arrival_never_retries_or_starts_horizontal_leg(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.park_target=[10.5,110,20.5];client.navigate_phase='waiting'
            self.finish(client)
            self.assertEqual(['scan','navigate','safe_logout'],client.actions)
            fallback=json.loads((client.out/'park-fallback.json').read_text())
            self.assertEqual(fallback['action'],'safe_logout')
            self.assertGreaterEqual(fallback['elapsed_seconds'],0)

    def test_disconnect_after_vertical_leg_never_retries_or_starts_horizontal_leg(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.park_target=[10.5,110,20.5]
            original=client.request
            def request(op,**params):
                reply=original(op,**params)
                if op=='navigate':client.state['connected']=False
                return reply
            client.request=request
            self.finish(client)
            self.assertEqual(['scan','navigate'],client.actions)
            self.assertTrue(client.heartbeat.closed)

    def test_manual_takeover_after_column_scan_sends_no_movement_or_logout(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.park_target=[10.5,110,20.5]
            original=client.request
            def request(op,**params):
                reply=original(op,**params)
                if op=='scan':client.state['manual_movement']=True
                return reply
            client.request=request
            self.finish(client)
            self.assertEqual(['scan'],client.actions)
            self.assertTrue(client.heartbeat.closed)

    def test_verified_natural_ground_can_exit_a_leaf_canopy_before_rising(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.state['pos']=[.5,64,.5];client.park_target=[10.5,110,20.5]
            client.scan_blocks=[{'pos':[x,63,z],'state':'Block{minecraft:grass_block}',
                                 'solid':True,'passable':False,'fluid':False,'block_entity':False}
                                for x in range(-4,5) for z in range(-4,5)]
            client.scan_blocks += [{'pos':[x,68,z],'state':'Block{minecraft:oak_leaves}',
                                    'solid':True,'passable':False,'fluid':False,'block_entity':False}
                                   for x in range(-1,2) for z in range(-1,2)]
            with patch('material_cleanup.run',return_value=[]),patch('craft_recovery.clear_owned_workbench'):
                client._finish()
            actions=client.actions
            self.assertEqual(actions[:2],['scan','scan'])
            self.assertEqual(actions.count('navigate'),4)
            self.assertEqual(actions[-3], 'scan')
            navigations=[params for op,params in client.calls if op=='navigate']
            self.assertEqual(navigations[2]['target'][::2],navigations[1]['target'][::2])
            self.assertEqual(navigations[3]['target'],client.park_target)
            self.assertTrue(all(entry['air_only'] for entry in navigations))
            receipt=json.loads((client.out/'park-canopy-route.json').read_text())
            self.assertTrue(receipt['confirmed'])
            self.assertEqual(receipt['new_step_initiation_budget_seconds'],12)
            self.assertGreaterEqual(receipt['elapsed_seconds'],0)
            self.assertFalse((client.out/'park-fallback.json').exists())

    def test_leaf_canopy_near_hostile_or_busy_guard_never_starts_lateral_movement(self):
        for change in ({'guard_busy':True},
                       {'entities':[{'type':'minecraft:zombie','hostile':True,'pos':[1.5,64,.5]}]}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as directory:
                client=FakeClient(directory,health=20)
                client.state['pos']=[.5,64,.5]
                if 'entities' in change:client.state.update(change)
                client.scan_blocks=[{'pos':[x,63,z],'state':'Block{minecraft:stone_bricks}',
                                     'solid':True,'passable':False,'fluid':False,'block_entity':False}
                                    for x in range(-4,5) for z in range(-4,5)]
                client.scan_blocks += [{'pos':[0,68,0],'state':'Block{minecraft:oak_leaves}',
                                        'solid':True,'passable':False,'fluid':False,'block_entity':False}]
                if 'guard_busy' in change:
                    original=client.request;scans=[0]
                    def request(op,**params):
                        reply=original(op,**params)
                        if op=='scan':
                            scans[0]+=1
                            if scans[0]==2:client.state['guard_busy']=True
                        return reply
                    client.request=request
                self.finish(client)
                self.assertEqual(client.actions,['scan','scan','safe_logout'])

    def test_critical_health_never_enters_canopy_route_and_caps_straight_ascent_to_eight_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=13)
            self.finish(client)
            self.assertEqual(client.actions,['scan','navigate','safe_logout'])
            self.assertEqual(client.calls[1][1]['seconds'],8)
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=13)
            client.scan_blocks=[{'pos':[1,68,2],'state':'Block{minecraft:oak_leaves}',
                                 'solid':True,'passable':False,'fluid':False,'block_entity':False}]
            self.finish(client)
            self.assertEqual(client.actions,['scan','safe_logout'])

    def test_underwater_low_air_still_surfaces_before_high_park(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.state.update(pos=[1,52,2],under_water=True,air_supply=25)
            self.finish(client)
            self.assertEqual([entry[0] for entry in client.calls],['navigate','scan','navigate'])
            self.assertEqual(client.calls[0][1]['target'],[1,70,2])
            self.assertTrue(client.calls[2][1]['air_only'])
            self.assertTrue((client.out/'stock-safety.json').exists())

    def test_minor_injury_eats_available_food_then_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,food=18);client.heal=True
            self.finish(client)
            self.assertEqual(['scan','navigate','use_item'],client.actions)
            self.assertEqual(20,client.state['health'])
            self.assertFalse((client.root/'material-health-hold.json').exists())

    def test_moderate_injury_may_recover_before_parking(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=16,food=18);client.heal=True
            self.finish(client)
            self.assertEqual(['scan','navigate','use_item'],client.actions)
            self.assertTrue((client.out/'stock-safety.json').exists())

    def test_critical_health_ascends_logs_out_and_persists_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=13)
            self.finish(client)
            self.assertEqual(['scan','navigate','safe_logout'],client.actions)
            self.assertTrue(client.heartbeat.closed)
            hold=json.loads((client.root/'material-health-hold.json').read_text())
            self.assertTrue(hold['active']);self.assertEqual(13,hold['health'])

    def test_failed_moderate_recovery_still_exits_with_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=16)
            self.finish(client)
            self.assertEqual(['scan','navigate','safe_logout'],client.actions)
            self.assertTrue(json.loads((client.root/'material-health-hold.json').read_text())['active'])

    def test_recovery_yields_to_manual_takeover(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory);client.state['pos']=[1,110,2]
            with patch.object(client,'status',side_effect=Handoff('manual')):
                with self.assertRaises(Handoff):client.recover_park_health()
            self.assertEqual([],client.actions)

if __name__=='__main__':unittest.main()
