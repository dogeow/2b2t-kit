"""Exact transfers between ordinary storage slots, with no ambiguous click replay."""
from kit_runtime.inventory import destination_capacity


def move_amount(session, state, source, destination, amount):
    menu_id = state['menu']['id']
    source_slot, size, item = source['slot'], source['count'], source['item']
    target_slot, initial = destination['slot'], destination['count']
    if (not 0 < amount <= size or source_slot == target_slot
            or initial and destination['item'] != item
            or initial + amount > destination_capacity(source, destination)):
        raise ValueError('Storage transfer does not fit its source and destination')
    if state['menu']['cursor']['count']:
        raise RuntimeError('Storage transfer requires an empty cursor')
    session._expect_slot(state, source_slot, item, size)
    session._expect_slot(state, target_slot, item, initial)

    # Choose the fewest single-item clicks after a full/half pickup. A whole
    # stack can then be placed or returned in one click without crossing target.
    choices = [(min(amount, picked - amount), picked, button)
               for picked, button in ((size, 0), ((size + 1) // 2, 1))
               if picked >= amount]
    _, picked, button = min(choices)
    direct = amount < picked - amount

    def wait(current, source_count, target_count, carried, stage):
        return session._wait(current, menu_id, lambda m:
            m['slots'][source_slot]['count'] == source_count
            and (not source_count or m['slots'][source_slot]['item'] == item)
            and m['slots'][target_slot]['count'] == target_count
            and (not target_count or m['slots'][target_slot]['item'] == item)
            and m['cursor']['count'] == carried
            and (not carried or m['cursor']['item'] == item), stage)

    state = session.click(state, source_slot, button=button)
    state = wait(state, size - picked, initial, picked, 'storage_pickup')
    if direct:
        for placed in range(amount):
            state = session.click(state, target_slot, button=1)
            state = wait(state, size - picked, initial + placed + 1,
                         picked - placed - 1, 'storage_place')
        state = session.click(state, source_slot)
    else:
        for returned in range(picked - amount):
            state = session.click(state, source_slot, button=1)
            state = wait(state, size - picked + returned + 1, initial,
                         picked - returned - 1, 'storage_remainder')
        state = session.click(state, target_slot)
    return wait(state, size - amount, initial + amount, 0, 'storage_complete')
