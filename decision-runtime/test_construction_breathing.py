import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.construction_breathing import interrupt_submerged, vertical_air_target
from material_jobs.protocol import JobBlocked, JobPaused


class Client:
    def __init__(self, root):
        self.root=self.out=Path(root);self.world='w';self.task='task';self.rev=3;self.last='original'
        self.heartbeat=SimpleNamespace(id='lease');self.calls=[];self.bad_move=False;self.manual_after_pause=False
        self.state={'connected':True,'world_session':'w','control_revision':3,'pos':[1.5,59.,3.5],
                    'health':20,'air_supply':280,'under_water':True,'oxygen_bonus':3,
                    'auto_log':True,'flight':True,'air_return_protocol':1,
                    'build_job':{'active':True,'session':'build'},
                    'supervision_lease':{'kind':'materials','job_session':'task','id':'lease',
                                         'world_session':'w','revision':3}}
        self.scan={'phase':'done','world_session':'w','scan_cells_read':14,
                   'blocks':[{'pos':[1,y,3],'state':'Block{minecraft:water}[level=0]',
                              'solid':False,'block_entity':False}for y in range(59,64)]}
    def status(self):return copy.deepcopy(self.state)
    def checked(self,op,**kw):
        result=self.request(op,**kw)
        if result.get('phase')!='done':raise JobBlocked('unconfirmed native action')
        return result
    def request(self,op,**kw):
        self.calls.append((op,kw));self.last='r'+str(len(self.calls))
        if op=='build_control':
            self.state['build_job']['active']=False
            if self.manual_after_pause:self.state['manual_movement']=True
        elif op=='scan':return copy.deepcopy(self.scan)
        elif op=='navigate':
            if self.bad_move:return {'phase':'waiting'}
            self.state.update(pos=kw['target'],under_water=False,air_supply=280)
        return {'phase':'done'}


class BreathingTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.c=Client(self.temp.name)
    def run_guard(self):return interrupt_submerged(self.c,self.c.status(),self.c.out)
    def test_dry_state_does_not_send_any_action(self):
        self.c.state['under_water']=False
        self.assertFalse(self.run_guard());self.assertEqual([],self.c.calls)
    def test_exact_water_column_returns_before_oxygen_runs_out_without_replaying_build(self):
        with self.assertRaisesRegex(JobBlocked,'干燥位置'):self.run_guard()
        self.assertEqual(['build_control','scan','air_return_set','navigate'],[op for op,_ in self.c.calls])
        self.assertEqual([1.5,64.05,3.5],self.c.state['pos'])
        proof=json.loads((self.c.out/'construction-breathing.json').read_text())
        self.assertTrue(proof['dry_return_confirmed']);self.assertFalse(proof['resource_actions_replayed'])
        self.assertEqual(0,proof['goal_completion_credit'])
    def test_actual_tower_roof_cannot_be_used_as_an_escape_column(self):
        self.c.scan['blocks']=[row for row in self.c.scan['blocks'] if row['pos']!=[1,61,3]]
        self.c.scan['blocks'].append({'pos':[1,61,3],'state':'Block{minecraft:cobblestone_slab}[type=bottom,waterlogged=false]','solid':False})
        # A partial collision shape remains a roof even if solid=False.
        with patch('safety_interlock.record_material_health_exit')as hold:
            with self.assertRaisesRegex(JobBlocked,'没有已核验退路'):self.run_guard()
        self.assertEqual(['build_control','scan','safe_logout'],[op for op,_ in self.c.calls]);hold.assert_called_once()
    def test_low_air_never_waits_for_a_scan_or_attempts_new_navigation(self):
        self.c.state['air_supply']=240
        with patch('safety_interlock.record_material_health_exit'):
            with self.assertRaises(JobBlocked):self.run_guard()
        self.assertEqual(['build_control','safe_logout'],[op for op,_ in self.c.calls])
    def test_manual_owner_or_screen_is_never_closed_or_logged_out(self):
        for change in ({'manual_movement':True},{'screen':'ChatScreen'},
                       {'world_session':'different'},{'control_revision':4}):
            state={**self.c.status(),**change}
            with self.assertRaises(JobPaused):interrupt_submerged(self.c,state,self.c.out)
        self.assertEqual([],self.c.calls)
    def test_takeover_after_pause_prevents_scan_movement_and_logout(self):
        self.c.manual_after_pause=True
        with self.assertRaises(JobPaused):self.run_guard()
        self.assertEqual(['build_control'],[op for op,_ in self.c.calls])
    def test_unknown_navigation_is_not_retried_or_marked_as_a_dry_return(self):
        self.c.bad_move=True
        with self.assertRaisesRegex(JobBlocked,'尚未核验'):self.run_guard()
        self.assertEqual(1,sum(op=='navigate' for op,_ in self.c.calls))
        proof=json.loads((self.c.out/'construction-breathing.json').read_text())
        self.assertFalse(proof['dry_return_confirmed'])
    def test_unloaded_incomplete_or_foreign_scan_never_authorizes_navigation(self):
        for change in ({'phase':'waiting'},{'scan_cells_read':13},{'world_session':'foreign'}):
            self.assertIsNone(vertical_air_target(self.c.state['pos'],{**self.c.scan,**change},'w'))
    def test_bounding_body_corners_must_also_be_dry(self):
        scan=copy.deepcopy(self.c.scan);scan['scan_cells_read']=28
        scan['blocks'].append({'pos':[2,64,3],'state':'Block{minecraft:water}[level=0]','solid':False})
        self.assertEqual([1.8,65.05,3.5],vertical_air_target([1.8,59.,3.5],scan,'w'))
        # At x=1.8 the body also spans x=2, so first breathable row is 65.
        scan['blocks'].append({'pos':[2,66,3],'state':'Block{minecraft:stone}','solid':True})
        self.assertIsNone(vertical_air_target([1.8,59.,3.5],scan,'w'))


if __name__=='__main__':unittest.main()
