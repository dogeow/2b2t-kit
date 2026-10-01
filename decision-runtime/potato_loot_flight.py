"""Caller-injected potato pickup flight; movement receipts never prove pickup."""
import math

from potato_farm import FarmWait, POTATO, plan
from potato_harvest import _lease


def make_pickup(center, *, radius=2, checkpoint=lambda: None):
    """Return run(pickup=...) for a caller already hovering above source water.

    Native air_only validates the actual complete player-body path. This callback
    offers no fallback, reconnect, mining or anonymous loot collection.
    """
    layout = plan({'authorized': True, 'center': center, 'radius': radius})
    center = layout['center']
    home = [center[0]+.5, center[1]+1.6, center[2]+.5]
    claimed = set()

    def point(value):
        return (isinstance(value, list) and len(value) == 3
                and all(type(v) in (int, float) and math.isfinite(v) for v in value))

    def bounded(pos):
        return (point(pos) and all(layout['scan_min'][i] <= pos[i] < layout['scan_max'][i]+1 for i in (0, 2))
                and center[1] <= pos[1] <= center[1]+2)

    def pickup(c, drop, observation):
        uuid = drop.get('uuid'); stack = drop.get('stack') or {}
        if (not isinstance(uuid, str) or not uuid or uuid in claimed
                or type(drop.get('id')) is not int
                or stack.get('item') != POTATO or type(stack.get('count')) is not int
                or not 1 <= stack['count'] <= 64 or drop.get('remaining_count') != stack['count']
                or not bounded(drop.get('pos'))):
            raise FarmWait('WAIT_LOOT', 'Fresh exact unclaimed potato UUID/count within the field is required')
        hurt = observation.get('recent_hurt_at')
        if type(hurt) is not int:
            raise FarmWait('WAIT_SAFETY', 'Original injury marker is unavailable')

        def safe(state):
            checkpoint(); _lease(c, state, hurt)
            if state.get('flight') is not True or state.get('health') != 20:
                raise FarmWait('WAIT_SAFETY', 'Full-health guarded flight must remain active')

        safe(observation); safe(c.status())
        fresh = c.request('snapshot'); safe(fresh)
        if (type(fresh.get('time')) is not int or type(observation.get('time')) is not int
                or not 0 <= fresh['time']-observation['time'] <= 2500):
            raise FarmWait('WAIT_LOOT', 'Known drop observation became stale before movement')
        current = next((e for e in fresh.get('entities', []) if e.get('uuid') == uuid), None)
        if current is None:
            return {'movement_request': None, 'movement_only': True,
                    'scope': 'known UUID no longer loaded; helper must prove actual pickup'}
        actual = current.get('stack') or {}
        if (current.get('type') != 'minecraft:item' or current.get('id') != drop.get('id')
                or actual.get('item') != POTATO or type(actual.get('count')) is not int
                or actual['count'] != stack['count'] or not bounded(current.get('pos'))
                or math.dist(current['pos'], drop['pos']) > 1
                or not point(fresh.get('pos')) or math.dist(fresh['pos'], home) > .65):
            raise FarmWait('WAIT_LOOT', 'Known UUID/stack or bounded center-hover context changed')
        target = [current['pos'][0], home[1], current['pos'][2]]
        claimed.add(uuid)  # Helper journals this callback before invocation.
        safe(c.status())
        outward = c.checked('navigate', target=target, arrival=.25, seconds=10, air_only=True)
        reached = c.request('snapshot'); safe(reached)
        if not point(reached.get('pos')) or math.dist(reached['pos'], target) > .6:
            raise FarmWait('WAIT_RECONCILE', 'Outward flight arrival is unproved; no movement replay')
        safe(c.status())
        inward = c.checked('navigate', target=home, arrival=.25, seconds=10, air_only=True)
        returned = c.request('snapshot'); safe(returned)
        if not point(returned.get('pos')) or math.dist(returned['pos'], home) > .6:
            raise FarmWait('WAIT_RECONCILE', 'Center return is unproved; no movement replay')
        return {'movement_request': outward.get('id'), 'return_request': inward.get('id'),
                'movement_only': True, 'scope': 'bounded native flight; helper must prove actual pickup'}

    return pickup
