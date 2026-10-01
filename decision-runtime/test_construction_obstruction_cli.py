import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import construction_obstruction_cli as cli
from construction_obstruction import HorseNudgeWaiting, HorseObstructionBlocked


class Client:
    def __init__(self, root, *, confirmed=True):
        self.out = Path(root);self.out.mkdir(parents=True, exist_ok=True)
        self.confirmed = confirmed;self.finished = False
        self.world = 'world-a';self.task = 'task-a'
        self.heartbeat = type('Heartbeat', (), {'id': 'lease-a'})()
    def finish(self):
        self.finished = True
        (self.out / 'stock-safety.json').write_text(json.dumps({
            'action': 'KEEP_PVE_GUARD' if self.confirmed else 'LOGOUT',
            'lease': 'lease-a', 'job_session': self.task,
            'snapshot': {'world_session': self.world}}))
    def raw(self):
        return {'connected': self.confirmed, 'guard_armed': self.confirmed,
                'guard_pve_only': self.confirmed, 'flight': self.confirmed,
                'health': 20, 'pos': [1, 100, 1], 'world_session': self.world}
    def park_near(self, state):
        return self.confirmed


class ConstructionObstructionCliTest(unittest.TestCase):
    def test_cli_has_no_direct_escape_bypass(self):
        self.assertNotIn("'--escape'", inspect.getsource(cli.main))

    def test_done_and_waiting_both_finish_in_verified_high_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Client(folder)
            with patch.object(cli, 'approach_and_nudge_explicit_horse',
                              return_value={'phase': 'done'}):
                result, code = cli.execute(client, [1, 2, 3], 'Block{minecraft:dirt}', 74, 30)
            self.assertEqual(code, 0);self.assertTrue(client.finished)
            self.assertTrue(result['high_guard_finish']['confirmed'])
        with tempfile.TemporaryDirectory() as folder:
            client = Client(folder);reply = {'phase': 'waiting', 'horse_nudge': {'attack_count': 1}}
            with patch.object(cli, 'approach_and_nudge_explicit_horse',
                              side_effect=HorseNudgeWaiting('waiting', reply)):
                result, code = cli.execute(client, [1, 2, 3], 'Block{minecraft:dirt}', 74, 30)
            self.assertEqual(code, 2);self.assertTrue(client.finished)
            self.assertEqual(result['phase'], 'waiting')
            self.assertTrue(result['high_guard_finish']['confirmed'])

    def test_unconfirmed_finish_preserves_result_and_uses_distinct_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Client(folder, confirmed=False)
            with patch.object(cli, 'approach_and_nudge_explicit_horse',
                              return_value={'phase': 'done', 'horse_nudge': {'attack_count': 1}}):
                with self.assertRaises(cli.GuardFinishUnconfirmed) as caught:
                    cli.execute(client, [1, 2, 3], 'Block{minecraft:dirt}', 74, 30)
            self.assertTrue(client.finished)
            self.assertEqual(caught.exception.result['phase'], 'done')
            self.assertFalse(caught.exception.result['high_guard_finish']['confirmed'])

    def test_fail_closed_approach_still_finishes_and_verifies_high_guard(self):
        for detail in ('No freshly scanned solid escape', 'Exact horse changed after landing',
                       'No exact horse entered the construction clearance before timeout',
                       'Scout drifted again after the one allowed recenter'):
            with self.subTest(detail=detail), tempfile.TemporaryDirectory() as folder:
                client = Client(folder)
                with patch.object(cli, 'approach_and_nudge_explicit_horse',
                                  side_effect=HorseObstructionBlocked(detail)):
                    with self.assertRaises(cli.HorseApproachFailed) as caught:
                        cli.execute(client, [1, 2, 3], 'Block{minecraft:dirt}', 74, 30)
                self.assertTrue(client.finished)
                self.assertEqual(caught.exception.result['phase'], 'blocked')
                self.assertTrue(caught.exception.result['high_guard_finish']['confirmed'])

    def test_old_or_foreign_guard_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            client = Client(folder)
            client.finish();path = client.out / 'stock-safety.json'
            receipt = json.loads(path.read_text());receipt['lease'] = 'old-lease'
            path.write_text(json.dumps(receipt))
            with self.assertRaises(cli.GuardFinishUnconfirmed):
                cli.verify_high_guard_finish(client)


if __name__ == '__main__':
    unittest.main()
