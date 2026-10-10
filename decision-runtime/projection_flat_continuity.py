"""Reuse a flat-map material ledger only across an exact healthy parking handoff."""
import json
from pathlib import Path

from kit_runtime.journal import write_json
from projection_flat_cache import FlatMaterialLedger
from projection_flat_plan import FlatLayout

NAME = 'flat-map-continuation-cache.json'


def restore(backend, state):
    if backend.request.get('flat_map', {}).get('reuse_parked_material_ledger') is not True:
        return False
    path = backend.root / NAME
    try:
        if path.stat().st_size > 32 * 1024 * 1024:
            return False
        saved = json.loads(path.read_text())
        lease = state.get('supervision_lease') or {}
        if (saved.get('schema') != 1 or not saved.get('native_parking_verified')
                or saved.get('world_session') != state.get('world_session')
                or saved.get('control_revision') != state.get('control_revision')
                or lease.get('kind') != 'parking' or lease.get('id') != saved.get('lease_id')
                or lease.get('job_session') != saved.get('task_session')
                or lease.get('world_session') != state.get('world_session')
                or lease.get('revision') != state.get('control_revision')
                or state.get('manual_movement') or not state.get('connected')
                or state.get('safety_hold', {}).get('active')):
            return False
        model = saved['model']
        layout = FlatLayout(model, backend.request['flat_map'])
        selection = state.get('projection_selection') or {}
        if (layout.key != backend.request['projection_key'] or selection.get('key') != layout.key
                or selection.get('min') != list(layout.low) or selection.get('max') != list(layout.high)):
            return False
        ledger = FlatMaterialLedger(layout, saved['audit'], state['world_session'])
        backend.flat_layout, backend.flat_model, backend.flat_ledger = layout, model, ledger
        backend.audit, backend.audit_dirty = ledger.audit, False
        backend.parked_ledger_reused = True
        write_json(backend.out / 'parked-ledger-reuse.json', {
            'source': str(path), 'world_session': ledger.world,
            'baseline_observed_at': ledger.baseline_at, 'matched': ledger.audit['matched'],
            'native_parking_verified': True, 'fresh_full_scan': False})
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def save(backend, client, state):
    """Called only after Backend.finish proves the native guarded park receipt."""
    layout = getattr(backend, 'flat_layout', None)
    model = getattr(backend, 'flat_model', None)
    audit = getattr(backend, 'audit', None)
    lease = state.get('supervision_lease') or {}
    if (layout is None or model is None or audit is None or getattr(backend, 'audit_dirty', True)
            or state.get('world_session') != client.world or lease.get('kind') != 'parking'
            or lease.get('id') != client.heartbeat.id or lease.get('job_session') != client.task
            or lease.get('revision') != state.get('control_revision') or state.get('manual_movement')
            or not state.get('connected') or state.get('safety_hold', {}).get('active')):
        return False
    layout.observed(audit)
    write_json(backend.root / NAME, {
        'schema': 1, 'world_session': client.world, 'control_revision': state['control_revision'],
        'lease_id': lease['id'], 'task_session': client.task, 'saved_at': state['time'],
        'native_parking_verified': True, 'model': model, 'audit': audit})
    return True
