import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from collections import Counter

from material_plan import MaterialPlanner, PlanningLimit, quantities, ledger_counts
from recipe_catalog import RecipeCatalog


def recipe(output, count, ingredients):
    return {'type': 'minecraft:crafting_shapeless', 'ingredients': ingredients,
            'result': {'id': output, 'count': count}}


class PlannerTests(unittest.TestCase):
    def catalog(self, recipes):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        jar = Path(folder.name) / 'client.jar'
        with zipfile.ZipFile(jar, 'w') as z:
            for key, value in recipes.items():
                z.writestr('data/minecraft/recipe/' + key + '.json', json.dumps(value))
        return RecipeCatalog(jar)

    def wood(self):
        return self.catalog({
            'planks': recipe('minecraft:oak_planks', 4, ['minecraft:oak_log']),
            'door': recipe('minecraft:oak_door', 3, ['minecraft:oak_planks'] * 6),
        })

    def verify_mass_balance(self, plan):
        stock = Counter(plan['input_stock'])
        reserved = Counter(plan['reserved_finished_items'])
        for step in plan['steps']:
            if step['kind'] == 'acquire':
                stock[step['item']] += step['count']
            elif step['kind'] == 'reserve':
                reserved[step['item']] = step['count']
            else:
                for ingredient, amount in step['ingredients'].items():
                    self.assertGreaterEqual(stock[ingredient] - reserved[ingredient] - plan['kept'].get(ingredient, 0), amount)
                    stock[ingredient] -= amount
                stock[step['item']] += step['produced']
        expected = Counter(plan['targets']) + Counter(plan['kept']) + Counter(plan['surplus'])
        self.assertEqual(+stock, +expected)

    def test_rounding_keeps_surplus_and_orders_intermediate_first(self):
        p = MaterialPlanner(self.wood()).plan({'minecraft:oak_door': 2}, {'minecraft:oak_log': 2})
        self.assertFalse(p['missing_supplies'])
        self.assertEqual([s['item'] for s in p['steps'] if s['kind'] == 'craft'], ['minecraft:oak_planks', 'minecraft:oak_door'])
        self.assertEqual(p['surplus'], {'minecraft:oak_planks': 2, 'minecraft:oak_door': 1})
        self.verify_mass_balance(p)

    def test_existing_finished_materials_are_not_spent_on_other_goals(self):
        p = MaterialPlanner(self.wood()).plan({'minecraft:oak_planks': 4, 'minecraft:oak_door': 2}, {'minecraft:oak_planks': 6, 'minecraft:oak_log': 1})
        self.assertEqual(p['reserved_finished_items']['minecraft:oak_planks'], 4)
        self.assertFalse(p['missing_supplies'])
        self.verify_mass_balance(p)

    def test_intermediate_materials_are_not_reserved_before_their_root_goal(self):
        p = MaterialPlanner(self.wood()).plan({'minecraft:oak_planks': 4, 'minecraft:oak_door': 2}, {'minecraft:oak_log': 3})
        self.assertFalse(p['missing_supplies'])
        self.verify_mass_balance(p)

    def test_personal_supplies_are_kept(self):
        p = MaterialPlanner(self.wood()).plan({'minecraft:oak_door': 2}, {'minecraft:oak_log': 3}, {'minecraft:oak_log': 2})
        self.assertEqual(p['missing_supplies'], {'minecraft:oak_log': 1})
        self.verify_mass_balance(p)

    def test_conversion_cycle_does_not_invent_a_block_of_ingots(self):
        cat = self.catalog({'block': recipe('minecraft:iron_block', 1, ['minecraft:iron_ingot'] * 9),
                            'ingot': recipe('minecraft:iron_ingot', 9, ['minecraft:iron_block'])})
        p = MaterialPlanner(cat).plan({'minecraft:iron_ingot': 1}, {})
        self.assertEqual(p['missing_supplies'], {'minecraft:iron_ingot': 1})
        self.assertFalse(any(s['kind'] == 'craft' for s in p['steps']))
        self.verify_mass_balance(p)
        p = MaterialPlanner(cat).plan({'minecraft:iron_ingot': 1}, {'minecraft:iron_block': 1})
        self.assertFalse(p['missing_supplies'])
        self.assertEqual(p['surplus']['minecraft:iron_ingot'], 8)
        self.verify_mass_balance(p)

    def test_alternative_uses_recorded_stock_without_inventing_supply(self):
        cat = self.catalog({'rose': recipe('minecraft:black_dye', 1, ['minecraft:wither_rose']),
                            'ink': recipe('minecraft:black_dye', 1, ['minecraft:ink_sac'])})
        p = MaterialPlanner(cat).plan({'minecraft:black_dye': 2}, {'minecraft:ink_sac': 3})
        self.assertFalse(p['missing_supplies'])
        self.assertEqual(p['steps'][0]['recipe_id'], 'ink')
        self.verify_mass_balance(p)

    def test_large_batch_uses_logs_instead_of_expanding_a_few_loose_planks(self):
        woods = ['minecraft:oak_planks', 'minecraft:birch_planks']
        cat = self.catalog({'barrel': recipe('minecraft:barrel', 1, [woods] * 6),
                            'oak': recipe('minecraft:oak_planks', 4, ['minecraft:oak_log']),
                            'birch': recipe('minecraft:birch_planks', 4, ['minecraft:birch_log'])})
        p = MaterialPlanner(cat).plan({'minecraft:barrel': 45}, {'minecraft:oak_log': 100, 'minecraft:birch_planks': 2})
        self.assertFalse(p['missing_supplies'])
        self.assertEqual(p['surplus']['minecraft:birch_planks'], 2)
        self.verify_mass_balance(p)

    def test_cycle_in_base_material_does_not_hide_the_parent_recipe(self):
        cat = self.catalog({'block': recipe('minecraft:iron_block', 1, ['minecraft:iron_ingot'] * 9),
                            'ingot': recipe('minecraft:iron_ingot', 9, ['minecraft:iron_block']),
                            'trapdoor': recipe('minecraft:iron_trapdoor', 1, ['minecraft:iron_ingot'] * 4)})
        p = MaterialPlanner(cat).plan({'minecraft:iron_trapdoor': 3}, {})
        self.assertEqual(p['missing_supplies'], {'minecraft:iron_ingot': 12})
        self.assertTrue(any(s['kind'] == 'craft' and s['item'] == 'minecraft:iron_trapdoor' for s in p['steps']))
        self.verify_mass_balance(p)

    def test_partial_and_uncraftable_stock_stays_an_explicit_acquisition(self):
        p = MaterialPlanner(self.wood()).plan({'minecraft:quartz': 12}, {'minecraft:quartz': 3})
        self.assertEqual(p['missing_supplies'], {'minecraft:quartz': 9})
        self.verify_mass_balance(p)

    def test_plan_is_reproducible_and_does_not_mutate_input(self):
        planner = MaterialPlanner(self.wood())
        stock = {'minecraft:oak_log': 8}
        before = dict(stock)
        a = planner.plan({'minecraft:oak_door': 5}, stock)
        self.assertEqual(a, planner.plan({'minecraft:oak_door': 5}, stock))
        self.assertEqual(stock, before)

    def test_search_budget_does_not_return_an_incomplete_executable_plan(self):
        with self.assertRaises(PlanningLimit):
            MaterialPlanner(self.wood(), max_expansions=1).plan({'minecraft:oak_door': 1}, {})

    def test_invalid_quantities_are_rejected(self):
        for value in ({'diamond': 1}, {'minecraft:diamond': -1}, {'minecraft:diamond': True}, {'minecraft:diamond': 1.2}):
            with self.assertRaises(ValueError):
                quantities(value)

    def test_portable_container_history_cannot_be_counted_as_permanent_stock(self):
        source = {'key': 'old-shulker-position', 'kind': 'warehouse_record', 'block_id': 'minecraft:shulker_box',
                  'observed_at': 123, 'stock': {'minecraft:diamond': 64}}
        with self.assertRaises(ValueError):
            ledger_counts({'sources': [source]})

    def test_duplicate_depot_keys_cannot_double_the_stock(self):
        source = {'key': 'depot', 'kind': 'warehouse_record', 'block_id': 'minecraft:chest',
                  'observed_at': 123, 'stock': {'minecraft:oak_log': 64}}
        self.assertEqual(ledger_counts({'sources': [source]})['minecraft:oak_log'], 64)
        with self.assertRaises(ValueError):
            ledger_counts({'sources': [source, source]})


if __name__ == '__main__':
    unittest.main()
