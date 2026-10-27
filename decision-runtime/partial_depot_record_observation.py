"""Observe completed depot visits before an unstarted missing-record access."""
from material_plan import inventory_counts, quantities


def observable(command, error, baseline, visits, event, state, world, task):
    try:
        if (command['action'] != 'exchange' or command.get('deposit')
                or error['error'] != 'Storage position has no current scoped Kit record'
                or error['native_inflight'] is not None or error['unconfirmed_native_request'] is not None
                or baseline['phase'] != 'done' or baseline['world_session'] != world
                or not 0 < len(visits) < len(command['positions'])
                or event['request_id'] != error['last_request'] or event['request_id'] != state['last_request']
                or event['world_session'] != world or event['op'] != 'close_menu' or event['phase'] != 'done'
                or event['inventory_delta'] != {} or event['params']['task_session'] != task
                or event['revision_before'] != event['revision_after'] or event['revision_after'] != state['control_revision']
                or event['position_before'] != event['position_after'] or event['position_after'] != state['pos']
                or event['health_before'] != event['health_after'] or state['health'] != event['health_after'] or state['health'] != 20
                or state['world_session'] != world or state['connected'] is not True
                or state['manual_movement'] is not False or state['screen'] != ''
                or state['menu']['type'] != 'InventoryMenu' or state['menu']['cursor']['count'] != 0
                or any(state.get(k) for k in ('navigating', 'native_material_busy', 'pending_scan'))
                or any(state['movement_keys'].values())):
            return False
        expected = inventory_counts(baseline)
        stamp = baseline['time']
        targets = quantities(command['withdraw'])
        for pos, visit in zip(command['positions'], visits):
            if visit['pos'] != pos or not stamp < visit['at_ms'] <= state['time']:
                return False
            before, after = quantities(visit['before']), quantities(visit['after'])
            if before != expected:
                return False
            for item in set(before) | set(after):
                change = after[item] - before[item]
                if change < 0 or change and (item not in targets or after[item] > targets[item]):
                    return False
            expected, stamp = after, visit['at_ms']
        return inventory_counts(state) == expected
    except (KeyError, TypeError, ValueError):
        return False
