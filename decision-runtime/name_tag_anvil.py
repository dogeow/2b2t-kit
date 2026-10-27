"""Bind the anvil opened by our last ordinary interaction, then validate its preview."""
from material_plan import inventory_counts


def bind(state, reply, command, anvil):
    menu = state.get('menu') or {}
    lease = state.get('supervision_lease') or {}
    previous_lease = reply.get('supervision_lease') or {}
    params = command.get('params') or {}
    source_menu = reply.get('menu') or {}
    source_id = source_menu.get('id')
    new_id = menu.get('id')
    transition = (source_menu.get('type') == 'AnvilMenu' and source_id == new_id
                  or reply.get('screen') == '' and source_id == 0 and new_id != source_id)
    if not (command.get('action') == 'native' and command.get('op') == 'interact'
            and params.get('pos') == anvil and params.get('face') == 'up'
            and params.get('expected_state', '').startswith('Block{minecraft:anvil}')
            and reply.get('phase') == 'done' and bool(reply.get('id'))
            and reply['id'] == state.get('last_request')
            and state.get('connected') is True and state.get('health') == 20
            and state.get('manual_movement') is False and not state.get('health_recovery_hold')
            and not (state.get('safety_hold') or {}).get('active')
            and state.get('world_session') == reply.get('world_session')
            and state.get('control_revision') == reply.get('control_revision')
            and state.get('pos') == reply.get('pos')
            and not any((state.get('movement_keys') or {}).values())
            and lease.get('kind') == 'materials' and bool(lease.get('id'))
            and all(lease.get(k) == previous_lease.get(k) for k in
                    ('id', 'job_session', 'world_session', 'kind'))
            and state.get('screen') == 'AnvilScreen' and menu.get('type') == 'AnvilMenu'
            and type(new_id) is int and new_id > 0 and transition
            and len(menu.get('slots', [])) >= 3 and not menu.get('cursor', {}).get('count')
            and all(not r['count'] for r in menu['slots'][:3])
            and inventory_counts(state)['minecraft:name_tag'] == 1):
        raise ValueError('Only the unchanged anvil opened by our last interaction may be bound')
    return {'type': 'AnvilMenu', 'id': new_id, 'world_session': state['world_session'],
            'lease_id': lease['id'], 'task_session': lease['job_session'],
            'control_revision': state['control_revision'], 'purpose': 'name_tag_rename',
            'source_request': reply['id'], 'source_command': command['id'], 'anvil_pos': anvil}


def preview(state, menu_id):
    """This proves quantity and affordable cost; the UI must separately witness the name."""
    m = state.get('menu') or {}
    rows = m.get('slots') or []
    if not (m.get('type') == 'AnvilMenu' and m.get('id') == menu_id and len(rows) >= 3
            and not m.get('cursor', {}).get('count')
            and rows[0]['item'] == rows[2]['item'] == 'minecraft:name_tag'
            and rows[0]['count'] == rows[2]['count'] == 1 and not rows[1]['count']
            and m.get('anvil_cost') == 1 and state.get('experience_level', 0) >= 1
            and m.get('anvil_result_may_pickup') is True and not m.get('anvil_too_expensive')):
        raise ValueError('Expected one name tag and an affordable one-level rename preview')
    return rows[2], 1


def permitted_click(state, certificate, params):
    """Two cursor-free quick moves only; no general anvil or inventory permission."""
    m = state.get('menu') or {}
    rows = m.get('slots') or []
    slot = params.get('slot')
    if not (certificate.get('purpose') == 'name_tag_rename'
            and certificate.get('type') == m.get('type') == 'AnvilMenu'
            and certificate.get('id') == params.get('menu_id') == m.get('id')
            and bool(certificate.get('source_request'))
            and params.get('kind') == 'quick_move' and params.get('button') == 0
            and type(slot) is int and 0 <= slot < len(rows)
            and params.get('expected_item') == rows[slot].get('item') == 'minecraft:name_tag'
            and params.get('expected_count') == rows[slot].get('count') == 1
            and params.get('expected_cursor') == 'minecraft:air'
            and params.get('expected_cursor_count') == 0
            and m.get('cursor', {}).get('count') == 0):
        return False
    if slot >= 3:
        return all(not r['count'] for r in rows[:3]) and inventory_counts(state)['minecraft:name_tag'] == 1
    witness = certificate.get('ui_name_witness') or {}
    if (slot != 2 or witness.get('text') != 'Kit Iron Farm'
            or witness.get('menu_id') != m['id']
            or witness.get('source_request') != state.get('last_request')):
        return False
    try:
        preview(state, m['id'])
    except ValueError:
        return False
    return True
