import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

from material_jobs.prior_quarry_observation import verify
from material_jobs.protocol import JobBlocked


class PriorQuarryObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.out=Path(self.tmp.name)
        self.file=self.out/'original.json'
        self.source={'item':'minecraft:tuff','source':'natural_survey','min':[0,-19,0],'max':[1,-2,1],
                     'access_shaft':{'min':[0,-1,0],'max':[1,74,1]},'prior_unknown_journal':str(self.file)}
        self.old={'schema':1,'item':'minecraft:tuff','world_session':'old',
                  'resource_regions':[self.source],
                  'visited':{'unknown':{'state':'inflight','min':[0,3,0],'max':[1,20,1]}}}
        self.file.write_text(json.dumps(self.old));self.raw=self.file.read_bytes()
        self.reply={'phase':'done','world_session':'now','scan_cells_read':72,'scan_total_cells':72,
                    'scan_start_revision':3,'scan_end_revision':3,'control_revision':3,
                    'scan_predictions':{'protocol':1,'complete':True,'pending_count':0,'pending_positions':[]}}
        self.c=SimpleNamespace(world='now',rev=3,status=lambda:{'scan_prediction_protocol':1},
                               request=Mock(side_effect=lambda *a,**k:self.reply))

    def test_current_empty_predictions_keep_old_unknown_bytes_and_zero_credit(self):
        files=verify(self.c,{'resource_regions':[self.source]},'minecraft:tuff',self.out)
        self.assertEqual(1,len(files));proof=json.loads(Path(files[0]).read_text())
        self.assertEqual(0,proof['old_action_confirmation_credit']);self.assertFalse(proof['mining_sent'])
        self.assertEqual(self.raw,self.file.read_bytes())
        self.assertEqual('scan',self.c.request.call_args.args[0]);self.assertTrue(self.c.request.call_args.kwargs['include_predictions'])

    def test_pending_partial_foreign_or_changed_revision_never_authorizes_new_mining(self):
        cases=[{'scan_cells_read':71},{'world_session':'other'},{'scan_end_revision':4},
               {'scan_predictions':{'protocol':1,'complete':True,'pending_count':1,'pending_positions':[[0,18,0]]}},
               {'scan_predictions':{'protocol':1,'complete':False,'pending_count':0,'pending_positions':[]}}]
        for change in cases:
            with self.subTest(change=change):
                base=dict(self.reply);self.reply={**base,**change}
                with self.assertRaises(JobBlocked):verify(self.c,{'resource_regions':[self.source]},'minecraft:tuff',self.out)
                self.assertEqual(self.raw,self.file.read_bytes());self.reply=base
        self.assertTrue(all(c.args[0]=='scan'for c in self.c.request.call_args_list))

    def test_foreign_source_or_old_host_does_not_send_probe_or_move(self):
        self.c.status=lambda:{'scan_prediction_protocol':0}
        with self.assertRaises(JobBlocked):verify(self.c,{'resource_regions':[self.source]},'minecraft:tuff',self.out)
        self.c.request.assert_not_called()
        self.c.status=lambda:{'scan_prediction_protocol':1};self.source['min']=[4,-19,0]
        with self.assertRaises(JobBlocked):verify(self.c,{'resource_regions':[self.source]},'minecraft:tuff',self.out)
        self.c.request.assert_not_called()


if __name__=='__main__':unittest.main()
