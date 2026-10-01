"""Diagnostic material-pipeline outcomes. Never promote a module report to a skill."""
import json
from pathlib import Path
import time
import uuid


def record_outcome(backend, item, target_count, target_scope, out, *, result=None,
                   error=None, duration_ms=0):
    """Best effort only: recording cannot replace a receipt or trigger a game retry."""
    event = {'schema': 1, 'kind': 'material_pipeline_experience',
             'id': uuid.uuid4().hex, 'time': time.time(),
             'tags': ['minecraft', 'projection', 'mining', 'materials', '投影建造', '挖矿', '材料'],
             'item': item, 'target_count': target_count, 'target_scope': target_scope,
             'duration_ms': max(0, int(duration_ms)),
             'evidence_scope': 'pipeline_report_not_independent_native_verification',
             'automatic_retry_allowed': False}
    if error is not None:
        name = type(error).__name__
        event.update(outcome='interrupted' if name in ('JobPaused', 'JobCancelled', 'Handoff')
                     else 'raised', error_type=name)
    else:
        value = result if isinstance(result, dict) else {}
        phase = value.get('phase')
        event.update(outcome='reported_done' if phase == 'done' else 'reported_incomplete',
                     reported_phase=phase, code=value.get('code'),
                     pending_present=bool(value.get('pending')))
    try:
        from experience_recording import state_for_backend
        root = state_for_backend(backend)
        # The journal is local evidence; no raw request, profile, secrets or error text.
        directory = Path(out); directory.mkdir(parents=True, exist_ok=True)
        with (directory / 'pipeline-experiences.jsonl').open('a') as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        from experience_recording import record_lesson
        record_lesson(event, root)
        return {'status': 'lesson', 'id': event['id']}
    except Exception as failure:
        # In particular, do not turn an already finished mutation into a retry.
        try:
            with (Path(out) / 'experience-recording-errors.jsonl').open('a') as stream:
                stream.write(json.dumps({'kind': event['kind'], 'error_type': type(failure).__name__}) + '\n')
        except Exception:
            pass
        return {'status': 'recording_failed'}
