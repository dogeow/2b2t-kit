import copy
import json
from pathlib import Path
import tempfile
import unittest

from animal_breed import FOODS, plan, run
from test_potato_harvest import Clock, HarvestClient

SPEC = {'authorized': True, 'species': 'minecraft:cow', 'adults': ['adult-a', 'adult-b'], 'center': [0,64,0]}


def animal(uuid, ident, species='minecraft:cow', baby=False, pos=None):
    return {'uuid': uuid, 'id': ident, 'type': species, 'pos': pos or [.5,64,.5],
            'alive': True, 'visible': True, 'is_baby': baby}


class BreedClient(HarvestClient):
    def __init__(self, species='minecraft:cow', food=2):
        super().__init__(); self.rows = {}; self.extra['pos'] = [.5,64,.5]
        self.species = species; self.feeding = 0; self.no_consume = False
        self.no_birth = False; self.transient_baby = False; self.birth_scans = 0
        self.phase = 'done'; self.consume = 1; self.after_feed = None; self.refresh_ids = False
        self.entities = [animal('adult-a', 10, species, pos=[-.3,64,.5]),
                         animal('adult-b', 11, species, pos=[1.3,64,.5])]
        self.inv[12].update(item=FOODS[species], count=food, max_stack=64)

    def request(self, op, **params):
        if op == 'scan' and self.feeding == 2:
            self.birth_scans += 1
            if self.transient_baby:
                self.entities = [e for e in self.entities if e['uuid'] != 'new-baby']
                if self.birth_scans == 3: self.entities.append(animal('new-baby', 99, self.species, True))
        if op == 'interact_entity':
            self.calls.append((op, copy.deepcopy(params))); self.feeding += 1
            actual = next(e for e in self.entities if e['uuid'] == params['expected_uuid'])
            assert params['entity_id'] == actual['id']
            if self.phase == 'done' and not self.no_consume:
                hand = self.inv[self.selected]; assert hand['item'] == FOODS[self.species]
                hand['count'] -= self.consume
                if hand['count'] == 0: hand['item'] = 'minecraft:air'
            if self.feeding == 2 and not self.no_birth and not self.transient_baby:
                self.entities.append(animal('new-baby', 99, self.species, True))
            if self.after_feed: self.after_feed(self)
            return {**self.status(), 'id': 'native-feed-'+str(self.feeding), 'phase': self.phase,
                    'detail': 'entity interaction sent; verify resulting world state'}
        result = super().request(op, **params)
        if op == 'select_item' and self.refresh_ids:
            for entity in self.entities: entity['id'] += 100
        return result

    def feeds(self): return [p for op, p in self.calls if op == 'interact_entity']


class AnimalBreedTests(unittest.TestCase):
    def execute(self, client, request=None, directory=None, **options):
        clock = Clock(); spec = request or {**SPEC, 'species': client.species}
        if directory is not None:
            return run(client, spec, directory, sleep=clock.sleep, monotonic=clock.monotonic, **options)
        with tempfile.TemporaryDirectory() as out:
            result = run(client, spec, out, sleep=clock.sleep, monotonic=clock.monotonic, **options)
            return result, json.loads(Path(result['journal']).read_text())

    def test_cow_and_chicken_two_actual_food_uses_then_two_fresh_baby_frames(self):
        for species in FOODS:
            client = BreedClient(species)
            result, book = self.execute(client)
            self.assertEqual('done', result['phase'], result)
            self.assertEqual(2, result['fed_adults']); self.assertEqual(1, result['observed_births'])
            self.assertEqual('new-baby', result['baby_uuid']); self.assertFalse(result['server_verified'])
            self.assertEqual(2, len(client.feeds()))
            self.assertTrue(all(len(r['observed_times']) == 2 for r in book['feeds'].values()))
            self.assertEqual(2, len(book['baby']['observed_times']))
            self.assertNotIn('in_love', book['baby'])
            self.assertTrue(all(op in ('scan', 'select_item', 'interact_entity') for op, _ in client.calls))

    def test_existing_baby_never_counts_as_a_new_birth(self):
        client = BreedClient(); client.no_birth = True
        client.entities.append(animal('old-baby', 98, baby=True))
        result, book = self.execute(client)
        self.assertEqual('WAIT_BABY', result['code']); self.assertEqual(0, result['observed_births'])
        self.assertIn('old-baby', book['pre_birth_uuids']); self.assertEqual(2, len(client.feeds()))

    def test_sheep_uses_wheat_and_requires_a_same_species_new_baby(self):
        client = BreedClient('minecraft:sheep')
        result, book = self.execute(client)
        self.assertEqual('done', result['phase'], result)
        self.assertEqual('minecraft:sheep', book['baby']['type'])
        self.assertEqual('minecraft:wheat', book['scope']['layout']['food'])
        self.assertEqual(2, len(client.feeds()))

    def test_transient_new_baby_cannot_pass_two_distinct_frames(self):
        client = BreedClient(); client.transient_baby = True
        result, _ = self.execute(client)
        self.assertEqual('WAIT_BABY', result['code']); self.assertEqual(0, result['observed_births'])

    def test_receipt_pass_or_wrong_consumption_is_not_feeding_success_and_never_replays(self):
        for no_consume, consume in ((True,1), (False,2), (False,-1)):
            client = BreedClient(); client.no_consume = no_consume; client.consume = consume
            with tempfile.TemporaryDirectory() as out:
                first = self.execute(client, directory=out)
                self.assertEqual('WAIT_RECONCILE', first['code'])
                self.assertEqual(0, first['fed_adults']); self.assertEqual(1, len(client.feeds()))
                book = json.loads(Path(first['journal']).read_text())
                self.assertEqual('feed', book['pending']['operation'])
                calls = len(client.calls)
                self.assertEqual('WAIT_RECONCILE', self.execute(client, directory=out)['code'])
                self.assertEqual(calls, len(client.calls))

    def test_unknown_native_interaction_remains_durable_with_no_second_feed(self):
        client = BreedClient(); client.phase = 'waiting'
        result, book = self.execute(client)
        self.assertEqual('WAIT_RECONCILE', result['code'])
        self.assertEqual('feed', book['pending']['operation']); self.assertEqual(1, len(client.feeds()))

    def test_birth_wait_resume_only_reads_never_repeats_two_proven_food_uses(self):
        client = BreedClient(); client.no_birth = True
        with tempfile.TemporaryDirectory() as out:
            first = self.execute(client, directory=out)
            self.assertEqual('WAIT_BABY', first['code']); self.assertEqual(2, len(client.feeds()))
            start = len(client.calls)
            client.entities.append(animal('late-baby', 99, baby=True))
            second = self.execute(client, directory=out)
            self.assertEqual('done', second['phase'], second)
            self.assertEqual('late-baby', second['baby_uuid'])
            self.assertTrue(all(op == 'scan' for op, _ in client.calls[start:]))

    def test_two_food_items_complete43_slots_and_live_adult_pair_required_before_feed(self):
        for change, expected in ((lambda c:c.inv[12].update(count=1), 'WAIT_FOOD'),
                                 (lambda c:c.inv.pop(), 'WAIT_INVENTORY'),
                                 (lambda c:c.entities[0].update(is_baby=True), 'WAIT_PAIR'),
                                 (lambda c:c.entities.pop(), 'WAIT_PAIR'),
                                 (lambda c:c.entities[0].pop('is_baby'), 'WAIT_SCAN'),
                                 (lambda c:c.extra.update(health=21), 'WAIT_SAFETY'),
                                 (lambda c:c.extra.update(native_material_busy=True), 'WAIT_SAFETY')):
            client = BreedClient(); change(client)
            result, _ = self.execute(client)
            self.assertEqual(expected, result['code'], result); self.assertEqual([], client.feeds())

    def test_fresh_los_and_normal_reach_are_required_without_movement(self):
        for change in (lambda c:c.entities[0].update(visible=False),
                       lambda c:c.extra.update(pos=[3.8,64,.5])):
            client = BreedClient(); change(client)
            result, _ = self.execute(client)
            self.assertEqual('WAIT_REACH', result['code']); self.assertEqual([], client.feeds())

    def test_fresh_scan_id_for_uuid_is_used_after_inventory_selection(self):
        client = BreedClient(); client.refresh_ids = True
        result, _ = self.execute(client)
        self.assertEqual('done', result['phase'], result)
        self.assertEqual([110,111], [p['entity_id'] for p in client.feeds()])

    def test_manual_input_world_injury_and_foreign_lease_stop_before_second_feed(self):
        for change, expected in ((lambda c:c.extra.update(manual_movement=True), 'WAIT_SAFETY'),
                                 (lambda c:c.extra.update(world_session='foreign'), 'WAIT_CONTROL'),
                                 (lambda c:c.extra.update(recent_hurt_at=1), 'WAIT_SAFETY'),
                                 (lambda c:c.extra['supervision_lease'].update(id='foreign'), 'WAIT_CONTROL')):
            client = BreedClient(); client.after_feed = change
            result, book = self.execute(client)
            self.assertEqual(expected, result['code']); self.assertEqual(1, len(client.feeds()))
            self.assertEqual('feed', book['pending']['operation'])

    def test_completed_receipt_reuse_checks_context_and_never_feeds_again(self):
        client = BreedClient()
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual('done', self.execute(client, directory=out)['phase'])
            reused = self.execute(client, directory=out)
            self.assertEqual('done', reused['phase']); self.assertTrue(reused['prior_receipt_reuse'])
            self.assertEqual(2, len(client.feeds()))
            client.extra['safety_hold'] = {'active': True}
            self.assertEqual('WAIT_SAFETY', self.execute(client, directory=out)['code'])
            self.assertEqual(2, len(client.feeds()))

    def test_authorization_pair_species_region_and_wait_are_bounded(self):
        for request in ({}, {**SPEC, 'authorized': False}, {**SPEC, 'species': 'minecraft:pig'},
                        {**SPEC, 'adults': ['adult-a']*2}, {**SPEC, 'radius': 5},
                        {**SPEC, 'center': [0, True, 0]}):
            with self.assertRaises(ValueError): plan(request)
        with self.assertRaises(ValueError): self.execute(BreedClient(), birth_wait_seconds=13)


if __name__ == '__main__': unittest.main()
