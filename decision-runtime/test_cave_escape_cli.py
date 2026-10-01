"""Offline cave fixture: the old scan only models obstacles, never authorizes a live move."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cave_escape_cli import (EscapeBlocked, FinishUnverified, PARK, SERVER, SHAFT,
                             _await_clear, _near_actor, execute, main, plan,
                             verify_guard_finish)
from material_client import Handoff


def block(x,y,z,name='stone'):
    return {'pos':[x,y,z],'state':f'Block{{minecraft:{name}}}',
            'passable':False,'solid':True,'fluid':False,'block_entity':False}


class FixtureClient:
    world='fresh-world-session'
    def __init__(self,out):
        self.out=Path(out);self.root=self.out;self.last=None;self.serial=0;self.actions=[]
        self.state={'connected':True,'server':SERVER,'dimension':'minecraft:overworld',
                    'world_session':self.world,'pos':[760969.683,31.0,797907.70],
                    'health':20,'food':20,'safety_hold':{'active':False},'under_water':False,
                    'screen':'','manual_movement':False,'guard_armed':True,'guard_pve_only':True,
                    'guard_busy':False,'air_only_navigation_protocol':2,'entities':[],
                    'flight':False,'on_ground':True}
        # The 2026-09-28 pocket had a stone floor at the player's body, a
        # roof above the original column, and an open western shaft. Other
        # space is kept sparse to test fail-closed native scan handling.
        self.rows=[block(760969,30,797907),block(760969,30,797908),
                   block(760969,35,797907,'andesite')]
        self.navigate_phase='done';self.on_navigate=None;self.on_scan=None
        self.status_hook=None
    def status(self):
        if self.status_hook:self.status_hook(self)
        if self.state['manual_movement']:raise Handoff('Fixture player took over')
        return copy.deepcopy(self.state)
    def request(self,op,**params):
        self.actions.append((op,copy.deepcopy(params)))
        self.serial+=1;self.last='materials-fixture-'+str(self.serial)
        if op=='scan':
            low,high=params['min'],params['max']
            result={'id':self.last,'world_session':self.world,
                    'blocks':[copy.deepcopy(row) for row in self.rows
                              if all(low[i]<=row['pos'][i]<=high[i] for i in range(3))]}
            if self.on_scan:self.on_scan(self)
            return result
        if op=='navigate':
            if self.navigate_phase=='done':
                self.state['pos']=list(params['target']);self.state['flight']=True
                self.state['on_ground']=False
            if self.on_navigate:self.on_navigate(self)
            return {'phase':self.navigate_phase,'detail':'fixture result'}
        raise AssertionError('No excavation, placement, teleport or other action is allowed: '+op)


class CaveEscapeTests(unittest.TestCase):
    def test_fresh_plan_routes_west_under_the_old_roof_and_then_ascends_only_at_open_shaft(self):
        with tempfile.TemporaryDirectory() as folder:
            c=FixtureClient(folder)
            itinerary=plan(c)
            self.assertEqual(itinerary['start'],c.state['pos'])
            self.assertEqual(itinerary['shaft'],list(SHAFT))
            self.assertEqual(itinerary['park'],PARK)
            self.assertEqual(itinerary['turns'][0],[760969.5,31.0,797907.5])
            self.assertEqual(itinerary['turns'][-1],[760957.5,31.0,797900.5])
            self.assertLessEqual(len(itinerary['turns']),12)
            self.assertEqual(['scan','scan'],[op for op,_ in c.actions])

    def test_one_shot_exec_uses_only_fresh_scanned_air_only_moves_and_verifies_high_park(self):
        with tempfile.TemporaryDirectory() as folder,patch('cave_escape_cli.settled_state',side_effect=lambda c,*a,**k:c.status()):
            c=FixtureClient(folder)
            moves=execute(c,Path(folder))
            navigation=[params for op,params in c.actions if op=='navigate']
            self.assertTrue(navigation)
            self.assertTrue(all(p['air_only'] is True for p in navigation))
            self.assertTrue(all(op in ('scan','navigate') for op,_ in c.actions))
            self.assertEqual(navigation[0]['target'],[760969.683,31.0,797907.70])
            self.assertEqual(moves[0]['actual'],[760969.683,31.0,797907.70])
            self.assertEqual(navigation[-1]['target'],PARK)
            self.assertEqual(c.state['pos'],PARK)
            self.assertTrue(json.loads((Path(folder)/'cave-escape-receipt.json').read_text())['confirmed'])
            self.assertTrue(all(row['phase']=='done' for row in moves))

    def test_new_stone_in_open_shaft_stops_before_horizontal_motion(self):
        with tempfile.TemporaryDirectory() as folder:
            c=FixtureClient(folder);c.rows.append(block(SHAFT[0],50,SHAFT[1]))
            with self.assertRaisesRegex(EscapeBlocked,'shaft'):
                plan(c)
            self.assertFalse(any(op=='navigate' for op,_ in c.actions))

    def test_changed_manual_scope_after_first_move_never_starts_a_second_move(self):
        with tempfile.TemporaryDirectory() as folder,patch('cave_escape_cli.settled_state',side_effect=lambda c,*a,**k:c.status()):
            c=FixtureClient(folder)
            c.on_navigate=lambda client:client.state.update(manual_movement=True)
            with self.assertRaises(Handoff):execute(c,Path(folder))
            self.assertEqual(1,sum(op=='navigate' for op,_ in c.actions))

    def test_uncertain_native_move_is_not_replayed_or_treated_as_settled(self):
        with tempfile.TemporaryDirectory() as folder,patch('cave_escape_cli.settled_state',side_effect=AssertionError('No settlement on waiting')):
            c=FixtureClient(folder);c.navigate_phase='waiting'
            with self.assertRaisesRegex(EscapeBlocked,'no retry'):
                execute(c,Path(folder))
            self.assertEqual(1,sum(op=='navigate' for op,_ in c.actions))
            self.assertEqual(next(p['target'] for op,p in c.actions if op=='navigate'),
                             [760969.683,31.0,797907.70])

    def test_low_health_aborts_before_a_scan_or_motion(self):
        with tempfile.TemporaryDirectory() as folder:
            c=FixtureClient(folder);c.state['health']=13
            with self.assertRaises(EscapeBlocked):plan(c)
            self.assertEqual([],c.actions)

    def test_guard_clears_hostile_before_original_route_is_freshly_scanned(self):
        with tempfile.TemporaryDirectory() as folder,patch('cave_escape_cli.time.sleep'):
            c=FixtureClient(folder);calls=[]
            c.state['entities']=[{'type':'minecraft:zombie','pos':[760970,31,797907],
                                  'hostile':True}]
            def defend(client):
                calls.append(len(client.actions))
                if len(calls)==3:client.state['entities']=[]
            c.status_hook=defend
            itinerary=plan(c)
            self.assertEqual(itinerary['shaft'],list(SHAFT))
            self.assertEqual(calls[:3],[0,0,0])
            self.assertFalse(any(op=='navigate' for op,_ in c.actions))
            self.assertTrue((Path(folder)/'cave-escape-combat.jsonl').exists())

    def test_combat_after_scan_discards_that_scan_before_using_the_same_route(self):
        with tempfile.TemporaryDirectory() as folder,patch('cave_escape_cli.time.sleep'):
            c=FixtureClient(folder);busy=[]
            def interrupt_after_first_scan(client):
                if sum(op=='scan' for op,_ in client.actions)==1:
                    client.state['guard_busy']=True
                    client.state['entities']=[{'type':'minecraft:skeleton',
                         'pos':[760970,31,797907],'hostile':True}]
            def clear_on_guard_status(client):
                if client.state['guard_busy']:
                    busy.append(1)
                    if len(busy)==2:
                        client.state['guard_busy']=False;client.state['entities']=[]
            c.on_scan=interrupt_after_first_scan;c.status_hook=clear_on_guard_status
            itinerary=plan(c)
            self.assertEqual(itinerary['shaft'],list(SHAFT))
            self.assertEqual(3,sum(op=='scan' for op,_ in c.actions))
            self.assertFalse(any(op=='navigate' for op,_ in c.actions))

    def test_guard_timeout_and_dropped_health_do_not_start_moving(self):
        with tempfile.TemporaryDirectory() as folder,patch('cave_escape_cli.time.sleep'):
            c=FixtureClient(folder)
            c.state['entities']=[{'type':'minecraft:skeleton','pos':[760970,31,797907],
                                  'hostile':True}]
            with self.assertRaisesRegex(EscapeBlocked,'did not clear'):
                _await_clear(c,first=True,seconds=0)
            self.assertEqual([],c.actions)
            c.status_hook=lambda client:client.state.update(health=13)
            with self.assertRaisesRegex(EscapeBlocked,'not ready'):
                _await_clear(c,first=True,seconds=1)
            self.assertEqual([],c.actions)

    def test_minor_damage_continues_and_moderate_damage_waits_for_guarded_recovery(self):
        with tempfile.TemporaryDirectory() as folder,patch('cave_escape_cli.time.sleep'):
            c=FixtureClient(folder);c.state['health']=18
            self.assertFalse(_await_clear(c,first=True,seconds=0)[1])
            c.state['health']=16
            calls=[]
            def recover(client):
                calls.append(len(client.actions))
                if len(calls)==3:client.state['health']=18
            c.status_hook=recover
            state,waited=_await_clear(c,first=True,seconds=1)
            self.assertTrue(waited)
            self.assertEqual(state['health'],18)
            self.assertEqual(calls[:3],[0,0,0])

    def test_manual_takeover_during_guard_combat_yields_without_motion(self):
        with tempfile.TemporaryDirectory() as folder,patch('cave_escape_cli.time.sleep'):
            c=FixtureClient(folder);c.state['guard_busy']=True
            calls=[]
            def take_over(client):
                calls.append(1)
                if len(calls)==2:client.state['manual_movement']=True
            c.status_hook=take_over
            with self.assertRaises(Handoff):_await_clear(c,first=True,seconds=1)
            self.assertEqual([],c.actions)

    def test_entity_in_middle_of_leg_blocks_it_despite_clear_endpoints(self):
        state={'entities':[{'type':'minecraft:cow','pos':[4.5,31,0.5],
                            'hostile':False}]}
        with self.assertRaisesRegex(EscapeBlocked,'near the next'):
            _near_actor(state,[.5,31,.5],[8.5,31,.5])

    def test_finish_accepts_native_released_lease_only_with_owned_receipt_and_safe_state(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);client=SimpleNamespace(root=out,out=out,world='fresh-world-session',
                task='cave-job',heartbeat=SimpleNamespace(id='materials-cave'))
            good={'action':'KEEP_PVE_GUARD','lease':'materials-cave','job_session':'cave-job'}
            state=FixtureClient(out).state
            state.update(world_session=client.world,pos=list(PARK),flight=True,on_ground=False,
                         supervision_lease=None,time=1234)
            (out/'stock-safety.json').write_text(json.dumps(good))
            with patch('cave_escape_cli.read_fresh',return_value=state):
                verify_guard_finish(client,out)
            self.assertTrue(json.loads((out/'cave-escape-guard-verified.json').read_text())['confirmed'])
            for bad_receipt,bad_state in (
                    ({**good,'lease':'other'},state),
                    ({**good,'action':'LOGOUT'},state),
                    (good,{**state,'world_session':'another-world'}),
                    (good,{**state,'health':17}),
                    (good,{**state,'guard_armed':False}),
                    (good,{**state,'screen':'InventoryScreen'}),
                    (good,{**state,'under_water':True}),
                    (good,{**state,'entities':[{'type':'minecraft:zombie',
                          'pos':[760957,145,797900],'hostile':True}]}),
                    (good,{**state,'supervision_lease':{'id':'someone-else','kind':'parking'}})):
                (out/'stock-safety.json').write_text(json.dumps(bad_receipt))
                with self.subTest(bad_receipt=bad_receipt,bad_state=bad_state), \
                        patch('cave_escape_cli.read_fresh',return_value=bad_state), \
                        self.assertRaises(FinishUnverified):
                    verify_guard_finish(client,out)

    def test_main_rejects_active_foreign_work_before_constructing_material_client(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);state=FixtureClient(base).state
            state['professional_printer']={'enabled':True}
            with patch('cave_escape_cli.read_fresh',return_value=state), \
                    patch('cave_escape_cli.MaterialClient',side_effect=AssertionError('must not create client')):
                with self.assertRaises(EscapeBlocked):
                    main(['--root',str(base),'--out',str(base/'new'),'--execute'])

    def test_main_rejects_nonempty_prior_run_before_reading_game_state(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);out=base/'old';out.mkdir();(out/'plan.json').write_text('{}')
            with patch('cave_escape_cli.read_fresh',side_effect=AssertionError('must not read game')), \
                    self.assertRaisesRegex(EscapeBlocked,'already contains'):
                main(['--root',str(base),'--out',str(out),'--execute'])

    def test_finish_logout_receipt_returns_unverified_without_second_logout(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);out=base/'new';initial=FixtureClient(base).state
            def finish():
                (out/'stock-safety.json').write_text(json.dumps({
                    'action':'LOGOUT','lease':'materials-cave','job_session':'cave-job'}))
            fake=SimpleNamespace(root=base,out=out,world='fresh-world-session',task='cave-job',
                heartbeat=SimpleNamespace(id='materials-cave'),finish=finish,
                request=lambda *a,**k:(_ for _ in ()).throw(AssertionError('no second logout')))
            with patch('cave_escape_cli.read_fresh',return_value=initial), \
                    patch('cave_escape_cli.MaterialClient',return_value=fake), \
                    patch('cave_escape_cli.execute',return_value=[]):
                self.assertEqual(2,main(['--root',str(base),'--out',str(out),'--execute']))
            self.assertEqual(json.loads((out/'cave-escape-failed.json').read_text())['action'],
                             'finish_unverified_no_replay')


if __name__=='__main__':unittest.main()
