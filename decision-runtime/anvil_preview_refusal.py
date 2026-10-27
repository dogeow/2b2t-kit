"""Only observe an exact anvil face rejection BEFORE its window/input stage."""
from anvil_enchant_preview import stack_key

DETAIL = 'Target interaction face is occluded or out of reach'


def observable(command, error, book, event, reply, state, world, task):
    try:
        menu = state['menu']; params = event['params']
        if not (command['action'] == 'anvil_enchant_preview'
                and error['error'] == DETAIL and error['native_inflight'] is None
                and error['unconfirmed_native_request'] is None
                and book['complete'] is False and book['pending'] == {'stage': 'open_owned_anvil'}
                and book['output_clicks'] == 0 and book['experience_spent'] == 0
                and book['world_session'] == world and book['task_session'] == task
                and book.get('opening_request') is None and book.get('menu_id') is None
                and not book.get('returned_slots') and book.get('cost_levels') is None
                and book['anvil'] == command['pos'] == params['pos']
                and book['left'] == command['expected_left'] and book['right'] == command['expected_right']
                and book['expected_enchantments'] == command['expected_enchantments']
                and book['input_source_slots'] == {'left': command['left_slot'], 'right': command['right_slot']}
                and event['op'] == 'interact' and params['task_session'] == task
                and params['face'] == command.get('face', 'south')
                and any(params['expected_state'].startswith('Block{minecraft:' + k + '}')
                        for k in ('anvil', 'chipped_anvil', 'damaged_anvil'))
                and params['expected_hand'].endswith('_sword')
                and event['phase'] == reply['phase'] == 'error'
                and event['detail'] == reply['detail'] == DETAIL
                and reply.get('outcome_pending') is not True
                and event['request_id'] == reply['id'] == error['last_request'] == state['last_request']
                and event['world_session'] == reply['world_session'] == state['world_session'] == world
                and event['inventory_delta'] == {}
                and event['position_before'] == event['position_after'] == reply['pos'] == state['pos']
                and event['revision_before'] == event['revision_after'] == reply['control_revision'] == state['control_revision']
                and event['health_before'] == event['health_after'] == state['health'] == 20
                and state['connected'] is True and state['manual_movement'] is False
                and state['screen'] == '' and menu['type'] == 'InventoryMenu' and menu['id'] == 0
                and menu['cursor']['count'] == 0 and not state.get('navigating')
                and not state.get('native_material_busy') and not state.get('pending_scan')
                and not any(state['movement_keys'].values())):
            return False
        rows = {r['slot']: r for r in state['inventory']}
        return all(rows[slot]['count'] == 1 and stack_key(rows[slot]) == stack_key(expected)
                   for slot, expected in ((command['left_slot'], command['expected_left']),
                                          (command['right_slot'], command['expected_right'])))
    except (KeyError, TypeError, AttributeError):
        return False
