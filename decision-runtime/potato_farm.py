"""Bounded potato planting with an injected, already-owned MaterialClient.

No controller, movement, water placement, harvesting, reconnect or safety unlock
is created here. Generic native interact supports hoe and crop use, but exposes
no per-cell server ACK. Completion is explicitly stable client observation.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

from kit_runtime.journal import write_json

POTATO = 'minecraft:potato'
HOES = {'minecraft:' + name + '_hoe' for name in
        ('wooden', 'stone', 'iron', 'golden', 'diamond', 'netherite')}
ENTITY_SCOPE = 'current_client_loaded_rendering_entities_intersecting_scan_AABB_not_whole_herd'
ENTITY_SCOPE_AT_SCAN_END = 'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd'
_ENTITY_SCOPES = frozenset((ENTITY_SCOPE, ENTITY_SCOPE_AT_SCAN_END))
PROOF_SCOPE = 'two_distinct_post_interaction_loaded_client_scans_and_exact_carried_item_or_hoe_durability_delta_not_per_cell_server_ack'


class FarmWait(RuntimeError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def valid_entity_scope(value):
    """Accept only known client-loaded entity sets intersecting the scan AABB.

    The newer spelling makes sampling at scan end explicit. Neither spelling
    establishes a whole-herd census, atomic world snapshot or server ACK.
    """
    return isinstance(value, str) and value in _ENTITY_SCOPES


def hydration_covers(soil, water):
    """26.1.2 FarmlandBlock checks X/Z +/-4 and Y soil..soil+1."""
    return (abs(soil[0]-water[0]) <= 4 and abs(soil[2]-water[2]) <= 4
            and soil[1] <= water[1] <= soil[1]+1)


def plan(request):
    if not isinstance(request, dict) or request.get('authorized') is not True:
        raise ValueError('An explicitly authorized farm request is required')
    center = request.get('center')
    if (not isinstance(center, list) or len(center) != 3
            or any(type(n) is not int or abs(n) > 30_000_000 for n in center)
            or not -63 <= center[1] <= 317):
        raise ValueError('Farm center must be bounded integer [x, floor_y, z]')
    radius = request.get('radius', 2)
    if type(radius) is not int or not 1 <= radius <= 2:
        raise ValueError('Potato pilot radius is limited to 1..2')
    x, y, z = center
    cells = [[a, y, b] for a in range(x-radius, x+radius+1)
             for b in range(z-radius, z+radius+1) if (a, b) != (x, z)]
    assert all(hydration_covers(p, center) for p in cells)
    return {'center': center[:], 'radius': radius, 'cells': cells,
            'scan_min': [x-radius-1, y-1, z-radius-1],
            'scan_max': [x+radius+1, y+2, z+radius+1],
            'potatoes': len(cells), 'maximum_interactions': 2*len(cells)}


def _key(pos):
    return ','.join(map(str, pos))


def _block(row):
    state = row.get('state', '')
    return state.split('}', 1)[0].removeprefix('Block{') if state.startswith('Block{') else ''


def _properties(row, block, prop, high):
    match = re.fullmatch(r'Block\{minecraft:' + block + r'\}\[' + prop + r'=([0-' + str(high) + r'])\]', row.get('state', ''))
    return int(match[1]) if match else None


def _counts(state):
    rows = state.get('inventory')
    if not isinstance(rows, list):
        raise FarmWait('WAIT_INVENTORY', 'Actual carried inventory is unavailable')
    result = Counter(); seen = set()
    for row in rows:
        slot, count, item = row.get('slot'), row.get('count'), row.get('item')
        if (type(slot) is not int or not 0 <= slot <= 42 or slot in seen
                or type(count) is not int or not 0 <= count <= 64 or not isinstance(item, str)):
            raise FarmWait('WAIT_INVENTORY', 'Inventory metadata is malformed or duplicated')
        seen.add(slot)
        if slot < 36 and count:
            result[item] += count
    return result


def _gate(c, state, hurt_at):
    lease = state.get('supervision_lease') or {}
    if (state.get('connected') is not True or state.get('world_session') != c.world
            or state.get('control_revision') != c.rev
            or lease.get('kind') != 'materials' or lease.get('job_session') != c.task
            or lease.get('world_session') != c.world or lease.get('revision') != c.rev):
        raise FarmWait('WAIT_CONTROL', 'World or current material lease changed; no resume or reconnect')
    if (state.get('manual_movement') is not False or state.get('screen') != ''
            or state.get('health', 0) < 20 or state.get('food', 0) < 8
            or state.get('recent_hurt_at') != hurt_at
            or state.get('guard_armed') is not True or state.get('guard_pve_only') is not True
            or state.get('guard_busy') is not False or state.get('under_water') is not False
            or (state.get('safety_hold') or {}).get('active') is not False
            or state.get('dimension') != 'minecraft:overworld'
            or state.get('game_mode') != 'survival'
            or any(state.get(k) for k in ('borer_active', 'chopping', 'navigating', 'printing', 'planter_active', 'feeder_active', 'fisher_active'))
            or any(e.get('hostile') is True for e in state.get('entities', []))):
        raise FarmWait('WAIT_SAFETY', 'Health, injury, guard, manual input or another task requires stopping')
    menu = state.get('menu') or {}
    if (menu.get('id') != 0 or menu.get('type') != 'InventoryMenu'
            or (menu.get('cursor') or {}).get('count') != 0
            or not isinstance(state.get('time'), int)):
        raise FarmWait('WAIT_INVENTORY', 'Idle timestamped inventory menu with empty cursor is required')


def survey_rows(reply, layout, records, pending=None):
    """Sparse native AIR is valid only inside this successfully scanned volume."""
    if (not isinstance(reply.get('blocks'), list) or reply.get('unloaded_chunks', 0)
            or not valid_entity_scope(reply.get('scan_entity_scope'))
            or not isinstance(reply.get('scan_entities'), list)):
        raise FarmWait('WAIT_SCAN', 'Detailed bounded native scan/entity evidence is unavailable')
    if reply['scan_entities']:
        raise FarmWait('WAIT_ENTITY', 'A currently loaded entity intersects the farm/buffer')
    lo, hi = layout['scan_min'], layout['scan_max']; by = {}
    for row in reply['blocks']:
        point = row.get('pos')
        if (not isinstance(point, list) or len(point) != 3 or any(type(v) is not int for v in point)
                or not all(a <= b <= d for a, b, d in zip(lo, point, hi))
                or tuple(point) in by or not isinstance(row.get('state'), str)
                or type(row.get('solid')) is not bool or type(row.get('fluid')) is not bool
                or type(row.get('block_entity')) is not bool):
            raise FarmWait('WAIT_SCAN', 'Missing typed details, duplicate or out-of-volume scan row')
        by[tuple(point)] = row
        if row['block_entity']:
            raise FarmWait('WAIT_CONTAINER', 'Container or block entity in farm buffer is protected')
        if row['fluid'] and point != layout['center']:
            raise FarmWait('WAIT_WATER', 'A fluid outside the declared center is protected')
    water = by.get(tuple(layout['center']), {})
    if water.get('state') != 'Block{minecraft:water}[level=0]' or water.get('fluid') is not True:
        raise FarmWait('WAIT_WATER', 'The center must already contain an actual level-0 water source')
    for pos in [layout['center']] + layout['cells']:
        x, y, z = pos
        bottom = by.get((x, y-1, z), {})
        if bottom.get('solid') is not True or bottom.get('fluid') is not False:
            raise FarmWait('WAIT_FOOTING', 'Farm/source lacks observed dry full-block bottom')
        if (x, y+2, z) in by:
            raise FarmWait('WAIT_AIR', 'Farm headroom is occupied')
        if pos == layout['center']:
            if (x, y+1, z) in by:
                raise FarmWait('WAIT_AIR', 'Center headroom is occupied')
            continue
        soil = by.get(tuple(pos), {})
        crop = by.get((x, y+1, z))
        farmland = _properties(soil, 'farmland', 'moisture', 7) is not None
        if (_block(soil) not in ('minecraft:grass_block', 'minecraft:dirt') and not farmland
                or soil.get('fluid') is not False or soil.get('block_entity') is not False
                or not farmland and soil.get('solid') is not True):
            raise FarmWait('WAIT_SOIL', 'Farm floor is not fresh grass/dirt or known farmland')
        light = soil.get('spawn_block_light')
        if type(light) is not int or not 9 <= light <= 15:
            raise FarmWait('WAIT_LIGHT', 'Crop cell needs actual block light >=9 for reliable survival/growth')
        known = records.get(_key(pos), {}).get('planted') is True
        expected_crop = pending and pending.get('operation') == 'plant' and pending.get('pos') == pos
        if crop and not ((known or expected_crop) and farmland and _properties(crop, 'potatoes', 'age', 7) is not None):
            raise FarmWait('WAIT_AIR', 'Unowned crop or obstacle occupies a planting cell')
        if known and crop is None:
            raise FarmWait('WAIT_RECONCILE', 'A previously planted crop is missing; no automatic reseed')
    return by


class _GuardedClient:
    def __init__(self, c, checkpoint, hurt):
        self.c, self.checkpoint, self.hurt = c, checkpoint, hurt
    def status(self):
        self.checkpoint(); state = self.c.status(); _gate(self.c, state, self.hurt); return state
    def checked(self, op, **params):
        self.status(); reply = self.c.request(op, **params)
        if reply.get('phase') != 'done':
            raise FarmWait('WAIT_RECONCILE', 'Native inventory/selection result is unknown; do not replay')
        return reply


def _survey(proxy, layout, book):
    before = proxy.status()
    reply = proxy.c.request('scan', min=layout['scan_min'], max=layout['scan_max'], details=True)
    _gate(proxy.c, reply, proxy.hurt)
    if reply['time'] <= before['time']:
        raise FarmWait('WAIT_SCAN', 'Scan is not a later native observation')
    by = survey_rows(reply, layout, book['cells'], book.get('pending'))
    return reply, by


def _hand(proxy, item, slot):
    proxy.checked('select_item', item=item, slot=slot)
    state = proxy.status(); hand = state.get('hand') or {}
    if hand.get('item') != item or type(hand.get('count')) is not int or hand['count'] < 1:
        raise FarmWait('WAIT_HAND', 'Selected held item was not actually confirmed')
    return state


def _potato(proxy, state=None):
    state = proxy.status() if state is None else state; hand = state.get('hand') or {}
    if hand.get('item') == POTATO and hand.get('count', 0) >= 1:
        return state
    source = max((r for r in state['inventory'] if r['slot'] < 36 and r['item'] == POTATO and r['count'] > 0),
                 key=lambda r:r['count'], default=None)
    if source is None:
        raise FarmWait('WAIT_POTATO', 'No actual carried planting potatoes')
    # Ordinary carried stacks are supported by native BlockItem.useOn. Re-select
    # only when the previous carried stack was exhausted or the hand changed.
    return _hand(proxy, POTATO, source['slot'])


def _hoe(proxy, remaining):
    state = proxy.status()
    choices = [r for r in state['inventory'] if r['slot'] < 36 and r['item'] in HOES and r['count'] == 1
               and type(r.get('durability')) is int and r['durability'] > remaining and not r.get('enchantments')]
    if not choices:
        raise FarmWait('WAIT_HOE', 'A plain singleton hoe with remaining tills plus one durability is required')
    tool = max(choices, key=lambda r: r['durability'])
    return _hand(proxy, tool['item'], tool['slot'])


def action_proved(operation, pos, before, after, rows):
    soil = rows.get(tuple(pos), {}); above = rows.get((pos[0], pos[1]+1, pos[2]))
    a, b = _counts(before), _counts(after)
    if operation == 'plant':
        expected = a.copy(); expected[POTATO] -= 1
        if not expected[POTATO]: del expected[POTATO]
        hand_a, hand_b = before.get('hand') or {}, after.get('hand') or {}
        left = hand_a.get('count', 0)-1
        return (b == expected and _properties(soil, 'farmland', 'moisture', 7) is not None
                and above is not None and _properties(above, 'potatoes', 'age', 7) is not None
                and hand_a.get('item') == POTATO and left >= 0 and hand_b.get('count') == left
                and (left == 0 and hand_b.get('item') == 'minecraft:air' or left > 0 and hand_b.get('item') == POTATO)
                and before.get('selected_slot') == after.get('selected_slot'))
    hand_a, hand_b = before.get('hand') or {}, after.get('hand') or {}
    return (a == b and _properties(soil, 'farmland', 'moisture', 7) is not None and above is None
            and hand_a.get('item') in HOES and hand_b.get('item') == hand_a.get('item')
            and hand_a.get('count') == hand_b.get('count') == 1
            and type(hand_a.get('durability')) is int and hand_b.get('durability') == hand_a['durability']-1)


def run(c, request, out, checkpoint=lambda: None, *, max_cells=24):
    """Plant up to max_cells (1..24) using this caller's live lease; never harvest."""
    layout = plan(request)
    if type(max_cells) is not int or not 1 <= max_cells <= 24:
        raise ValueError('Farm cell budget is limited to 1..24')
    directory = Path(out); directory.mkdir(parents=True, exist_ok=True)
    scope = {'server': c.server.strip().lower().removesuffix(':25565'), 'dimension': 'minecraft:overworld', 'layout': layout}
    identity = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
    path = directory / ('potato-farm-' + identity + '.json')
    book = json.loads(path.read_text()) if path.exists() else {'schema': 1, 'scope': scope, 'world_session': c.world, 'cells': {}, 'pending': None}
    def result(code=None, detail=''):
        planted = sum(r.get('planted') is True for r in book['cells'].values())
        return {'phase': 'done' if code is None else 'waiting', 'code': code, 'detail': detail,
                'planted_cells': planted, 'target_cells': len(layout['cells']), 'journal': str(path),
                'verification_scope': PROOF_SCOPE, 'server_verified': False, 'automatic_retry_allowed': False}
    if book.get('scope') != scope or book.get('world_session') != c.world:
        return result('WAIT_CONTROL', 'Saved farm world/scope changed; explicit recovery is required')
    if book.get('pending'):
        return result('WAIT_RECONCILE', 'An inventory/till/plant action is unresolved; no repeated action sent')
    try:
        checkpoint(); initial = c.status()
        hurt = book.setdefault('recent_hurt_at', initial.get('recent_hurt_at'))
        if type(hurt) is not int:
            raise FarmWait('WAIT_SAFETY', 'Recent injury marker is unavailable')
        proxy = _GuardedClient(c, checkpoint, hurt); _gate(c, initial, hurt)
        initial_counts = _counts(initial)
        if book.get('complete') and all(book['cells'].get(_key(p), {}).get('planted') is True for p in layout['cells']):
            # A completed planting receipt does not freeze the player's potato
            # inventory forever: later harvest/cooking/trades are separate work.
            first, _ = _survey(proxy, layout, book)
            second, _ = _survey(proxy, layout, book)
            if second['time'] <= first['time']:
                raise FarmWait('WAIT_SCAN', 'Completed field re-audit did not advance')
            book['completion_reaudit'] = {'observed_times': [first['time'], second['time']],
                                         'current_carried_potatoes': initial_counts[POTATO]}
            write_json(path, book)
            return result()
        book.setdefault('potatoes_before', initial_counts[POTATO]); write_json(path, book)
        if initial_counts[POTATO] != book['potatoes_before'] - sum(r.get('planted') is True for r in book['cells'].values()):
            raise FarmWait('WAIT_RECONCILE', 'Potato stock differs from saved exact planting consumption')
        snapshot, rows = _survey(proxy, layout, book)
        remaining = [p for p in layout['cells'] if not book['cells'].get(_key(p), {}).get('planted')]
        if initial_counts[POTATO] < len(remaining):
            raise FarmWait('WAIT_POTATO', 'Need actual carried potatoes for all remaining cells')
        batch = remaining[:max_cells]
        tills = [p for p in batch if _properties(rows[tuple(p)], 'farmland', 'moisture', 7) is None]
        if tills:
            _hoe(proxy, len(tills))
        # Till the selected batch first, then select a carried potato stack once.
        # No cursor clicks or per-cell potato splitting are necessary.
        work = [('till', p) for p in tills] + [('plant', p) for p in batch]
        for index, (operation, pos) in enumerate(work):
            snapshot, rows = _survey(proxy, layout, book)
            player = snapshot.get('pos')
            if (not isinstance(player, list) or len(player) != 3
                    or math.dist([player[0], player[1]+1.62, player[2]], [pos[0]+.5, pos[1]+1, pos[2]+.5]) > 4.2):
                raise FarmWait('WAIT_REACH', 'Pilot does not move; place the player within conservative interaction reach')
            book['pending'] = {'operation': 'prepare_' + operation, 'pos': pos[:], 'stage': 'before_hand'}; write_json(path, book)
            before = snapshot if operation == 'till' else _potato(proxy, snapshot)
            hand = before.get('hand') or {}
            if operation == 'till' and (hand.get('item') not in HOES or hand.get('count') != 1
                    or type(hand.get('durability')) is not int or hand['durability'] <= len(tills)-index):
                raise FarmWait('WAIT_HOE', 'Selected hoe changed or lacks reserved durability')
            before, fresh_rows = _survey(proxy, layout, book)
            hand = before.get('hand') or {}
            if (operation == 'plant' and (hand.get('item') != POTATO or hand.get('count', 0) < 1)
                    or operation == 'till' and (hand.get('item') not in HOES or hand.get('count') != 1)):
                raise FarmWait('WAIT_HAND', 'Fresh native held item no longer matches this operation')
            fresh_soil = fresh_rows[tuple(pos)]
            # Moisture changes naturally near the already-confirmed water source.
            # Use the newest exact state in the request rather than freezing old
            # moisture. A different kind of floor still stops before interaction.
            if (operation == 'plant' and _properties(fresh_soil, 'farmland', 'moisture', 7) is None
                    or operation == 'till' and _block(fresh_soil) not in ('minecraft:grass_block', 'minecraft:dirt')):
                book['pending'] = None; write_json(path, book)
                raise FarmWait('WAIT_SOIL', 'Floor kind changed before sending any world interaction')
            book['pending'] = {'operation': operation, 'pos': pos[:], 'expected_state': fresh_rows[tuple(pos)]['state'],
                               'before_counts': dict(_counts(before)), 'hand_before': before['hand'], 'stage': 'before_single_interact'}
            write_json(path, book); proxy.status()
            reply = c.request('interact', pos=pos, face='up', expected_state=fresh_rows[tuple(pos)]['state'], expected_hand=before['hand']['item'])
            book['pending']['native_receipt'] = {k: reply.get(k) for k in ('id', 'phase', 'detail', 'time')}; write_json(path, book)
            if reply.get('phase') != 'done':
                raise FarmWait('WAIT_RECONCILE', 'Single interact was not confirmed; no second use sent')
            times = []
            for _ in range(6):
                observed, observed_rows = _survey(proxy, layout, book)
                # The scan reply contains a native snapshot from this same tick.
                # status.json may still describe an older periodic observation.
                after = observed; proxy.status()
                if not action_proved(operation, pos, before, after, observed_rows):
                    times = []; continue
                if times and observed['time'] <= times[-1]:
                    times = []; continue
                times.append(observed['time'])
                if len(times) >= 2: break
            if len(times) < 2:
                raise FarmWait('WAIT_RECONCILE', 'Post-interaction floor/crop/count/durability proof is incomplete; only reads were repeated')
            record = book['cells'].setdefault(_key(pos), {})
            record[operation] = {'native_receipt': book['pending']['native_receipt'], 'observed_times': times,
                                 'before_counts': dict(_counts(before)), 'after_counts': dict(_counts(after)),
                                 'hand_before': before['hand'], 'hand_after': after['hand'],
                                 'expected_before_state': fresh_rows[tuple(pos)]['state'],
                                 'floor_after_state': observed_rows[tuple(pos)]['state'],
                                 'crop_after_state': observed_rows.get((pos[0], pos[1]+1, pos[2]), {}).get('state', 'Block{minecraft:air}'),
                                 'scope': PROOF_SCOPE}
            if operation == 'plant': record['planted'] = True
            book['pending'] = None; write_json(path, book)
        if len(remaining) > len(batch):
            return result('FARM_BATCH', 'Known cell budget completed; caller retains control')
        _survey(proxy, layout, book)
        book['complete'] = True; write_json(path, book)
        return result()
    except FarmWait as error:
        book['last_wait'] = {'code': error.code, 'detail': str(error)}; write_json(path, book)
        return result(error.code, str(error))
    except Exception as error:
        # Includes cancellation/handoff and uncertain native/IO exceptions. No cleanup
        # action can reconnect, move, repeat an interact or hide the saved pending step.
        return result('WAIT_CONTROL', type(error).__name__ + ': ' + str(error))
