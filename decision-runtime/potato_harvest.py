"""One bounded harvest/replant cycle with the caller's already-owned Client.

Only native scan, select_item, interact and mine_block are issued directly. An
optional caller-owned pickup callback may perform its bounded normal movement;
no controller, reconnect, safety unlock or guessed crop yield is created here.
"""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_jobs.protocol import JobPaused
from material_trip_policy import room_for_item
from potato_farm import (FarmWait, POTATO, _counts as _carried_counts, _gate, _key,
                         _properties, action_proved, crop_descriptor, plan as farm_plan, survey_rows, valid_entity_scope)

BONE = 'minecraft:bone_meal'
POISON = 'minecraft:poisonous_potato'
PROOF_SCOPE = 'two_distinct_loaded_client_crop_and_actual_carried_stock_observations_not_server_ack'


def _counts(state):
    counts = _carried_counts(state)
    if len(state['inventory']) != 43 or {r['slot'] for r in state['inventory']} != set(range(43)):
        raise FarmWait('WAIT_INVENTORY', 'Complete actual inventory slots 0..42 are required')
    return counts


def plan(request):
    """Authorize floor cells in a source-water-centered radius 1..2 field."""
    layout = farm_plan(request)
    x, y, z = layout['center']
    cells = request.get('cells', [[x+1, y, z], [x-1, y, z],
                                  [x, y, z+1], [x, y, z-1]])
    if (not isinstance(cells, list) or not 1 <= len(cells) <= 24
            or any(not isinstance(p, list) or len(p) != 3
                   or any(type(v) is not int for v in p) or p not in layout['cells'] for p in cells)
            or len({tuple(p) for p in cells}) != len(cells)):
        raise ValueError('Harvest cells must be unique authorized floor cells within the declared field')
    layout['harvest_cells'] = [p[:] for p in cells]
    return layout


def _lease(c, state, hurt):
    _gate(c, state, hurt)
    heartbeat = getattr(c, 'heartbeat', None)
    lease = state.get('supervision_lease') or {}
    if (heartbeat is None or not isinstance(getattr(heartbeat, 'id', None), str)
            or not heartbeat.id
            or lease.get('id') != heartbeat.id or lease.get('remote_finish') != 'guard'):
        raise FarmWait('WAIT_CONTROL', 'Caller must retain its exact live material heartbeat lease and guard finish')


def _reach(state, floor):
    player = state.get('pos')
    if (not isinstance(player, list) or len(player) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in player)
            or math.dist([player[0], player[1]+1.62, player[2]],
                         [floor[0]+.5, floor[1]+1.5, floor[2]+.5]) > 4.2):
        raise FarmWait('WAIT_REACH', 'Place the player within normal interaction reach; this helper does not move')


def _drop_ids(state):
    entities = state.get('entities')
    if not isinstance(entities, list):
        raise FarmWait('WAIT_ENTITY', 'Fresh nearby entity identities are unavailable')
    ids = set()
    for row in entities:
        if not isinstance(row, dict):
            raise FarmWait('WAIT_ENTITY', 'Malformed nearby entity observation')
        if row.get('type') == 'minecraft:item':
            if not isinstance(row.get('uuid'), str) or not row['uuid']:
                raise FarmWait('WAIT_ENTITY', 'Item identity is unavailable')
            ids.add(row['uuid'])
    return ids


def _owned_drops(state, active, before_ids, known_loot, *, crop='potato'):
    descriptor = crop_descriptor(crop)
    accepted_items = {descriptor.harvest_item, *descriptor.harvest_byproducts}
    entities = state.get('scan_entities')
    if not valid_entity_scope(state.get('scan_entity_scope')) or not isinstance(entities, list):
        raise FarmWait('WAIT_SCAN', 'Fresh bounded entity scan is unavailable')
    nearby = {row.get('uuid'): row for row in state.get('entities', [])}
    owned = []
    for row in entities:
        if not isinstance(row, dict):
            raise FarmWait('WAIT_ENTITY', 'Malformed scoped entity observation')
        uuid = row.get('uuid'); matching = nearby.get(uuid, {}); stack = matching.get('stack') or {}
        pos = row.get('pos')
        origin = known_loot.get(uuid, {}).get('floor', active)
        if (origin is None or row.get('type') != 'minecraft:item'
                or not isinstance(uuid, str) or not uuid or uuid in before_ids and uuid not in known_loot
                or type(row.get('id')) is not int or row['id'] != matching.get('id')
                or matching.get('type') != 'minecraft:item'
                or stack.get('item') not in accepted_items
                or type(stack.get('count')) is not int or not 1 <= stack['count'] <= 64
                or not isinstance(pos, list) or len(pos) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in pos)
                or math.dist(pos, [origin[0]+.5, origin[1]+1.5, origin[2]+.5]) > 2
                or uuid in known_loot and stack['item'] != known_loot[uuid]['item']):
            raise FarmWait('WAIT_ENTITY', 'Only fresh identified near-target '+descriptor.name+' loot may intersect the field')
        owned.append({'uuid': uuid, 'id': row['id'], 'type': 'minecraft:item', 'item': stack['item'],
                      'count': stack['count'], 'remaining_count': stack['count'],
                      'stack': {'item': stack['item'], 'count': stack['count']},
                      'pos': pos[:], 'floor': origin[:]})
    return owned


def _same_except(before, after, allowed):
    a, b = _counts(before), _counts(after)
    return all(a[item] == b[item] for item in a.keys() | b.keys() if item not in allowed)



def _registered_wheat(c, request, journal):
    """The harvest uses an existing explicit planting registry, never invents one."""
    root = getattr(c, 'root', None)
    if root is None:
        raise FarmWait('WAIT_REGISTERED_FARM', 'Registered wheat farm root is required')
    layout = farm_plan(request)
    scope = {'server': c.server.strip().lower().removesuffix(':25565'),
             'dimension': 'minecraft:overworld', 'layout': layout}
    key = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
    registry = Path(root)/'farms'/key/'registry.json'
    try:
        if registry.stat().st_size > 1_000_000:
            raise ValueError('Registry exceeds limit')
        saved = json.loads(registry.read_text())
        if saved.get('scope') != scope or saved.get('world_session') != c.world:
            raise ValueError('Registry belongs to another layout/world')
        directory = Path(saved['directory'])
        planted_path = directory/('wheat-farm-'+key+'.json')
        if planted_path.stat().st_size > 4_000_000:
            raise ValueError('Planting journal exceeds limit')
        planted = json.loads(planted_path.read_text())
        if planted.get('scope') != scope or planted.get('world_session') != c.world:
            raise ValueError('Planting journal scope differs')
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise FarmWait('WAIT_REGISTERED_FARM', 'Existing wheat planting registration is unavailable: '+str(error)) from error
    if planted.get('pending') or planted.get('cleanup_pending'):
        raise FarmWait('WAIT_RECONCILE', 'Original wheat planting/cleanup is unresolved')
    if any(planted.get('cells', {}).get(_key(pos), {}).get('planted') is not True for pos in plan(request)['harvest_cells']):
        raise FarmWait('WAIT_REGISTERED_FARM', 'Harvest targets must be originally registered planted wheat cells')
    active = registry.parent/'harvest-active.json'
    if active.exists():
        prior = json.loads(active.read_text())
        prior_path = Path(prior['journal'])
        if prior_path.resolve() != Path(journal).resolve():
            previous = json.loads(prior_path.read_text())
            if previous.get('pending') or previous.get('cleanup_pending'):
                error = FarmWait('WAIT_RECONCILE', 'Another original wheat harvest is unresolved; reuse '+str(prior_path))
                error.active_journal = str(prior_path)
                raise error
    write_json(active, {'schema': 1, 'scope': scope, 'world_session': c.world, 'journal': str(Path(journal).resolve())})
    return {'registry': str(registry), 'planting_journal': str(planted_path), 'field_key': key}


def run(c, request, out, checkpoint=lambda: None, *, max_cells=4,
        bonemeal_budget=16, max_bonemeal_per_cell=4, pickup_seconds=6,
        pickup=None, sleep=time.sleep, monotonic=time.monotonic, _recover_only=False):
    """Grow optionally, harvest only fresh age=7, prove pickup, then reseed once.

    request['bonemeal'] must be True to use bone meal. Journal reuse continues
    only resolved work; an unresolved single action never dispatches again.
    Optional pickup(c, exact_owned_drop, fresh_observation) belongs to the caller;
    each UUID is offered once and its return is never accepted as pickup proof.
    """
    layout = plan(request)
    descriptor = crop_descriptor(request)
    wheat = descriptor.name == 'wheat'
    seed, produce = descriptor.item, descriptor.harvest_item
    loot_items = {produce, *descriptor.harvest_byproducts}
    for value, low, high in ((max_cells, 1, 4), (bonemeal_budget, 0, 16),
                             (max_bonemeal_per_cell, 0, 4)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError('Harvest budget is bounded to four cells and sixteen bone meal')
    if type(pickup_seconds) not in (int, float) or not 0 < pickup_seconds <= 6:
        raise ValueError('Automatic pickup read wait must be in (0, 6] seconds')
    if type(request.get('bonemeal', False)) is not bool:
        raise ValueError('Bone meal authorization must be boolean')
    if pickup is not None and not callable(pickup):
        raise ValueError('Pickup must be an explicitly supplied callback or None')
    directory = Path(out); directory.mkdir(parents=True, exist_ok=True)
    scope = {'server': c.server.strip().lower().removesuffix(':25565'),
             'layout': layout, 'bonemeal': request.get('bonemeal', False)}
    identity = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
    path = directory / (descriptor.name+'-harvest-' + identity + '.json')
    book = json.loads(path.read_text()) if path.exists() else {
        'schema': 1, 'scope': scope, 'world_session': c.world,
        'cells': {}, 'pending': None, 'bone_meal_used': 0}

    def save(): write_json(path, book)
    def result(code=None, detail=''):
        value = {'phase': 'done' if code is None else 'waiting', 'code': code, 'detail': detail,
                'harvested_replanted': sum(r.get('replanted') is True for r in book['cells'].values()),
                'target_cells': len(layout['harvest_cells']), 'bone_meal_used': book['bone_meal_used'],
                'potato_gain': sum(r.get('potato_gain', 0)-int(r.get('replanted', False))
                                   for r in book['cells'].values()),
                'journal': str(path), 'verification_scope': PROOF_SCOPE,
                'server_verified': False, 'automatic_retry_allowed': False}
        if wheat:
            value.pop('potato_gain')
            grains = sum(r.get('wheat_gain', 0) for r in book['cells'].values())
            value.update(crop='wheat', wheat_gain=grains, grain_gain=grains,
                         seed_gain=sum(r.get('seed_gain', 0)-int(r.get('replanted', False)) for r in book['cells'].values()),
                         verification_scope='native_single_crop_removal_ack_plus_two_distinct_client_grain_seed_and_field_observations')
            if book.get('active_journal'):value['active_journal'] = book['active_journal']
        return value

    if book.get('scope') != scope or book.get('world_session') != c.world:
        return result('WAIT_CONTROL', 'Saved harvest belongs to another world/scope')
    resume = book.get('pending')
    if resume and resume.get('operation') not in ('await_loot', 'await_replant'):
        return result('WAIT_RECONCILE', 'A saved single action is unresolved; no replay is sent')
    if _recover_only and (not resume or resume.get('operation') not in ('await_loot', 'await_replant')):
        return result('WAIT_RECONCILE', 'No proven harvested cell has a known loot/replant stage')
    try:
        checkpoint(); initial = c.status()
        hurt = book.setdefault('recent_hurt_at', initial.get('recent_hurt_at'))
        if type(hurt) is not int:
            raise FarmWait('WAIT_SAFETY', 'Injury marker is unavailable')
        if wheat:
            _lease(c, initial, hurt)
            book['registration'] = _registered_wheat(c, request, path)
            book.pop('active_journal', None)

        def status():
            checkpoint(); state = c.status(); _lease(c, state, hurt); _counts(state); return state

        def survey(active=None, before_ids=frozenset()):
            before = status()
            state = c.request('scan', min=layout['scan_min'], max=layout['scan_max'], details=True)
            _lease(c, state, hurt); _counts(state); _drop_ids(state)
            if state['time'] <= before['time']:
                raise FarmWait('WAIT_SCAN', 'Scan must be a later native frame')
            known_loot = {d['uuid']: d for r in book['cells'].values()
                          for d in r.get('harvest', {}).get('owned_loot', [])}
            known_loot.update({d['uuid']: d for d in (book.get('pending') or {}).get('owned_loot', [])})
            drops = _owned_drops(state, active, before_ids, known_loot, crop=descriptor)
            if active is None and any(d['item'] in (loot_items if wheat else {POTATO}) for d in drops):
                raise FarmWait('WAIT_LOOT', 'Previously harvested potatoes remain uncollected; no extra break')
            # The existing farm validator protects source, support, light and
            # headroom. Its entity policy is replaced only after scoped loot proof.
            known = {_key(p): {'planted': p != active} for p in layout['cells']}
            raw_rows = state.get('blocks')
            if isinstance(raw_rows, list) and active is not None:
                crop = [active[0], active[1]+1, active[2]]
                known[_key(active)]['planted'] = any(r.get('pos') == crop for r in raw_rows if isinstance(r, dict))
            rows = survey_rows({**state, 'scan_entities': []}, layout, known)
            for p in layout['cells']:
                if _properties(rows.get(tuple(p), {}), 'farmland', 'moisture', 7) is None:
                    raise FarmWait('WAIT_SOIL', 'Every field cell must remain actual farmland')
            return state, rows, drops

        def select(item):
            before = status()
            if (before.get('hand') or {}).get('item') == item and before['hand'].get('count', 0) > 0:
                return
            source = max((r for r in before['inventory'] if r['slot'] < 36
                          and r['item'] == item and r['count'] > 0), key=lambda r:r['count'], default=None)
            if source is None:
                raise FarmWait('WAIT_ITEM', 'No actual carried ' + item)
            prior_pending = book['pending']
            book['pending'] = {'operation': 'select_item', 'item': item, 'slot': source['slot'],
                               'after': prior_pending}; save()
            reply = c.request('select_item', item=item, slot=source['slot'])
            after = status()
            if (reply.get('phase') != 'done' or _counts(before) != _counts(after)
                    or after.get('hand', {}).get('item') != item or after['hand'].get('count', 0) < 1):
                raise FarmWait('WAIT_RECONCILE', 'Held item selection outcome is unknown')
            book['pending'] = prior_pending; save()

        def dispatch(operation, pos, before, rows, **params):
            if wheat:
                fresh, fresh_rows, fresh_drops = survey(pos if operation == 'plant' else None,
                    set((book.get('pending') or {}).get('pre_drop_ids', [])))
                if (_counts(fresh) != _counts(before) or fresh.get('hand') != before.get('hand')
                        or fresh.get('selected_slot') != before.get('selected_slot')):
                    raise FarmWait('WAIT_RECONCILE', 'Wheat inventory/hand changed before the single action')
                if fresh_drops:
                    raise FarmWait('WAIT_LOOT', 'Fresh wheat/seed drops must reconcile before another action')
                fresh_crop = (pos[0], pos[1]+1, pos[2])
                if operation == 'harvest' and _properties(fresh_rows.get(fresh_crop, {}), descriptor.block, 'age', 7) != 7:
                    raise FarmWait('WAIT_GROWTH', 'The original wheat crop is no longer exactly mature')
                if operation == 'plant' and fresh_crop in fresh_rows:
                    raise FarmWait('WAIT_AIR', 'The original wheat planting cell is no longer empty')
                if operation == 'bonemeal' and fresh_rows.get(fresh_crop, {}).get('state') != rows.get(fresh_crop, {}).get('state'):
                    raise FarmWait('WAIT_GROWTH', 'Wheat age changed before bone meal; observe again')
                before, rows = fresh, fresh_rows
            _reach(before, pos)
            target = pos if operation == 'plant' else [pos[0], pos[1]+1, pos[2]]
            book['pending'] = {'operation': operation, 'pos': pos[:],
                               'expected_state': rows[tuple(target)]['state'],
                               'before_counts': dict(_counts(before)), 'hand_before': before['hand'],
                               'before_inventory': before['inventory'],
                               'before_time': before['time'], 'pre_drop_ids': sorted(_drop_ids(before))}
            save(); status()
            op = 'mine_block' if operation == 'harvest' else 'interact'
            reply = c.request(op, pos=target, face='up', expected_state=rows[tuple(target)]['state'],
                              **({} if operation == 'harvest' else {'expected_hand': before['hand']['item']}), **params)
            book['pending']['receipt'] = {k: reply.get(k) for k in ('id', 'phase', 'detail', 'time')}; save()
            if reply.get('phase') != 'done':
                raise FarmWait('WAIT_RECONCILE', 'Single native action outcome is unknown; do not repeat')
            if wheat and operation == 'harvest':
                from terminal_confirmation import verified
                proof_keys = ('id','world_session','phase','server_confirmed','outcome_pending','confirmation_scope',
                              'server_update_seen','server_observed_state','native_sequence','server_ack_sequence','mining_target')
                book['pending']['native_mining_receipt'] = {key:reply.get(key) for key in proof_keys}; save()
                if not verified('mine_block', reply, c.world, getattr(c, 'last', None), {'pos':target}):
                    raise FarmWait('WAIT_RECONCILE', 'Wheat removal lacks its exact native server block/sequence confirmation')
                book['pending']['native_mining_confirmed'] = True; save()

        _lease(c, initial, hurt); start_counts = _counts(initial)
        if book.get('complete'):
            current, _, _ = survey()
            if _counts(current)[seed] < 4:
                raise FarmWait('WAIT_RESERVE', 'Current carried stock no longer retains the four-seed reserve' if wheat else 'Current carried stock no longer retains the four-potato reserve')
            reused = result()
            reused.update(prior_receipt_reuse=True, current_context_verified=True, current_observed_time=current['time'])
            if wheat:reused.update(current_carried_seeds=_counts(current)[seed], current_carried_wheat=_counts(current)[produce])
            else:reused['current_potatoes'] = _counts(current)[seed]
            return reused
        if start_counts[seed] < 5:
            raise FarmWait('WAIT_RESERVE', 'Five carried wheat seeds are required to retain four after one reseed' if wheat else 'Five carried potatoes are required to retain four after one reseed')
        book.setdefault(descriptor.before_key, start_counts[seed])
        if wheat:book.setdefault('wheat_before', start_counts[produce])
        save()
        if resume:
            if (resume.get('pos') not in layout['harvest_cells']
                    or resume.get('operation') == 'await_loot' and resume.get('crop_removed') is not True
                    or resume.get('operation') == 'await_replant'
                    and not book['cells'].get(_key(resume['pos']), {}).get('harvest')):
                raise FarmWait('WAIT_RECONCILE', 'Saved loot/replant stage lacks exact harvest evidence')
            survey(resume['pos'], set(resume.get('pre_drop_ids', [])))
        else:
            survey()
        remaining = [p for p in layout['harvest_cells'] if not book['cells'].get(_key(p), {}).get('replanted')]
        if resume and (not remaining or remaining[0] != resume['pos']):
            raise FarmWait('WAIT_RECONCILE', 'Saved harvested cell is not the next unresolved cell')
        for pos in remaining[:max_cells]:
            record = book['cells'].setdefault(_key(pos), {'bone_meal_used': 0})
            crop = (pos[0], pos[1]+1, pos[2])
            recovering = resume is not None and resume['pos'] == pos
            while not recovering:
                before, rows, _ = survey()
                age = _properties(rows.get(crop, {}), descriptor.block, 'age', descriptor.age_max)
                if age == 7: break
                if (not scope['bonemeal'] or record['bone_meal_used'] >= max_bonemeal_per_cell
                        or book['bone_meal_used'] >= bonemeal_budget):
                    raise FarmWait('WAIT_GROWTH', 'Fresh crop is immature or the authorized bone meal limit is reached')
                select(BONE); before, rows, _ = survey()
                age = _properties(rows.get(crop, {}), descriptor.block, 'age', descriptor.age_max)
                if age == 7: continue
                if before.get('hand', {}).get('item') != BONE or before['hand'].get('count', 0) < 1:
                    raise FarmWait('WAIT_HAND', 'Fresh held bone meal is unavailable')
                dispatch('bonemeal', pos, before, rows)
                times = []
                for _ in range(6):
                    after, observed, _ = survey()
                    hand_a, hand_b = before['hand'], after['hand']; expected = _counts(before)
                    expected[BONE] -= 1
                    if not expected[BONE]: del expected[BONE]
                    new_age = _properties(observed.get(crop, {}), descriptor.block, 'age', descriptor.age_max)
                    if (new_age is not None and new_age > age and _counts(after) == expected
                            and hand_b.get('count') == hand_a['count']-1
                            and hand_b.get('item') == (BONE if hand_b['count'] else 'minecraft:air')
                            and before['selected_slot'] == after['selected_slot']):
                        if not times or after['time'] > times[-1]: times.append(after['time'])
                        if len(times) == 2: break
                    else: times = []
                if len(times) != 2:
                    raise FarmWait('WAIT_RECONCILE', 'Bone meal requires actual minus-one stock and two fresh age-increase frames')
                record.setdefault('growth', []).append({**book['pending'], 'observed_times': times, 'age_after': new_age})
                record['bone_meal_used'] += 1; book['bone_meal_used'] += 1
                book['pending'] = None; save()

            if not recovering:
                select(seed); before, rows, _ = survey()
                if _properties(rows.get(crop, {}), descriptor.block, 'age', descriptor.age_max) != 7:
                    raise FarmWait('WAIT_GROWTH', 'Only a fresh exact age-seven '+descriptor.name+' crop may be harvested')
                if _counts(before)[seed] < 5:
                    raise FarmWait('WAIT_RESERVE', 'Four-seed reserve must survive the next reseed' if wheat else 'Four-potato reserve must survive the next reseed')
                if room_for_item(before, produce) < 1 or wheat and room_for_item(before, seed) < 1:
                    raise FarmWait('WAIT_INVENTORY', 'No actual carried capacity for crop produce/seeds')
                if wheat:
                    slots = [r for r in before['inventory'] if r['slot'] < 36]
                    required_slots = sum(not any(r['item'] == item and 0 < r['count'] < r.get('max_stack', 64)
                                                for r in slots) for item in loot_items)
                    if sum(not r['count'] for r in slots) < required_slots:
                        raise FarmWait('WAIT_INVENTORY', 'Wheat and seed drops need independently available carrying space')
                pre_ids = _drop_ids(before)
                dispatch('harvest', pos, before, rows, seconds=10)
                harvest = dict(book['pending'])
            else:
                harvest = dict(resume if resume['operation'] == 'await_loot' else record['harvest'])
                before = {'inventory': harvest['before_inventory']}
                pre_ids = set(harvest['pre_drop_ids'])
            deadline = monotonic()+pickup_seconds
            times = []; owned = {d['uuid']: d for d in harvest.get('owned_loot', [])}; after = None
            observed_total = harvest.get('observed_potato_total', 0)
            observed_totals = {item:harvest.get('observed_drop_totals', {}).get(item, 0) for item in loot_items}
            attempts = harvest.get('pickup_attempts', {})
            for _ in range(32):
                after, observed, drops = survey(pos, pre_ids)
                owned.update({d['uuid']: d for d in drops})
                if wheat:
                    gains = {item:_counts(after)[item]-_counts(before)[item] for item in loot_items}
                    potatoes = [d for d in drops if d['item'] in loot_items and d['floor'] == pos]
                    left_by_item = Counter()
                    for drop in potatoes:left_by_item[drop['item']] += drop['remaining_count']
                    remaining_count = sum(left_by_item.values())
                    consistent = (crop not in observed and all(amount >= 0 for amount in gains.values())
                                  and _same_except(before, after, loot_items))
                    if consistent:
                        observed_totals = {item:max(observed_totals[item], gains[item]+left_by_item[item])
                                           for item in loot_items}
                        book['pending'] = {**harvest, 'operation':'await_loot', 'crop_removed':True,
                                           'owned_loot':list(owned.values()), 'current_loot':potatoes,
                                           'actual_gains':gains, 'remaining_count':remaining_count,
                                           'observed_drop_totals':observed_totals, 'pickup_attempts':attempts}
                        save()
                    reconciled = (consistent and gains[produce] > 0 and not potatoes
                                  and all(gains[item] == observed_totals[item] for item in loot_items))
                    signature = tuple(sorted(gains.items()))
                else:
                    gain = _counts(after)[POTATO]-_counts(before)[POTATO]
                    potatoes = [d for d in drops if d['item'] == POTATO and d['floor'] == pos]
                    remaining_count = sum(d['remaining_count'] for d in potatoes)
                    consistent = (crop not in observed and gain >= 0 and _same_except(before, after, {POTATO, POISON})
                                  and _counts(after)[POISON] >= _counts(before)[POISON])
                    if consistent:
                        observed_total = max(observed_total, gain+remaining_count)
                        book['pending'] = {**harvest, 'operation':'await_loot', 'crop_removed':True,
                                           'owned_loot':list(owned.values()), 'current_loot':potatoes,
                                           'actual_gain':gain, 'remaining_count':remaining_count,
                                           'observed_potato_total':observed_total, 'pickup_attempts':attempts}
                        save()
                    reconciled = (crop not in observed and gain > 0 and _same_except(before, after, {POTATO, POISON})
                                  and _counts(after)[POISON] >= _counts(before)[POISON]
                                  and not potatoes and gain == observed_total)
                    signature = gain
                if reconciled:
                    if times and (after['time'] <= times[-1] or signature != previous_gain): times = []
                    times.append(after['time']); previous_gain = signature
                    if len(times) == 2: break
                else: times = []
                if consistent and pickup is not None and not _recover_only:
                    target = next((d for d in potatoes if d['uuid'] not in attempts), None)
                    if target is not None:
                        attempts[target['uuid']] = {'stage':'sent_once', 'remaining_count':target['remaining_count'],
                                                    'observation_time':after['time']}; save(); status()
                        answer = pickup(c, target, after)
                        status()
                        attempts[target['uuid']]['returned'] = answer if type(answer) is bool else type(answer).__name__
                        save()
                        deadline = monotonic()+pickup_seconds
                        continue
                if monotonic() >= deadline: break
                sleep(min(.2, max(0, deadline-monotonic())))
            if len(times) != 2:
                book['pending']['owned_loot'] = list(owned.values()); save()
                waiting = result('WAIT_LOOT', 'All owned crop drops and separate stable carried stock must reconcile before reseed; no extra break')
                waiting.update(recoverable_known_loot=book['pending'].get('operation') == 'await_loot',
                               known_loot=book['pending'].get('current_loot', []),
                               remaining_count=book['pending'].get('remaining_count', 0))
                book['last_wait'] = {'code':waiting['code'], 'detail':waiting['detail']}; save(); return waiting
            record['harvest'] = {**harvest, 'observed_times':times, 'after_counts':dict(_counts(after)),
                                 'owned_loot':list(owned.values()), 'pickup_attempts':attempts,
                                 'remaining_count':0}
            if wheat:
                record['harvest'].update(observed_drop_totals=observed_totals, actual_gains=gains,
                                        loot_proof='native_crop_ack_and_separate_observed_grain_seed_balances')
                record['wheat_gain'] = gains[produce]; record['seed_gain'] = gains[seed]
            else:
                record['harvest'].update(observed_potato_total=observed_total,
                    loot_proof='new_scoped_item_ids_and_actual_stock' if owned else 'empty_pre_scan_single_crop_break_and_actual_stock')
                record['potato_gain'] = gain
            book['pending'] = {'operation': 'await_replant', 'pos': pos[:], 'pre_drop_ids': sorted(pre_ids)}; save()
            if _recover_only:
                ready = result('REPLANT_READY', 'Known loot reconciled by reads; one saved harvested cell awaits reseed')
                ready.update(recoverable_known_loot=True, known_loot=[], remaining_count=0)
                return ready
            select(seed); before, rows, _ = survey(pos, pre_ids)
            if crop in rows or _counts(before)[seed] < 5:
                raise FarmWait('WAIT_RECONCILE', 'Fresh air, farmland and actual reseed stock plus reserve are required')
            if before.get('hand', {}).get('item') != seed or before['hand'].get('count', 0) < 1:
                raise FarmWait('WAIT_HAND', 'Fresh held planting '+descriptor.label+' is unavailable')
            dispatch('plant', pos, before, rows)
            times = []
            for _ in range(6):
                after, observed, _ = survey(pos, pre_ids)
                if (action_proved('plant', pos, before, after, observed, crop=descriptor)
                        and _properties(observed.get(crop, {}), descriptor.block, 'age', descriptor.age_max) == 0
                        and _counts(after)[seed] >= 4):
                    if not times or after['time'] > times[-1]: times.append(after['time'])
                    if len(times) == 2: break
                else: times = []
            if len(times) != 2:
                raise FarmWait('WAIT_RECONCILE', 'Reseed needs exactly one actual planting item consumed and two fresh age-zero frames')
            record['plant'] = {**book['pending'], 'observed_times': times, 'after_counts': dict(_counts(after))}
            record['replanted'] = True; book['pending'] = None; resume = None; save()
        final, _, _ = survey()
        book[descriptor.quantity_key+'_after'] = _counts(final)[seed]
        if wheat:book['wheat_after'] = _counts(final)[produce]
        save()
        if len(remaining) > max_cells:
            return result('HARVEST_BATCH', 'Bounded batch completed; caller retains control')
        book['complete'] = True; save(); return result()
    except JobPaused:
        raise
    except FarmWait as error:
        if getattr(error, 'active_journal', None):book['active_journal'] = error.active_journal
        book['last_wait'] = {'code': error.code, 'detail': str(error)}; save()
        return result(error.code, str(error))
    except Exception as error:
        book['last_wait'] = {'code': 'WAIT_CONTROL', 'detail': type(error).__name__ + ': ' + str(error)}
        save(); return result('WAIT_CONTROL', book['last_wait']['detail'])


def recover_known_loot(c, request, out, checkpoint=lambda: None, **options):
    """Read-only reconciliation of a saved known harvest; never mine or replant.

    WAIT_LOOT retains exact UUID/remaining_count. REPLANT_READY lets an explicit
    subsequent run continue the saved cell without repeating its mining action.
    """
    if options.get('pickup') is not None:
        raise ValueError('Known-loot inspection is read-only; supply pickup to run instead')
    return run(c, request, out, checkpoint, _recover_only=True, **options)
