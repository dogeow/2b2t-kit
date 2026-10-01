"""Small live harvests for natural dripstone blocks and giant mushroom stems.

Targets are absolute main-backpack totals, not depot totals. Only explicitly
authorized ``natural_source_regions`` with ``source=natural_survey`` are used.
Block states do not encode ownership: registration and protected footprints are
required in addition to the fresh natural context. No quarry support is assumed.
"""
import json
import math
from pathlib import Path

from drop_collection import collect_drop
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from work_access import approach_faces, ApproachUnavailable
from .acquisition import NATURAL, FALLING
from .colored_sources import _name, _point, _protected, _safe
from .protocol import JobBlocked, JobPaused

OUTPUTS = frozenset(('minecraft:dripstone_block', 'minecraft:mushroom_stem'))
TARGET_SCOPE = 'absolute_backpack'
CAPS = {'minecraft:red_mushroom_block', 'minecraft:brown_mushroom_block'}
SOIL = {'minecraft:dirt', 'minecraft:grass_block', 'minecraft:podzol', 'minecraft:mycelium'}
CONTEXT = NATURAL | CAPS | {'minecraft:mushroom_stem', 'minecraft:mycelium'}
SOFT = {'minecraft:'+n for n in ('short_grass', 'tall_grass', 'fern', 'large_fern',
                               'brown_mushroom', 'red_mushroom')}
HAZARDS = FALLING | {'minecraft:pointed_dripstone', 'minecraft:cobweb', 'minecraft:powder_snow',
                     'minecraft:fire', 'minecraft:soul_fire', 'minecraft:magma_block'}


def _wait(item, target, code='WAIT_SOURCE', detail='No live authorized dry natural source'):
    return {'phase': 'waiting', 'code': code, 'detail': detail, 'item': item,
            'target_scope': TARGET_SCOPE, 'requirements': {item: target}, 'ai_calls': 0}


def _regions(profile, item):
    for r in profile.get('natural_source_regions', []):
        if not isinstance(r, dict) or r.get('item') != item or r.get('authorized') is not True:
            continue
        lo, hi = r.get('min'), r.get('max')
        if (r.get('source') != 'natural_survey' or not _point(lo) or not _point(hi)
                or any(lo[i] > hi[i] or hi[i]-lo[i] > 15 for i in range(3))
                or not -64 <= lo[1] <= hi[1] <= 319):
            continue
        yield r


def _scan(c, low, high, checkpoint):
    checkpoint()
    reply = c.request('scan', min=low, max=high, details=True)
    if (reply.get('world_session') != c.world or reply.get('phase') not in (None, 'done')
            or reply.get('unloaded_chunks', 0) or not isinstance(reply.get('blocks'), list)):
        return None
    seen = set()
    for row in reply['blocks']:
        pos = row.get('pos') if isinstance(row, dict) else None
        if (not _point(pos) or tuple(pos) in seen or not _name(row)
                or not all(low[i] <= pos[i] <= high[i] for i in range(3))
                or any(type(row.get(k)) is not bool for k in ('solid', 'fluid', 'block_entity', 'passable'))):
            return None
        seen.add(tuple(pos))
    return reply['blocks']


def _dry_natural(rows):
    return rows is not None and all(
        not r['fluid'] and not r['block_entity'] and _name(r) not in HAZARDS
        and (_name(r) in CONTEXT or _name(r) in ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air')
             or _name(r) in SOFT and not r['solid'] and r['passable'])
        for r in rows)


def _giant_mushroom(rows, pos):
    column = sorted(r['pos'][1] for r in rows if _name(r) == 'minecraft:mushroom_stem'
                    and r['pos'][0] == pos[0] and r['pos'][2] == pos[2])
    if len(column) < 2 or any(b != a+1 for a, b in zip(column, column[1:])):
        return False
    by = {tuple(r['pos']): r for r in rows}
    floor = by.get((pos[0], column[0]-1, pos[2]))
    return (floor is not None and _name(floor) in SOIL and floor['solid']
            and any(_name(r) in CAPS and 0 < r['pos'][1]-column[-1] <= 15
                    and abs(r['pos'][0]-pos[0]) <= 3 and abs(r['pos'][2]-pos[2]) <= 3 for r in rows))


def _tool(state, item):
    kind = 'axe' if item == 'minecraft:mushroom_stem' else 'pickaxe'
    candidates = [r for r in state.get('inventory', []) if 0 <= r.get('slot', -1) < 36
                  and r.get('count') == 1 and r.get('item') in ('minecraft:diamond_'+kind, 'minecraft:netherite_'+kind)
                  and r.get('durability', 0) >= 33 and r.get('max_durability', 0) > 0
                  and (item != 'minecraft:mushroom_stem' or any(
                      e.get('id') == 'minecraft:silk_touch' and e.get('level', 0) >= 1
                      for e in r.get('enchantments', [])))]
    return max(candidates, key=lambda r: r['durability']) if candidates else None


def _hand_matches(state, tool, selected, *, mined=False):
    hand = state.get('hand', {})
    return (state.get('selected_slot') == selected and hand.get('item') == tool['item']
            and hand.get('count') == 1 and hand.get('max_durability') == tool['max_durability']
            and hand.get('enchantments', []) == tool.get('enchantments', [])
            and type(hand.get('durability')) is int
            and tool['durability']-(1 if mined else 0) <= hand['durability'] <= tool['durability'])


def run(c, profile, item, target_count, out, checkpoint):
    """Harvest at most four proved blocks per call using the same owned Backend.

    Native mine_block has no continuous Silk-Axe lock. We verify the actual hand
    before/after and require the real one-stem drop; a changed tool or unknown
    receipt remains WAIT_RECONCILE and is never retried or called completed.
    """
    if item not in OUTPUTS or type(target_count) is not int or not 1 <= target_count <= 2304:
        raise ValueError('Expected natural block and absolute backpack target 1..2304')
    backend = getattr(c, 'natural_backend', None) or getattr(c, 'material_backend', None)
    if backend is None or getattr(backend, 'client', None) is not c or backend.profile != profile:
        raise JobBlocked('Natural block pipeline requires the same existing Backend.client/profile')
    world = c.world
    def state():
        checkpoint(); s = c.status()
        if s.get('world_session') != world or c.world != world or s.get('manual_movement'):
            raise JobPaused('Natural block world or manual control changed')
        if (not _safe(s, world) or s.get('dimension') != profile.get('dimension')
                or str(s.get('server', '')).lower().removesuffix(':25565') != profile.get('server', '').lower().removesuffix(':25565')):
            return None
        room_for_item(s, item)  # Reject partial/duplicate backpack snapshots.
        return s
    first = state()
    if first is None:
        return _wait(item, target_count, 'WAIT_SAFETY')
    out = Path(out); out.mkdir(parents=True, exist_ok=True); path = out/'natural-block-pipeline.json'
    if path.exists():
        if path.stat().st_size > 1_000_000:
            raise JobBlocked('Natural block journal exceeds bounded read limit')
        try:
            book = json.loads(path.read_text())
        except (OSError, ValueError) as error:
            raise JobBlocked('Natural block journal cannot be parsed') from error
    else:
        book = {'schema': 1, 'world_session': world, 'item': item, 'target': target_count,
                'target_scope': TARGET_SCOPE, 'pending': None, 'receipts': []}
    if not isinstance(book, dict) or not isinstance(book.get('receipts'), list):
        raise JobBlocked('Natural block journal must contain an object/receipts list')
    if any(book.get(k) != v for k, v in (('schema', 1), ('world_session', world), ('item', item),
                                        ('target', target_count), ('target_scope', TARGET_SCOPE))):
        raise JobPaused('Natural source journal world/item/target changed')
    if book.get('pending'):
        return _wait(item, target_count, 'WAIT_RECONCILE', 'Prior natural-block action uncertain; no replay')
    if book.get('complete') and inventory_counts(first)[item] < target_count:
        return {'phase': 'blocked', 'code': 'COMPLETED_RECEIPT', 'item': item,
                'target_scope': TARGET_SCOPE, 'detail': 'Completed output subsequently moved; use a new batch journal'}
    if inventory_counts(first)[item] >= target_count:
        book.update(complete=True, verified_count=inventory_counts(first)[item]); write_json(path, book)
        return {'phase': 'done', 'item': item, 'target_scope': TARGET_SCOPE,
                'count': inventory_counts(first)[item], 'ai_calls': 0}
    regions = list(_regions(profile, item))
    if not regions:
        return _wait(item, target_count)
    if _tool(first, item) is None:
        return _wait(item, target_count, 'WAIT_TOOL', 'Need actual durable Silk Touch axe' if item.endswith('mushroom_stem') else 'Need actual durable pickaxe')
    mined = 0
    for region in regions:
        rows = _scan(c, region['min'], region['max'], checkpoint)
        if not _dry_natural(rows):
            continue
        candidates = sorted((r for r in rows if _name(r) == item), key=lambda r: -r['pos'][1])
        for candidate in candidates:
            s = state()
            if s is None:
                return _wait(item, target_count, 'WAIT_SAFETY')
            pos = candidate['pos']
            if _protected(pos, profile, s):
                continue
            current = _scan(c, region['min'], region['max'], checkpoint)
            target = next((r for r in current or [] if r['pos'] == pos and _name(r) == item), None)
            if (not _dry_natural(current) or target is None
                    or item == 'minecraft:mushroom_stem' and not _giant_mushroom(current, pos)):
                continue
            local = _scan(c, [v-2 for v in pos], [v+2 for v in pos], checkpoint)
            if not _dry_natural(local):
                continue
            if room_for_item(s, item) < 1:
                return _wait(item, target_count, 'WAIT_CAPACITY')
            book['pending'] = {'kind': 'approach', 'pos': pos, 'expected_state': target['state']}
            write_json(path, book)
            backend.prepare_travel()
            try:
                face = approach_faces(c, pos, target['state'], ('up', 'north', 'south', 'west', 'east'), seconds=45)
            except ApproachUnavailable:
                book['pending'] = None; write_json(path, book)
                continue
            s = state()
            if s is None or _protected(pos, profile, s):
                return _wait(item, target_count, 'WAIT_RECONCILE', 'Source approach scope changed')
            tool = _tool(s, item)
            if tool is None:
                book['pending'] = None; write_json(path, book)
                return _wait(item, target_count, 'WAIT_TOOL')
            book['pending'].update(kind='select_tool', tool=tool); write_json(path, book)
            c.checked('select_item', item=tool['item'], slot=tool['slot'])
            s = state(); selected = tool['slot'] if tool['slot'] < 9 else 5
            if s is None or not _hand_matches(s, tool, selected):
                return _wait(item, target_count, 'WAIT_RECONCILE', 'Actual selected tool metadata differs')
            local = _scan(c, [v-2 for v in pos], [v+2 for v in pos], checkpoint)
            live = next((r for r in local or [] if r['pos'] == pos), None)
            if not _dry_natural(local) or live is None or live['state'] != target['state']:
                book['pending'] = None; write_json(path, book)
                continue
            s = state()
            if s is None or _protected(pos, profile, s) or not _hand_matches(s, tool, selected):
                return _wait(item, target_count, 'WAIT_RECONCILE', 'Source or tool changed before mining')
            before = inventory_counts(s)[item]
            old = {e['uuid']: e['stack'] for e in s.get('entities', []) if e.get('type') == 'minecraft:item'
                   and e.get('stack', {}).get('item') == item and isinstance(e.get('uuid'), str)}
            book['pending'].update(kind='mine', before=before, old_drops=old, selected=selected)
            write_json(path, book); checkpoint()
            try:
                reply = c.request('mine_block', pos=pos, face=face, expected_state=live['state'], seconds=20)
            finally:
                book['pending']['request_id'] = getattr(c, 'last', None); write_json(path, book)
            if (reply.get('phase') != 'done' or reply.get('id') != getattr(c, 'last', None)
                    or reply.get('world_session') != world):
                return _wait(item, target_count, 'WAIT_RECONCILE', 'Mining receipt not owned/complete')
            s = state()
            if s is None or not _hand_matches(s, tool, selected, mined=True):
                return _wait(item, target_count, 'WAIT_RECONCILE', 'Tool/safety changed during mining')
            for drop in s.get('entities', []):
                if (drop.get('type') != 'minecraft:item' or drop.get('stack', {}).get('item') != item
                        or drop.get('uuid') in old or drop.get('stack', {}).get('count') != 1
                        or not isinstance(drop.get('uuid'), str) or len(drop.get('pos', [])) != 3
                        or math.dist(drop['pos'], pos) > 3 or _protected(drop['pos'], profile, s)):
                    continue
                point = [math.floor(v) for v in drop['pos']]
                if not _dry_natural(_scan(c, [v-1 for v in point], [v+1 for v in point], checkpoint)):
                    continue
                book['pending'].update(kind='pickup', uuid=drop['uuid']); write_json(path, book)
                checkpoint()
                if not collect_drop(c, drop, s):
                    return _wait(item, target_count, 'WAIT_RECONCILE', 'New source drop pickup not confirmed')
            final = state(); removed = _scan(c, pos, pos, checkpoint)
            remaining = {e['uuid']: e['stack'] for e in (final or {}).get('entities', [])
                         if e.get('type') == 'minecraft:item' and isinstance(e.get('uuid'), str)}
            after = inventory_counts(final)[item] if final else before
            if (final is None or removed is None or removed or after != before+1
                    or any(remaining.get(uuid) != stack for uuid, stack in old.items())
                    or not _hand_matches(final, tool, selected, mined=True)):
                return _wait(item, target_count, 'WAIT_RECONCILE', 'Source removal/new one-item gain not proved')
            book['receipts'].append({**book['pending'], 'after': after, 'gained': 1})
            book['pending'] = None; write_json(path, book); mined += 1
            if after >= target_count:
                book.update(complete=True, verified_count=after); write_json(path, book)
                return {'phase': 'done', 'item': item, 'target_scope': TARGET_SCOPE, 'count': after, 'ai_calls': 0}
            if mined == 4:
                return _wait(item, target_count, 'SOURCE_BATCH', 'Four actual source blocks confirmed; continue same journal')
    return _wait(item, target_count)
