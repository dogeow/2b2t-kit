import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from material_shutdown import settle_terminal_read


class TerminalReadFinishTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.c = SimpleNamespace(root=root, out=root, last='read-a', world='world', task='task', rev=4,
            heartbeat=SimpleNamespace(id='lease'), native_inflight={
                'request_id':'read-a', 'op':'scan', 'world_session':'world', 'task_session':'task',
                'lease_id':'lease', 'base_revision':4, 'request_revision':4, 'expected_revision':4,
                'server':'server.test', 'dimension':'minecraft:overworld'})
        self.state = {'time':200, 'connected':True, 'manual_movement':False, 'world_session':'world',
            'control_revision':4, 'last_request':'read-a', 'id':'old-move', 'op':'navigate', 'phase':'done',
            'server':'server.test:25565', 'dimension':'minecraft:overworld', 'pending_scan':None,
            'supervision_lease':{'id':'lease', 'job_session':'task', 'kind':'materials',
                                 'world_session':'world', 'revision':4}}
        self.reply = {'time':150, 'id':'read-a', 'world_session':'world', 'control_revision':4,
                      'phase':'done', 'blocks':[]}
        self.path = root/'reply-read-a.json'
        self.path.write_text(json.dumps(self.reply))

    def test_cancelled_scan_uses_its_exact_reply_even_when_status_describes_previous_move(self):
        self.assertTrue(settle_terminal_read(self.c, self.state))
        self.assertIsNone(self.c.native_inflight)
        self.assertEqual(self.reply, json.loads(self.path.read_text()))
        saved=json.loads((self.c.out/'observed-terminal-read-read-a.json').read_text())
        self.assertEqual(0,saved['goal_completion_credit'])
        self.assertFalse(saved['resource_actions_replayed'])

    def test_missing_invalid_or_wrong_reply_never_clears_envelope(self):
        for content in (None, 'invalid', json.dumps({**self.reply,'id':'other'}),
                        json.dumps({**self.reply,'world_session':'other'}),
                        json.dumps({**self.reply,'control_revision':5}),
                        json.dumps({**self.reply,'phase':'running'}),
                        json.dumps({**self.reply,'time':201})):
            with self.subTest(content=content):
                if content is None:self.path.unlink(missing_ok=True)
                else:self.path.write_text(content)
                pending=self.c.native_inflight
                self.assertFalse(settle_terminal_read(self.c,self.state))
                self.assertIs(pending,self.c.native_inflight)

    def test_busy_manual_or_changed_owner_keeps_original_pending(self):
        variations=[{'pending_scan':{'id':'read-a'}}, {'navigating':True}, {'manual_movement':True},
                    {'control_revision':5}, {'last_request':'other'}, {'connected':False},
                    {'supervision_lease':{**self.state['supervision_lease'],'id':'other'}},
                    {'control_stop':{'kind':'emergency','revision':4}}]
        for changes in variations:
            with self.subTest(changes=changes):
                self.assertFalse(settle_terminal_read(self.c,{**self.state,**changes}))
                self.assertIsNotNone(self.c.native_inflight)

    def test_backend_finish_observes_cancelled_read_without_dispatching_a_new_action(self):
        from material_jobs_backend import Backend
        self.state['menu']={'id':0,'type':'InventoryMenu','cursor':{'count':0}}
        self.c.status=lambda:copy.deepcopy(self.state)
        actual=Backend.wait_finish_idle(SimpleNamespace(client=self.c))
        self.assertEqual(self.state,actual)
        self.assertIsNone(self.c.native_inflight)
        self.assertEqual(self.reply,json.loads(self.path.read_text()))

    def test_resource_actions_never_use_this_read_only_settlement(self):
        for op in ('mine_block','inventory_click','navigate','quarry_batch','interact'):
            with self.subTest(op=op):
                self.c.native_inflight['op']=op
                self.assertFalse(settle_terminal_read(self.c,self.state))
                self.assertIsNotNone(self.c.native_inflight)


if __name__=='__main__':
    unittest.main()
