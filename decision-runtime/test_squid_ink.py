import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from material_jobs.squid_ink import collect,observed_live
from material_jobs.protocol import JobBlocked


class DiveClient:
    world = 'w'
    native_inflight = None
    last = None

    def __init__(self, unknown=False, partial=False):
        self.calls = []; self.unknown = unknown; self.partial = partial
        self.squid = {'uuid': 's', 'id': 7, 'type': 'minecraft:squid',
                      'has_custom_name': False, 'health': 10, 'pos': [.5, 55, .5]}
        self.q = {'world_session': 'w', 'health': 20, 'guard_busy': False,
                  'material_ink_attack_protocol': 2, 'pos': [.5, 64.2, .5],
                  'air_supply': 300, 'air_pickup_floor': 260, 'under_water': False,
                  'attack_strength': 1, 'entities': [self.squid], 'inventory': []}

    def request(self, op, **args):
        self.calls.append((op, args)); self.last = 'request-'+str(len(self.calls))
        if op == 'scan':
            n = math.prod(b-a+1 for a, b in zip(args['min'], args['max']))
            return {'phase': 'done', 'world_session': 'w', 'blocks': [],
                    'scan_cells_read': n-1 if self.partial else n, 'scan_total_cells': n}
        if op == 'navigate':
            self.q['pos'] = args['target']; self.q['under_water'] = args['target'][1]+1.62 < 63
            self.q['air_supply'] = self.q['air_supply']-5 if self.q['under_water'] else 300
        if op == 'walk':
            old = self.q['pos']; self.q['pos'] = list(args['target'])
            if args.get('water_descend'):
                assert .5 <= old[1]-args['target'][1] <= 5
            elif old[1] > 63 and args['target'][1] == 60:
                self.q['pos'][1] = 61.1  # Native ordinary-walk vertical tolerance.
            self.q['under_water'] = True; self.q['air_supply'] -= 10
        if op == 'material_ink_attack':
            assert self.q['under_water'] and self.q['air_supply'] >= 260
            if self.unknown:
                self.native_inflight = {'op': op, 'request_id': self.last}
                return {'phase': 'waiting', 'ink_attack': {'action_sent': True}}
            self.squid['health'] -= 8
            if self.squid['health'] <= 0:
                self.q['entities'] = []
                self.q['inventory'] = [{'slot': 14, 'item': 'minecraft:ink_sac', 'count': 4}]
            return {'phase': 'done', 'ink_attack': {'action_sent': True, 'in_water': True}}
        return {'phase': 'done'}

    def checked(self, op, **args):
        r = self.request(op, **args)
        if r.get('phase') != 'done':
            raise RuntimeError(r['phase'])
        return r


class SquidInkTests(unittest.TestCase):
    def test_deep_glow_target_remains_observed_outside_the_nearby_snapshot_radius(self):
        c=DiveClient();c.root=Path('/unused');q={**c.q,'entities':[]}
        e={**c.squid,'type':'minecraft:glow_squid','pos':[.5,27.,.5]}
        with patch('material_jobs.loaded_squid_survey.read_glow',return_value=[e])as live:
            self.assertEqual(e,observed_live(c,e['uuid'],e['type'],q));live.assert_called_once_with(c.root,q)
        with patch('material_jobs.loaded_squid_survey.read_glow',return_value=[]):self.assertIsNone(observed_live(c,e['uuid'],e['type'],q))
    def test_retained_unknown_attack_fence_also_blocks_surface_mutations(self):
        c=DiveClient(unknown=True);original=c.request
        def request(op,**kw):
            r=original(op,**kw)
            if op=='material_ink_attack':c.native_inflight=None;c.unconfirmed_native_request={'request_id':c.last}
            return r
        c.request=request
        with TemporaryDirectory()as d,patch('material_jobs.squid_ink.settled_state',side_effect=lambda *a,**k:c.q):
            with self.assertRaises(JobBlocked):collect(c,dict(c.squid),d,lambda:c.q)
        self.assertEqual('material_ink_attack',c.calls[-1][0])
    def test_glow_squid_requires_actual_glow_protocol_and_credits_matching_ink(self):
        c=DiveClient();c.squid['type']='minecraft:glow_squid';c.q['material_ink_attack_protocol']=3
        original=c.request
        def request(op,**kw):
            r=original(op,**kw)
            for row in c.q['inventory']:
                if row['item']=='minecraft:ink_sac':row['item']='minecraft:glow_ink_sac'
            return r
        c.request=request
        with TemporaryDirectory()as d,patch('material_jobs.squid_ink.settled_state',side_effect=lambda *a,**k:c.q):
            proof=collect(c,dict(c.squid),d,lambda:c.q)
        self.assertEqual('minecraft:glow_ink_sac',proof['ink_item']);self.assertEqual(4,proof['actual_ink_gain'])
        self.assertTrue(proof['surface_confirmed'])
        self.assertTrue(all('slot'not in p for op,p in c.calls if op=='select_item'))

    def test_old_host_never_dispatches_glow_squid_attack(self):
        c=DiveClient();c.squid['type']='minecraft:glow_squid'
        with TemporaryDirectory()as d,patch('material_jobs.squid_ink.settled_state',side_effect=lambda *a,**k:c.q):
            with self.assertRaises(JobBlocked):collect(c,dict(c.squid),d,lambda:c.q)
        self.assertFalse(any(op=='material_ink_attack'for op,_ in c.calls))

    def test_real_inventory_gain_after_two_underwater_hits_and_surface(self):
        c = DiveClient()
        with TemporaryDirectory() as d, patch('material_jobs.squid_ink.settled_state', side_effect=lambda *a, **k: c.q):
            proof = collect(c, dict(c.squid), d, lambda: c.q)
        self.assertEqual(4, proof['actual_ink_gain'])
        self.assertEqual(2, len(proof['attacks']))
        self.assertTrue(proof['surface_confirmed'])
        self.assertGreaterEqual(len(proof['air_return_sets']), 1)
        entry = next(i for i, (op, _) in enumerate(c.calls) if op == 'walk')
        first_attack = next(i for i, (op, _) in enumerate(c.calls) if op == 'material_ink_attack')
        self.assertTrue(any(op == 'air_return_set' for op, _ in c.calls[entry:first_attack]))
        self.assertTrue(proof['complete'])
        self.assertFalse(c.q['under_water'])
        self.assertTrue(any(op == 'navigate' and args['target'][1] < 61 for op, args in c.calls))

    def test_uncertain_attack_retains_original_and_never_replays_or_claims_ink(self):
        c = DiveClient(unknown=True)
        with TemporaryDirectory() as d, patch('material_jobs.squid_ink.settled_state', side_effect=lambda *a, **k: c.q):
            with self.assertRaises(JobBlocked):
                collect(c, dict(c.squid), d, lambda: c.q)
            p = Path(d)/'squid-ink.json'; original = p.read_bytes(); q = json.loads(original)
            self.assertEqual('attack', q['pending']['kind'])
            self.assertEqual(0, q['actual_ink_gain'])
            self.assertFalse(q['complete'])
            with self.assertRaises(JobBlocked):
                collect(c, dict(c.squid), d, lambda: c.q)
            self.assertEqual(original, p.read_bytes())
        self.assertEqual(1, sum(op == 'material_ink_attack' for op, _ in c.calls))
        self.assertEqual('material_ink_attack', c.calls[-1][0])

    def test_partial_column_scan_does_not_enter_water(self):
        c = DiveClient(partial=True)
        with TemporaryDirectory() as d, patch('material_jobs.squid_ink.settled_state', side_effect=lambda *a, **k: c.q):
            with self.assertRaises(JobBlocked):
                collect(c, dict(c.squid), d, lambda: c.q)
        self.assertFalse(any(op == 'walk' for op, _ in c.calls))


if __name__ == '__main__':
    unittest.main()
