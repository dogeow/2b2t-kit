"""Recognize conserved, terminal legacy glass batches without changing receipts."""
import json
import math
from pathlib import Path
import re

GLASS = 'Block{minecraft:glass}'


def _json(path, maximum):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('Unavailable bounded proof')
    return json.loads(path.read_text())


def _server(value):
    return value.strip().lower().removesuffix(':25565') if isinstance(value, str) else None


def _batch(proof, scope):
    path = Path(proof)
    if (not path.is_absolute() or path.name != 'selected-glass-targets.json'
            or not re.fullmatch(r'depot-[0-9a-f]{12}', path.parent.name)
            or any(p.is_symlink() for p in (path, *path.parents))):
        return None
    plan = _json(path, 65536)
    worker = _json(path.parent / 'worker.json', 65536)
    audit = _json(path.parent / 'native-glass-result.json', 4 * 1024 * 1024)
    targets = plan.get('targets')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 64:
        return None
    positions = []
    for target in targets:
        p = target.get('pos')
        if (target.get('expected') != GLASS or not isinstance(p, list) or len(p) != 3
                or any(type(n) is not int for n in p)):
            return None
        positions.append(tuple(p))
    if len(set(positions)) != len(positions):
        return None
    result = worker.get('result', {})
    world = plan.get('world_session')
    if (not isinstance(world, str) or not world or worker.get('world_session') != world
            or worker.get('active') is not False or worker.get('phase') != 'terminal'
            or worker.get('safe_return_verified') is not True
            or plan.get('mining_sent') is not False
            or result.get('other_blocks_unchanged') is not True or result.get('health') != 20
            or type(result.get('planned')) is not int or result['planned'] != len(targets)
            or audit.get('audit_schema') != 2 or audit.get('loaded_chunks_verified') is not True
            or audit.get('loaded_server_chunks_verified') is not True
            or _server(audit.get('server')) != _server(scope.get('server'))
            or audit.get('dimension') != scope.get('dimension')
            or not scope.get('projection_key') or audit.get('placement_key') != scope['projection_key']):
        return None
    mismatches = audit.get('mismatches')
    if not isinstance(mismatches, list):
        return None
    bad = set()
    for row in mismatches:
        p = row.get('pos')
        if not isinstance(p, list) or len(p) != 3 or any(type(n) is not int for n in p):
            return None
        bad.add(tuple(p))
    completed = set(positions) - bad
    quantities = (plan.get('stock_before'), result.get('glass_remaining'), result.get('verified_glass_placed'))
    if (any(type(n) is not int or n < 0 for n in quantities)
            or quantities[0] - quantities[1] != quantities[2] or quantities[2] != len(completed)):
        return None
    events = path.parent / 'control/events.jsonl'
    if events.is_symlink() or events.parent.is_symlink():
        return None
    with events.open('rb') as stream:
        stream.seek(max(0, events.stat().st_size - 65536))
        last = json.loads(stream.read().splitlines()[-1])
    params = last.get('params', {})
    if (last.get('op') != 'material_job_pause' or last.get('phase') != 'done'
            or params.get('release') is not True or not worker.get('task_session')
            or params.get('task_session') != worker['task_session']
            or last.get('world_session') != world or last.get('health_after') != 20
            or last.get('inventory_delta') != {}
            or type(last.get('time')) not in (int, float)
            or not math.isfinite(last['time'])
            or type(audit.get('observed_at')) is not int or audit['observed_at'] <= 0
            or last['time'] * 1000 < audit['observed_at']):
        return None
    return world, completed


def resolved_legacy_glass(record, scope, cache):
    """Only an already-cleared legacy batch can cease blocking new work.

    Unknown/native claims, absent proofs, unfinished targets and bad conservation
    remain protected. No file or original action identity is changed here.
    """
    pending = record.get('pending')
    if (not isinstance(pending, dict) or set(pending) != {'legacy_records'}
            or record.get('preserve_original_claims') is not True
            or type(record.get('inventory_credit')) is not int or record['inventory_credit'] != 0):
        return False
    records = pending['legacy_records']
    if not isinstance(records, list) or not records:
        return False
    try:
        pos = tuple(scope['pos'])
        for legacy in records:
            if (legacy.get('target') != scope['pos'] or legacy.get('claim_not_cleared') is not False
                    or ('native_claim_not_cleared' in legacy and legacy['native_claim_not_cleared'] is not False)
                    or legacy.get('queue_settled_and_scene_conserved') is not True
                    or legacy.get('reason') != 'Fresh scoped native Mod glass batch'
                    or not isinstance(legacy.get('proof'), str)):
                return False
            key = (legacy['proof'], scope.get('server'), scope.get('dimension'), scope.get('projection_key'))
            if key not in cache:
                cache[key] = _batch(legacy['proof'], scope)
            batch = cache[key]
            if batch is None or batch[0] != legacy.get('world_session') or pos not in batch[1]:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError):
        return False
