import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from material_jobs.gravel_staging import target, stage
from material_jobs.protocol import JobBlocked


class GravelStagingTest(unittest.TestCase):
    def spec(self, point=None):
        return {'gravel_staging': {'authorized': True, 'source': 'verified_open_water',
                                  'target': point or [761075.5, 90, 797883.5]}}

    def test_only_explicit_registered_water_target_is_used(self):
        self.assertIsNone(target({}))
        for spec in ({'target': [1, 90, 3]}, {'authorized': True, 'source': 'cache', 'target': [1, 90, 3]},
                     {'authorized': True, 'source': 'verified_open_water', 'target': [1, 65, 3]},
                     {'authorized': True, 'source': 'verified_open_water', 'target': [float('nan'), 90, 3]}):
            with self.assertRaises(JobBlocked):
                target({'gravel_staging': spec})

    def test_native_checked_arrival_uses_same_client_and_durable_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = Mock();backend.out=Path(tmp);backend.profile=self.spec()
            client=backend.ensure_client.return_value;client.world='w'
            client.status.return_value={'world_session':'w','health':20,'pos':target(backend.profile)}
            with patch('material_jobs.acquisition._travel') as travel:
                self.assertTrue(stage(backend))
            self.assertIs(travel.call_args.args[0],client)
            self.assertTrue((Path(tmp)/'gravel-preflight/open-water-staging-travel.json').exists())

    def test_arrival_without_current_world_or_with_guard_cannot_start_dive(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend=Mock();backend.out=Path(tmp);backend.profile=self.spec()
            client=backend.ensure_client.return_value;client.world='w'
            for extra in ({'world_session':'old'}, {'guard_busy':True}, {'under_water':True},
                          {'manual_movement':True}, {'pos':[1,90,3]}, {'health':18}):
                client.status.return_value={'world_session':'w','health':20,
                                            'pos':target(backend.profile), **extra}
                with patch('material_jobs.acquisition._travel'), self.assertRaises(JobBlocked):
                    stage(backend)


if __name__ == '__main__':
    unittest.main()
