"""Meaningful pure load/reserve/metadata tests; no Client or game reads."""
from copy import deepcopy
import unittest
from projection_stock_plan import plan_stock

ITEM = 'minecraft:sandstone'
META = {'item': ITEM, 'max_stack': 64}


def inventory(free=0):
    rows = [{'slot': i, 'item': 'minecraft:diamond_pickaxe', 'count': 1, 'max_stack': 1, 'durability': 1200} for i in range(43)]
    for i in range(free): rows[9+i] = {'slot': 9+i, 'item': 'minecraft:air', 'count': 0, 'max_stack': 1}
    return rows


def target(rows, slot, count, **metadata):
    rows[slot] = {'slot': slot, **META, **metadata, 'count': count}


class ProjectionStockPlanTests(unittest.TestCase):
    def test_218_once226_four_real_stack_budgets(self):
        rows = inventory(4); before = deepcopy(rows)
        p = plan_stock(rows, ITEM, 218, 64, stack_metadata=META)
        self.assertEqual((p['phase'], p['withdraw_amount'], p['stock_total_target'], p['construction_cells']), ('ready', 226, 226, 218))
        self.assertEqual([a['target_count'] for a in p['allocations']], [64, 64, 64, 34])
        self.assertEqual([s['planned_cells'] for s in p['construction_stacks']], [62, 62, 62, 32])
        self.assertTrue(all(s['retained_after_cells'] == 2 for s in p['construction_stacks']))
        self.assertEqual(rows, before); self.assertEqual(p['game_operations'], 0)

    def test_14_plus2_main_partial_first_takes32_for44(self):
        rows = inventory(); target(rows, 5, 14); target(rows, 26, 2)
        p = plan_stock(rows, ITEM, 44, 64, stack_metadata=META)
        self.assertEqual((p['withdraw_amount'], p['stock_total_target'], p['construction_cells']), (32, 48, 44))
        self.assertEqual([(a['slot'], a['target_count']) for a in p['allocations']], [(26, 34)])
        self.assertEqual([s['planned_cells'] for s in p['construction_stacks']], [32, 12])

    def test_insufficient_two_slots_one_whole_load_and94_remaining(self):
        p = plan_stock(inventory(2), ITEM, 218, 64, stack_metadata=META)
        self.assertEqual((p['phase'], p['withdraw_amount'], p['construction_cells'], p['remaining_cells']), ('partial', 128, 124, 94))
        self.assertTrue(p['remaining_requires_new_inventory_plan'])

    def test_enough_current_stock_no_fetch_or_unneeded_fragment_topup(self):
        rows = inventory(2); target(rows, 5, 64); target(rows, 26, 1)
        p = plan_stock(rows, ITEM, 20, 64, stack_metadata=META)
        self.assertEqual(p['withdraw_amount'], 0); self.assertEqual(p['allocations'], [])
        self.assertEqual(p['construction_stacks'][0]['retained_after_cells'], 44)
        self.assertIn(rows[5], p['supply_preserved_inventory'])
        self.assertNotIn(rows[5], p['protected_inventory'])
        self.assertIn(rows[26], p['protected_inventory'])

    def test_actual_max16_and_empty_air_one_limit(self):
        p = plan_stock(inventory(2), ITEM, 15, 16, stack_metadata={**META, 'max_stack': 16})
        self.assertEqual(p['stock_total_target'], 19)
        self.assertEqual([a['target_count'] for a in p['allocations']], [16, 3])
        self.assertEqual([s['planned_cells'] for s in p['construction_stacks']], [14, 1])

    def test_offhand_equipment_packed_hint_not_loose_credit(self):
        rows = inventory(1); target(rows, 40, 64)
        rows[0] = {'slot': 0, 'item': 'minecraft:shulker_box', 'count': 1, 'max_stack': 1,
                   'contains': [{'item': ITEM, 'count': 64, 'max_stack': 64}]}
        p = plan_stock(rows, ITEM, 100, 64, stack_metadata=META)
        self.assertEqual((p['current_eligible_stock'], p['construction_cells'], p['withdraw_amount']), (0, 62, 64))
        self.assertEqual(p['excluded_auxiliary_target_count'], 64)
        self.assertIn(rows[40], p['protected_inventory']); self.assertIn(rows[0], p['protected_inventory'])

    def test_named_other_meta_target_protected_not_merged_or_used(self):
        rows = inventory(1); target(rows, 26, 60, custom_name='Player property')
        p = plan_stock(rows, ITEM, 50, 64, stack_metadata=META)
        self.assertEqual(p['withdraw_amount'], 52)
        self.assertEqual((p['current_main_item_stock'], p['eligible_stock_total_target'], p['stock_total_target']), (60, 52, 112))
        self.assertTrue(p['metadata_scoped_transfer_required'])
        self.assertFalse(p['item_only_transfer_authorized'])
        self.assertEqual(p['protected_different_metadata_target_slots'], [26])
        self.assertIn(rows[26], p['protected_inventory'])

    def test_unknown_max_meta_inventory_empty_shape_block(self):
        for size, meta in [(None, META), (64, None), (64, {'item': ITEM}), (64, {**META, 'max_stack': 16}), (True, META)]:
            self.assertEqual(plan_stock(inventory(1), ITEM, 1, size, stack_metadata=meta)['phase'], 'blocked')
        for mutate in [lambda r: r.pop(), lambda r: r.__setitem__(42, deepcopy(r[0])),
                       lambda r: r[0].update(count=True), lambda r: r[0].pop('max_stack'),
                       lambda r: r[9].update(contains=[]), lambda r: r[0].update(durability=float('nan'))]:
            rows = inventory(1); mutate(rows)
            self.assertEqual(plan_stock(rows, ITEM, 1, 64, stack_metadata=META)['phase'], 'blocked')

    def test_max_one_cannot_place_and_keep_two(self):
        self.assertEqual(plan_stock(inventory(1), ITEM, 1, 1, stack_metadata={**META, 'max_stack': 1})['code'], 'stack_reserve_unusable')

    def test_zero_missing_and_full_non_target_no_disposal(self):
        p = plan_stock(inventory(), ITEM, 0, 64, stack_metadata=META)
        self.assertEqual((p['phase'], p['withdraw_amount'], p['construction_cells']), ('ready', 0, 0))
        p = plan_stock(inventory(), ITEM, 20, 64, stack_metadata=META)
        self.assertEqual((p['phase'], p['withdraw_amount'], p['remaining_cells']), ('blocked', 0, 20))
        self.assertEqual(len(p['protected_inventory']), 43)

    def test_every_deficit_up_to_four_stacks_exact_usable_cells_and_reserves(self):
        for needed in range(1, 249):
            p = plan_stock(inventory(4), ITEM, needed, 64, stack_metadata=META)
            self.assertEqual(p['construction_cells'], needed)
            self.assertEqual(sum(s['planned_cells'] for s in p['construction_stacks']), needed)
            self.assertEqual(p['withdraw_amount'], needed + 2 * len(p['allocations']))
            self.assertTrue(all(3 <= a['target_count'] <= 64 for a in p['allocations']))

    def test_source_count_is_not_availability_proof(self):
        p = plan_stock(inventory(4), ITEM, 218, 64, stack_metadata={**META, 'slot': 4, 'count': 1})
        self.assertEqual(p['withdraw_amount'], 226); self.assertFalse(p['source_availability_proved'])
        self.assertTrue(p['requires_fresh_native_supply_and_per_stack_proof'])

    def test_invalid_observed_source_or_unknown_deficit_never_plans_mutation(self):
        for missing in (None, True, -1, 3.5):
            self.assertEqual(plan_stock(inventory(1), ITEM, missing, 64, stack_metadata=META)['phase'], 'blocked')
        for count in (0, True, 65):
            self.assertEqual(plan_stock(inventory(1), ITEM, 1, 64, stack_metadata={**META, 'count': count})['phase'], 'blocked')
        self.assertEqual(plan_stock(inventory(1), ITEM, 1, 64, stack_metadata={**META, 'custom': float('inf')})['phase'], 'blocked')

    def test_nested_metadata_types_cannot_merge_true_integer_or_float(self):
        for observed, source in [(1, True), (1, 1.0), (False, 0)]:
            rows = inventory(1); target(rows, 26, 20, custom={'marked': observed})
            p = plan_stock(rows, ITEM, 10, 64, stack_metadata={**META, 'custom': {'marked': source}})
            self.assertEqual(p['current_eligible_stock'], 0)
            self.assertEqual(p['withdraw_amount'], 12)
            self.assertIn(rows[26], p['protected_inventory'])


if __name__ == '__main__': unittest.main()
