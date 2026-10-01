"""Bounded wood stockpile batches under the caller's existing material lease.

target_count is the final total in distinct approved depots, not a carried
increment. Backend.client must already be c. No controller is created and no
personal profile/source geometry is rewritten. Each call makes at most one
known batch; an uncertain pending operation blocks every later call.
"""
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json
from material_depots import audit, exchange
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from .protocol import JobBlocked, JobPaused

SPECIES = ('oak', 'dark_oak', 'cherry', 'acacia', 'spruce')
LOGS = {'minecraft:' + name + '_log': name for name in SPECIES}
PLANKS = {'minecraft:' + name + '_planks': name for name in SPECIES}
MAX_NEW_LOGS = 16
MAX_PLANK_BATCH = 64


def _wait(code, detail, **evidence):
    return {'phase': 'waiting', 'code': code, 'detail': detail,
            'target_scope': 'approved_depot_total', **evidence}


def _check(c, profile, checkpoint):
    checkpoint()
    state = c.status()
    if (state.get('world_session') != c.world or not state.get('connected', False)
            or state.get('health', 0) < 19 or state.get('food', 0) < 8
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or state.get('manual_movement') or state.get('under_water')
            or (state.get('safety_hold') or {}).get('active')
            or state.get('dimension') != profile.get('dimension')
            or str(state.get('server', '')).lower().removesuffix(':25565') != profile.get('server', '').lower().removesuffix(':25565')):
        raise JobPaused('Wood pipeline world, health or guard changed; no new action')
    if (state.get('menu') or {}).get('cursor', {}).get('count', 0):
        raise JobPaused('Wood pipeline has an occupied cursor; retain the original operation')
    room_for_item(state, 'minecraft:oak_log')  # Require all36 main slots, not a partial capacity guess.
    return state


def _recipe(backend, output, raw):
    """Verify current JAR's one-family input -> four planks; craft takes totals."""
    catalog = getattr(backend, 'crafting_catalog', None)
    if catalog is None:
        raise JobBlocked('Current game crafting catalog is unavailable')
    specs = catalog.candidates(output, {raw: 1}, 2)
    selected = next((r for r in specs if r.get('output') == output and r.get('produces') == 4
                     and set(r.get('ingredients', {})) == {raw}
                     and sum(map(len, r['ingredients'].values())) == 1), None)
    if selected is None:
        raise JobBlocked('Current game does not verify the requested log-to-planks recipe')
    alternatives = set()
    for recipe in catalog.recipes.get(output, []):
        if recipe.count == 4 and len(recipe.cells) == 1:
            alternatives.update(recipe.cells[0][1])
    family = PLANKS[output]
    allowed = {'minecraft:' + family + '_log', 'minecraft:' + family + '_wood',
               'minecraft:stripped_' + family + '_log', 'minecraft:stripped_' + family + '_wood'}
    if not alternatives or not alternatives <= allowed or raw not in alternatives:
        raise JobBlocked('Plank recipe has unsupported inputs; no guessed conversion')
    return selected['recipe_id'], alternatives


def _known_chop(receipt, directory, c, raw, before, after):
    if receipt.get('phase') == 'done':return True
    if receipt.get('phase') != 'waiting' or after <= before:return False
    if receipt.get('native_phase') == 'done':return True
    # Existing acquisition returns a goal-level waiting result after one clean
    # small tree. Its actual native DONE is retained in the acquisition ledger.
    path = directory / ('acquisition-' + raw.split(':')[-1] + '.json')
    if not path.exists():return False
    ledger = json.loads(path.read_text())
    if ledger.get('world_session') != c.world or ledger.get('item') != raw:return False
    return any(entry.get('state') == 'progress' and entry.get('native_phase') == 'done'
               and entry.get('before') == before and entry.get('after') == after
               and entry.get('gained') == after - before for entry in ledger.get('visited', {}).values())


def _source_key(region):
    return json.dumps([region['item'], region['min'], region['max']], separators=(',', ':'))


def _empty_idle(state):
    return (all(state.get(k) is False for k in ('chopping', 'navigating', 'borer_active', 'printing', 'guard_busy'))
            and not state.get('native_material_busy') and not state.get('health_recovery_hold')
            and all(type(state.get(k)) is int and state[k] == 0 for k in ('chopper_remaining', 'chopper_platforms'))
            and type(state.get('recent_hurt_at')) is int and state['recent_hurt_at'] >= 0)


def _inventory_signature(state):
    # Preserve real stack metadata as well as counts; an axe use or unexpected
    # pickup must not turn a partial operation into permission to change source.
    return json.dumps(sorted((r if r.get('count') else {'slot': r['slot'], 'count': 0}
                              for r in state['inventory']), key=lambda r: r['slot']), sort_keys=True)


def _unchanged_empty(before, after):
    return (_empty_idle(before) and _empty_idle(after)
            and before['health'] == after['health']
            and before['recent_hurt_at'] == after['recent_hurt_at']
            and _inventory_signature(before) == _inventory_signature(after))


def _known_empty_chop(receipt, directory, c, raw, before, after):
    if (receipt.get('phase') != 'blocked' or receipt.get('code') != 'no_safe_candidate'
            or receipt.get('gained', 0) != 0 or not _unchanged_empty(before, after)):
        return False
    path = directory / ('acquisition-' + raw.split(':')[-1] + '.json')
    if not path.exists():return False
    ledger = json.loads(path.read_text())
    visited = ledger.get('visited')
    return (ledger.get('schema') == 1 and ledger.get('world_session') == c.world and ledger.get('item') == raw
            and isinstance(visited, dict) and not ledger.get('pending') and not ledger.get('route_holds')
            and not ledger.get('guard_hold')
            and all(isinstance(v, dict) and v.get('state') == 'empty_or_unsafe'
                    and not any(k in v for k in ('native', 'native_phase', 'before', 'after', 'gained', 'regrowth'))
                    for v in visited.values()))


def run(c, profile, item, target_count, out, checkpoint):
    """One acquire/craft/deposit batch, or an honest source/capacity/receipt wait.

Use c.wood_backend (or c.material_backend), bound to this same c and profile.
Call again only after this call has a known receipt. Actual acquisition keeps
its own unique completed-batch directory so regrown trees are freshly surveyed;
an old inflight directory is never bypassed. Existing discovery and regrowth
implementations remain responsible for real natural-tree/plant/growth proof.
"""
    if item not in LOGS and item not in PLANKS:
        return _wait('unsupported_wood', 'Only ordinary oak/dark-oak/cherry/acacia/spruce logs/planks are supported')
    if type(target_count) is not int or not 1 <= target_count <= 100000:
        raise ValueError('Wood target must be a positive approved-depot total')
    backend = getattr(c, 'wood_backend', None) or getattr(c, 'material_backend', None)
    if backend is None or getattr(backend, 'client', None) is not c or getattr(backend, 'profile', None) != profile:
        return _wait('wait_source', 'Bind an existing Backend.client to c and pass that Backend.profile; no new controller')
    if getattr(backend, 'request', {}).get('mode') == 'projection':
        return _wait('wait_source', 'Stockpile wood requires an item-mode backend; projection fetch can withdraw unrelated finished outputs')
    depots = profile.get('depots')
    if (not isinstance(depots, list) or not depots or any(not isinstance(p, list) or len(p) != 3
            or any(type(v) is not int for v in p) for p in depots)
            or len({tuple(p) for p in depots}) != len(depots)):
        return _wait('wait_source', 'Distinct approved canonical depot inventories are required')
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    path = out / 'wood-pipeline.json'
    spec = {'world_session': c.world, 'item': item, 'target': target_count,
            'target_scope': 'approved_depot_total', 'depots': depots}
    if path.exists():
        job = json.loads(path.read_text())
        if any(job.get(k) != v for k, v in spec.items()):
            return _wait('wait_receipt', 'Existing wood journal belongs to another scope/target; do not overwrite it')
        if job.get('pending'):
            return _wait('wait_receipt', 'Prior wood operation is uncertain; no request or directory replay', pending=job['pending'])
    else:
        job = {'schema': 1, **spec, 'expected_depot': None, 'pending': None,
               'sequence': 0, 'batches': [], 'sources': []}
    job.setdefault('empty_sources', {})
    job.setdefault('discovery_exhausted', {})
    def save():write_json(path, job)
    def state():return _check(c, profile, checkpoint)
    def stock():return dict(inventory_counts(state()))
    def depot():
        backend.prepare_travel(); backend.stage_near_base(depots)
        proof = audit(c, depots, [item])
        if proof.get('complete') is not True or proof.get('world_session') != c.world:
            raise JobBlocked('Approved depot audit is incomplete')
        return proof['counts'][item], proof
    def operation(kind, callback):
        job['pending'] = {'kind': kind, 'sequence': job['sequence'] + 1}
        save()
        result = callback()
        state()
        return result
    def known(kind, receipt):
        job['sequence'] += 1
        job['batches'].append({'kind': kind, 'receipt': receipt})
        job['pending'] = None; save()

    state(); save()
    current_depot, initial_audit = depot()
    if job['expected_depot'] is not None and current_depot != job['expected_depot']:
        return _wait('wait_depot', 'Approved depot stock changed outside the recorded pipeline; re-audit before resuming',
                     expected=job['expected_depot'], observed=current_depot)
    job['expected_depot'] = current_depot; save()
    if current_depot >= target_count:
        job['complete'] = True; save()
        return {'phase': 'done', 'target_scope': 'approved_depot_total', 'item': item,
                'target': target_count, 'depot_count': current_depot, 'audit': initial_audit}

    def deliver():
        nonlocal current_depot
        held = stock().get(item, 0)
        amount = min(held, target_count - current_depot)
        if not amount:return None
        before_depot = current_depot
        result = operation('deposit', lambda: exchange(c, depots, deposit={item: held - amount}))
        after_held = stock().get(item, 0)
        observed, proof = depot()
        moved = held - after_held
        if not 0 <= moved <= amount or observed - before_depot != moved:
            return _wait('wait_receipt', 'Depot gain does not equal actual carried loss; pending retained')
        current_depot = observed; job['expected_depot'] = observed
        known('deposit', {'before_carried': held, 'after_carried': after_held, 'depot_gain': moved,
                          'exchange': result, 'audit': proof})
        complete = observed >= target_count
        job['complete'] = complete; save()
        return {'phase': 'done' if complete else 'waiting',
                'code': 'complete' if complete else 'batch_delivered' if moved == amount else 'wait_depot',
                'target_scope': 'approved_depot_total', 'item': item, 'target': target_count,
                'depot_count': observed, 'delivered': moved, 'carried_surplus': after_held}

    # Finished carried stock is preserved and stored before acquiring more raw inputs.
    delivered = deliver()
    if delivered is not None:return delivered
    raw = item if item in LOGS else 'minecraft:' + PLANKS[item] + '_log'
    try:
        recipe_id, inputs = (None, {raw}) if item in LOGS else _recipe(backend, item, raw)
    except (JobBlocked, ValueError, AttributeError) as error:
        return _wait('wait_source', str(error))
    fresh = state(); held = inventory_counts(fresh)
    remaining = target_count - current_depot
    room = room_for_item(fresh, item)
    wanted = min(remaining, MAX_NEW_LOGS if item in LOGS else MAX_PLANK_BATCH,
                 room if item in LOGS else room // 4 * 4)
    if wanted < 1:
        return _wait('wait_capacity', 'No proved capacity for a complete ordinary wood batch; stage items without discarding')
    units = wanted if item in LOGS else math.ceil(wanted / 4)
    available_units = sum(held.get(i, 0) for i in inputs)
    if item in PLANKS and available_units:
        units = min(units, available_units)
        wanted = min(wanted, units * 4)  # Use existing inputs before another sourcing trip.
    if available_units < units:
        raw_target = held.get(raw, 0) + units - available_units
        if item in PLANKS:
            fetched = operation('fetch', lambda: backend.fetch({raw: raw_target}))
            if (not isinstance(fetched, dict) or fetched.get('phase') not in ('done', 'waiting')
                    or fetched.get('phase') == 'waiting' and not isinstance(fetched.get('missing'), dict)):
                return _wait('wait_receipt', 'Fetch outcome is not a known completed transfer/shortage; pending retained')
            known('fetch', fetched)
        # Logs already in the audited goal depots are not new supply; never
        # withdraw them only to deposit the same logs and fabricate progress.
        fresh = state(); after_fetch = inventory_counts(fresh)
        available_units = sum(after_fetch.get(i, 0) for i in inputs)
        if available_units < units and profile.get('ender_chest') and profile.get('shulker_pad'):
            packed = operation('fetch_packed', lambda: backend.fetch_packed({raw: raw_target}))
            if packed is not None and packed.get('phase') != 'done':
                return _wait('wait_receipt', 'Packed source outcome uncertain; pending retained')
            state(); known('fetch_packed', packed)
            available_units = sum(stock().get(i, 0) for i in inputs)
        if available_units < units:
            from .acquisition import acquire, _bounds
            from .discovery import discover
            from .equipment import prepare
            backend.prepare_travel()
            configured = [r for r in profile.get('resource_regions', []) if r.get('item') == raw]
            candidates = configured + [r for r in job['sources'] if r.get('item') == raw and r.get('pipeline_world_session') == c.world]
            sources = []
            for region in candidates:
                _bounds(region)
                key = _source_key(region)
                if key not in job['empty_sources'] and all(_source_key(r) != key for r in sources):sources.append(region)

            def find_source():
                if not profile.get('search_origin') or type(profile.get('search_radius')) is not int:
                    return [], _wait('wait_source', 'No bounded local discovery scope; cache hints are not harvest permission')
                empty = [v for v in job['empty_sources'].values() if v.get('item') == raw and v.get('world_session') == c.world]
                before_search = state()
                if (not _empty_idle(before_search) or any(v['recent_hurt_at'] != before_search['recent_hurt_at']
                                                           for v in empty)):
                    job['pending'] = {'kind': 'source_transition_hold', 'reason': 'native busy or damage after known empty source'}; save()
                    return [], _wait('wait_receipt', 'Source transition has a native or damage hold; no discovery')
                search_profile = {**profile, 'resource_regions':
                                  [r for r in profile.get('resource_regions', []) if r.get('item') != raw] +
                                  [r for r in sources if _source_key(r) not in job['empty_sources']],
                                  'protected_regions': list(profile.get('protected_regions', [])) +
                                  [{'min': v['region']['min'], 'max': v['region']['max']} for v in empty]}
                search_key = json.dumps([profile['search_origin'], profile['search_radius'],
                                         sorted(_source_key(v['region']) for v in empty)], sort_keys=True)
                if job['discovery_exhausted'].get(raw) == search_key:
                    return [], _wait('wait_source', 'This bounded discovery frontier is exhausted; empty sources are not revisited')
                stopped_search = job['discovery_exhausted'].get(raw)
                if isinstance(stopped_search, dict) and stopped_search.get('scope') == search_key:
                    return [], _wait('wait_source', 'Discovery returned a previously empty source; retain its rejection before another route')
                found = operation('discover', lambda: discover(c, raw, search_profile,
                                  out / 'discovery', checkpoint, max_tiles=8))
                after_search = state()
                progress = getattr(c, 'material_search_progress', {})
                if (not _unchanged_empty(before_search, after_search) or not isinstance(progress, dict)
                        or progress.get('guard_hold')):
                    return [], _wait('wait_receipt', 'Discovery was displaced, changed stock or remained active; pending retained')
                if found is None:
                    if progress.get('has_more') is False:job['discovery_exhausted'][raw] = search_key
                    known('discover', {'found': None, 'progress': progress})
                    return [], _wait('wait_source', 'Bounded discovery has no live safe natural source', search_progress=progress)
                _bounds(found)
                if (found.get('item') != raw or found.get('source') != 'natural_survey'
                        or found.get('world_session') not in (None, c.world)):
                    return [], _wait('wait_receipt', 'Discovery did not return its verified natural source; pending retained')
                if _source_key(found) in job['empty_sources']:
                    job['discovery_exhausted'][raw] = {'scope': search_key, 'reason': 'repeated_empty_source'}
                    known('discover_repeated_empty', {'source': found, 'progress': progress})
                    return [], _wait('wait_source', 'Discovery repeated a proved empty source; no harvest or repeated travel')
                found = {**found, 'pipeline_world_session': c.world}
                job['sources'].append(found); known('discover', {'source': found, 'progress': progress})
                return [found], None

            if not sources:
                sources, waited = find_source()
                if waited is not None:return waited
            checked_profile = {**profile, 'resource_regions':
                               [r for r in profile.get('resource_regions', []) if r.get('item') != raw] + list(sources)}
            fresh = state(); before_raw = inventory_counts(fresh).get(raw, 0)
            increment = min(MAX_NEW_LOGS, max(1, units - sum(inventory_counts(fresh).get(i, 0) for i in inputs)))
            absolute = before_raw + increment
            if absolute > 512 or room_for_item(fresh, raw) < increment + 64:
                return _wait('wait_capacity', 'Reserve room for whole-tree overshoot before native chopping')
            batch_dir = out / ('harvest-%04d' % (job['sequence'] + 1))
            batch_dir.mkdir(exist_ok=True)
            prepared = operation('equipment', lambda: prepare(c, raw, absolute, checked_profile, batch_dir / 'equipment', checkpoint))
            if prepared.get('phase') != 'done':
                return _wait('wait_receipt', 'Equipment preparation has not completed; retain its receipt', receipt=prepared)
            known('equipment', prepared)
            before_acquire = state()
            acquired = operation('acquire', lambda: acquire(c, raw, absolute, checked_profile, batch_dir / 'acquisition', checkpoint))
            fresh = state(); after_raw = inventory_counts(fresh).get(raw, 0)
            if _known_empty_chop(acquired, batch_dir / 'acquisition', c, raw, before_acquire, fresh):
                for region in sources:
                    job['empty_sources'][_source_key(region)] = {
                        'item': raw, 'world_session': c.world, 'region': json.loads(json.dumps(region)),
                        'recent_hurt_at': fresh['recent_hurt_at'], 'health': fresh['health'],
                        'inventory_unchanged': True, 'observed_at': fresh.get('time'),
                        'acquisition_ledger': str(batch_dir / 'acquisition')}
                known('acquire_no_source', {'result': acquired, 'source_keys': [_source_key(r) for r in sources]})
                found_sources, waited = find_source()
                return waited or _wait('source_discovered', 'Fresh natural source recorded; next known batch may harvest it',
                                       source=found_sources[0])
            if (fresh.get('chopper_remaining') or fresh.get('chopper_platforms') or fresh.get('chopping')
                    or acquired.get('code') in ('guard_displaced', 'route_uncertain', 'route_geometry_blocked')
                    or not _known_chop(acquired, batch_dir / 'acquisition', c, raw, before_raw, after_raw)):
                return _wait('wait_receipt', 'Native chop/regrowth outcome is pending; no new harvest directory', receipt=acquired)
            if after_raw < before_raw or acquired.get('gained', after_raw - before_raw) != after_raw - before_raw:
                return _wait('wait_receipt', 'Actual collected logs disagree with the acquisition receipt')
            known('acquire', {'result': acquired, 'raw_before': before_raw, 'raw_after': after_raw,
                              'regrowth': acquired.get('regrowth'),
                              'regrowth_scope': 'reported actual receipt; a single dark-oak sapling is not a proved2x2 renewal'})
    if item in PLANKS:
        before = stock(); raw_units = sum(before.get(i, 0) for i in inputs)
        if raw_units < 1:return _wait('wait_source', 'No actual log-family inputs are available')
        produced = min(math.ceil(wanted / 4), raw_units) * 4
        if room_for_item(state(), item) < produced:
            return _wait('wait_capacity', 'Current inventory cannot hold the verified plank output')
        target = before.get(item, 0) + produced
        result = operation('craft', lambda: backend.craft({item: target}))
        after = stock()
        if (not isinstance(result, dict) or result.get('phase') != 'done'
                or after.get(item, 0) - before.get(item, 0) != produced
                or sum(before.get(i, 0) - after.get(i, 0) for i in inputs) != produced // 4):
            return _wait('wait_receipt', 'Actual plank output/input delta or craft receipt is uncertain')
        known('craft', {'recipe_id': recipe_id, 'absolute_carried_target': target,
                        'produced': produced, 'result': result})
    return deliver() or _wait('wait_source', 'No verified finished wood was available for delivery')
