"""Offline real-drop/scope/tool tests; no game client is opened."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from material_jobs import natural_block_pipeline as natural
from material_jobs.protocol import JobBlocked, JobPaused


def block(pos, name, *, fluid=False, container=False):
    return {'pos': list(pos), 'state': 'Block{minecraft:'+name+'}', 'solid': not fluid,
            'fluid': fluid, 'block_entity': container, 'passable': fluid}


class Client:
    world = 'world'
    def __init__(self, out, item='minecraft:dripstone_block'):
        self.out = out; self.item = item; self.count = 0; self.actions = []
        self.last = None; self.selected = 10; self.entities = []; self.full = False
        kind = 'axe' if item.endswith('mushroom_stem') else 'pickaxe'
        self.tool = {'slot': 10, 'item': 'minecraft:diamond_'+kind, 'count': 1,
                     'durability': 1500, 'max_durability': 1561, 'max_stack': 1,
                     'enchantments': [{'id': 'minecraft:silk_touch', 'level': 1}] if kind == 'axe' else []}
        self.hand = copy.deepcopy(self.tool)
        self.uncertain = False; self.bad_hand = False; self.switch_tool = False
        self.auto_gain = True; self.merge_old = False; self.wrong_id = False; self.unloaded = False
        self.manual = False; self.health = 20; self.post_world_change = False
        self.rows = [block([x,64,100], item.split(':')[1]) for x in range(100,106)]
        self.rows += [block([x,63,100], 'stone') for x in range(99,107)]
        if item.endswith('mushroom_stem'):
            self.rows = [block([100,y,100], 'mushroom_stem') for y in range(64,68)]
            self.rows += [block([100,63,100], 'mycelium'), block([100,68,100], 'brown_mushroom_block')]
    def status(self):
        rows = [{'slot': i, 'item': 'minecraft:air', 'count': 0, 'max_stack': 1} for i in range(36)]
        if self.full:
            rows = [{'slot': i, 'item': 'minecraft:stone', 'count': 64, 'max_stack': 64} for i in range(36)]
        rows[self.tool['slot']] = copy.deepcopy(self.tool)
        if not self.full:
            rows[6] = {'slot': 6, 'item': self.item, 'count': self.count, 'max_stack': 64}
        return {'world_session': self.world, 'connected': True, 'health': self.health, 'food': 20,
                'server': 'test:25565', 'dimension': 'minecraft:overworld', 'manual_movement': self.manual,
                'guard_armed': True, 'guard_pve_only': True, 'guard_busy': False, 'under_water': False,
                'pos': [99.5,64,100.5], 'selected_slot': self.selected, 'hand': copy.deepcopy(self.hand),
                'inventory': rows, 'entities': copy.deepcopy(self.entities)}
    def request(self, op, **params):
        self.actions.append((op, copy.deepcopy(params))); self.last = 'req-'+str(len(self.actions))
        if op == 'scan':
            if params.get('details') is not True:
                raise AssertionError('Native metadata exists only on details=True scans')
            return {'phase': 'done', 'world_session': self.world, 'unloaded_chunks': int(self.unloaded),
                    'blocks': [copy.deepcopy(r) for r in self.rows if all(params['min'][i] <= r['pos'][i] <= params['max'][i] for i in range(3))]}
        if op == 'mine_block':
            if self.uncertain:
                return {'phase': 'waiting', 'id': self.last, 'world_session': self.world}
            pos = params['pos']; row = next(r for r in self.rows if r['pos'] == pos)
            assert params['expected_state'] == row['state']
            self.rows.remove(row); self.tool['durability'] -= 1; self.hand = copy.deepcopy(self.tool)
            if self.switch_tool:
                self.hand['enchantments'] = []
            if self.auto_gain:
                self.count += 1
            else:
                if self.merge_old:
                    self.entities = []
                self.entities.append({'type': 'minecraft:item', 'uuid': 'new-'+self.last,
                                      'pos': [pos[0]+.5,pos[1]+.2,pos[2]+.5],
                                      'stack': {'item': self.item, 'count': 2 if self.merge_old else 1}})
            if self.post_world_change:
                self.world = 'new-world'
            return {'phase': 'done', 'id': 'foreign' if self.wrong_id else self.last,
                    'world_session': self.world}
        raise AssertionError(op)
    def checked(self, op, **params):
        self.actions.append((op, copy.deepcopy(params)))
        assert op == 'select_item' and params['slot'] == self.tool['slot']
        if self.tool['slot'] >= 9:
            self.tool['slot'] = 5  # Actual existing native SWAP-to-hotbar behavior.
        self.selected = self.tool['slot']; self.hand = copy.deepcopy(self.tool)
        if self.bad_hand:
            self.hand['enchantments'] = []
        return {'phase': 'done'}


class NaturalBlockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name); self.reset()
    def reset(self, item='minecraft:dripstone_block'):
        self.c = Client(self.out, item)
        self.profile = {'server': 'test', 'dimension': 'minecraft:overworld',
                        'protected_regions': [{'min': [0,50,0], 'max': [10,90,10]}],
                        'natural_source_regions': [{'item': item, 'authorized': True, 'source': 'natural_survey',
                                                    'min': [99,62,99], 'max': [106,70,102]}]}
        self.backend = SimpleNamespace(client=self.c, profile=self.profile, prepare_travel=Mock())
        self.c.material_backend = self.backend
    def collect(self, c, drop, before):
        assert drop['uuid'].startswith('new-')
        current = next(e for e in c.entities if e['uuid'] == drop['uuid'])
        c.count += current['stack']['count']; c.entities.remove(current)
        return True
    def go(self, target=1):
        with (patch.object(natural, 'approach_faces', return_value='west'),
              patch.object(natural, 'collect_drop', side_effect=self.collect)):
            return natural.run(self.c, self.profile, self.c.item, target, self.out, lambda: None)
    def mines(self):
        return [p for op,p in self.c.actions if op == 'mine_block']
    def test_dripstone_uses_plain_mine_not_quarry_and_exact_actual_gain(self):
        result = self.go()
        self.assertEqual(('done', 'absolute_backpack', 1),
                         (result['phase'], result['target_scope'], result['count']))
        self.assertEqual(1, len(self.mines()))
        self.assertFalse(any('quarry' in op for op,_ in self.c.actions))
    def test_silk_axe_selected_with_actual_hotbar_metadata_and_one_stem(self):
        self.reset('minecraft:mushroom_stem')
        self.assertEqual('done', self.go()['phase'])
        self.assertEqual(5, self.c.selected)
        self.assertEqual(1, self.c.count)
    def test_no_silk_axe_waits_before_scanning_or_mining(self):
        self.reset('minecraft:mushroom_stem'); self.c.tool['enchantments'] = []
        self.assertEqual('WAIT_TOOL', self.go()['code'])
        self.assertEqual([], self.c.actions)
    def test_tool_hand_mismatch_is_not_assumed_silk(self):
        self.reset('minecraft:mushroom_stem'); self.c.bad_hand = True
        self.assertEqual('WAIT_RECONCILE', self.go()['code'])
        self.assertEqual([], self.mines())
    def test_tool_change_during_mining_never_claims_completed_stem(self):
        self.reset('minecraft:mushroom_stem'); self.c.switch_tool = True
        self.assertEqual('WAIT_RECONCILE', self.go()['code'])
        self.assertEqual('WAIT_RECONCILE', self.go()['code'])
        self.assertEqual(1, len(self.mines()))
    def test_missing_authorization_cache_hint_or_wrong_source_never_mines(self):
        for changes in ({'authorized': False}, {'source': 'cached_resource_points'}):
            with self.subTest(changes=changes):
                self.profile['natural_source_regions'][0].update(changes)
                self.assertEqual('WAIT_SOURCE', self.go()['code'])
                self.assertEqual([], self.c.actions)
                self.profile['natural_source_regions'][0].update(authorized=True, source='natural_survey')
    def test_protected_area_and_missing_protection_skip_sources(self):
        self.profile['protected_regions'] = [{'min': [90,50,90], 'max': [110,90,110]}]
        self.assertEqual('WAIT_SOURCE', self.go()['code']); self.assertEqual([], self.mines())
        self.profile.pop('protected_regions'); self.c.actions.clear()
        self.assertEqual('WAIT_SOURCE', self.go()['code']); self.assertEqual([], self.mines())
    def test_liquid_falling_container_and_player_building_are_rejected(self):
        for row in (block([101,65,100], 'water', fluid=True), block([101,65,100], 'gravel'),
                    block([101,65,100], 'chest', container=True), block([101,65,100], 'oak_planks'),
                    block([101,65,100], 'pointed_dripstone')):
            with self.subTest(row=row):
                self.c.rows.append(row)
                self.assertEqual('WAIT_SOURCE', self.go()['code']); self.assertEqual([], self.mines())
                self.c.rows.remove(row); self.c.actions.clear()
    def test_stem_requires_current_soil_column_and_mushroom_cap(self):
        self.reset('minecraft:mushroom_stem')
        self.c.rows = [r for r in self.c.rows if 'brown_mushroom_block' not in r['state']]
        self.assertEqual('WAIT_SOURCE', self.go()['code']); self.assertEqual([], self.mines())
    def test_new_drop_only_is_collected_old_uuid_is_preserved(self):
        self.c.auto_gain = False
        old = {'type': 'minecraft:item', 'uuid': 'old', 'pos': [100,64,100],
               'stack': {'item': self.c.item, 'count': 1}}
        self.c.entities = [copy.deepcopy(old)]
        self.assertEqual('done', self.go()['phase'])
        self.assertEqual([old], self.c.entities)
        self.assertEqual(1, self.c.count)
    def test_merge_with_old_drop_cannot_be_collected_or_credited(self):
        self.c.auto_gain = False; self.c.merge_old = True
        self.c.entities = [{'type': 'minecraft:item', 'uuid': 'old', 'pos': [100,64,100],
                            'stack': {'item': self.c.item, 'count': 1}}]
        self.assertEqual('WAIT_RECONCILE', self.go()['code']); self.assertEqual(0, self.c.count)
    def test_unknown_mining_receipt_and_foreign_reply_never_replay(self):
        self.c.uncertain = True
        self.assertEqual('WAIT_RECONCILE', self.go()['code'])
        self.assertEqual('WAIT_RECONCILE', self.go()['code']); self.assertEqual(1, len(self.mines()))
    def test_wrong_reply_identity_is_rejected_even_when_inventory_increases(self):
        self.c.wrong_id = True
        self.assertEqual('WAIT_RECONCILE', self.go()['code']); self.assertEqual(1, self.c.count)
        self.assertEqual('WAIT_RECONCILE', self.go()['code']); self.assertEqual(1, len(self.mines()))
    def test_four_block_batch_resumes_without_remining_old_cells(self):
        first = self.go(5)
        self.assertEqual(('waiting', 'SOURCE_BATCH', 4), (first['phase'], first['code'], self.c.count))
        self.assertEqual('done', self.go(5)['phase']); self.assertEqual(5, self.c.count)
        self.assertEqual(5, len({tuple(p['pos']) for p in self.mines()}))
    def test_completed_output_move_does_not_reproduce_same_batch(self):
        self.go(); self.c.count = 0
        self.assertEqual('COMPLETED_RECEIPT', self.go()['code'])
        self.assertEqual(1, len(self.mines()))
    def test_unloaded_scan_and_full_inventory_never_mine(self):
        self.c.unloaded = True
        self.assertEqual('WAIT_SOURCE', self.go()['code']); self.assertEqual([], self.mines())
        self.c.unloaded = False; self.c.full = True
        self.assertEqual('WAIT_CAPACITY', self.go()['code']); self.assertEqual([], self.mines())
    def test_manual_takeover_and_world_transition_pause(self):
        self.c.manual = True
        with self.assertRaises(JobPaused): self.go()
        self.assertEqual([], self.c.actions)
        self.c.manual = False; self.go(); self.c.world = 'next'
        with self.assertRaises(JobPaused): self.go()
    def test_existing_backpack_count_cannot_override_health_scope(self):
        self.c.count = 1; self.c.health = 18
        self.assertEqual('WAIT_SAFETY', self.go()['code'])
        self.assertEqual([], self.c.actions)
    def test_world_changes_during_mining_never_claims_success(self):
        self.c.post_world_change = True
        self.assertEqual('WAIT_RECONCILE', self.go()['code'])
        with self.assertRaises(JobPaused): self.go()
        self.assertEqual(1, len(self.mines()))
    def test_new_backend_controller_is_never_created_or_accepted(self):
        self.backend.client = Client(self.out)
        with self.assertRaises(JobBlocked): self.go()
        self.assertEqual([], self.c.actions)
    def test_incomplete_metadata_scan_is_not_treated_as_safe_natural_blocks(self):
        self.c.rows[0].pop('block_entity')
        self.assertEqual('WAIT_SOURCE', self.go()['code']); self.assertEqual([], self.mines())


if __name__ == '__main__':
    unittest.main()
