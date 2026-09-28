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
        self.state={'health':health,'food':food,'pos':[1,67,2],
            'guard_armed':True,'flight':True,'time':100,'air_supply':300,
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
    def status(self):return self.state.copy()
    def raw(self):return self.status()
    def request(self,op,**params):
        self.actions.append(op)
        self.calls.append((op,params))
        if (self.root/'material-health-hold.json').exists():
            raise AssertionError('The escape/logout must finish before the hold blocks requests')
        if op=='navigate':
            self.state['pos']=params['target']
            if self.state.get('under_water') and params['target'][1]>=70:
                self.state['under_water']=False;self.state['air_supply']=300
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
            self.assertEqual(['navigate'],client.actions)
            self.assertTrue(client.heartbeat.closed)
            self.assertFalse((client.root/'material-health-hold.json').exists())
            self.assertTrue((client.out/'stock-safety.json').exists())

    def test_dry_y63_paving_hole_routes_to_high_park_without_water_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.state.update(pos=[1,63.15,2],under_water=False,air_supply=300)
            self.finish(client)
            self.assertEqual([('navigate',{'target':[1,110,2],'arrival':2,'seconds':120})],client.calls)
            self.assertTrue((client.out/'stock-safety.json').exists())
            self.assertFalse((client.out/'park-fallback.json').exists())

    def test_underwater_low_air_still_surfaces_before_high_park(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=20)
            client.state.update(pos=[1,52,2],under_water=True,air_supply=25)
            self.finish(client)
            self.assertEqual([('navigate',{'target':[1,70,2],'arrival':1,'seconds':8}),
                              ('navigate',{'target':[1,110,2],'arrival':2,'seconds':120})],client.calls)
            self.assertTrue((client.out/'stock-safety.json').exists())

    def test_minor_injury_eats_available_food_then_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,food=18);client.heal=True
            self.finish(client)
            self.assertEqual(['navigate','use_item'],client.actions)
            self.assertEqual(20,client.state['health'])
            self.assertFalse((client.root/'material-health-hold.json').exists())

    def test_moderate_injury_may_recover_before_parking(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=16,food=18);client.heal=True
            self.finish(client)
            self.assertEqual(['navigate','use_item'],client.actions)
            self.assertTrue((client.out/'stock-safety.json').exists())

    def test_critical_health_ascends_logs_out_and_persists_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=13)
            self.finish(client)
            self.assertEqual(['navigate','safe_logout'],client.actions)
            self.assertTrue(client.heartbeat.closed)
            hold=json.loads((client.root/'material-health-hold.json').read_text())
            self.assertTrue(hold['active']);self.assertEqual(13,hold['health'])

    def test_failed_moderate_recovery_still_exits_with_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory,health=16)
            self.finish(client)
            self.assertEqual(['navigate','safe_logout'],client.actions)
            self.assertTrue(json.loads((client.root/'material-health-hold.json').read_text())['active'])

    def test_recovery_yields_to_manual_takeover(self):
        with tempfile.TemporaryDirectory() as directory:
            client=FakeClient(directory);client.state['pos']=[1,110,2]
            with patch.object(client,'status',side_effect=Handoff('manual')):
                with self.assertRaises(Handoff):client.recover_park_health()
            self.assertEqual([],client.actions)

if __name__=='__main__':unittest.main()
