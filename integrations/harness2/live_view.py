"""Read-only presentation of selected policy and historical live evidence."""
import hashlib
import json
from pathlib import Path


def read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def inside(root, value):
    path = Path(value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('Evidence path escaped local Harness records')
    return path


def state(root):
    from harness_strategy import load_selected
    root = Path(root)
    try:
        selected = load_selected(root / 'adopted-policy.json')
        registry = read(root / 'adopted-policy.json', {})
        if not selected.get('active'):
            return {'available': False, 'detail': '尚无通过验证的策略'}
        result = {'available': True, 'run_id': selected['run_id'],
                  'policy_sha256': selected['policy_sha256'], 'policy': selected['policy'],
                  'evaluations': {key: {field: registry.get(key, {}).get(field)
                                       for field in ('passed', 'total')}
                                  for key in ('baseline', 'training', 'heldout')},
                  'last_runtime_record': read(root / 'runtime-status.json'),
                  'scope': 'historical_evidence_not_current_game_state',
                  'application': None, 'experience': None, 'retrieval_verified': False}
        reflection = registry.get('post_execution_reflection', {}).get('path')
        if reflection:
            directory = inside(root, reflection)
            evidence = read(directory / 'live-reflection-result.json', {})
            if evidence.get('complete') and evidence.get('model_reflection_verified'):
                result['application'] = evidence.get('summary')
                result['experience'] = evidence.get('experience') if evidence.get('entry_created') else None
                reuse = read(directory.parent / 'retrieval/retrieval-result.json', {})
                lesson = inside(root, evidence['experience_path']) if evidence.get('experience_path') else None
                result['retrieval_verified'] = bool(
                    reuse.get('verified') and reuse.get('model_called') and lesson and lesson.is_file()
                    and reuse.get('source_experience_sha256') == hashlib.sha256(lesson.read_bytes()).hexdigest()
                    and Path(reuse.get('source_experience_path', '')).resolve() == lesson)
                result['next_recommendation'] = reuse.get('decision', {}).get('action')
                # Read the original saved model prompt; never reconstruct it for display.
                result['actual_reflection_prompts'] = [p.read_text() for p in
                    sorted(directory.glob('codex-audit/*/prompt.txt'))]
        return result
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {'available': False, 'detail': str(error), 'scope': 'evidence_unverified'}
