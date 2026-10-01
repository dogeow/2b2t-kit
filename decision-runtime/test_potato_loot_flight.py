import copy
import unittest

from potato_farm import FarmWait, POTATO
from potato_loot_flight import make_pickup
from test_potato_harvest import HarvestClient


class FlightClient(HarvestClient):
    def __init__(self):
        super().__init__(); self.extra['pos'] = [.5, 64.6, .5]; self.blocked = False
        self.entities = [{'uuid': 'owned-drop', 'id': 80, 'type': 'minecraft:item',
                          'pos': [2.1, 63.9375, .5], 'stack': {'item': POTATO, 'count': 1}}]

    def request(self, op, **params):
        if op == 'snapshot':
            self.calls.append((op, params)); return self.status()
        return super().request(op, **params)

    def checked(self, op, **params):
        self.calls.append((op, copy.deepcopy(params)))
        assert op == 'navigate' and params['air_only'] is True
        if self.blocked: raise RuntimeError('Native air-only path is blocked')
        self.extra['pos'] = params['target'][:]
        self.rev += 1; self.extra['control_revision'] = self.rev
        self.extra['supervision_lease']['revision'] = self.rev
        return {**self.status(), 'id': 'native-move-'+str(len(self.calls)), 'phase': 'done'}


class PotatoLootFlightTest(unittest.TestCase):
    def prepare(self):
        client = FlightClient(); observation = client.status()
        drop = {**copy.deepcopy(client.entities[0]), 'remaining_count': 1}
        return client, observation, drop

    def moves(self, client): return [p for op, p in client.calls if op == 'navigate']

    def test_fresh_exact_owned_drop_uses_current_position_and_returns_at_fixed_hover_height(self):
        client, observation, drop = self.prepare()
        client.entities[0]['pos'][0] += .2
        client.entities[0]['stack']['max_stack'] = 64  # Actual native stack has extra metadata.
        result = make_pickup([0,63,0])(client, drop, observation)
        moves = self.moves(client); self.assertEqual(2, len(moves))
        self.assertAlmostEqual(2.3, moves[0]['target'][0])
        self.assertEqual([64.6,.5], moves[0]['target'][1:])
        self.assertEqual([.5,64.6,.5], moves[1]['target'])
        self.assertTrue(all(p['air_only'] is True and p['seconds'] == 10 for p in moves))
        self.assertTrue(result['movement_only']); self.assertNotIn('pickup_verified', result)
        self.assertEqual(8, sum(r['count'] for r in client.inv[:36] if r['item'] == POTATO))

    def test_stale_wrong_stack_injury_foreign_lease_or_outside_buffer_never_moves(self):
        changes = [lambda c,o,d:o.update(time=o['time']-3000),
                   lambda c,o,d:c.entities[0]['stack'].update(count=2),
                   lambda c,o,d:c.extra.update(recent_hurt_at=1),
                   lambda c,o,d:c.extra['supervision_lease'].update(id='foreign'),
                   lambda c,o,d:c.extra.update(health=19),
                   lambda c,o,d:d.update(pos=[8,64,.5])]
        for change in changes:
            client, observation, drop = self.prepare(); change(client, observation, drop)
            with self.assertRaises(FarmWait): make_pickup([0,63,0])(client, drop, observation)
            self.assertEqual([], self.moves(client))

    def test_unknown_native_path_result_claims_uuid_and_never_replays_movement(self):
        client, observation, drop = self.prepare(); client.blocked = True
        pickup = make_pickup([0,63,0])
        with self.assertRaises(RuntimeError): pickup(client, drop, observation)
        self.assertEqual(1, len(self.moves(client)))
        client.blocked = False
        with self.assertRaises(FarmWait): pickup(client, drop, client.status())
        self.assertEqual(1, len(self.moves(client)))


if __name__ == '__main__': unittest.main()
