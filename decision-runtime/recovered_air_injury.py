"""Read-only admission after a known stopped air route and recovered minor injury.

The original arrival remains unconfirmed. No movement or attack is authorized.
"""
import math
from material_plan import inventory_counts
DETAIL = 'air-only waypoint interrupted by new injury; arrival not confirmed'

def observable(command, reply, event, state, world, task):
    try:
        lease = state['supervision_lease']
        positions = reply['pos'] + state['pos']
        return (command['action'] == 'native' and command['op'] == 'navigate'
            and command['params']['air_only'] is True
            and event['params']['target'] == command['params']['target']
            and event['params']['task_session'] == task
            and event['op'] == 'navigate'
            and reply['phase'] == event['phase'] == 'waiting'
            and reply['detail'] == event['detail'] == DETAIL
            and bool(reply['id']) and reply['id'] == event['request_id'] == state['last_request']
            and reply['world_session'] == event['world_session'] == state['world_session'] == world
            and reply['control_revision'] == event['revision_after'] == state['control_revision'] == lease['revision']
            and lease['kind'] == 'materials' and lease['job_session'] == task and lease['world_session'] == world
            and event['health_before'] == 20 and 19 <= event['health_after'] == reply['health'] < 20
            and event['position_after'] == reply['pos'] and event['inventory_delta'] == {}
            and len(reply['pos']) == len(state['pos']) == 3
            and all(type(v) in (int, float) and math.isfinite(v) for v in positions)
            and math.dist(reply['pos'], state['pos']) <= .1
            and inventory_counts(reply) == inventory_counts(state)
            and state['health'] == 20 and state['connected'] is True and state['flight'] is True
            and state['guard_armed'] is True and state['guard_pve_only'] is True and state['guard_busy'] is False
            and state['manual_movement'] is False and state['screen'] == '' and state['under_water'] is False
            and state['time'] - state['recent_hurt_at'] >= 30000
            and not any(state.get(k) for k in ('health_recovery_hold','navigating','native_material_busy','pending_scan'))
            and isinstance(state['movement_keys'], dict) and not any(state['movement_keys'].values())
            and (state.get('safety_hold') or {}).get('active') is False)
    except (KeyError, TypeError, ValueError):
        return False
