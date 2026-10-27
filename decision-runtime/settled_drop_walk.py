"""Read-only recognition of ordinary short coast after the walk drop guard."""
import math
from material_plan import inventory_counts


def conserved_coast(reply, state):
    a, b = reply.get('pos'), state.get('pos')
    if (reply.get('phase') != 'waiting' or reply.get('detail') != 'unsafe drop ahead; choose another walking waypoint'
            or state.get('phase') != reply['phase'] or state.get('detail') != reply['detail']
            or reply.get('world_session') != state.get('world_session')
            or reply.get('id') != state.get('last_request')
            or state.get('health') != 20 or state.get('on_ground') is not True
            or state.get('manual_movement') is not False or state.get('screen')
            or state.get('navigating') or any((state.get('movement_keys') or {}).values())
            or any(not isinstance(p, list) or len(p) != 3
                   or any(type(v) not in (int, float) or not math.isfinite(v) for v in p) for p in (a, b))):
        return False
    return (0 < math.dist(a, b) <= .3 and abs(a[1] - b[1]) <= .05
            and inventory_counts(reply) == inventory_counts(state))
