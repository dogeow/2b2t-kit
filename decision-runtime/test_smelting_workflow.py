import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from smelting_workflow import inspect_batch, load_or_resume, wait_collect


class SmeltingWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'batch.json'
        self.positions = [[0,64,0], [3,64,0]]
        self.client = Mock(world='w')
        self.client.status.return_value = {'health':20}
        self.job = {'world_session':'w', 'source':'minecraft:stone', 'output':'minecraft:smooth_stone',
                    'amount':40, 'complete':False,
                    'furnaces':[{'pos':p, 'amount':20, 'stage':'loaded'} for p in self.positions]}

    def save(self):
        self.path.write_text(json.dumps(self.job))

    def resume(self):
        return load_or_resume(self.client, self.positions, 'minecraft:stone', 'minecraft:smooth_stone',40,self.path)

    def test_existing_loaded_or_collected_batch_never_reloads_ingredients(self):
        for complete in (False, True):
            self.job['complete'] = complete
            for entry in self.job['furnaces']:
                entry['stage'] = 'collected' if complete else 'loaded'
            self.save()
            with patch('smelting_workflow.load') as load:
                self.assertEqual(self.job, self.resume())
                load.assert_not_called()
            self.client.request.assert_not_called()
            self.client.checked.assert_not_called()

    def test_new_batch_loads_once(self):
        with patch('smelting_workflow.load',return_value=self.job) as load:
            self.assertEqual(self.job,self.resume())
            load.assert_called_once()

    def test_changed_world_plan_partial_or_false_completion_fails_before_actions(self):
        for changes in ({'world_session':'new'}, {'amount':41}, {'source':'minecraft:iron_ore'},
                        {'furnaces':self.job['furnaces'][:1]}, {'complete':True},
                        {'furnaces':[dict(e,stage='input_loading') for e in self.job['furnaces']]}):
            with self.subTest(changes=changes):
                self.path.write_text(json.dumps({**self.job,**changes}))
                with patch('smelting_workflow.load') as load:
                    with self.assertRaises(RuntimeError):self.resume()
                    load.assert_not_called()
        self.client.checked.assert_not_called()
        self.client.request.assert_not_called()

    def test_wait_keeps_observing_safety_and_stops_for_health(self):
        self.client.status.side_effect = [{'health':20},{'health':18}]
        with patch('smelting_workflow.collect',return_value=False) as collect, patch('smelting_workflow.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'recover health'):
                wait_collect(self.client,self.path,initial_delay=20)
            collect.assert_not_called()
        self.assertEqual(2,self.client.status.call_count)

    def test_timeout_does_not_repeat_loading_and_preserves_journal(self):
        self.save()
        with patch('smelting_workflow.time.monotonic',side_effect=[0,0,0,0,12]), patch('smelting_workflow.time.sleep'), patch('smelting_workflow.collect',return_value=False) as collect:
            with self.assertRaisesRegex(RuntimeError,'preserve the furnace journal'):
                wait_collect(self.client,self.path,maximum=10)
            collect.assert_called_once()
        self.assertEqual(self.job,json.loads(self.path.read_text()))
        self.client.checked.assert_not_called()

    def test_complete_collection_returns_without_idle_wait(self):
        with patch('smelting_workflow.collect',return_value=True) as collect, patch('smelting_workflow.time.sleep') as sleep:
            wait_collect(self.client,self.path)
            collect.assert_called_once()
            sleep.assert_not_called()


if __name__ == '__main__':unittest.main()
