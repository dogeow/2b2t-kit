"""Return task-owned crafting cursor/inputs through verified inventory clicks."""
import json
import time


def _owns_inventory_crafting(client, state, menu):
    """Require the exact lease and the empty-preflight ownership marker."""
    marker = getattr(client, 'owned_inventory_crafting', None)
    heartbeat = getattr(client, 'heartbeat', None)
    lease = state.get('supervision_lease') or {}
    isolation = state.get('inventory_isolation') or {}
    world = getattr(client, 'world', None)
    task = getattr(client, 'task', None)
    return bool(
        isinstance(marker, dict)
        and marker.get('menu_id') == 0
        and marker.get('world_session') == world == state.get('world_session')
        and marker.get('task_session') == task and task
        and menu.get('type') == 'InventoryMenu' and menu.get('id') == 0
        and not state.get('screen') and not state.get('manual_movement')
        and state.get('connected') is True
        and state.get('inventory_cursor_precondition_protocol', 0) >= 1
        and isolation.get('supported') is True and isolation.get('active') is True
        and heartbeat is not None and getattr(heartbeat, 'attached', False)
        and lease.get('kind') == 'materials' and lease.get('job_session') == task
        and lease.get('id') == getattr(heartbeat, 'id', None)
        and lease.get('world_session') == world
        and lease.get('revision') == state.get('control_revision')
    )


def clear_owned_workbench(client):
    state = client.status()
    menu = state.get('menu', {})
    menu_type = menu.get('type')
    workbench = (menu_type == 'CraftingMenu'
                 and menu.get('id') == getattr(client, 'owned_material_menu', None))
    inventory = _owns_inventory_crafting(client, state, menu)
    if not workbench and not inventory:
        return False
    menu_id = menu['id']

    def menu_signature(current):
        m = current.get('menu', {})
        return ((m.get('cursor', {}).get('item'), m.get('cursor', {}).get('count')),
                tuple((row.get('item'), row.get('count')) for row in m.get('slots', [])))

    def fresh_stable(current, confirmations=3):
        """Let an already-sent click finish before recovery mutates the menu.

        A failed dependent click can expose a short-lived server rollback of the
        preceding successful click.  Acting on that one frame can move the wrong
        cursor stack.  Recovery therefore observes a time-advanced, unchanged
        menu three times before deciding what it owns and needs to return.
        """
        until = time.monotonic() + 6
        last_time = current.get('time')
        poll_interval = .1 if isinstance(last_time, (int, float)) else 0
        last_signature = None
        seen = 0
        while True:
            current = client.status()
            m = current.get('menu', {})
            if (m.get('id') != menu_id or m.get('type') != menu_type
                    or inventory and not _owns_inventory_crafting(client, current, m)):
                raise RuntimeError('Owned crafting menu changed during recovery')
            observed_time = current.get('time')
            advanced = (not isinstance(last_time, (int, float))
                        or not isinstance(observed_time, (int, float))
                        or observed_time > last_time)
            if advanced:
                signature = menu_signature(current)
                seen = seen + 1 if signature == last_signature else 1
                last_signature = signature
                if isinstance(observed_time, (int, float)):
                    last_time = observed_time
                if seen >= confirmations:
                    return current
            if time.monotonic() >= until:
                raise RuntimeError('Crafting recovery menu did not settle; no click was sent')
            time.sleep(poll_interval)

    state = fresh_stable(state)
    menu = state['menu']

    def wait_for(predicate):
        until = time.monotonic() + 6
        last_time = state.get('time')
        poll_interval = .1 if isinstance(last_time, (int, float)) else 0
        seen = 0
        while True:
            current = client.status()
            m = current.get('menu', {})
            if (m.get('id') != menu_id or m.get('type') != menu_type
                    or inventory and not _owns_inventory_crafting(client, current, m)):
                raise RuntimeError('Owned crafting menu changed during recovery')
            observed_time = current.get('time')
            advanced = (not isinstance(last_time, (int, float))
                        or not isinstance(observed_time, (int, float))
                        or observed_time > last_time)
            if advanced:
                seen = seen + 1 if predicate(m) else 0
                if isinstance(observed_time, (int, float)):
                    last_time = observed_time
                if seen >= 2:
                    return current
            if time.monotonic() >= until:
                raise RuntimeError('Crafting recovery not confirmed; no repeated click')
            time.sleep(poll_interval)

    recovered = {'schema': 1, 'menu_type': menu_type, 'menu_id': menu_id,
                 'guard_armed': state.get('guard_armed') is True,
                 'cursor': None, 'grid_slots': [], 'confirmed': False}
    cursor = dict(menu['cursor'])
    if cursor['count']:
        # InventoryMenu slots 9..44 are ordinary storage. Slot 45 is offhand
        # and must never be used as recovery scratch space.
        player_slots = menu['slots'][-36:] if workbench else menu['slots'][9:45]
        free = next((row for row in player_slots
                     if row.get('item') == 'minecraft:air' and row.get('count') == 0), None)
        if free is None:
            raise RuntimeError('No empty ordinary inventory slot to recover crafting cursor')
        client.checked('slot_click', menu_id=menu_id, slot=free['slot'],
                       expected_item='minecraft:air', expected_count=0,
                       expected_cursor=cursor['item'], expected_cursor_count=cursor['count'],
                       kind='pickup')
        state = wait_for(lambda m: not m['cursor']['count'] and
                         m['slots'][free['slot']]['item'] == cursor['item'] and
                         m['slots'][free['slot']]['count'] == cursor['count'])
        recovered['cursor'] = {'item': cursor['item'], 'count': cursor['count'],
                               'destination_slot': free['slot'],
                               'expected_destination': {'item': 'minecraft:air', 'count': 0}}
    grid_slots = range(1, 10) if workbench else range(1, 5)
    for slot in grid_slots:
        cell = state['menu']['slots'][slot]
        if not cell['count']:
            continue
        client.checked('slot_click', menu_id=menu_id, slot=slot, expected_item=cell['item'],
                       expected_count=cell['count'], expected_cursor='minecraft:air',
                       expected_cursor_count=0, kind='quick_move')
        state = wait_for(lambda m, slot=slot: not m['cursor']['count']
                         and not m['slots'][slot]['count'])
        recovered['grid_slots'].append(slot)
    recovered['confirmed'] = not state['menu']['cursor']['count'] and all(
        not state['menu']['slots'][slot]['count'] for slot in grid_slots)
    if inventory and recovered['confirmed']:
        client.owned_inventory_crafting = None
    if recovered['cursor'] is not None or recovered['grid_slots']:
        try:
            (client.out/'craft-recovery.json').write_text(
                json.dumps(recovered, ensure_ascii=False, indent=2))
        except (AttributeError, OSError, TypeError):
            pass
    return recovered['confirmed']
