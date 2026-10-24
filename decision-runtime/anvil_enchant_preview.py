"""Owned, zero-XP anvil preview; return BOTH inputs and never click output.

Uses the existing normal block use and InventorySession transactions. It does
not use the integrated-server-only inventory_probe or claim full component
equality. Visible stack identities, XP levels, lease and window are verified.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import json
import time

from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json

_LEFT = {'minecraft:enchanted_book', 'minecraft:wooden_shovel',
         'minecraft:bow', 'minecraft:crossbow', 'minecraft:trident'} | {
    'minecraft:diamond_' + name for name in
    ('helmet', 'chestplate', 'leggings', 'boots', 'sword', 'pickaxe', 'axe', 'shovel', 'hoe')}


def enchantments(row):
    field = 'stored_enchantments' if row.get('item') == 'minecraft:enchanted_book' else 'enchantments'
    return {r['id']: r['level'] for r in row.get(field, [])}


def stack_key(row):
    value = {k: deepcopy(v) for k, v in row.items() if k not in ('slot', 'count')}
    for field in ('enchantments', 'stored_enchantments'):
        if field in value:
            value[field] = sorted(value[field], key=lambda v: (v['id'], v['level']))
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def bag(state):
    result = Counter()
    for row in state['inventory']:
        if row.get('count'):
            result[stack_key(row)] += row['count']
    return result


def menu_slot(inventory_slot):
    if type(inventory_slot) is not int or not 0 <= inventory_slot < 36:
        raise ValueError('Explicit carried inventory slot 0..35 required')
    return 30 + inventory_slot if inventory_slot < 9 else 3 + inventory_slot - 9


def validate_inputs(left, right, expected):
    if (left.get('count') != 1 or left.get('item') not in _LEFT
            or right.get('count') != 1 or right.get('item') != 'minecraft:enchanted_book'
            or not enchantments(right)):
        raise ValueError('One approved base and one observed enchanted book required')
    if not isinstance(expected, dict) or not expected or any(
            not isinstance(k, str) or not k.startswith('minecraft:')
            or type(v) is not int or v < 1 for k, v in expected.items()):
        raise ValueError('Explicit complete expected output enchantments required')
    union = {**enchantments(left), **enchantments(right)}
    if set(expected) != set(union):
        raise ValueError('Preview cannot invent or discard an input enchantment')
    for row in (left, right):
        for name, level in enchantments(row).items():
            if name.endswith('_curse') or expected.get(name, 0) < level:
                raise ValueError('Cursed inputs or stripped enchantments are not approved')


def inspect_preview(state, left, right, expected):
    menu = state['menu']; slots = menu['slots']
    if (menu.get('type') != 'AnvilMenu' or len(slots) != 39
            or menu.get('cursor', {}).get('count')
            or any(stack_key(slots[i]) != stack_key(row) or slots[i].get('count') != 1
                   for i, row in enumerate((left, right)))):
        raise RuntimeError('Exact owned anvil inputs changed; no output or recovery replay')
    cost = menu.get('anvil_cost')
    if type(cost) is not int or cost < 0:
        raise RuntimeError('Actual anvil cost is unavailable')
    output = slots[2]
    expected_item = left['item']
    matches = (output.get('count') == 1 and output.get('item') == expected_item
               and enchantments(output) == expected
               and all(output.get(k) == left.get(k) for k in ('durability', 'max_durability')))
    return {'cost_levels': cost, 'result': deepcopy(output),
            'result_matches': bool(matches), 'too_expensive': menu.get('anvil_too_expensive') is True,
            'affordable_now': menu.get('anvil_result_may_pickup') is True,
            'preview_accepted': bool(cost > 0 and matches)}


def infer_left_penalty(preview, *, right_enchantment_value, right_penalty):
    if (preview.get('complete') is not True or preview.get('inputs_returned') is not True
            or preview.get('output_clicks') != 0 or preview.get('preview_accepted') is not True):
        raise ValueError('A completed exact zero-output preview is required')
    if (type(right_enchantment_value) is not int or right_enchantment_value < 1
            or type(right_penalty) is not int or right_penalty < 0):
        raise ValueError('Known right-hand values required, not a fresh-book assumption')
    penalty = preview['cost_levels'] - right_enchantment_value - right_penalty
    if penalty < 0:
        raise ValueError('Preview differs from the supplied native cost model')
    return penalty


def infer_right_penalty(preview, *, right_enchantment_value, left_penalty):
    """The same native equation, with a genuinely known fresh left seed."""
    return infer_left_penalty(preview, right_enchantment_value=right_enchantment_value,
                              right_penalty=left_penalty)


def _wait(client, predicate, *, seconds=6):
    end = time.monotonic() + seconds; seen = []; last = None
    while True:
        state = client.status()
        if not predicate(state):
            seen = []
        elif last is None or state['time'] > last:
            seen.append(state['time']); last = state['time']
            if len(seen) == 2:
                return state, seen
        if time.monotonic() >= end:
            raise RuntimeError('Original preview/input observation unconfirmed; no click replay')
        time.sleep(.15)


def run(client, pos, left_slot, right_slot, expected_left, expected_right, expected, out, *, face='south'):
    """Actor must already be at a valid anvil stance; this never finds a route."""
    if (not isinstance(pos, list) or len(pos) != 3 or any(type(v) is not int for v in pos)
            or face not in ('north', 'south', 'east', 'west', 'up')):
        raise ValueError('Explicit anvil block and ordinary interaction face required')
    lslot, rslot = menu_slot(left_slot), menu_slot(right_slot)
    if left_slot == right_slot:
        raise ValueError('Two distinct carried input slots required')
    validate_inputs(expected_left, expected_right, expected)
    initial = client.status(); cursor = initial.get('menu', {}).get('cursor', {})
    if initial.get('screen') or cursor.get('count'):
        raise ValueError('Preview must open its own anvil from a clean world interface')
    held = {r['slot']: r for r in initial['inventory']}
    for slot, expected_row in ((left_slot, expected_left), (right_slot, expected_right)):
        if held.get(slot, {}).get('count') != 1 or stack_key(held[slot]) != stack_key(expected_row):
            raise ValueError('Declared carried input identity changed before opening')
    hand = initial.get('hand', {}).get('item', '')
    if not hand.endswith('_sword'):
        raise ValueError('Select an existing safe container hand before binding input slots')
    out = Path(out); out.mkdir(exist_ok=False); path = out / 'preview.json'
    record = {'complete': False, 'pending': None, 'world_session': client.world,
              'task_session': client.task,
              'input_source_slots': {'left': left_slot, 'right': right_slot},
              'anvil': pos, 'left': deepcopy(expected_left), 'right': deepcopy(expected_right),
              'expected_enchantments': expected, 'output_clicks': 0, 'experience_spent': 0}
    def save(): write_json(path, record)
    save()
    scanned = client.checked('scan', min=pos, max=pos, details=True)
    if (len(scanned.get('blocks', [])) != 1 or not any(
            scanned['blocks'][0]['state'].startswith('Block{minecraft:' + k + '}')
            for k in ('anvil', 'chipped_anvil', 'damaged_anvil'))):
        raise ValueError('Actual anvil is absent; no input moved')
    record['pending'] = {'stage': 'open_owned_anvil'}; save()
    opened = client.checked('interact', pos=pos, face=face,
                            expected_state=scanned['blocks'][0]['state'], expected_hand=hand)
    state, _ = _wait(client, lambda s: s['menu']['type'] == 'AnvilMenu' and s['menu']['id'] > 0)
    menu = state['menu']; mid = menu['id']
    if len(menu['slots']) != 39 or menu['cursor']['count'] or any(r['count'] for r in menu['slots'][:3]):
        raise RuntimeError('Own anvil opening did not yield empty inputs; no transfer')
    before = bag(state); level = state['experience_level']
    for slot, row in ((lslot, expected_left), (rslot, expected_right)):
        if menu['slots'][slot]['count'] != 1 or stack_key(menu['slots'][slot]) != stack_key(row):
            raise RuntimeError('Anvil menu source identity differs from bound carried input')
    client.owned_material_menu = mid
    from owned_material_menu import owned_menu_result
    owned_menu_result(client, {})
    record.update(pending=None, opening_request=opened['id'], menu_id=mid, level_before=level,
                  lease_id=state['supervision_lease']['id'], control_revision=state['control_revision'],
                  returned_slots={}); save()
    session = InventorySession(client)
    for source_slot, cell, source in ((lslot, 0, expected_left), (rslot, 1, expected_right)):
        state = client.status(); row = state['menu']['slots'][source_slot]
        if row['count'] != 1 or stack_key(row) != stack_key(source):
            raise RuntimeError('Input changed before original placement; no substitute')
        record['pending'] = {'stage': 'place_input', 'source': source_slot, 'cell': cell}; save()
        session.place_cell(state, row, cell, 1)
        _wait(client, lambda s, cell=cell, source=source:
              s['menu']['id'] == mid and not s['menu']['cursor']['count']
              and s['menu']['slots'][cell]['count'] == 1
              and stack_key(s['menu']['slots'][cell]) == stack_key(source))
        record['pending'] = None; save()
    # Allow server costs/results to settle, including unaffordable valid previews.
    end = time.monotonic() + 6; last = None; repeated = 0; last_time = None; preview_times = []
    while True:
        state = client.status()
        if state['menu']['id'] != mid:
            raise RuntimeError('Original anvil window changed; no recovery or output sent')
        preview = inspect_preview(state, expected_left, expected_right, expected)
        key = (preview['cost_levels'], stack_key(preview['result']), preview['result'].get('count'))
        if last != key:
            repeated = 1; preview_times = [state['time']]; last_time = state['time']
        elif state['time'] > last_time:
            repeated += 1; preview_times.append(state['time']); last_time = state['time']
        last = key
        if repeated >= 2 and (preview['preview_accepted'] or preview['too_expensive'] or time.monotonic() >= end):
            break
        if time.monotonic() >= end:
            break
        time.sleep(.15)
    if repeated < 2:
        raise RuntimeError('Cost/result preview lacks two fresh frames; no recovery or output sent')
    record.update(preview, pending=None, preview_times=preview_times[-2:]); save()
    # Only input cells are clicked. Output slot 2 is intentionally unreachable.
    for cell, source in ((1, expected_right), (0, expected_left)):
        state = client.status(); row = state['menu']['slots'][cell]
        if state['menu']['id'] != mid or row['count'] != 1 or stack_key(row) != stack_key(source):
            raise RuntimeError('Original input changed before return; no recovery replay')
        record['pending'] = {'stage': 'return_input', 'cell': cell}; save()
        player_before = deepcopy(state['menu']['slots'][3:])
        session.click(state, cell, 'quick_move')
        returned, _ = _wait(client, lambda s, cell=cell: s['menu']['id'] == mid
                           and not s['menu']['cursor']['count'] and not s['menu']['slots'][cell]['count'])
        changed = [(old, new) for old, new in zip(player_before, returned['menu']['slots'][3:])
                   if old['count'] != new['count'] or stack_key(old) != stack_key(new)]
        if (len(changed) != 1 or changed[0][0]['count'] != 0
                or changed[0][1]['count'] != 1 or stack_key(changed[0][1]) != stack_key(source)):
            raise RuntimeError('Input return destination is ambiguous; no next click or output sent')
        destination = changed[0][1]['slot']
        inventory_slot = destination - 30 if destination >= 30 else destination + 6
        record['returned_slots']['right' if cell == 1 else 'left'] = inventory_slot
        record['pending'] = None; save()
    state, times = _wait(client, lambda s: s['menu']['id'] == mid and not s['menu']['cursor']['count']
                        and all(not r['count'] for r in s['menu']['slots'][:3])
                        and bag(s) == before and s['experience_level'] >= level)
    record['pending'] = {'stage': 'close_empty_owned_anvil'}; save()
    client.checked('close_menu')
    final, closed_times = _wait(client, lambda s: not s.get('screen') and s['menu']['id'] == 0
                               and not s['menu']['cursor']['count'] and bag(s) == before
                               and s['experience_level'] >= level)
    record.update(complete=True, pending=None, inputs_returned=True, visible_inventory_unchanged=True,
                  returned_times=times, closed_times=closed_times,
                  level_after=final['experience_level'], no_output_click_sent=True)
    save(); owned_menu_result(client, {}); return record
