import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from potato_harvest import BONE, POISON, POTATO, plan, recover_known_loot, run
from test_potato_farm import FarmClient, SPEC, row


class Clock:
    def __init__(self): self.now = 0
    def monotonic(self): return self.now
    def sleep(self, seconds): self.now += seconds


class HarvestClient(FarmClient):
    def __init__(self, age=7, potatoes=8):
        super().__init__(potatoes=potatoes, farmland=True)
        # MaterialClient material_session ownership is its native lease; the
        # inherited old guard-action boolean remains False in the real adapter.
        self.owned = False; self.heartbeat = SimpleNamespace(id='owned-heartbeat')
        self.extra['supervision_lease'].update(id=self.heartbeat.id, remote_finish='guard')
        self.extra['pos'][1] = 64.5
        for p in plan(SPEC)['cells']:
            crop = (p[0], p[1]+1, p[2])
            self.rows[crop] = row(crop, 'Block{minecraft:potatoes}[age='+str(age)+']', False)
        self.inv[11].update(item=BONE, count=32, max_stack=64)
        self.pickup_delay = 1; self.pending_pickup = None; self.yield_count = 3
        self.no_break = False; self.no_grow = False; self.growth = 4
        self.mine_phase = 'done'; self.poison = False; self.change_on_mine = None
        self.partial_pickup = None

    def status(self):
        state = super().status(); state['entities'] = copy.deepcopy(self.entities)
        return state

    def request(self, op, **params):
        if op == 'scan' and self.pending_pickup is not None:
            self.pending_pickup -= 1
            if self.pending_pickup <= 0 and self.pickup_delay is not None:
                source = next(r for r in self.inv if r['slot'] < 36 and r['item'] == POTATO)
                amount = self.yield_count if self.partial_pickup is None else self.partial_pickup
                source['count'] += amount
                if amount == self.yield_count:
                    self.entities = [e for e in self.entities if e['stack']['item'] != POTATO]
                else:
                    for entity in self.entities:
                        if entity['stack']['item'] == POTATO:
                            entity['stack']['count'] -= amount
                self.pending_pickup = None
        if op == 'scan':
            state = super().request(op, **params)
            # Match the actual bridge: scoped scan identities omit item stacks.
            for entity in state['scan_entities']: entity.pop('stack', None)
            return state
        if op == 'mine_block':
            self.calls.append((op, copy.deepcopy(params)))
            pos = tuple(params['pos']); assert self.rows[pos]['state'] == params['expected_state']
            assert params['expected_state'] == 'Block{minecraft:potatoes}[age=7]'
            if self.mine_phase == 'done' and not self.no_break:
                self.rows.pop(pos)
                self.rev += 1; self.extra['control_revision'] = self.rev
                self.extra['supervision_lease']['revision'] = self.rev
                self.pending_pickup = self.pickup_delay if self.pickup_delay is not None else 1000
                self.entities.append({'uuid': 'drop-'+str(len(self.calls)), 'id': len(self.calls),
                                      'type': 'minecraft:item', 'pos': [pos[0]+.5, pos[1]+.2, pos[2]+.5],
                                      'stack': {'item': POTATO, 'count': self.yield_count}})
                if self.poison:
                    self.entities.append({'uuid': 'poison-'+str(len(self.calls)), 'id': len(self.calls)+1000,
                                          'type': 'minecraft:item', 'pos': [pos[0]+.5, pos[1]+.2, pos[2]+.5],
                                          'stack': {'item': POISON, 'count': 1}})
            if self.change_on_mine: self.change_on_mine(self)
            return {**self.status(), 'phase': self.mine_phase, 'id': 'native-mine-'+str(len(self.calls))}
        if op == 'interact' and params.get('expected_hand') == BONE:
            self.calls.append((op, copy.deepcopy(params)))
            pos = tuple(params['pos']); assert params['expected_state'] == self.rows[pos]['state']
            hand = self.inv[self.selected]; assert hand['item'] == BONE
            if not self.no_grow:
                age = int(self.rows[pos]['state'].split('age=')[1][0])
                self.rows[pos]['state'] = 'Block{minecraft:potatoes}[age='+str(min(7, age+self.growth))+']'
                hand['count'] -= 1
            return {**self.status(), 'phase': 'done', 'id': 'native-bone-'+str(len(self.calls))}
        return super().request(op, **params)


class HarvestTests(unittest.TestCase):
    def execute(self, client, request=None, out=None, **options):
        clock = Clock()
        if out is None:
            with tempfile.TemporaryDirectory() as directory:
                result = run(client, request or SPEC, directory,
                             sleep=clock.sleep, monotonic=clock.monotonic, **options)
                journal = json.loads(Path(result['journal']).read_text())
                return result, journal
        return run(client, request or SPEC, out, sleep=clock.sleep, monotonic=clock.monotonic, **options)

    def actions(self, client):
        return [(op, params) for op, params in client.calls if op in ('mine_block', 'interact')]

    def test_four_mature_axial_cells_harvest_and_replant_without_bone_meal_or_movement(self):
        client = HarvestClient()
        self.assertFalse(client.owned)
        result, book = self.execute(client, bonemeal_budget=0)
        self.assertEqual('done', result['phase'], result)
        self.assertEqual(4, result['harvested_replanted'])
        self.assertEqual(8, result['potato_gain'])
        self.assertEqual(0, result['bone_meal_used'])
        self.assertEqual(16, book['potatoes_after'])
        self.assertFalse(result['server_verified'])
        self.assertEqual(8, len(self.actions(client)))
        self.assertTrue(all(op in ('scan', 'select_item', 'mine_block', 'interact') for op, _ in client.calls))
        for record in book['cells'].values():
            self.assertEqual(3, record['potato_gain'])
            self.assertEqual(2, len(record['harvest']['observed_times']))
            self.assertEqual(2, len(record['plant']['observed_times']))
            self.assertEqual('empty_pre_scan_single_crop_break_and_actual_stock', record['harvest']['loot_proof'])
        self.assertEqual(24, sum('minecraft:potatoes' in r['state'] for r in client.rows.values()))

    def test_delayed_owned_scoped_drop_pickup_uses_actual_gain(self):
        client = HarvestClient(); client.pickup_delay = 3; client.yield_count = 2
        result, book = self.execute(client, max_cells=1)
        self.assertEqual('HARVEST_BATCH', result['code'], result)
        self.assertEqual(1, result['potato_gain'])
        record = next(iter(book['cells'].values()))
        self.assertEqual('new_scoped_item_ids_and_actual_stock', record['harvest']['loot_proof'])
        self.assertEqual(1, len(record['harvest']['owned_loot']))

    def test_no_loot_stops_after_exactly_one_break_and_cannot_replay(self):
        client = HarvestClient(); client.pickup_delay = None
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(client, out=directory)
            self.assertEqual('WAIT_LOOT', result['code'], result)
            self.assertEqual(1, len(self.actions(client)))
            pending = json.loads(Path(result['journal']).read_text())['pending']
            self.assertEqual('await_loot', pending['operation'])
            self.assertEqual([], pending['pre_drop_ids'])
            self.assertTrue(pending['owned_loot'])
            count = len(self.actions(client))
            again = self.execute(client, out=directory)
            self.assertEqual('WAIT_LOOT', again['code'])
            self.assertEqual(count, len(self.actions(client)))

    def test_fake_done_break_without_world_or_inventory_change_is_wait_loot(self):
        client = HarvestClient(); client.no_break = True
        result, _ = self.execute(client)
        self.assertEqual('WAIT_LOOT', result['code'])
        self.assertEqual(1, len(self.actions(client)))

    def test_unknown_mine_receipt_stays_pending_and_does_not_replant(self):
        client = HarvestClient(); client.mine_phase = 'waiting'
        result, book = self.execute(client)
        self.assertEqual('WAIT_RECONCILE', result['code'])
        self.assertEqual('harvest', book['pending']['operation'])
        self.assertEqual(1, len(self.actions(client)))

    def test_immature_crop_never_breaks_without_bone_authorization(self):
        client = HarvestClient(age=6)
        result, book = self.execute(client)
        self.assertEqual('WAIT_GROWTH', result['code'])
        self.assertEqual([], self.actions(client))
        self.assertIsNone(book['pending'])

    def test_optional_bone_meal_requires_actual_consumption_and_fresh_growth(self):
        client = HarvestClient(age=0)
        result, book = self.execute(client, {**SPEC, 'bonemeal': True}, max_cells=1)
        self.assertEqual('HARVEST_BATCH', result['code'], result)
        self.assertEqual(2, result['bone_meal_used'])
        record = next(iter(book['cells'].values()))
        self.assertEqual(2, len(record['growth']))
        self.assertTrue(all(len(step['observed_times']) == 2 for step in record['growth']))
        self.assertEqual(30, next(r['count'] for r in client.inv if r['item'] == BONE))

    def test_bone_receipt_alone_cannot_trigger_harvest_or_repeat(self):
        client = HarvestClient(age=0); client.no_grow = True
        result, book = self.execute(client, {**SPEC, 'bonemeal': True})
        self.assertEqual('WAIT_RECONCILE', result['code'])
        self.assertEqual('bonemeal', book['pending']['operation'])
        self.assertEqual(1, len(self.actions(client)))

    def test_per_cell_bone_limit_stops_without_mining(self):
        client = HarvestClient(age=0); client.growth = 1
        result, book = self.execute(client, {**SPEC, 'bonemeal': True})
        self.assertEqual('WAIT_GROWTH', result['code'])
        self.assertEqual(4, result['bone_meal_used'])
        self.assertEqual(4, len(self.actions(client)))
        self.assertIsNone(book['pending'])

    def test_unknown_entity_and_preexisting_loot_are_protected(self):
        for item in (POTATO, 'minecraft:diamond'):
            client = HarvestClient(); client.entities = [{'id': 999, 'uuid': 'old', 'type': 'minecraft:item',
                'pos': [1.5, 64, .5], 'stack': {'item': item, 'count': 1}}]
            result, _ = self.execute(client)
            self.assertEqual('WAIT_ENTITY', result['code'])
            self.assertEqual([], self.actions(client))

    def test_poison_drop_is_owned_and_can_remain_while_four_cells_are_replanted(self):
        client = HarvestClient(); client.poison = True
        result, book = self.execute(client)
        self.assertEqual('done', result['phase'], result)
        self.assertEqual(4, len(client.entities))
        self.assertTrue(all(e['stack']['item'] == POISON for e in client.entities))
        self.assertEqual(4, book['cells'].__len__())

    def test_actual_reserve_and_full_field_integrity_required_before_mining(self):
        client = HarvestClient(potatoes=4)
        result, _ = self.execute(client)
        self.assertEqual('WAIT_RESERVE', result['code']); self.assertEqual([], self.actions(client))
        client = HarvestClient(); client.rows.pop((-2, 64, -2))
        result, _ = self.execute(client)
        self.assertEqual('WAIT_RECONCILE', result['code']); self.assertEqual([], self.actions(client))

    def test_incomplete_inventory_or_full_potato_capacity_stops_before_break(self):
        client = HarvestClient(); client.inv.pop()
        result, _ = self.execute(client)
        self.assertEqual('WAIT_INVENTORY', result['code']); self.assertEqual([], self.actions(client))
        client = HarvestClient()
        for slot in client.inv[:36]: slot.update(item=POTATO, count=64, max_stack=64)
        result, _ = self.execute(client)
        self.assertEqual('WAIT_INVENTORY', result['code']); self.assertEqual([], self.actions(client))

    def test_manual_takeover_injury_and_changed_lease_stop_before_replant(self):
        for change, expected in ((lambda c:c.extra.update(manual_movement=True), 'WAIT_SAFETY'),
                                 (lambda c:c.extra.update(recent_hurt_at=1), 'WAIT_SAFETY'),
                                 (lambda c:c.extra['supervision_lease'].update(id='foreign'), 'WAIT_CONTROL')):
            client = HarvestClient(); client.change_on_mine = change
            result, book = self.execute(client)
            self.assertEqual(expected, result['code'])
            self.assertEqual('harvest', book['pending']['operation'])
            self.assertEqual(1, len(self.actions(client)))

    def test_complete_journal_does_not_start_another_cycle(self):
        client = HarvestClient()
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(client, out=directory)
            self.assertEqual('done', result['phase'])
            actions = len(self.actions(client)); count = len(client.calls)
            # A crop may have naturally grown since the original age-zero proof.
            client.rows[(1,64,0)]['state'] = 'Block{minecraft:potatoes}[age=3]'
            reused = self.execute(client, out=directory)
            self.assertEqual('done', reused['phase'])
            self.assertTrue(reused['prior_receipt_reuse'])
            self.assertTrue(reused['current_context_verified'])
            self.assertEqual(actions, len(self.actions(client)))
            self.assertGreater(len(client.calls), count)
            self.assertTrue(all(op == 'scan' for op, _ in client.calls[count:]))

    def test_completed_receipt_cannot_claim_current_success_after_disconnect_or_hold(self):
        for change, expected in ((lambda c:c.extra.update(connected=False), 'WAIT_CONTROL'),
                                 (lambda c:c.extra.update(safety_hold={'active': True}), 'WAIT_SAFETY'),
                                 (lambda c:c.extra.update(health=19), 'WAIT_SAFETY'),
                                 (lambda c:c.extra['supervision_lease'].update(id='foreign'), 'WAIT_CONTROL')):
            client = HarvestClient()
            with tempfile.TemporaryDirectory() as directory:
                self.assertEqual('done', self.execute(client, out=directory)['phase'])
                count = len(client.calls); change(client)
                rejected = self.execute(client, out=directory)
                self.assertEqual(expected, rejected['code'])
                self.assertEqual('waiting', rejected['phase'])
                self.assertEqual(count, len(client.calls))
                self.assertNotIn('current_context_verified', rejected)

    def test_completed_receipt_reaudits_actual_field_before_reuse(self):
        client = HarvestClient()
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual('done', self.execute(client, out=directory)['phase'])
            actions = len(self.actions(client)); client.rows.pop((1,64,0))
            rejected = self.execute(client, out=directory)
            self.assertEqual('WAIT_RECONCILE', rejected['code'])
            self.assertEqual(actions, len(self.actions(client)))

    def test_request_and_runtime_budgets_are_bounded(self):
        for request in ({}, {**SPEC, 'cells': [[0,63,0]]}, {**SPEC, 'cells': [[1,63,0]]*2},
                        {**SPEC, 'radius': 3}, {**SPEC, 'cells': [[3,63,0]]}):
            with self.assertRaises(ValueError): plan(request)
        for options in ({'max_cells': 5}, {'bonemeal_budget': 17}, {'max_bonemeal_per_cell': 5},
                        {'pickup_seconds': 7}, {'max_cells': True}):
            with self.assertRaises(ValueError): self.execute(HarvestClient(), **options)

    def pickup_exact(self, client, drop, observation):
        actual = next(e for e in client.entities if e['uuid'] == drop['uuid'])
        self.assertEqual(drop['remaining_count'], actual['stack']['count'])
        self.assertEqual(POTATO, actual['stack']['item'])
        source = next(r for r in client.inv if r['slot'] < 36 and r['item'] == POTATO)
        source['count'] += actual['stack']['count']
        client.entities.remove(actual)
        return True

    def test_partial_pickup_never_replants_or_breaks_next_cell(self):
        client = HarvestClient(); client.partial_pickup = 2
        result, book = self.execute(client)
        self.assertEqual('WAIT_LOOT', result['code'], result)
        self.assertTrue(result['recoverable_known_loot'])
        self.assertEqual(1, result['remaining_count'])
        self.assertEqual(1, len(result['known_loot']))
        self.assertEqual(1, result['known_loot'][0]['remaining_count'])
        self.assertEqual(2, book['pending']['actual_gain'])
        self.assertEqual(3, book['pending']['observed_potato_total'])
        self.assertEqual('await_loot', book['pending']['operation'])
        self.assertEqual(1, len(self.actions(client)))
        self.assertEqual(0, result['harvested_replanted'])
        self.assertEqual(23, sum('minecraft:potatoes' in r['state'] for r in client.rows.values()))

    def test_injected_exact_uuid_pickup_proves_all_loot_before_replant(self):
        client = HarvestClient(); client.partial_pickup = 2; offered = []
        def pickup(c, drop, observation):
            offered.append(drop['uuid']); return self.pickup_exact(c, drop, observation)
        result, book = self.execute(client, {**SPEC, 'cells': [[1,63,0]]}, pickup=pickup)
        self.assertEqual('done', result['phase'], result)
        self.assertEqual(1, len(offered)); self.assertEqual(2, result['potato_gain'])
        record = next(iter(book['cells'].values()))
        self.assertEqual(3, record['potato_gain']); self.assertEqual(0, record['harvest']['remaining_count'])
        self.assertEqual(2, len(record['harvest']['observed_times']))
        self.assertEqual(2, len(self.actions(client)))

    def test_known_loot_read_only_recovery_then_resume_never_remines(self):
        client = HarvestClient(); client.partial_pickup = 2
        request = {**SPEC, 'cells': [[1,63,0]]}; clock = Clock()
        with tempfile.TemporaryDirectory() as directory:
            first = self.execute(client, request, out=directory)
            self.assertEqual('WAIT_LOOT', first['code'])
            start = len(client.calls)
            waiting = recover_known_loot(client, request, directory, sleep=clock.sleep, monotonic=clock.monotonic)
            self.assertEqual('WAIT_LOOT', waiting['code'])
            self.assertEqual(1, waiting['remaining_count'])
            self.assertTrue(all(op == 'scan' for op, _ in client.calls[start:]))
            fresh = client.status(); drop = waiting['known_loot'][0]
            self.pickup_exact(client, drop, fresh)
            start = len(client.calls)
            ready = recover_known_loot(client, request, directory, sleep=clock.sleep, monotonic=clock.monotonic)
            self.assertEqual('REPLANT_READY', ready['code'], ready)
            self.assertTrue(all(op == 'scan' for op, _ in client.calls[start:]))
            final = self.execute(client, request, out=directory)
            self.assertEqual('done', final['phase'], final)
            self.assertEqual(1, sum(op == 'mine_block' for op, _ in self.actions(client)))
            self.assertEqual(1, sum(op == 'interact' for op, _ in self.actions(client)))

    def test_pickup_callback_receipt_or_drop_disappearance_cannot_replace_gain(self):
        client = HarvestClient(); client.partial_pickup = 2
        def fake_pickup(c, drop, observation):
            c.entities = [e for e in c.entities if e['uuid'] != drop['uuid']]
            return True
        result, book = self.execute(client, pickup=fake_pickup)
        self.assertEqual('WAIT_LOOT', result['code'])
        self.assertEqual(1, len(self.actions(client)))
        self.assertEqual(3, book['pending']['observed_potato_total'])
        self.assertEqual(2, book['pending']['actual_gain'])

    def test_unknown_pickup_is_journaled_once_and_read_recovery_never_replays_it(self):
        client = HarvestClient(); client.partial_pickup = 2; called = []
        def unknown(c, drop, observation):
            called.append(drop['uuid']); raise RuntimeError('unknown normal pickup result')
        request = {**SPEC, 'cells': [[1,63,0]]}
        with tempfile.TemporaryDirectory() as directory:
            first = self.execute(client, request, out=directory, pickup=unknown)
            self.assertEqual('WAIT_CONTROL', first['code'])
            second = self.execute(client, request, out=directory, pickup=unknown)
            self.assertEqual('WAIT_LOOT', second['code'])
            self.assertEqual(1, len(called))
            self.assertEqual(1, len(self.actions(client)))

    def test_known_loot_recovery_cannot_adopt_new_world_or_unknown_mine(self):
        client = HarvestClient(); client.partial_pickup = 2
        with tempfile.TemporaryDirectory() as directory:
            self.execute(client, out=directory); client.world = 'new-world'
            recovered = recover_known_loot(client, SPEC, directory)
            self.assertEqual('WAIT_CONTROL', recovered['code'])
        client = HarvestClient(); client.mine_phase = 'waiting'
        with tempfile.TemporaryDirectory() as directory:
            self.execute(client, out=directory)
            recovered = recover_known_loot(client, SPEC, directory)
            self.assertEqual('WAIT_RECONCILE', recovered['code'])


if __name__ == '__main__': unittest.main()
