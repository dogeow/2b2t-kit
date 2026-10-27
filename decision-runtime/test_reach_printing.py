import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from reach_printing import reachable, print_stations, CurrentOwner


class ReachTests(unittest.TestCase):
    def test_missing_floor_under_actor_requires_higher_hover_pose(self):
        from reach_printing import floor_stance_clearance
        self.assertFalse(floor_stance_clearance([[1,63,1]], [1.5,64.1,1.5]))
        self.assertTrue(floor_stance_clearance([[1,63,1]], [1.5,65.2,1.5]))
        self.assertTrue(floor_stance_clearance([[1,63,1]], [2.5,64.1,1.5]))
        self.assertTrue(floor_stance_clearance([], [1.5,64.1,1.5]))

    def test_plain_cube_material_supports_stone_and_rejects_mixed_or_stateful_blocks(self):
        from reach_printing import plain_cube_material
        for item in ('minecraft:cobblestone', 'minecraft:dark_oak_planks'):
            self.assertEqual(item, plain_cube_material({'expected':[{'item':item,'state':'Block{'+item+'}'}]}))
        for rows in ([], [{'item':'minecraft:composter','state':'Block{minecraft:composter}[level=0]'}],
                     [{'item':'minecraft:cobblestone','state':'Block{minecraft:stone}'}],
                     [{'item':'minecraft:cobblestone','state':'Block{minecraft:cobblestone}'},
                      {'item':'minecraft:dark_oak_planks','state':'Block{minecraft:dark_oak_planks}'}]):
            with self.assertRaises(ValueError): plain_cube_material({'expected':rows})

    def test_direct_owner_retains_native_checked_input_and_read_paths(self):
        class Client:
            world = 'same-world'
            calls = []
            def request(self, op, **params):
                self.calls.append(('read',op,params))
                return {'phase':None,'projection_audit':{}}
            def checked(self, op, **params):
                self.calls.append(('checked',op,params))
                raise RuntimeError('original unresolved native outcome')
        client = Client()
        with tempfile.TemporaryDirectory() as directory:
            owner = CurrentOwner(client,directory)
            self.assertIsNone(owner.native('projection_audit')['phase'])
            with self.assertRaisesRegex(RuntimeError,'original unresolved'):
                owner.native('professional_print',seconds=20)
            with self.assertRaises(ValueError):
                owner.native('mine_block',pos=[1,2,3])
            self.assertEqual(client.calls,[('read','projection_audit',{}),
                                           ('checked','professional_print',{'seconds':20})])
            self.assertEqual(owner.world,'same-world')

    def test_centered_room_can_group_both_walls_and_rear(self):
        positions = [[x, y, z] for x in (17, 19) for y in (65,66,67) for z in range(805,810)]
        positions += [[18, y, 805] for y in (65,66,67)]
        batch = reachable(positions, [18.5,65,807.5], 64)
        self.assertEqual(len(batch), 32)

    def test_real_small_stack_limits_batch_even_when_total_stock_is_large(self):
        self.assertEqual(len(reachable([[x,65,805] for x in range(17,20)], [18.5,65,807.5], 1)), 1)

    def test_actor_body_and_out_of_reach_targets_are_excluded(self):
        self.assertEqual(reachable([[18,65,807],[18,66,807],[100,65,807]], [18.5,65,807.5], 64), [])

    def test_duplicate_or_zero_capacity_is_rejected(self):
        with self.assertRaises(ValueError):
            reachable([[1,1,1],[1,1,1]], [0,0,0], 64)
        with self.assertRaises(ValueError):
            reachable([[1,1,1]], [0,0,0], 0)

    def test_unconfirmed_print_is_retained_without_clear_or_retry(self):
        pos = [17,65,807]
        table = {'expected': [{'pos': pos, 'item': 'minecraft:dark_oak_planks',
                               'state': 'Block{minecraft:dark_oak_planks}'}]}
        state = {'professional_printer': {'enabled': False}, 'projection_batch': {'active': False},
                 'inventory': [{'slot': 0,'item': 'minecraft:dark_oak_planks','count': 64}],
                 'hand': {'item':'minecraft:dark_oak_planks','count':64}, 'pos':[18.5,65,807.5]}
        class Owner:
            world = 'world'
            calls = []
            def native(self, op, **params):
                self.calls.append(op)
                if op == 'projection_model':
                    return {'projection_model': {}}
                if op == 'projection_audit':
                    return {'projection_audit': {'placement_key':'key','total':1,'matched':0,
                            'mismatches':[{'kind':'missing','pos':pos}]}}
                if op == 'professional_print':
                    raise RuntimeError('unconfirmed native request')
                return {}
        q = Owner()
        with tempfile.TemporaryDirectory() as directory, patch('reach_printing.verify', return_value='key'):
            path = Path(directory)/'proof.json'
            with self.assertRaisesRegex(RuntimeError, 'unconfirmed'):
                print_stations(q, table, [{'positions':[pos],'route':[]}], path, lambda:state)
            proof = json.loads(path.read_text())
            self.assertFalse(proof['complete'])
            self.assertEqual(proof['pending']['op'], 'professional_print')
            self.assertEqual(proof['batches'], [])
            self.assertEqual(q.calls.count('professional_print'), 1)
            self.assertNotIn('projection_batch_clear', q.calls)


if __name__ == '__main__':
    unittest.main()
