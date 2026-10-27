"""Admit observation only after the enclosure scan failed before any food intent."""
from material_plan import inventory_counts

DETAIL = 'Founder enclosure has a possible route to the outside'


def observable(command, error, book, event, state, world, task):
    try:
        low, high = command['min'], command['max']
        quota = command['quotas']
        lease = state['supervision_lease']
        return (command['action'] == 'feed_village_founders'
                and error['error'] == DETAIL and error['type'] == 'RuntimeError'
                and error['native_inflight'] is None and error['unconfirmed_native_request'] is None
                and book['complete'] is False and book['pending'] is None and book['pending_food'] is None
                and book['receipts'] == [] and book['required'] == quota
                and book['delivered'] == {uid: 0 for uid in quota}
                and book['error'] == "RuntimeError('" + DETAIL + "')"
                and book['world_session'] == state['world_session'] == event['world_session'] == world
                and event['request_id'] == error['last_request'] == state['last_request']
                and event['op'] == 'scan' and event['phase'] == state['phase'] == 'done'
                and event['params']['min'] == [low[0], low[1]-1, low[2]]
                and event['params']['max'] == high and event['params']['details'] is True
                and event['params']['task_session'] == lease['job_session'] == task
                and lease['kind'] == 'materials' and lease['world_session'] == world
                and event['inventory_delta'] == {}
                and event['position_before'] == event['position_after'] == state['pos']
                and event['revision_before'] == event['revision_after'] == state['control_revision']
                and event['health_before'] == event['health_after'] == state['health'] == 20
                and inventory_counts(state)['minecraft:bread'] == sum(quota.values())
                and state['connected'] is True and state['manual_movement'] is False
                and state['screen'] == '' and state['menu']['cursor']['count'] == 0
                and not state.get('navigating') and not state.get('native_material_busy')
                and not state.get('pending_scan') and not any(state['movement_keys'].values()))
    except (KeyError, TypeError, ValueError):
        return False
