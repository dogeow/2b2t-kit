"""Pure load goals from current inventory/deficit; no transfers or game actions."""
from copy import deepcopy
import hashlib
import json
import re
from kit_runtime.inventory import destination_capacity

_ITEM = re.compile(r'minecraft:[a-z0-9_]+\Z')
_ORDER = tuple(range(9, 36)) + tuple(range(9))  # Actual chest player-slot order.
_RESERVE = 2


def _blocked(code, detail, item, missing):
    return {'schema': 1, 'phase': 'blocked', 'code': code, 'detail': detail,
            'item': item, 'missing_cells': missing, 'withdraw_amount': 0,
            'construction_cells': 0, 'game_operations': 0, 'placement_credit': 0}


def _metadata(row):
    return {k: deepcopy(v) for k, v in row.items() if k not in ('slot', 'count')}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def plan_stock(inventory, item, missing_cells, actual_stack_max, *, stack_metadata=None):
    """Allocate one material load, keeping two in every hand used for building.

    Inputs must be current native observations: exactly43 inventory slots,
    independently audited missing cells, actual stack limit and complete source
    metadata (source slot/count may be included). Source quantities, cursor,
    packed contents and future allocations are never acknowledged loose stock.
    Other-metadata target stacks remain protected and are neither filled nor
    spent. A kernel still needs source/menu/conservation and legal select proofs.
    """
    if not isinstance(item, str) or not _ITEM.fullmatch(item) or item == 'minecraft:air':
        return _blocked('item_unknown', 'One explicit block item is required', item, missing_cells)
    if type(missing_cells) is not int or missing_cells < 0:
        return _blocked('deficit_unknown', 'A current integer missing-cell count is required', item, missing_cells)
    if type(actual_stack_max) is not int or not 1 <= actual_stack_max <= 99:
        return _blocked('stack_max_unknown', 'Actual native max_stack is required; never guess64', item, missing_cells)
    if actual_stack_max <= _RESERVE and missing_cells:
        return _blocked('stack_reserve_unusable', 'Stack limit cannot retain two and place a block', item, missing_cells)
    if (not isinstance(stack_metadata, dict) or stack_metadata.get('item') != item
            or type(stack_metadata.get('max_stack')) is not int or stack_metadata['max_stack'] != actual_stack_max
            or 'count' in stack_metadata and (type(stack_metadata['count']) is not int
                                             or not 1 <= stack_metadata['count'] <= actual_stack_max)):
        return _blocked('stack_metadata_unknown', 'Exact source item/max_stack/metadata is required', item, missing_cells)
    try:
        source_meta = _metadata(stack_metadata)
        source_key = _json(source_meta)
        if (not isinstance(inventory, list) or len(inventory) != 43
                or any(not isinstance(r, dict) or type(r.get('slot')) is not int
                       or not isinstance(r.get('item'), str) or not _ITEM.fullmatch(r['item'])
                       or type(r.get('count')) is not int or r['count'] < 0
                       or type(r.get('max_stack')) is not int or not 1 <= r['max_stack'] <= 99
                       or r['count'] > r['max_stack']
                       or (r['item'] == 'minecraft:air') != (r['count'] == 0) for r in inventory)
                or {r['slot'] for r in inventory} != set(range(43))):
            return _blocked('inventory_unknown', 'Complete typed43 counts and native limits are required', item, missing_cells)
        rows = {r['slot']: deepcopy(r) for r in inventory}
        _json(rows)
    except (TypeError, ValueError):
        return _blocked('metadata_unknown', 'Metadata must be exact finite serializable native data', item, missing_cells)
    empty = [s for s in _ORDER if rows[s]['count'] == 0]
    if any(set(rows[s]) != {'slot', 'item', 'count', 'max_stack'} or rows[s]['max_stack'] != 1 for s in empty):
        return _blocked('empty_slot_unknown', 'Receiving slots need canonical AIR/count0/max_stack1', item, missing_cells)
    same = [s for s in _ORDER if rows[s]['item'] == item and rows[s]['count']
            and _json(_metadata(rows[s])) == source_key]
    protected_target = [s for s in range(36) if rows[s]['item'] == item and rows[s]['count'] and s not in same]
    usable_before = sum(max(0, rows[s]['count'] - _RESERVE) for s in same)
    counts = {s: rows[s]['count'] for s in same}
    remaining = max(0, missing_cells - usable_before)
    additions = {}
    source = {**source_meta, 'count': 1}  # Capacity template, not a fabricated observation.
    for s in same + empty:
        if not remaining:
            break
        before = counts.get(s, 0)
        # Both occupied/source limits are known, so no default capacity is used.
        room = max(0, destination_capacity(source, rows[s]) - before)
        take = min(room, remaining + max(0, _RESERVE - before))
        gain = max(0, before + take - _RESERVE) - max(0, before - _RESERVE)
        if gain > 0:
            additions[s] = take
            counts[s] = before + take
            remaining -= gain
    usable_after = sum(max(0, n - _RESERVE) for n in counts.values())
    load_cells = min(missing_cells, usable_after)
    schedule, left = [], load_cells
    for s in sorted(counts, key=lambda slot: (-counts[slot], slot >= 9, slot)):
        budget = max(0, counts[s] - _RESERVE)
        planned = min(left, budget)
        if planned:
            schedule.append({'slot': s, 'expected_count_after_supply': counts[s], 'stack_max': actual_stack_max,
                             'usable_budget': budget, 'planned_cells': planned,
                             'retained_after_cells': counts[s] - planned,
                             'actual_stack_and_legal_select_required': True})
            left -= planned
    allocations = [{'slot': s, 'observed_count': rows[s]['count'], 'target_count': counts[s],
                    'additional_count': additions[s], 'metadata': deepcopy(source_meta),
                    'expected_only_not_observed': True} for s in same + empty if s in additions]
    withdraw = sum(additions.values())
    current = sum(rows[s]['count'] for s in same)
    current_main_item = sum(rows[s]['count'] for s in range(36) if rows[s]['item'] == item)
    used = {s['slot'] for s in schedule}
    return {'schema': 1, 'phase': 'ready' if load_cells == missing_cells else 'partial' if load_cells else 'blocked',
            'code': 'load_planned' if load_cells == missing_cells else 'main_capacity_limited',
            'scope': 'pure allocation goals; no source availability or mutation acknowledgement',
            'item': item, 'missing_cells': missing_cells, 'actual_stack_max': actual_stack_max,
            'reserve_per_stack': _RESERVE, 'current_eligible_stock': current,
            'current_main_item_stock': current_main_item,
            'stock_total_target': current_main_item + withdraw,
            'eligible_stock_total_target': current + withdraw, 'withdraw_amount': withdraw,
            'usable_before': usable_before, 'usable_after_supply': usable_after,
            'construction_cells': load_cells, 'remaining_cells': missing_cells - load_cells,
            'remaining_purchase_minimum': missing_cells - load_cells,
            'remaining_requires_new_inventory_plan': load_cells < missing_cells,
            'allocations': allocations, 'construction_stacks': schedule,
            'supply_preserved_inventory': [deepcopy(rows[s]) for s in range(43) if s not in additions],
            'protected_inventory': [deepcopy(rows[s]) for s in range(43) if s not in additions and s not in used],
            'protected_different_metadata_target_slots': protected_target,
            'metadata_scoped_transfer_required': bool(protected_target),
            'item_only_transfer_authorized': False,
            'excluded_auxiliary_target_count': sum(rows[s]['count'] for s in range(36, 43) if rows[s]['item'] == item),
            'main_empty_slots': len(empty),
            'input_inventory_sha256': hashlib.sha256(_json([rows[s] for s in range(43)]).encode()).hexdigest(),
            'cursor_credited': False, 'packed_contents_credited': False,
            'equipment_and_non_target_slots_preserved': True, 'source_availability_proved': False,
            'source_routes_require_actual_inventory': True,
            'requires_fresh_native_supply_and_per_stack_proof': True,
            'game_operations': 0, 'placement_credit': 0}
