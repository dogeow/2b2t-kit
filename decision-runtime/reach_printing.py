"""Print grouped plain cubes from reachable stations through the existing owner.

One initial audit, exact bounded server receipts per batch, two final audits.
Unknown or partial native outcomes stop immediately; this module never retries
them, deletes their masks, or awards credit based on timing telemetry.
"""
from pathlib import Path
import math
import time
from material_plan import inventory_counts
from terminal_confirmation import verified
from village_projection import verify
from kit_runtime.journal import write_json


class CurrentOwner:
    """Use the retained native client directly, never acquire a second lease."""
    READS = frozenset(('projection_model', 'projection_audit'))
    INPUTS = frozenset(('navigate', 'select_item', 'projection_batch_set',
                        'professional_print', 'projection_batch_clear'))

    def __init__(self, client, out):
        from action_efficiency import ActionEfficiency
        self.client = client
        self.world = client.world
        self.efficiency = ActionEfficiency(out, 'native-print', self.world)

    def native(self, op, **params):
        if op not in self.READS | self.INPUTS:
            raise ValueError('Operation is outside the bounded printing macro')
        started = time.monotonic()
        reply = None
        error = None
        try:
            method = self.client.request if op in self.READS else self.client.checked
            reply = method(op, **params)
            return reply
        except Exception as exc:
            error = repr(exc)
            raise
        finally:
            try:
                self.efficiency.record('native', {'op': op, 'params': params}, started,
                                       time.monotonic(), reply, error)
            except Exception:
                pass  # A timing report cannot hide an original receipt/error.


def reachable(positions, feet, capacity, limit=32, reach=4.1):
    if type(capacity) is not int or capacity < 1 or type(limit) is not int or not 1 <= limit <= 64:
        raise ValueError('Positive actual stack capacity and bounded mask required')
    if len(set(map(tuple, positions))) != len(positions):
        raise ValueError('Duplicate targets are not separate placements')
    eye = [feet[0], feet[1] + 1.62, feet[2]]
    def clear(p):
        # Conservatively exclude every voxel intersecting the player's body.
        return not (p[0] < feet[0] + .31 and p[0] + 1 > feet[0] - .31
                    and p[2] < feet[2] + .31 and p[2] + 1 > feet[2] - .31
                    and p[1] < feet[1] + 1.81 and p[1] + 1 > feet[1])
    candidates = [p for p in positions if clear(p) and math.dist(eye, [v + .5 for v in p]) <= reach]
    return sorted(candidates, key=lambda p: (p[1], math.dist(eye, [v + .5 for v in p]), p))[:min(capacity, limit)]


def plain_cube_material(table):
    rows = table.get('expected') or []
    item = rows[0].get('item') if rows else None
    if item not in ('minecraft:dark_oak_planks', 'minecraft:cobblestone') or any(
            r.get('item') != item or r.get('state') != 'Block{' + item + '}' for r in rows):
        raise ValueError('Bounded printing requires one supported plain cube material')
    return item


def floor_stance_clearance(positions, feet):
    """Leave two blocks of height for a missing floor directly under the actor.

    A lower hovering pose passed the body-box test but left its own floor cell
    without a usable native placement proposal.
    """
    return not any(0 < feet[1] - p[1] < 2
                   and p[0] < feet[0] + .31 and p[0] + 1 > feet[0] - .31
                   and p[2] < feet[2] + .31 and p[2] + 1 > feet[2] - .31
                   for p in positions)


def print_stations(q, table, stations, proof, checkpoint, limit=32):
    path = Path(proof)
    if path.exists():
        raise RuntimeError('Retain original print journal; never replay it')
    started = time.monotonic()
    initial = checkpoint()
    if initial['professional_printer']['enabled'] or initial['projection_batch']['active']:
        raise RuntimeError('Previous printer or mask is still active')
    item = plain_cube_material(table)
    stock = inventory_counts(initial)
    key = verify(q.native('projection_model')['projection_model'], table)
    audit = q.native('projection_audit')['projection_audit']
    if audit['placement_key'] != key or audit['total'] != len(table['expected']):
        raise RuntimeError('Current audit differs from exact stage')
    missing = audit['mismatches']
    planned = {tuple(r['pos']): r for r in table['expected']}
    if len(missing) != audit['total'] - audit['matched'] or any(r['kind'] != 'missing' for r in missing):
        raise RuntimeError('Incomplete audit or occupied target; no replacement')
    todo = [r['pos'] for r in missing]
    for station in stations:
        scope = set(map(tuple, station['positions']))
        feet = station['route'][-1] if station['route'] else initial['pos']
        if not floor_stance_clearance([p for p in todo if tuple(p) in scope], feet):
            raise ValueError('Raise the floor printing pose before dispatching any placement')
    b = {'complete': False, 'world_session': q.world, 'placement_key': key,
         'inventory_before': dict(stock), 'before': audit, 'pending': None, 'batches': []}
    def save():
        write_json(path, b)
    def native(op, **params):
        checkpoint()
        b['pending'] = {'op': op, 'params': params}
        save()
        result = q.native(op, **params)
        b['pending'] = None
        save()
        return result
    save()
    try:
        for station in stations:
            checkpoint()
            scope = set(map(tuple, station['positions']))
            if not scope or not scope.issubset(planned):
                raise ValueError('Station scope must belong to the verified stage')
            # Caller supplies collision-aware room/aisle routes. The actual
            # arrival, rather than intended position, determines reachable cells.
            for point in station['route']:
                native('navigate', target=point, arrival=.1, air_only=True, seconds=30)
            while todo:
                state = checkpoint()
                available = [r for r in state['inventory'] if 0 <= r['slot'] < 36
                             and r['count'] and r['item'] == item]
                if not available:
                    break
                hand = state['hand']
                held = next((r for r in available if r['item'] == hand['item'] and r['count'] == hand['count']), None)
                choice = held if held and held['count'] >= min(limit, len(todo)) else max(available, key=lambda r: r['count'])
                positions = reachable([p for p in todo if tuple(p) in scope], state['pos'], choice['count'], limit)
                if not positions:
                    break
                if not held or hand['count'] < len(positions):
                    native('select_item', item=choice['item'], slot=choice['slot'])
                before = inventory_counts(checkpoint())
                native('projection_batch_set', placement_key=key, positions=positions)
                reply = native('professional_print', seconds=math.ceil(max(12, len(positions) * 1.2 + 5)))
                if (not verified('professional_print', reply, q.world, reply.get('id'), {})
                        or reply.get('placement_key') != key
                        or set(map(tuple, reply.get('bounded_targets', []))) != set(map(tuple, positions))):
                    raise RuntimeError('Exact bounded server confirmation is absent; no retry or clear')
                expected = before.copy()
                expected[item] -= len(positions)
                times = []
                end = time.monotonic() + 8
                while len(times) < 2:
                    state = checkpoint()
                    if inventory_counts(state) == +expected and (not times or state['time'] > times[-1]):
                        times.append(state['time'])
                    if time.monotonic() > end:
                        raise RuntimeError('Exact print material debit remains unproved')
                    time.sleep(.1)
                if checkpoint()['professional_printer']['enabled']:
                    raise RuntimeError('Printer did not release its queue')
                native('projection_batch_clear', placement_key=key)
                done = set(map(tuple, positions))
                todo = [p for p in todo if tuple(p) not in done]
                b['batches'].append({'positions': positions, 'native_request': reply['id'],
                                     'inventory_times': times, 'server_confirmed': True})
                save()
                print('REACH_PRINT_CONFIRMED', sum(len(v['positions']) for v in b['batches']), flush=True)
        finals = [native('projection_audit')['projection_audit'] for _ in range(2)]
        completed = {tuple(p) for batch in b['batches'] for p in batch['positions']}
        for frame in finals:
            if (frame['placement_key'] != key or not frame.get('loaded_server_chunks_verified')
                    or frame['total'] != len(planned) or frame['matched'] != audit['matched'] + len(completed)
                    or any(tuple(r['pos']) in completed for r in frame['mismatches'])):
                raise RuntimeError('Whole-stage final audit does not conserve acknowledged progress')
        after = inventory_counts(checkpoint())
        expected = stock.copy()
        expected[item] -= len(completed)
        if after != +expected:
            raise RuntimeError('Whole-stage inventory conservation differs')
        b.update(complete=True, stage_complete=finals[-1]['matched'] == finals[-1]['total'],
                 newly_confirmed=len(completed), after=finals, inventory_after=dict(after),
                 elapsed_seconds=time.monotonic()-started, goal_complete=False)
        save()
        return b
    except Exception as error:
        b['error'] = repr(error)
        save()
        raise
