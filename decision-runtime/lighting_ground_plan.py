"""Pure one-scan ground lighting routes; no Client, inputs, or world mutations.

Only adjacent same-level full-cube ground is planned. Native walk DONE alone
does not prove grounding, reach, or safe exit: an eventual executor must rescan
each short leg, settle the actual pose and use native visible-UP interaction.
"""
from collections import deque
import math

from ground_pickup import clear_segment, hazard
from lighting_cli import (SAFE_SUPPORTS, bounds, point, candidate_protected, protection_boxes,
                          scan_cells, swept_entities, validate_native_details, LightingBlocked)
from material_jobs.navigation import _body_sweep
from survival_world import World


class GroundPlanRejected(ValueError):
    pass


_BODY_PASS = frozenset('minecraft:' + name for name in
    ('torch', 'wall_torch', 'short_grass', 'tall_grass', 'fern', 'large_fern', 'dandelion'))


def _id(row):
    state = row.get('state', '')
    return state[6:].split('}', 1)[0] if state.startswith('Block{') and '}' in state else None


def _point(value):
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in value)):
        raise GroundPlanRejected('Three finite coordinates are required')
    return tuple(value)


def _scan(receipt, low, high, context, request_id, age):
    if not isinstance(receipt, dict) or not isinstance(context, dict):
        raise GroundPlanRejected('Explicit native receipt and current context are required')
    low, high = bounds(low, high)
    world, revision, now = (context.get(key) for key in ('world_session', 'control_revision', 'now_ms'))
    volume = math.prod(b - a + 1 for a, b in zip(low, high))
    if (not isinstance(world, str) or not world or world == 'UNBOUND'
            or type(revision) is not int or revision < 0 or type(now) is not int
            or not isinstance(request_id, str) or not request_id or receipt.get('id') != request_id
            or receipt.get('phase') != 'done' or receipt.get('world_session') != world
            or receipt.get('scan_scope') != 'loaded_client_cells_sampled_on_client_ticks_not_atomic_server_snapshot'
            or any(type(receipt.get(key)) is not int for key in ('control_revision', 'scan_start_revision',
                  'scan_end_revision', 'scan_cells_read', 'scan_total_cells', 'scan_started_at', 'scan_ended_at'))
            or any(receipt[key] != revision for key in ('control_revision', 'scan_start_revision', 'scan_end_revision'))
            or receipt['scan_cells_read'] != volume or receipt['scan_total_cells'] != volume
            or not 0 < receipt['scan_started_at'] <= receipt['scan_ended_at'] <= now
            or now - receipt['scan_ended_at'] > age):
        raise GroundPlanRejected('Exact fresh complete native RID/bounds/world/revision/time is unavailable')
    try:
        cells = validate_native_details(scan_cells(receipt, low, high, world))
    except (LightingBlocked, ValueError) as error:
        raise GroundPlanRejected(str(error)) from error
    # This also validates the native entity scope, typed list and every AABB.
    center = [(low[0] + high[0] + 1) / 2, low[1], (low[2] + high[2] + 1) / 2]
    try:
        swept_entities(receipt, center, center, low, high, world, revision)
    except LightingBlocked as error:
        raise GroundPlanRejected(str(error)) from error
    return cells, low, high


def plan(receipt, *, low, high, context, entry, supports, protected, movement_bounds,
         exit_scan=None, max_torches=1, max_age_ms=5000):
    """Return current geometry hints or needs_scan; never grant action permission.

    context names world_session/control_revision/now_ms/request_id explicitly.
    entry is a proposed centered integer-height ground stance, not a claim that
    the actor arrived. supports are explicitly authorized integer floor cells.
    exit_scan optionally holds receipt/request_id/min/max for the complete
    original entrance footprint from Y-64 through319, in this same context.
    """
    if type(max_torches) is not int or max_torches != 1:
        raise GroundPlanRejected('The first ground route plan is limited to one torch')
    if type(max_age_ms) is not int or not 1 <= max_age_ms <= 10000:
        raise GroundPlanRejected('Freshness must be explicitly bounded to at most ten seconds')
    if not isinstance(context, dict) or not isinstance(movement_bounds, dict):
        raise GroundPlanRejected('Explicit current context and authorized movement bounds are required')
    cells, low, high = _scan(receipt, low, high, context, context.get('request_id'), max_age_ms)
    protected = protection_boxes(protected)
    movement = protection_boxes([movement_bounds])[0]
    movement_low, movement_high = point(movement['min']), point(movement['max'])
    entry = _point(entry)
    if (entry[1] != math.floor(entry[1]) or abs(entry[0] % 1 - .5) > 1e-6 or abs(entry[2] % 1 - .5) > 1e-6):
        raise GroundPlanRejected('Plan an explicit centered full-cube ground stance; do not snap an actual pose')
    if (not isinstance(supports, list) or not supports or len(supports) > 64
            or any(not isinstance(p, (list, tuple)) or len(p) != 3 or any(type(n) is not int for n in p) for p in supports)
            or len({tuple(p) for p in supports}) != len(supports)):
        raise GroundPlanRejected('Explicit distinct integer authorized floor targets are required')
    world, revision = context['world_session'], context['control_revision']
    unknown, blocked, safe = set(), [], []
    body_y = int(entry[1])
    geometry = World(list(cells.values()), low, high)

    def known(pos):
        return all(low[i] <= pos[i] <= high[i] for i in range(3))

    def excluded(pos):
        return candidate_protected(pos, pos, protected)

    def open_body(pos):
        if not known(pos):
            unknown.add(pos); return False
        row = cells.get(pos)
        return (not excluded(pos) and (row is None or _id(row) in _BODY_PASS
                and row.get('passable') is True and row.get('fluid') is False
                and row.get('block_entity') is False and not hazard(row)))

    def standing(node):
        x, y, z = node; floor = (x, y - 1, z)
        if not known(floor):
            unknown.add(floor); return False
        row = cells.get(floor, {})
        if (_id(row) not in SAFE_SUPPORTS or row.get('solid') is not True or hazard(row)
                or row.get('block_entity') is not False or excluded(floor)):
            return False
        point = [x + .5, y, z + .5]
        body_low, body_high = _body_sweep(point, point)
        if any(body_low[i] < movement_low[i] or body_high[i] > movement_high[i] for i in range(3)):
            return False
        return open_body(node) and open_body((x, y + 1, z))

    def edge(start, end):
        a, b = [start[0] + .5, start[1], start[2] + .5], [end[0] + .5, end[1], end[2] + .5]
        sweep_low, sweep_high = _body_sweep(a, b)
        for x in range(sweep_low[0], sweep_high[0] + 1):
            for y in range(sweep_low[1], sweep_high[1] + 1):
                for z in range(sweep_low[2], sweep_high[2] + 1):
                    if not open_body((x, y, z)): return False
        if not clear_segment(a, b, list(cells.values())): return False
        return not swept_entities(receipt, a, b, low, high, world, revision)

    start = (math.floor(entry[0]), body_y, math.floor(entry[2]))
    if standing(start) and not swept_entities(receipt, entry, entry, low, high, world, revision):
        queue, parents = deque([start]), {start: None}
        while queue and len(parents) < 4096:
            node = queue.popleft()
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (node[0] + dx, body_y, node[2] + dz)
                if nxt not in parents and standing(nxt) and edge(node, nxt) and edge(nxt, node):
                    parents[nxt] = node; queue.append(nxt)
    else:
        parents = {}
        blocked.append('entry_ground_body_or_entity_is_not_proved')

    for support in supports:
        support = tuple(support); target = (support[0], support[1] + 1, support[2])
        if not known(support) or not known(target):
            unknown.update(p for p in (support, target) if not known(p)); continue
        row = cells.get(support, {})
        if (candidate_protected(support, target, protected) or _id(row) not in SAFE_SUPPORTS
                or row.get('solid') is not True or row.get('fluid') is not False or row.get('block_entity') is not False
                or row.get('zombie_spawn_floor') is not True or row.get('zombie_block_light_risk') is not True
                or target in cells or any(not movement_low[i] <= target[i] <= movement_high[i] for i in range(3))):
            blocked.append({'support': list(support), 'reason': 'protected_or_not_current_dark_dry_air_target'}); continue
        stances = [p for p in parents if p[1] == support[1] + 1
                   and abs(p[0] - support[0]) + abs(p[2] - support[2]) <= 2
                   and geometry.sight(p, support)]
        if not stances:
            blocked.append({'support': list(support), 'reason': 'no_proven_reversible_flat_route_or_conservative_sight'}); continue
        def route(node):
            nodes = []
            while node is not None:
                nodes.append([node[0] + .5, node[1], node[2] + .5]); node = parents[node]
            return list(reversed(nodes))
        stance = min(stances, key=lambda p: (len(route(p)), p))
        outward = route(stance)
        safe.append({'support': list(support), 'target': list(target), 'support_state': row['state'],
                     'stance': outward[-1], 'outward_route': outward, 'return_route': list(reversed(outward)),
                     'face': 'up', 'expected_hand': 'minecraft:torch',
                     'native_visible_up_face_and_actual_eye_range_required': True, 'ray_prediction_only': True})
    safe.sort(key=lambda item: (len(item['outward_route']), item['support']))
    safe = safe[:1]

    exit_proved = False; exit_required = {'min': [math.floor(entry[0] - .35), -64, math.floor(entry[2] - .35)],
        'max': [math.floor(entry[0] + .35), 319, math.floor(entry[2] + .35)]}
    if exit_scan is not None:
        exit_cells, exit_low, exit_high = _scan(exit_scan['receipt'], exit_scan['min'], exit_scan['max'], context,
                                               exit_scan.get('request_id'), max_age_ms)
        if list(exit_low) != exit_required['min'] or list(exit_high) != exit_required['max']:
            raise GroundPlanRejected('Exit proof must cover the actual entrance footprint through Y319')
        exit_proved = not any(p[1] >= body_y and (hazard(row) or row.get('passable') is not True
                             or row.get('block_entity') is not False or _id(row) not in _BODY_PASS)
                             for p, row in exit_cells.items())
        floor = (math.floor(entry[0]), body_y - 1, math.floor(entry[2]))
        original_floor, actual_floor = cells.get(floor, {}), exit_cells.get(floor, {})
        exit_proved = bool(exit_proved and actual_floor.get('state') == original_floor.get('state')
            and actual_floor.get('solid') is True and actual_floor.get('fluid') is False
            and actual_floor.get('block_entity') is False and not hazard(actual_floor)
            and not swept_entities(exit_scan['receipt'], entry, entry, exit_low, exit_high, world, revision))
        if not exit_proved: blocked.append('entrance_has_no_proved_existing_open_sky_exit')
    needs = []
    if unknown and not safe:
        needs.append({'reason': 'unknown_scan_boundary_not_air', 'coordinates': list(map(list, sorted(unknown)))})
    if safe and not exit_proved:
        needs.append({'reason': 'current_entrance_exit_full_column_required', **exit_required})
    return {'schema': 1, 'scope': 'one fresh native scan, reversible same-level ground geometry; no action permission',
            'world_session': world, 'control_revision': revision, 'scan_request_id': context['request_id'],
            'state': 'needs_scan' if needs else 'route_candidate' if safe and exit_proved else 'blocked',
            'candidates': safe, 'needs_scan': needs, 'diagnostics': blocked,
            'unknown_frontier': list(map(list, sorted(unknown))),
            'entrance': list(entry), 'exit_proved': exit_proved, 'known_ground_nodes': len(parents),
            'game_operations': 0, 'placement_credit': 0, 'physical_impossibility_claimed': False,
            'runtime_required': ['fresh short-leg support/body/entity scan', 'native walk restore_flight=false',
                'exact known terminal and actual settled on_ground pose', 'actual native visibleUP face and synced eye/reach',
                'durable lighting intent before one interaction', 'two distinct exact torch and inventory-1 frames',
                'fresh reverse route, actual exit column and bounded high ascent, native KEEP/PARK proof']}
