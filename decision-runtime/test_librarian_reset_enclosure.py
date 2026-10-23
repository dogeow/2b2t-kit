import copy
import unittest
from librarian_room import LibrarianRoom
from librarian_reset_enclosure import require_enclosed_reset


class ResetEnclosureTests(unittest.TestCase):
    def fixture(self, inward=-1):
        room = LibrarianRoom('keeper', (100, 65, 100), inward)
        blocks = {}
        def full(x, y, z):
            blocks[x, y, z] = {'pos': [x, y, z], 'state': 'Block{minecraft:dark_oak_planks}',
                               'solid': True, 'fluid': False, 'block_entity': False}
        for n in (1, 2, 3):
            z = 100 + n * inward
            full(100, 64, z)
            full(100, 68, z)
            for y in range(65, 68):
                full(99, y, z)
                full(101, y, z)
        for y in range(65, 68):
            full(100, y, 100 + 4 * inward)
        full(100, 64, 100)
        full(100, 67, 100)
        blocks[100, 66, 100] = {'pos': [100, 66, 100], 'state':
            'Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'}
        center = 100 + 2 * inward + .5
        actor = {'uuid': 'keeper', 'type': 'minecraft:villager', 'health': 20,
                 'is_baby': False, 'bounds': {'min': [100.2, 65.5625, center - .3],
                                            'max': [100.8, 67.5125, center + .3]}}
        return {'time': 123, 'world_session': 'world', 'blocks': list(blocks.values()),
                'scan_entities': [actor]}, room

    def test_bed_height_is_safe_with_full_shell_in_both_directions(self):
        for direction in (-1, 1):
            scene, room = self.fixture(direction)
            proof = require_enclosed_reset(scene, room)
            self.assertEqual(proof['pickup_route'], 'public_front_only')

    def test_closed_top_trapdoor_keeps_separate_player_pickup_route(self):
        scene, room = self.fixture()
        scene['blocks'][-1]['state'] = ('Block{minecraft:dark_oak_trapdoor}'
            '[half=top,open=false,waterlogged=false]')
        self.assertEqual(require_enclosed_reset(scene, room)['counter_opening'], 1.8125)

    def test_open_trapdoor_is_rejected_even_if_room_cap_reader_accepts_it(self):
        scene, room = self.fixture()
        scene['blocks'][-1]['state'] = ('Block{minecraft:dark_oak_trapdoor}'
            '[half=top,open=true,waterlogged=false,facing=north]')
        with self.assertRaises(ValueError): require_enclosed_reset(scene, room)

    def test_missing_side_rear_roof_or_floor_fails(self):
        for pos in ([99, 65, 99], [100, 66, 96], [100, 68, 98], [100, 64, 98]):
            scene, room = self.fixture()
            scene['blocks'] = [v for v in scene['blocks'] if v['pos'] != pos]
            with self.assertRaises(ValueError): require_enclosed_reset(scene, room)

    def test_solid_flag_does_not_make_unverified_block_a_full_cube(self):
        scene, room = self.fixture()
        scene['blocks'][0]['state'] = 'Block{minecraft:chest}'
        with self.assertRaises(ValueError): require_enclosed_reset(scene, room)

    def test_outside_or_small_body_is_rejected(self):
        for axis, edge, value in ((0, 'min', 99.9), (2, 'max', 100.1), (1, 'max', 66.6)):
            scene, room = self.fixture()
            scene['scan_entities'][0]['bounds'][edge][axis] = value
            with self.assertRaises(ValueError): require_enclosed_reset(scene, room)

    def test_another_entity_in_lectern_cell_is_rejected(self):
        scene, room = self.fixture()
        other = copy.deepcopy(scene['scan_entities'][0])
        other['uuid'] = 'other'
        other['bounds'] = {'min': [100.2, 65, 100.1], 'max': [100.8, 66.95, 100.7]}
        scene['scan_entities'].append(other)
        with self.assertRaises(ValueError): require_enclosed_reset(scene, room)

    def test_different_identity_or_unhealthy_resident_is_rejected(self):
        for key, value in (('uuid', 'other'), ('health', 19), ('is_baby', True)):
            scene, room = self.fixture()
            scene['scan_entities'][0][key] = value
            with self.assertRaises(ValueError): require_enclosed_reset(scene, room)


if __name__ == '__main__': unittest.main()

class InsetCounterEnclosureTests(unittest.TestCase):
    def fixture(self):
        scene,old=ResetEnclosureTests().fixture(inward=1)
        room=LibrarianRoom('keeper',(100,65,101),1,public_counter=(100,65,100),interior_depth=2)
        scene['blocks'].extend([
            {'pos':[100,66,101],'state':'Block{minecraft:oak_trapdoor}[half=top,open=false,waterlogged=false]'},
            {'pos':[100,67,101],'state':'Block{minecraft:oak_planks}','solid':True,'fluid':False,'block_entity':False}])
        return scene,room
    def test_exact_two_cell_room_keeps_full_original_rear_wall_and_adult_body(self):
        scene,room=self.fixture();proof=require_enclosed_reset(scene,room)
        self.assertEqual(proof['interior_depth'],2);self.assertEqual(proof['counter_opening'],1.8125)
        self.assertEqual(room.bounds()[1][2],104)
    def test_each_inset_side_floor_roof_and_real_rear_wall_is_required(self):
        for pos in [[99,65,102],[101,67,103],[100,64,102],[100,68,103],[100,66,104]]:
            scene,room=self.fixture();scene['blocks']=[r for r in scene['blocks']if r['pos']!=pos]
            with self.subTest(pos=pos),self.assertRaises(ValueError):require_enclosed_reset(scene,room)
    def test_relabeling_depth_does_not_admit_body_outside_or_remove_header(self):
        scene,room=self.fixture();scene['scan_entities'][0]['bounds']['min'][2]=101.9
        with self.assertRaises(ValueError):require_enclosed_reset(scene,room)
        scene,room=self.fixture();scene['blocks']=[r for r in scene['blocks']if r['pos']!=[100,67,101]]
        with self.assertRaises(ValueError):require_enclosed_reset(scene,room)
