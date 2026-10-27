"""Observe a refused storage entry after resolved movement/inventory preparation."""
from collections import Counter
from material_plan import inventory_counts

ERRORS = {
    'High house storage has no registered same-level return to the door exit': 'StockBlocked',
    'Original storage return body corridor changed; no movement sent': 'StockBlocked',
}
READ_MOVE = frozenset(('scan', 'snapshot', 'navigate', 'walk', 'approach_block', 'select_item', 'look'))


def observable(command, error, baseline, events, state, world, task):
    try:
        if (command['action'] != 'exchange' or error['error'] not in ERRORS
                or error['type'] != ERRORS[error['error']]
                or error['native_inflight'] is not None or error['unconfirmed_native_request'] is not None
                or baseline['phase'] != 'done' or baseline['world_session'] != world or not events
                or inventory_counts(baseline) != inventory_counts(state)
                or state['world_session'] != world or state['connected'] is not True
                or state['health'] != 20 or state['manual_movement'] is not False or state['screen'] != ''
                or state['menu']['type'] != 'InventoryMenu' or state['menu']['id'] != 0
                or state['menu']['cursor']['count'] != 0
                or any(state.get(k) for k in ('navigating', 'native_material_busy', 'pending_scan'))
                or any(state['movement_keys'].values())):
            return False
        revision = baseline['control_revision']
        delta = Counter()
        for event in events:
            p = event['params']
            if (event['phase'] != 'done' or event['world_session'] != world
                    or p['task_session'] != task or event['revision_before'] != revision
                    or event['health_before'] != 20 or event['health_after'] != 20):
                return False
            if event['op'] == 'slot_click':
                if (p['menu_id'] != 0 or not 9 <= p['slot'] <= 44 or p['kind'] != 'pickup'
                        or p['button'] != 0 or not isinstance(p['expected_item'], str)
                        or type(p['expected_count']) is not int or not 0 <= p['expected_count'] <= 64
                        or not isinstance(p['expected_cursor'], str)
                        or type(p['expected_cursor_count']) is not int or not 0 <= p['expected_cursor_count'] <= 64):
                    return False
                delta.update(event['inventory_delta'])
            elif event['op'] not in READ_MOVE or event['inventory_delta'] != {}:
                return False
            revision = event['revision_after']
        last = events[-1]
        return (not any(delta.values()) and revision == state['control_revision']
                and last['request_id'] == error['last_request'] == state['last_request']
                and last['position_after'] == state['pos'])
    except (KeyError, TypeError, ValueError):
        return False
