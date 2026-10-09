import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from packed_supplies import recover_and_return

class Tests(unittest.TestCase):
    def test_unknown_or_foreign_completed_geometry_never_repeats_pickup_or_steps(self):
        for change in ('unknown','foreign_request','foreign_revision','foreign_lease'):
            with self.subTest(change=change),tempfile.TemporaryDirectory()as d:
                out=Path(d);record={'stage':'broken','slot':11,'item':'minecraft:shulker_box','world_session':'world',
                    'initial_counts':{'minecraft:book':3},'remaining_counts':{'minecraft:book':2},
                    'temporary_position':[1,64,2],'before_drop_uuids':[]}
                state={'control_revision':7,'supervision_lease':{'kind':'materials','job_session':'task','world_session':'world','revision':7,'id':'lease'},
                    'inventory':[],'entities':[{'uuid':'box','type':'minecraft:item','pos':[1.5,64,2.5],
                       'stack':{'item':'minecraft:shulker_box','count':1,'contains':[]}}]}
                c=SimpleNamespace(world='world',task='task',last='read',native_inflight=None,unconfirmed_native_request=None,
                    heartbeat=SimpleNamespace(id='lease'),status=lambda:copy.deepcopy(state),
                    last_terminal_evidence={'op':'scan','phase':'done','request_id':'read','world_session':'world','task_session':'task','revision_after':7})
                if change=='unknown':c.unconfirmed_native_request={'request_id':'original'}
                if change=='foreign_request':c.last_terminal_evidence['request_id']='foreign'
                if change=='foreign_revision':c.last_terminal_evidence['revision_after']=6
                if change=='foreign_lease':state['supervision_lease']['id']='foreign'
                with patch('packed_supplies.collect_drop',return_value=False)as collected,patch('drop_pickup_settle.settle')as stepped:
                    with self.assertRaisesRegex(RuntimeError,'still needs recovery'):recover_and_return(c,record,[4,64,5],out/'journal.json')
                    self.assertEqual(1,collected.call_count);stepped.assert_not_called()
                self.assertEqual('broken',record['stage']);self.assertEqual('box',record['drop_uuid'])

if __name__=='__main__':unittest.main()
