"""Return to an unfinished owned plan using newly scanned normal terrain."""
import math

from singleplayer_trial_bridge import Paused
from survival_world import cell, center, distance


def observe_partial_shelter(skills, plan):
    required = {tuple(p) for p in (*plan['layout'], *plan['floor'])}
    required.update({tuple(plan['inside']), tuple(plan['door']),
                     (plan['door'][0], plan['door'][1] + 1, plan['door'][2])})
    local = skills.scan()
    if all(local.known(point) for point in required):
        return local
    before = skills.b.read()
    start = cell(before['pos'])
    last_world = None
    # Complete sparse bounds, including every saved cell and the current feet.
    # A missing remembered cell never becomes evidence of player modification.
    for padding in (4, 8):
        low = [min([start[axis], *(point[axis] for point in required)]) - padding for axis in range(3)]
        high = [max([start[axis], *(point[axis] for point in required)]) + padding for axis in range(3)]
        low[1], high[1] = max(-64, low[1]), min(319, high[1])
        volume = math.prod(b - a + 1 for a, b in zip(low, high))
        if volume <= 0 or volume > 30_000:
            break
        result = skills.b.request('scan', min=low, max=high, details=True)
        if (result.get('scan_cells_read') != volume or result.get('scan_total_cells') != volume
                or any(result.get(key) != before.get(key)
                       for key in ('world_id', 'world_session', 'dimension', 'control_revision'))
                or distance(result['pos'], before['pos']) > .3):
            raise Paused('Partial shelter corridor scan is incomplete or changed; no return route starts')
        world = type(local)(result['blocks'], low, high)
        last_world = world
        if not all(world.known(point) for point in required):
            raise Paused('Partial shelter corridor does not contain the full saved plan')
        parents = world.paths(result['pos'], limit=min(10_000, volume))
        inside = tuple(plan['inside'])
        approaches = []
        for stance in parents:
            if distance(center(stance), center(inside)) > 5 or abs(stance[1] - inside[1]) > 3:
                continue
            route = world.route(parents, stance)
            if len(route) > 128 or tuple(route) in getattr(skills, 'rejected_routes', set()):
                continue
            approaches.append((len(route), distance(center(stance), center(inside)), stance, route))
        skills.event('partial_shelter_return_corridor', inside=list(inside),
                     bounds={'min': low, 'max': high}, cells=volume, reachable=bool(approaches))
        if not approaches:
            continue
        unused, unused_distance, stance, route = min(approaches)
        skills.walk(route)
        current = skills.b.read()
        if distance(current['pos'], center(stance)) > .7:
            raise Paused('Actual partial shelter return arrival is not confirmed; no walking replay')
        fresh = skills.scan()
        if not all(fresh.known(point) for point in required):
            raise Paused('Returned shelter still lacks a complete fresh site observation')
        skills.event('partial_shelter_return_verified', inside=list(inside), position=current['pos'],
                     route_steps=len(route), flight_used=False)
        return fresh
    current = skills.b.read()
    inside = tuple(plan['inside'])
    if last_world is not None and current['pos'][1] < inside[1] - .5:
        # A manually entered or newly mined pit may have no open return graph.
        # Reuse the existing bounded headroom/ascent skill, protecting the
        # house and every real walked floor. No virtual air authorizes walking.
        parents = last_world.paths(current['pos'])
        source = cell(current['pos'])
        if source in parents:
            centering = last_world.route(parents, source)
            if centering:
                skills.walk(centering)
        from trial_surface_recovery import recover_upward
        skills.excluded.update(tuple(p) for p in (*plan['floor'], *plan['layout']))
        recovery = recover_upward(skills, max_rises=min(4, max(1, math.ceil(inside[1] - current['pos'][1]))),
                                  max_mined=8)
        skills.event('partial_shelter_return_ascent', inside=list(inside), recovery=recovery,
                     flight_used=False, surface_confirmed=False)
        if recovery.get('actual_rise', 0) >= .75:
            raise Paused('Normal bounded ascent advanced the partial shelter return; rescan this new position next cycle')
    raise Paused('No bounded freshly scanned normal return route to the partial shelter; retain its coordinates')
