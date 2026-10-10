import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.acquisition import _replant_tree_with_bonemeal, _apply_bone_meal, _outside_future_trunk, Unavailable


def native_cell(pos, state, *, solid=False, passable=True):
    return {'pos': list(pos), 'state': state, 'solid': solid,
            'passable': passable, 'replaceable': not solid,
            'fluid': False, 'block_entity': False}


class NativeTreeClient:
    """Native-style sparse scans plus server-confirmed item and cell changes."""
    world = 'tree-world'

    def __init__(self, hole='Block{minecraft:air}'):
        self.cells = {
            (2, 63, 3): native_cell([2, 63, 3], 'Block{minecraft:grass_block}[snowy=false]',
                                  solid=True, passable=False),
            (2, 64, 3): native_cell([2, 64, 3], hole,
                                  solid='air' not in hole, passable='air' in hole),
        }
        self.items = {'minecraft:oak_sapling': 2, 'minecraft:bone_meal': 6}
        self.actions = []
        self.time = 100
        self.pos = [1.5, 64, 3.5]

    def status(self):
        self.time += 1
        return {'world_session': self.world, 'pos': self.pos, 'health': 20, 'food': 20,
                'guard_armed': True, 'guard_pve_only': True, 'time': self.time,
                'entities': [], 'inventory': [
                    {'slot': i, 'item': item, 'count': count, 'max_stack': 64}
                    for i, (item, count) in enumerate(self.items.items())]}

    def request(self, op, **args):
        self.actions.append((op, copy.deepcopy(args)))
        if op != 'scan':
            raise AssertionError(op)
        # AutomationBridge.scan omits isEmptyBlock cells after verifying every
        # requested server chunk. A missing row is not a missing scan receipt.
        air = {'Block{minecraft:air}', 'Block{minecraft:cave_air}', 'Block{minecraft:void_air}'}
        return {'blocks': [copy.deepcopy(cell) for pos, cell in self.cells.items()
                          if cell['state'] not in air
                          and all(args['min'][i] <= pos[i] <= args['max'][i] for i in range(3))]}

    def checked(self, op, **args):
        self.actions.append((op, copy.deepcopy(args)))
        if op == 'select_item':
            if self.items.get(args['item'], 0) <= 0:
                raise AssertionError('Selected unavailable item')
            return {'phase': 'done'}
        if op != 'interact':
            raise AssertionError(op)
        pos = tuple(args['pos'])
        if self.cells[pos]['state'] != args['expected_state']:
            raise AssertionError('Interaction used an unobserved cell state')
        if args['expected_hand'] == 'minecraft:oak_sapling':
            if pos != (2, 63, 3):
                raise AssertionError('Sapling placed outside the verified stump')
            self.items['minecraft:oak_sapling'] -= 1
            self.cells[(2, 64, 3)] = native_cell([2, 64, 3], 'Block{minecraft:oak_sapling}[stage=0]')
        elif args['expected_hand'] == 'minecraft:bone_meal':
            if pos != (2, 64, 3):
                raise AssertionError('Bone meal used outside the confirmed sapling')
            self.items['minecraft:bone_meal'] -= 1
            self.cells[pos] = native_cell(pos, 'Block{minecraft:oak_log}[axis=y]',
                                          solid=True, passable=False)
            self.cells[(2, 65, 3)] = native_cell([2, 65, 3], 'Block{minecraft:oak_log}[axis=y]',
                                               solid=True, passable=False)
        else:
            raise AssertionError(args['expected_hand'])
        return {'phase': 'done'}


class TreeRegrowthTest(unittest.TestCase):
    def test_growth_scan_arrives_after_the_inventory_debit(self):
        client=NativeTreeClient('Block{minecraft:oak_sapling}[stage=0]')
        original_checked=client.checked
        original_scan=client.request
        pending=False
        def delayed_use(op,**args):
            nonlocal pending
            if op=='interact'and args.get('expected_hand')=='minecraft:bone_meal':
                client.actions.append((op,copy.deepcopy(args)));pending=True
                return {'phase':'done'}
            return original_checked(op,**args)
        def growth_scan(op,**args):
            nonlocal pending
            if pending and args.get('min')==[0,64,1]:
                pending=False;client.items['minecraft:bone_meal']-=1
                for y in (64,65):
                    client.cells[(2,y,3)]=native_cell([2,y,3],'Block{minecraft:oak_log}[axis=y]',solid=True,passable=False)
            return original_scan(op,**args)
        client.checked=delayed_use;client.request=growth_scan
        with patch('material_jobs.acquisition.approach_faces',return_value='up'):
            result=_apply_bone_meal(client,'minecraft:oak_log','minecraft:oak_sapling',[2,64,3],{},lambda:None)
        self.assertTrue(result['growth_confirmed'])
        self.assertEqual(1,result['bone_meal_used'])
        self.assertEqual(1,result['growth']['bone_meal_used'])
        self.assertEqual([{'before':6,'after':5,'consumed':True,'growth_confirmed':True}],result['bone_meal_receipts'])
        self.assertEqual(1,sum(op=='interact'for op,_ in client.actions))
    def test_neighbour_logs_and_leaves_do_not_confirm_an_unchanged_sapling(self):
        client=NativeTreeClient('Block{minecraft:oak_sapling}[stage=0]')
        client.cells[(3,64,3)]=native_cell([3,64,3],'Block{minecraft:oak_log}[axis=y]',solid=True,passable=False)
        client.cells[(2,66,3)]=native_cell([2,66,3],'Block{minecraft:oak_leaves}[persistent=false]',solid=True,passable=False)
        original=client.checked
        def no_growth(op,**args):
            if op=='interact'and args.get('expected_hand')=='minecraft:bone_meal':
                client.actions.append((op,copy.deepcopy(args)));return {'phase':'done'}
            return original(op,**args)
        client.checked=no_growth
        with patch('material_jobs.acquisition.approach_faces',return_value='up'),\
             patch('material_jobs.acquisition.time.monotonic',side_effect=[0,0,4]),\
             patch('material_jobs.acquisition.time.sleep'):
            result=_apply_bone_meal(client,'minecraft:oak_log','minecraft:oak_sapling',[2,64,3],{},lambda:None)
        self.assertFalse(result.get('growth_confirmed',False))
        self.assertEqual('sapling_kept_bone_meal_unconfirmed',result['stage'])
        self.assertEqual(6,client.items['minecraft:bone_meal'])
        self.assertEqual(1,sum(op=='interact'for op,_ in client.actions))
    def regrow(self, client):
        with tempfile.TemporaryDirectory() as out:
            return _replant_tree_with_bonemeal(
                client, 'minecraft:oak_log', [2, 64, 3], [2, 64, 3], {}, 0, 6,
                Path(out), lambda: None)

    def test_sparse_native_air_stump_replants_and_confirms_growth(self):
        for air in ('air', 'cave_air', 'void_air'):
            with self.subTest(air=air):
                client = NativeTreeClient('Block{minecraft:' + air + '}')
                with patch('material_jobs.acquisition.approach_faces', return_value='up'):
                    result = self.regrow(client)
                self.assertEqual('grown', result['stage'])
                self.assertTrue(result['planted'])
                self.assertTrue(result['growth_confirmed'])
                self.assertEqual(1, result['growth']['bone_meal_used'])
                self.assertEqual(1, result['bone_meal_used'])
                self.assertEqual({'minecraft:oak_sapling': 1, 'minecraft:bone_meal': 5}, client.items)
                self.assertEqual('Block{minecraft:oak_log}[axis=y]', client.cells[(2, 64, 3)]['state'])
                self.assertEqual(2, sum(op == 'interact' for op, _ in client.actions))

    def test_future_trunk_excludes_body_overlap_at_any_height_and_unknown_pose(self):
        for point in ([2.5,64,3.5], [2.5,90,3.5], [1.8,64,3.5],
                      [3.2,64,3.5], None, [], [float('nan'),64,3.5], [True,64,3.5]):
            with self.subTest(point=point):
                self.assertFalse(_outside_future_trunk({'pos':point},[2,64,3]))
        self.assertTrue(_outside_future_trunk({'pos':[1.5,64,3.5]},[2,64,3]))
        self.assertFalse(_outside_future_trunk({'pos':[1.5,64,3.5]},[2,64,3],'minecraft:dark_oak_log'))
        self.assertTrue(_outside_future_trunk({'pos':[.5,64,3.5]},[2,64,3],'minecraft:dark_oak_log'))

    def test_approach_into_root_never_uses_bone_meal(self):
        client=NativeTreeClient()
        def inside(*args, **kwargs):
            client.pos=[2.5,64,3.5]
            return 'up'
        with patch('material_jobs.acquisition.approach_faces', side_effect=inside):
            result=self.regrow(client)
        self.assertEqual('sapling_kept_unsafe_stand',result['stage'])
        self.assertEqual(6,client.items['minecraft:bone_meal'])
        self.assertFalse(any(args.get('expected_hand')=='minecraft:bone_meal' for _,args in client.actions))

    def test_pose_changes_after_scan_before_bone_click_are_rechecked(self):
        client=NativeTreeClient()
        client.cells[(2,64,3)]=native_cell([2,64,3],'Block{minecraft:oak_sapling}[stage=0]')
        scan=client.request
        scans=0
        def moving_scan(op, **args):
            nonlocal scans
            result=scan(op,**args);scans+=1
            if scans==3:client.pos=[2.5,80,3.5]
            return result
        client.request=moving_scan
        with patch('material_jobs.acquisition.approach_faces',return_value='up'):
            result=_apply_bone_meal(client,'minecraft:oak_log','minecraft:oak_sapling',[2,64,3],{},lambda:None)
        self.assertEqual('sapling_kept_unsafe_stand',result['stage'])
        self.assertEqual(6,client.items['minecraft:bone_meal'])
        self.assertFalse(any(op=='interact' for op,_ in client.actions))

    def test_occupied_stump_retains_sapling_and_bone_meal(self):
        client = NativeTreeClient('Block{minecraft:stone}')
        with patch('material_jobs.acquisition.approach_faces') as approach:
            result = self.regrow(client)
        self.assertEqual('seed_kept_site_not_ready', result['stage'])
        self.assertFalse(result['planted'])
        self.assertEqual({'minecraft:oak_sapling': 2, 'minecraft:bone_meal': 6}, client.items)
        self.assertFalse(any(op == 'interact' for op, _ in client.actions))
        approach.assert_not_called()

    def test_stump_occupied_during_approach_stops_before_placement(self):
        client = NativeTreeClient()

        def occupied(*args, **kwargs):
            client.cells[(2, 64, 3)] = native_cell([2, 64, 3], 'Block{minecraft:stone}',
                                                 solid=True, passable=False)
            return 'up'

        with patch('material_jobs.acquisition.approach_faces', side_effect=occupied):
            with self.assertRaises(Unavailable):
                self.regrow(client)
        self.assertEqual({'minecraft:oak_sapling': 2, 'minecraft:bone_meal': 6}, client.items)
        self.assertFalse(any(op == 'interact' for op, _ in client.actions))

    def test_failed_scan_does_not_treat_unloaded_stump_as_air(self):
        client = NativeTreeClient()
        client.request = lambda *args, **kwargs: {'phase': 'waiting', 'detail': 'Server chunk is not loaded'}
        with self.assertRaises(Unavailable) as stopped:
            self.regrow(client)
        self.assertEqual('waiting', stopped.exception.phase)
        self.assertFalse(any(op == 'interact' for op, _ in client.actions))


if __name__ == '__main__':
    unittest.main()
