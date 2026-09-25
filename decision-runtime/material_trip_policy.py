"""Decide when a collection trip has actually filled the backpack."""


def carried(state, item):
    return sum(row['count'] for row in state.get('inventory', [])
               if 0 <= row.get('slot', -1) < 36 and row['item'] == item)


def room_for_item(state, item, stack_size=64):
    if not 1 <= stack_size <= 64:
        raise ValueError('Item stack size must be 1..64')
    slots = [row for row in state.get('inventory', [])
             if 0 <= row.get('slot', -1) < 36]
    if len(slots) != 36 or len({row['slot'] for row in slots}) != 36:
        raise RuntimeError('Cannot decide trip capacity from an incomplete backpack snapshot')
    return sum(stack_size if row.get('count', 0) == 0 or row['item'] == 'minecraft:air'
               else max(0, row.get('max_stack', 64) - row['count'])
               if row['item'] == item else 0 for row in slots)


def trip_complete(state, item, target_carried=None, stack_size=64):
    if target_carried is not None and target_carried < 1:
        raise ValueError('Target carried amount must be positive')
    return (room_for_item(state, item, stack_size) == 0 or
            target_carried is not None and carried(state, item) >= target_carried)
