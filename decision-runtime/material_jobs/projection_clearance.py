"""Scheduling hints and independently witnessed progress for automatic clearance."""
import json
from pathlib import Path

from material_plan import inventory_counts
from projection_completion import TERRAIN
from .protocol import JobBlocked, server_key

NATURAL = frozenset(TERRAIN)


def identity(state):
    return state.split('}', 1)[0].removeprefix('Block{') if isinstance(state, str) else ''


def natural_rows(audit):
    rows = {}
    records = []
    for name in ('mismatches', 'enclosed_air_conflicts'):
        if isinstance(audit.get(name), list):
            records.extend(audit[name])
    for row in records:
        if not isinstance(row, dict):
            continue
        pos = row.get('pos')
        if (isinstance(pos, list) and len(pos) == 3 and all(type(n) is int for n in pos)
                and identity(row.get('actual')) in NATURAL):
            rows[tuple(pos)] = row
    return rows


def pending_positions(root, key, state):
    directory = Path(root)/'projection-terrain-intents'
    if not directory.exists():
        return set()
    if directory.is_symlink():
        raise JobBlocked('清障旧回执目录不安全，不能自动接管')
    files = list(directory.glob('*.json'))
    if len(files) > 2048:
        raise JobBlocked('清障旧回执需要整理，不能跳过检查')
    result = set()
    for path in files:
        try:
            if path.is_symlink() or path.stat().st_size > 16384:
                raise ValueError('invalid journal')
            record = json.loads(path.read_text()); scope = record['scope']
            if not isinstance(scope, dict):
                raise ValueError('invalid scope')
            if (server_key(scope.get('server')) != server_key(state.get('server'))
                    or scope.get('dimension') != state.get('dimension')):
                continue
            pos = scope.get('pos')
            if not isinstance(pos, list) or len(pos) != 3 or any(type(n) is not int for n in pos):
                raise ValueError('invalid position')
            if record.get('pending') is not None:
                result.add(tuple(pos))
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise JobBlocked('清障旧回执不可读，保留原动作不重放') from error
    return result


def possible(audit, state, root):
    """A cached hint may schedule a fresh audit; it never authorizes excavation."""
    key = (state.get('projection_selection') or {}).get('key')
    if (audit.get('audit_schema') != 2 or audit.get('placement_key') != key
            or server_key(audit.get('server')) != server_key(state.get('server'))
            or audit.get('dimension') != state.get('dimension')
            or audit.get('loaded_chunks_verified') is not True or audit.get('kinds', {}).get('unloaded')
            or not state.get('flight') or state.get('screen')):
        return False
    protected = pending_positions(root, key, state)
    try:
        held = inventory_counts(state)
    except ValueError:
        return False
    from projection_terrain import replacement_stock_item
    for pos, row in natural_rows(audit).items():
        if (pos in protected or row.get('block_entity') or row.get('fluid')
                or row.get('adjacent_fluid') is not False or row.get('neighbors_loaded') is not True):
            continue
        item = replacement_stock_item(row['expected'])
        if item is None or held[item] > 0:
            return True
    return False


def capture(audit):
    return {'audit_schema': audit.get('audit_schema'), 'placement_key': audit.get('placement_key'),
            'server': audit.get('server'), 'dimension': audit.get('dimension'),
            'observed_at': audit.get('observed_at'),
            'natural': [{'pos': list(pos), 'actual': row['actual']} for pos, row in natural_rows(audit).items()]}


def verified_progress(before, after, receipt, world):
    """Loot/eating/movement cannot substitute for changed terrain and native ACKs."""
    rows = receipt.get('clearance_confirmations')
    if (not isinstance(rows, list) or not rows or before.get('audit_schema') != 2
            or after.get('audit_schema') != 2 or after.get('loaded_chunks_verified') is not True
            or after.get('kinds', {}).get('unloaded')
            or type(before.get('observed_at')) is not int or type(after.get('observed_at')) is not int
            or after['observed_at'] <= before['observed_at']
            or not isinstance(after.get('mismatches'), list) or not isinstance(after.get('enclosed_air_conflicts'), list)
            or any(not isinstance(before.get(k), str) or not before[k] for k in ('placement_key', 'server', 'dimension'))
            or any(before.get(k) != after.get(k) for k in ('placement_key', 'server', 'dimension'))):
        return False
    originals = {tuple(row['pos']): row['actual'] for row in before.get('natural', [])}
    current = {tuple(row['pos']): row['actual'] for row in [*after.get('mismatches', []), *after.get('enclosed_air_conflicts', [])]}
    seen = set()
    for row in rows:
        pos = tuple(row.get('pos', []))
        sequence = row.get('native_sequence')
        if (pos in seen or pos not in originals or row.get('old_state') != originals[pos]
                or row.get('world_session') != world or row.get('server_confirmed') is not True
                or not isinstance(row.get('request_id'), str) or not row['request_id']
                or type(sequence) is not int or sequence <= 0 or row.get('server_ack_sequence') != sequence
                or (pos in current and current[pos] != 'Block{minecraft:air}'
                    and current[pos] not in {'Block{minecraft:water}[level='+str(n)+']' for n in range(16)})):
            return False
        seen.add(pos)
    return bool(seen)
