"""Recover explicitly registered ordinary furnaces through Kit's narrow empty-menu protocol."""
import math
import time

from furnace_batches import snapshot
from kit_runtime.inventory import InventorySession, destination_capacity
from kit_runtime.storage import move_amount
from kit_runtime.journal import write_json
from material_plan import inventory_counts


def recover(client, positions, directory, checkpoint):
    directory.mkdir(parents=True, exist_ok=False)
    positions = [list(p) for p in positions]
    if (not positions or len(positions) > 32 or len({tuple(p) for p in positions}) != len(positions)
            or any(len(p) != 3 or any(type(v) is not int for v in p) for p in positions)):
        raise ValueError('Distinct explicitly registered integer furnace positions required')
    state = checkpoint()
    if state.get('empty_furnace_recovery_protocol') != 1:
        raise RuntimeError('The installed host does not support server-empty furnace retrieval')
    journal = {'schema': 1, 'world_session': client.world, 'positions': positions,
               'recovered': [], 'pending': None, 'complete': False}
    path = directory / 'recovery-ledger.json'
    save = lambda: write_json(path, journal)
    save()
    for index, pos in enumerate(positions):
        checkpoint()
        state = snapshot(client, pos)
        write_json(directory / f'{index:02d}-opened.json', state)
        session = InventorySession(client)
        # Preserve every actual slot stack before breaking. Never discard input, fuel or output.
        for slot in (0, 1, 2):
            state = client.status()
            row = state['menu']['slots'][slot]
            while row['count']:
                candidates = state['menu']['slots'][3:]
                plain = set(row) == {'slot', 'item', 'count', 'max_stack'}
                target = next((r for r in candidates if plain and r['item'] == row['item'] and r['count']
                               and set(r) == {'slot', 'item', 'count', 'max_stack'}
                               and r['count'] < destination_capacity(row, r)), None)
                if target is None:
                    target = next((r for r in candidates if not r['count']), None)
                if target is None:
                    raise RuntimeError('No inventory room for furnace contents; leave the furnace intact')
                amount = min(row['count'], destination_capacity(row, target) - target['count'])
                state = move_amount(session, state, row, target, amount)
                row = state['menu']['slots'][slot]
        # Vanilla may omit redundant slot packets when the client's click prediction
        # agrees. Reopen once for a new full SERVER inventory, not a claimed empty local view.
        state = client.status()
        evidence = state.get('empty_furnace_recovery') or {}
        if (all(not r['count'] for r in state['menu']['slots'][:3])
                and evidence.get('server_content_seen') is True
                and evidence.get('server_slots_empty') is False):
            client.checked('close_menu')
            state = snapshot(client, pos)
            write_json(directory / f'{index:02d}-fresh-server-empty-menu.json', state)
            if any(r['count'] for r in state['menu']['slots'][:3]):
                raise RuntimeError('Reopened server inventory corrected the empty prediction; no transfer replay or mining')
        deadline = time.monotonic() + 180
        while True:
            state = client.request('snapshot')
            evidence = state.get('empty_furnace_recovery') or {}
            scan = client.request('scan', min=pos, max=pos, details=True)
            identity = scan['blocks'][0]['state']
            if (identity.startswith('Block{minecraft:furnace}') and 'lit=false' in identity
                    and evidence.get('server_content_seen') is True and evidence.get('server_slots_empty') is True
                    and evidence.get('pos') == pos and evidence.get('menu_id') == state['menu']['id']
                    and all(not r['count'] for r in state['menu']['slots'][:3])):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Furnace is still burning or its empty server contents are unconfirmed; no mining sent')
            time.sleep(.5)
        tools = [r for r in state['inventory'] if r['slot'] < 9 and r['item'] in
                 ('minecraft:diamond_pickaxe', 'minecraft:netherite_pickaxe') and r.get('durability', 0) >= 32]
        if not tools:
            raise RuntimeError('A usable hotbar pickaxe is required; leave the furnace intact')
        before = inventory_counts(state)
        journal['pending'] = {'pos': pos, 'state': identity, 'menu_id': state['menu']['id'],
                              'content_serial': evidence['content_serial'], 'stock_before': dict(before)}
        save()
        # Native preparation closes this exact empty menu, selects the validated hotbar pickaxe,
        # then uses the ordinary server block-update + prediction-sequence confirmation.
        reply = client.request('mine_block', pos=pos, expected_state=identity, recover_empty_furnace=True,
                               expected_menu_id=state['menu']['id'], expected_content_serial=evidence['content_serial'],
                               tool_slot=tools[0]['slot'], seconds=12)
        write_json(directory / f'{index:02d}-native-removal.json', reply)
        if reply.get('phase') != 'done' or reply.get('server_confirmed') is not True:
            raise RuntimeError('Furnace removal outcome is unconfirmed; preserve the exact request without replay')
        state = checkpoint()
        target_count = before.get('minecraft:furnace', 0) + 1
        if inventory_counts(state).get('minecraft:furnace', 0) < target_count:
            drops = [e for e in state.get('entities', []) if e.get('type') == 'minecraft:item'
                     and (e.get('stack') or {}).get('item') == 'minecraft:furnace'
                     and math.dist(e['pos'], [p + .5 for p in pos]) < 3]
            if len(drops) != 1:
                raise RuntimeError('Exact removed furnace drop is not observed; retain the pending recovery')
            drop = drops[0]
            pickup = client.request('collect_item', expected_uuid=drop['uuid'], expected_item='minecraft:furnace',
                                    expected_count=drop['stack']['count'], seconds=30)
            write_json(directory / f'{index:02d}-native-pickup.json', pickup)
            if pickup.get('phase') != 'done':
                # This exact result is terminal: movement reached a grid pose but a drifting
                # drop remained outside pickup range. Keep that receipt; never repeat collect_item.
                if pickup.get('phase')!='waiting' or pickup.get('detail')!='Drop pickup not confirmed at the reached position':
                    raise RuntimeError('Furnace pickup remains pending; do not repeat the collection')
                from drop_pickup_settle import settle
                client.request('snapshot')
                if not settle(client,drop,before.get('minecraft:furnace',0)):
                    raise RuntimeError('Furnace pickup still lacks inventory proof after one short adjustment')
                write_json(directory / f'{index:02d}-distinct-short-pickup-adjustment.json',
                           {'old_waiting_request':pickup['id'],'old_waiting_receipt_preserved':True,
                            'no_second_collect_item':True,'actual':client.status()})
            state = checkpoint()
        after = inventory_counts(state)
        if after.get('minecraft:furnace', 0) != target_count:
            raise RuntimeError('Recovered furnace inventory delta is not exact')
        if any(after.get(item, 0) != count for item, count in before.items() if item != 'minecraft:furnace'):
            raise RuntimeError('Unrelated inventory changed during furnace recovery; preserve the journal')
        journal['recovered'].append({'pos': pos, 'state_before': identity, 'actual_furnace_count_after': target_count,
                                     'native_request_id': reply['id'], 'observed_at': state['time']})
        journal['pending'] = None
        save()
    journal['complete'] = True
    save()
    return journal
