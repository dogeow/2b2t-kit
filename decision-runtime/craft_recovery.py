"""Return an owned workbench cursor/inputs through normal inventory clicks."""
import time


def clear_owned_workbench(client):
    state = client.status()
    menu = state.get('menu', {})
    if menu.get('type') != 'CraftingMenu' or menu.get('id') != client.owned_material_menu:
        return False
    menu_id = menu['id']

    def wait_for(predicate):
        until = time.monotonic() + 6
        while True:
            current = client.status()
            m = current['menu']
            if m.get('id') != menu_id or m.get('type') != 'CraftingMenu':
                raise RuntimeError('Owned workbench changed during recovery')
            if predicate(m):
                return current
            if time.monotonic() >= until:
                raise RuntimeError('Workbench recovery not confirmed; no repeated click')
            time.sleep(.15)

    cursor = menu['cursor']
    if cursor['count']:
        # Empty player slots avoid ambiguous same-item/different-component merges.
        free = next((v for v in menu['slots'][-36:] if not v['count']), None)
        if free is None:
            raise RuntimeError('No inventory slot to recover crafting cursor')
        client.checked('slot_click', menu_id=menu_id, slot=free['slot'],
                       expected_item='minecraft:air', expected_count=0, kind='pickup')
        state = wait_for(lambda m: not m['cursor']['count'] and
                         m['slots'][free['slot']]['item'] == cursor['item'] and
                         m['slots'][free['slot']]['count'] == cursor['count'])
    for slot in range(1, 10):
        cell = state['menu']['slots'][slot]
        if not cell['count']:
            continue
        client.checked('slot_click', menu_id=menu_id, slot=slot, expected_item=cell['item'],
                       expected_count=cell['count'], kind='quick_move')
        state = wait_for(lambda m: not m['slots'][slot]['count'])
    return True
