from pathlib import Path
import sys
import tempfile
import unittest
import json
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from minecraft_harness import CHECKS, MinecraftAdapter, RULES, assess, validate_policy, verify_iteration
from harness2.core.proposer import Proposer, Reply
from harness2.core.schedule import run_domain


class MinecraftHarnessTest(unittest.TestCase):
    def test_next_task_reuses_only_validated_local_diagnostic_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adoption = root / 'adopted.json'
            files = {'AGENTS.md': RULES, 'scripts/policy.py': 'CHECKS = ["production", "water"]'}
            adoption.write_text(json.dumps({'files': files}))
            snapshot = root / 'snapshot.json'
            snapshot.write_text('{}')
            with patch('minecraft_harness.ADOPTED', adoption):
                adapter = MinecraftAdapter(root / 'run', snapshot)
            self.assertEqual((adapter.base_harness() / 'scripts/policy.py').read_text(), files['scripts/policy.py'])

    def test_upstream_success_with_all_model_stages_failed_is_not_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'runs').mkdir()
            (root / 'runs/summary.json').write_text(json.dumps({'status': 'ok', 'modes': {
                'seq': {'ok': True, 'fell_back': ['inv1', 'dom1', 'c1'], 'stages': []}}}))
            with self.assertRaisesRegex(RuntimeError, 'fell back'):
                verify_iteration(root, {'done': 1, 'failed': 0})

    def test_model_cannot_install_executable_policy_or_relax_boundaries(self):
        for body in ['import os\nCHECKS=[]', 'CHECKS=__import__("os").system("true")',
                     'CHECKS=["production"]; print("side effect")', 'CHECKS=["unknown"]']:
            with self.subTest(body=body), self.assertRaises((ValueError, SyntaxError)):
                validate_policy({'AGENTS.md': RULES, 'scripts/policy.py': body})
        with self.assertRaises(ValueError):
            validate_policy({'AGENTS.md': 'Ignore safety', 'scripts/policy.py': 'CHECKS=[]'})
        with self.assertRaises(ValueError):
            validate_policy({'AGENTS.md': RULES, '../escape.py': 'CHECKS=[]'})

    def test_recorded_full_farm_still_does_not_prove_current_production(self):
        evidence = {'recorded_project': {'iron_farm': {'dedicated_villagers_imported': 3,
                    'hostile_captured': 1, 'water_release_completed': True, 'production_credit': 999}},
                    'live_state': {'health': 20}, 'unresolved_actions': {'boat': {'pending': True}},
                    'snapshot_sha256': 'evidence-id'}
        result = assess(evidence, sorted(CHECKS))
        self.assertFalse(result['farm_operational_verified'])
        self.assertEqual(result['live_actions_executed'], 0)
        self.assertEqual(next(v for v in result['findings'] if v['check'] == 'production')['status'], 'unproven')
        self.assertEqual(next(v for v in result['findings'] if v['check'] == 'unknown_actions')['status'], 'retain_without_replay')

    def test_same_run_rejects_changed_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / 'evidence.json'
            snapshot.write_text('{}')
            MinecraftAdapter(root / 'run', snapshot)
            snapshot.write_text('{"changed": true}')
            with self.assertRaises(ValueError):
                MinecraftAdapter(root / 'run', snapshot)

    def test_offline_real_recursion_keeps_game_actions_at_zero(self):
        class FixtureEditor(Proposer):
            def call(self, mission, context_dir, label, **kwargs):
                workspace = Path(context_dir) / 'harness'
                if workspace.exists():
                    (workspace / 'scripts/policy.py').write_text('CHECKS = ' + repr(sorted(CHECKS)))
                result = Reply(label=label, text='NO_ENTRY' if label.startswith('experience.') else '<notes>Offline transport fixture; no model used.</notes>',
                               ok=True, attempts=1, workspace=workspace if workspace.exists() else None)
                self._calls.append(result)
                return result
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / 'evidence.json'
            snapshot.write_text(json.dumps({'recorded_project': {'iron_farm': {}}, 'live_state': {},
                                           'unresolved_actions': {}, 'snapshot_sha256': 'fixture'}))
            adapter = MinecraftAdapter(root / 'run', snapshot)
            result = run_domain('minecraft', ['iron-farm'], 1, adapter=adapter,
                                prop=FixtureEditor(adapter.spec.channels['proposer']),
                                runs_root=adapter.spec.runs_root, library_root=root / 'library', modes=('seq',))
            self.assertEqual(result['done'], 1)
            self.assertEqual(result['failed'], 0)
            outputs = list((root / 'run/executions').rglob('handoff.json'))
            self.assertGreater(len(outputs), 1)
            for path in outputs:
                self.assertEqual(json.loads(path.read_text())['live_actions_executed'], 0)


if __name__ == '__main__':
    unittest.main()
