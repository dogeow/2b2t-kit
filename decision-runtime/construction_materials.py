"""Allocate observed construction stock to real backpack capacity, preserving equipment."""
import math
from build_supervisor import stocks


PRIORITY = ('minecraft:white_concrete', 'minecraft:smooth_stone',
            'minecraft:deepslate_tiles', 'minecraft:polished_andesite',
            'minecraft:blast_furnace', 'minecraft:hopper')


def supply_targets(state, needed, stored, reserve_empty=1, stack_sizes=None):
    slots = [row for row in state.get('inventory', []) if 0 <= row.get('slot', -1) < 36]
    if len(slots) != 36 or len({row['slot'] for row in slots}) != 36:
        raise RuntimeError('Complete backpack observation required before construction supplies')
    if type(reserve_empty) is not int or not 0 <= reserve_empty <= 36:
        raise ValueError('Reserve must be a valid number of backpack slots')
    empty = max(0, sum(row.get('count', 0) == 0 for row in slots) - reserve_empty)
    carried = stocks(state)
    result = {}
    stack_sizes=stack_sizes or {}
    for item in (*PRIORITY,*sorted(set(needed)-set(PRIORITY))):
        size=stack_sizes.get(item,64 if item in PRIORITY else None)
        if type(size) is not int or not 1<=size<=99:
            continue
        have = carried.get(item, 0)
        want = max(0, needed.get(item, 0) - have)
        partial = sum(max(0, row.get('max_stack', 64) - row['count'])
                      for row in slots if row['item'] == item and row['count'])
        take = min(want, stored.get(item, 0), partial + empty * size)
        if take:
            result[item] = have + take
            empty -= math.ceil(max(0, take - partial) / size)
    return result
