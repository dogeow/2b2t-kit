"""Feed one named adult pair normally and observe one new baby; no movement."""
import hashlib
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_jobs.protocol import JobPaused
from potato_farm import FarmWait, valid_entity_scope
from potato_harvest import _counts, _lease

FOODS = {'minecraft:cow': 'minecraft:wheat', 'minecraft:sheep': 'minecraft:wheat',
         'minecraft:chicken': 'minecraft:wheat_seeds'}
PROOF_SCOPE = 'two_distinct_loaded_client_food_delta_frames_then_new_nearby_baby_uuid_frames_not_server_parentage_ack'


def plan(request):
    if not isinstance(request, dict) or request.get('authorized') is not True:
        raise ValueError('An explicitly authorized breeding request is required')
    species, adults, center = request.get('species'), request.get('adults'), request.get('center')
    radius = request.get('radius', 4)
    if (species not in FOODS or not isinstance(adults, list) or len(adults) != 2
            or any(not isinstance(u, str) or not 1 <= len(u) <= 64 for u in adults) or adults[0] == adults[1]
            or not isinstance(center, list) or len(center) != 3
            or any(type(v) is not int or abs(v) > 30_000_000 for v in center)
            or not -63 <= center[1] <= 316 or type(radius) is not int or not 1 <= radius <= 4):
        raise ValueError('Choose one cow/sheep/chicken adult UUID pair and a bounded integer center/radius1..4')
    return {'species': species, 'adults': adults[:], 'center': center[:], 'radius': radius,
            'scan_min': [center[0]-radius, center[1]-1, center[2]-radius],
            'scan_max': [center[0]+radius, center[1]+3, center[2]+radius], 'food': FOODS[species]}


def _point(value):
    return (isinstance(value, list) and len(value) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in value))


def entity_rows(state, layout):
    rows = state.get('scan_entities')
    if (not valid_entity_scope(state.get('scan_entity_scope')) or not isinstance(rows, list)
            or not isinstance(state.get('blocks'), list) or state.get('unloaded_chunks', 0)):
        raise FarmWait('WAIT_SCAN', 'Fresh detailed bounded native entity scan is required')
    result = {}; ids = set()
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('uuid'), str) or not row['uuid']
                or row['uuid'] in result or type(row.get('id')) is not int or row['id'] in ids
                or not isinstance(row.get('type'), str) or not _point(row.get('pos'))
                or type(row.get('alive')) is not bool or type(row.get('visible')) is not bool
                or row['type'] == layout['species'] and type(row.get('is_baby')) is not bool):
            raise FarmWait('WAIT_SCAN', 'Native entity identity, position or live age metadata is incomplete')
        result[row['uuid']] = row; ids.add(row['id'])
    return result


def _pair(state, rows, layout, *, reach=False):
    pair = [rows.get(uuid, {}) for uuid in layout['adults']]
    for adult in pair:
        if (adult.get('type') != layout['species'] or adult.get('alive') is not True
                or adult.get('is_baby') is not False or not _point(adult.get('pos'))
                or not all(a <= b < d+1 for a, b, d in zip(layout['scan_min'], adult['pos'], layout['scan_max']))):
            raise FarmWait('WAIT_PAIR', 'Both selected UUIDs must remain actual live adults in the authorized region')
        if reach:
            player = state.get('pos'); lift = {'minecraft:cow':.77,'minecraft:sheep':.715,'minecraft:chicken':.385}[layout['species']]
            if (adult.get('visible') is not True or not _point(player)
                    or math.dist([player[0], player[1]+1.62, player[2]],
                                 [adult['pos'][0], adult['pos'][1]+lift, adult['pos'][2]]) > 2.8):
                raise FarmWait('WAIT_REACH', 'Selected adult must have fresh LOS and conservative normal entity reach')
    return pair


def run(c, request, out, checkpoint=lambda: None, *, birth_wait_seconds=12,
        sleep=time.sleep, monotonic=time.monotonic):
    """A single pair gets exactly two food uses; unresolved uses never replay.

    The native receipt says only an entity interaction was sent. No client age,
    love state or breeding cooldown is assigned or inferred by this helper.
    """
    layout = plan(request)
    if type(birth_wait_seconds) not in (int, float) or not 0 < birth_wait_seconds <= 12:
        raise ValueError('Birth read wait must be in (0, 12] seconds')
    directory = Path(out); directory.mkdir(parents=True, exist_ok=True)
    scope = {'server': c.server.strip().lower().removesuffix(':25565'), 'layout': layout}
    identity = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
    path = directory / ('animal-breed-'+identity+'.json')
    book = json.loads(path.read_text()) if path.exists() else {
        'schema': 1, 'scope': scope, 'world_session': c.world, 'feeds': {}, 'pending': None}

    def save(): write_json(path, book)
    def result(code=None, detail=''):
        return {'phase': 'done' if code is None else 'waiting', 'code': code, 'detail': detail,
                'fed_adults': len(book['feeds']), 'observed_births': int(book.get('complete') is True),
                'baby_uuid': book.get('baby', {}).get('uuid'), 'journal': str(path),
                'verification_scope': PROOF_SCOPE, 'server_verified': False, 'automatic_retry_allowed': False}
    if book.get('scope') != scope or book.get('world_session') != c.world:
        return result('WAIT_CONTROL', 'Saved breeding belongs to another world or scope')
    if book.get('pending'):
        return result('WAIT_RECONCILE', 'A saved food selection/use is unresolved; no repeated feeding')
    try:
        checkpoint(); initial = c.status()
        hurt = book.setdefault('recent_hurt_at', initial.get('recent_hurt_at'))
        if type(hurt) is not int:
            raise FarmWait('WAIT_SAFETY', 'Original injury marker is unavailable')

        def safe(state):
            _lease(c, state, hurt)
            if state.get('health') != 20 or state.get('native_material_busy') is True:
                raise FarmWait('WAIT_SAFETY', 'Exact HP20 and idle native material control are required')

        def status():
            checkpoint(); state = c.status(); safe(state); _counts(state); return state

        def survey():
            before = status()
            state = c.request('scan', min=layout['scan_min'], max=layout['scan_max'], details=True)
            safe(state); _counts(state)
            if state['time'] <= before['time']:
                raise FarmWait('WAIT_SCAN', 'Scan is not a later native observation')
            rows = entity_rows(state, layout); _pair(state, rows, layout)
            return state, rows

        safe(initial); current, rows = survey()
        if book.get('complete'):
            baby = rows.get(book['baby']['uuid'], {})
            if baby.get('type') != layout['species'] or baby.get('alive') is not True:
                raise FarmWait('WAIT_BABY', 'Historical baby UUID is no longer observed alive in this region')
            reused = result(); reused.update(prior_receipt_reuse=True, current_context_verified=True)
            return reused
        counts = _counts(current)
        if 'before_counts' not in book:
            if counts[layout['food']] < 2:
                raise FarmWait('WAIT_FOOD', 'Two actual carried breeding-food items are required')
            book['before_counts'] = dict(counts)
            book['pre_birth_uuids'] = sorted(set(rows) | {e['uuid'] for e in current.get('entities', []) if isinstance(e.get('uuid'), str)})
            save()
        expected = book['before_counts'].copy(); expected[layout['food']] -= len(book['feeds'])
        if not expected[layout['food']]: del expected[layout['food']]
        if dict(counts) != expected:
            raise FarmWait('WAIT_RECONCILE', 'Actual stock differs from saved exact food consumption')
        for uuid in layout['adults']:
            if uuid in book['feeds']: continue
            before = status(); hand = before.get('hand') or {}
            if hand.get('item') != layout['food'] or hand.get('count', 0) < 1:
                source = max((r for r in before['inventory'] if r['slot'] < 36
                              and r['item'] == layout['food'] and r['count'] > 0), key=lambda r:r['count'], default=None)
                if source is None: raise FarmWait('WAIT_FOOD', 'Actual carried breeding food is unavailable')
                book['pending'] = {'operation': 'select_item', 'item': layout['food'], 'slot': source['slot']}; save()
                reply = c.request('select_item', item=layout['food'], slot=source['slot']); selected = status()
                if (reply.get('phase') != 'done' or _counts(selected) != _counts(before)
                        or selected.get('hand', {}).get('item') != layout['food'] or selected['hand'].get('count', 0) < 1):
                    raise FarmWait('WAIT_RECONCILE', 'Food selection outcome is unknown')
                book['pending'] = None; save()
            before, rows = survey(); _pair(before, rows, layout, reach=True)
            hand = before.get('hand') or {}; adult = rows[uuid]
            if hand.get('item') != layout['food'] or type(hand.get('count')) is not int or hand['count'] < 1:
                raise FarmWait('WAIT_HAND', 'Fresh actual held breeding food is unavailable')
            ready = status()
            if (_counts(ready) != _counts(before) or ready.get('hand') != before.get('hand')
                    or ready.get('selected_slot') != before.get('selected_slot')):
                raise FarmWait('WAIT_HAND', 'Held food or inventory changed before the single entity interaction')
            book['pending'] = {'operation': 'feed', 'uuid': uuid, 'entity_id': adult['id'],
                               'before_counts': dict(_counts(before)), 'hand_before': hand,
                               'before_time': before['time']}; save()
            reply = c.request('interact_entity', entity_id=adult['id'], expected_uuid=uuid)
            book['pending']['receipt'] = {k: reply.get(k) for k in ('id', 'phase', 'detail', 'time')}; save()
            if reply.get('phase') != 'done':
                raise FarmWait('WAIT_RECONCILE', 'Single feeding intent is unknown; do not repeat it')
            times = []
            for _ in range(8):
                after, _ = survey(); target = _counts(before); target[layout['food']] -= 1
                if not target[layout['food']]: del target[layout['food']]
                after_hand = after.get('hand') or {}; left = hand['count']-1
                if (_counts(after) == target and after_hand.get('count') == left
                        and after_hand.get('item') == (layout['food'] if left else 'minecraft:air')
                        and after.get('selected_slot') == before.get('selected_slot')):
                    if not times or after['time'] > times[-1]: times.append(after['time'])
                    if len(times) == 2: break
                else: times = []
            if len(times) != 2:
                raise FarmWait('WAIT_RECONCILE', 'PASS/receipt without exact food-minus-one and two fresh hand/count frames is not feeding proof')
            book['feeds'][uuid] = {**book['pending'], 'observed_times': times, 'after_counts': dict(_counts(after))}
            book['pending'] = None; save()
        book['awaiting_birth'] = True; save(); deadline = monotonic()+birth_wait_seconds
        candidate = None; times = []
        for _ in range(64):
            after, rows = survey(); adults = _pair(after, rows, layout)
            expected = book['before_counts'].copy(); expected[layout['food']] -= 2
            if not expected[layout['food']]: del expected[layout['food']]
            if dict(_counts(after)) != expected:
                raise FarmWait('WAIT_RECONCILE', 'Both proven food consumptions must remain actual while awaiting birth')
            babies = [r for u, r in rows.items() if u not in book['pre_birth_uuids']
                      and r.get('type') == layout['species'] and r.get('alive') is True and r.get('is_baby') is True
                      and all(math.dist(r['pos'], a['pos']) <= 4 for a in adults)]
            if len(babies) > 1:
                raise FarmWait('WAIT_BABY', 'Multiple new babies make this bounded birth observation ambiguous')
            if babies:
                baby = babies[0]
                if candidate != baby['uuid']: candidate = baby['uuid']; times = []
                if not times or after['time'] > times[-1]: times.append(after['time'])
                if len(times) == 2:
                    book['baby'] = {**baby, 'observed_times': times, 'near_adults': layout['adults']}
                    book['complete'] = True; save(); return result()
            else: candidate = None; times = []
            if monotonic() >= deadline: break
            sleep(min(.2, max(0, deadline-monotonic())))
        raise FarmWait('WAIT_BABY', 'Two feeds are proven but no unique new nearby baby has two fresh frames; only reads may continue')
    except JobPaused:
        raise
    except FarmWait as error:
        book['last_wait'] = {'code': error.code, 'detail': str(error)}; save()
        return result(error.code, str(error))
    except Exception as error:
        book['last_wait'] = {'code': 'WAIT_CONTROL', 'detail': type(error).__name__+': '+str(error)}; save()
        return result('WAIT_CONTROL', book['last_wait']['detail'])
