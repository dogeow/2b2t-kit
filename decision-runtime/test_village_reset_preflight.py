import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from village_queue import VillageQueue


class ResetPreflightTests(unittest.TestCase):
    def fixture(self, directory, change=None):
        root = Path(directory)
        q = VillageQueue.__new__(VillageQueue)
        q.out = root / 'owner'
        q.out.mkdir()
        q.world = 'w'
        q.lease = {'job_session':'task'}
        q.closing_menu = None
        state = {'world_session':'w', 'screen':'', 'hand':{'item':'minecraft:diamond_axe'},
                 'loaded_villagers':{'villagers':[{'uuid':'resident','is_baby':False,'pos':[1.5,64,1.5]}]}}
        gate = {'world_session':'w', 'adult_assignment_bounds':{
            'resident':{'min':[1,64,1], 'max_exclusive':[2,67,4]}},
            'shared_adult_bounds':{}, 'new_workstations_prohibited_until_gate_passes':True,
            'all_contained_verified':True}
        if change == 'world': gate['world_session'] = 'old'
        if change == 'unverified': gate['all_contained_verified'] = False
        if change == 'new_adult':
            state['loaded_villagers']['villagers'].append({'uuid':'grown','is_baby':False,'pos':[3,64,3]})
        config = {'workstation_installation_gate':gate,
                  'active_village_bounds':{'min':[0,63,0], 'max':[10,70,10]}}
        (root/'project-state.json').write_text(json.dumps(config))
        q.status = lambda **kw: state
        q._dispatch = Mock(return_value={'phase':'done'})
        return q

    def test_reset_is_blocked_before_command_or_native_mining_is_queued(self):
        for change in ('world','unverified','new_adult'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                q = self.fixture(directory, change)
                with self.assertRaises(RuntimeError):
                    q._send('native',op='mine_block',params={'pos':[1,64,0],'reset_empty_lectern':True})
                q._dispatch.assert_not_called()
                self.assertFalse((q.out/'command.json').exists())

    def test_verified_reset_reaches_existing_dispatch_and_native_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            q = self.fixture(directory)
            q._send('native',op='mine_block',params={'pos':[1,64,0],'reset_empty_lectern':True})
            q._dispatch.assert_called_once()

    def test_ordinary_roof_or_bed_recovery_stays_available_while_assigning_residents(self):
        with tempfile.TemporaryDirectory() as directory:
            q = self.fixture(directory,'unverified')
            q._send('native',op='mine_block',params={'pos':[1,67,2]})
            q._dispatch.assert_called_once()
