import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from harness_strategy import DEFAULT, digest
from live_view import state


class LiveViewTest(unittest.TestCase):
    def fixture(self, root):
        lesson = root / 'EXPERIENCE.md'
        lesson.write_text('One verified source preparation, not proof of iron production.')
        directory = root / 'feedback/reflection'
        directory.mkdir(parents=True)
        registry = dict(schema=2, run_id='fixture', model_iteration_verified=True,
                        policy=DEFAULT, policy_sha256=digest(DEFAULT), heldout=dict(passed=1, total=1),
                        post_execution_reflection=dict(path=str(directory)))
        (root / 'adopted-policy.json').write_text(json.dumps(registry))
        evidence = dict(complete=True, model_reflection_verified=True, entry_created=True,
                        experience_path=str(lesson), experience={'lesson': lesson.read_text()},
                        summary={'scope': 'one_verified_native_application_not_live_speed_comparison'})
        (directory / 'live-reflection-result.json').write_text(json.dumps(evidence))
        reuse = directory.parent / 'retrieval'
        reuse.mkdir()
        (reuse / 'retrieval-result.json').write_text(json.dumps(dict(
            verified=True, model_called=True, source_experience_path=str(lesson),
            source_experience_sha256=hashlib.sha256(lesson.read_bytes()).hexdigest())))
        return registry, lesson

    def test_does_not_present_missing_policy_as_adopted(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertFalse(state(Path(temp))['available'])

    def test_historical_scope_and_retrieval_bound_to_exact_lesson(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _, lesson = self.fixture(root)
            result = state(root)
            self.assertTrue(result['retrieval_verified'])
            self.assertEqual(result['scope'], 'historical_evidence_not_current_game_state')
            lesson.write_text('Changed lesson')
            self.assertFalse(state(root)['retrieval_verified'])

    def test_reflection_path_cannot_read_outside_harness(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry, _ = self.fixture(root)
            registry['post_execution_reflection']['path'] = str(root.parent)
            (root / 'adopted-policy.json').write_text(json.dumps(registry))
            self.assertFalse(state(root)['available'])

    def test_invalid_policy_not_shown_as_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            registry, _ = self.fixture(root)
            registry['policy_sha256'] = 'wrong'
            (root / 'adopted-policy.json').write_text(json.dumps(registry))
            self.assertFalse(state(root)['available'])
