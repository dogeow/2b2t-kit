"""Read a confirmed first food debit without assigning its unknown recipient."""
from material_plan import inventory_counts

DETAIL = 'Original bread drop lacks its exact server collector receipt; do not repeat'


def settled(command, error, book, events, state, world, task, *, recoverable=False):
    try:
        food = book['pending_food']
        source = food['seen_drop']['entity']
        live=[e for e in state['entities']if e.get('uuid')==source['uuid']]
        ground_ok=(len(live)==1 and live[0].get('id')==source.get('id')and type(source.get('id'))is int
                   and live[0].get('type')=='minecraft:item'and live[0].get('stack',{}).get('item')=='minecraft:bread'
                   and live[0]['stack'].get('count')==1)if recoverable else not live
        if (command['action'] != 'feed_village_founders' or error['error'] != DETAIL
                or error['native_inflight'] is not None or error['unconfirmed_native_request'] is not None
                or book['world_session'] != world or book['complete'] is not False
                or book['pending'] is not None or book.get('recovery_pending') is not None
                or book['required'] != command['quotas'] or food['target'] not in book['required']
                or book['receipts'] or any(book['delivered'].values())
                or source['type'] != 'minecraft:item' or not source['uuid']
                or source['stack']['item'] != 'minecraft:bread' or source['stack']['count'] != 1
                or food['seen_drop']['world_session'] != world
                or food['seen_drop']['runtime_generation'] != state['runtime_generation']
                or inventory_counts(state)['minecraft:bread'] != food['before_bread'] - 1
                or not ground_ok):
            return False
        index = next(i for i, e in enumerate(events) if e['request_id'] == food['native_request'])
        tail = events[index:]
        first = tail[0]
        if (first['op'] != 'villager_bread_drop' or first['phase'] != 'done'
                or first['params']['expected_uuid'] != food['target']
                or first['inventory_delta'] != {'minecraft:bread': -1}):
            return False
        previous = None
        for i, e in enumerate(tail):
            if (e['world_session'] != world or e['params']['task_session'] != task
                    or e['health_before'] != 20 or e['health_after'] != 20
                    or e['phase'] != 'done'
                    or i and (e['op'] not in ('navigate', 'walk', 'scan', 'snapshot') or e['inventory_delta'])
                    or previous is not None and e['revision_before'] != previous['revision_after']):
                return False
            previous = e
        menu = state['menu']
        return (previous['request_id'] == error['last_request'] == state['last_request']
                and previous['revision_after'] == state['control_revision']
                and previous['position_after'] == state['pos']
                and state['health'] == 20 and state['screen'] == ''
                and menu['type'] == 'InventoryMenu' and menu['id'] == 0 and menu['cursor']['count'] == 0
                and state['manual_movement'] is False and not state.get('navigating')
                and not state.get('native_material_busy') and not state.get('pending_scan')
                and isinstance(state['movement_keys'], dict) and not any(state['movement_keys'].values()))
    except (KeyError, TypeError, ValueError, StopIteration):
        return False
