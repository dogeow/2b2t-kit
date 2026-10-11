import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from material_jobs_backend import Backend
from material_jobs.protocol import fingerprint


class SmeltingRecoveryTravelTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);station=root/'0001-smelt';station.mkdir()
        self.positions=[[1,65,3],[4,65,3]]
        recipe={'recipe_id':'smelting/deepslate','source':'minecraft:cobbled_deepslate','output':'minecraft:deepslate'}
        self.inflight={'operation':'smelt','args':[recipe,53]}
        (root/'active-operation.json').write_text(json.dumps({'operation_fingerprint':fingerprint(self.inflight),'directory':str(station),'name':'smelt'}))
        manifest={'world_session':'w','target':53,**recipe,'positions':self.positions,'batches':[{'journal':'batch-0001.json','amount':49}]}
        (station/'smelting.json').write_text(json.dumps(manifest))
        self.ledger={'world_session':'w',**recipe,'amount':49,'complete':False,
                     'furnaces':[{'pos':p,'amount':n,'stage':'loaded','pending':None} for p,n in zip(self.positions,[25,24])]}
        self.journal=station/'batch-0001.json';self.journal.write_text(json.dumps(self.ledger))
        self.backend=Backend.__new__(Backend);self.backend.out=root
        self.backend.profile={'furnace_positions':self.positions};self.backend.checkpoint=Mock()
        self.backend.ensure_client=Mock(return_value=Mock(world='w'))
        self.events=[]
        self.backend.prepare_travel=Mock(side_effect=lambda:self.events.append('prepare'))
        self.backend.stage_near_base=Mock(side_effect=lambda _:self.events.append('stage'))

    def test_returns_to_registered_bank_before_reading_remote_furnace(self):
        def recover(*_):self.events.append('recover');return {'phase':'done','safe_to_replan':True}
        with patch('material_jobs.processing.recover',side_effect=recover):
            self.assertTrue(self.backend.recover(self.inflight)['safe_to_replan'])
        self.assertEqual(self.events,['prepare','stage','recover'])
        self.backend.stage_near_base.assert_called_once_with(self.positions)
        self.assertEqual(json.loads(self.journal.read_text()),self.ledger)

    def test_partial_or_changed_world_journal_cannot_trigger_travel(self):
        for kind in ['partial','foreign']:
            ledger=json.loads(json.dumps(self.ledger))
            if kind=='partial':ledger['furnaces'][0]['stage']='input_loading'
            else:ledger['world_session']='other'
            self.journal.write_text(json.dumps(ledger))
            with patch('material_jobs.processing.recover') as recover:
                with self.assertRaises(RuntimeError):self.backend.recover(self.inflight)
                recover.assert_not_called()
        self.assertEqual(self.events,[])
