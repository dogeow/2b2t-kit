import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from projection_material_plan import ProcessingCatalog, plan


class ProjectionMaterialPlanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.jar = Path(self.temp.name) / 'recipes.jar'
        with zipfile.ZipFile(self.jar, 'w') as archive:
            def recipe(name, result, count, ingredients):
                archive.writestr('data/minecraft/recipe/' + name + '.json', json.dumps({
                    'type': 'minecraft:crafting_shapeless',
                    'ingredients': ['minecraft:' + item for item in ingredients],
                    'result': {'id': 'minecraft:' + result, 'count': count}}))
            recipe('furnace', 'furnace', 1, ['cobblestone'] * 8)
            recipe('blast_furnace', 'blast_furnace', 1, ['iron_ingot'] * 5 + ['furnace'] + ['smooth_stone'] * 3)
            recipe('polished_deepslate', 'polished_deepslate', 4, ['cobbled_deepslate'] * 4)
            recipe('deepslate_bricks', 'deepslate_bricks', 4, ['polished_deepslate'] * 4)
            recipe('deepslate_tiles', 'deepslate_tiles', 4, ['deepslate_bricks'] * 4)
            for source, output in [('cobblestone', 'stone'), ('stone', 'smooth_stone')]:
                archive.writestr('data/minecraft/recipe/' + output + '.json', json.dumps({
                    'type': 'minecraft:smelting', 'ingredient': 'minecraft:' + source,
                    'result': {'id': 'minecraft:' + output}, 'cookingtime': 200}))
        self.catalog = ProcessingCatalog(self.jar)

    def projection(self, **targets):
        return {'observed_at': 100, 'loaded_chunks_verified': True, 'placement_key': 'ship',
                'server': 'example.test', 'dimension': 'minecraft:overworld',
                'replacement_items': {'minecraft:' + key: value for key, value in targets.items()}}

    def source(self, key='backpack', kind='carried', **counts):
        return {'key': key, 'kind': kind, 'observed_at': 100, 'complete': True,
                'server': 'example.test', 'dimension': 'minecraft:overworld',
                'counts': {'minecraft:' + item: amount for item, amount in counts.items()}}

    def audit(self, *sources):
        return {'complete': True, 'sources': list(sources)}

    def test_net_smooth_stone_includes_only_remaining_build_and_blast_recipe(self):
        result = plan(self.projection(smooth_stone=135, blast_furnace=17), self.audit(self.source(
            furnace=17, iron_ingot=85, smooth_stone=20, stone=48, cobblestone=118)), self.catalog)
        self.assertEqual({}, result['acquire'])
        totals = result['smelt_totals']
        self.assertEqual({'minecraft:stone':118, 'minecraft:smooth_stone':166}, totals)
        self.assertEqual(17, next(row['produced'] for row in result['craft'] if row['item']=='minecraft:blast_furnace'))
        self.assertEqual('verified_audit_snapshot', result['quantity_status'])

    def test_previously_placed_furnaces_do_not_satisfy_crafting_inputs(self):
        result = plan(self.projection(blast_furnace=17), self.audit(
            self.source(furnace=11, iron_ingot=85, smooth_stone=51, cobblestone=48),
            self.source('workbank', 'installed', furnace=6)), self.catalog)
        self.assertEqual({}, result['acquire'])
        self.assertEqual(6, next(row['produced'] for row in result['craft'] if row['item']=='minecraft:furnace'))
        self.assertEqual(1, len(result['excluded_sources']))

    def test_existing_deepslate_tiles_and_raw_stock_reduce_acquisition(self):
        result = plan(self.projection(deepslate_tiles=625), self.audit(
            self.source(cobbled_deepslate=71), self.source('house', 'depot', cobbled_deepslate=3, deepslate_tiles=5)), self.catalog)
        self.assertEqual({'minecraft:cobbled_deepslate':546}, result['acquire'])
        self.assertEqual(620, next(row['produced'] for row in result['craft'] if row['item']=='minecraft:deepslate_tiles'))
        self.assertEqual(5, result['depot_stock_requires_withdrawal']['minecraft:deepslate_tiles'])

    def test_missing_or_historical_inventory_is_unknown_not_already_withdrawn(self):
        historical = self.source('old-box', 'historical', furnace=23, smooth_stone=216)
        result = plan(self.projection(smooth_stone=10), {'complete':False, 'sources':[historical]}, self.catalog)
        self.assertEqual('unknown', result['quantity_status'])
        self.assertEqual('upper_bound_from_verified_stock', result['deficit_basis'])
        self.assertEqual({}, result['carried_stock'])
        self.assertEqual({'minecraft:cobblestone':10}, result['acquire'])

    def test_inventory_before_projection_cannot_count_already_placed_materials_again(self):
        old = self.source(smooth_stone=50); old['observed_at']=99
        result = plan(self.projection(smooth_stone=135), self.audit(old), self.catalog)
        self.assertEqual('unknown', result['quantity_status'])
        self.assertEqual(135, next(row['produced'] for row in result['smelt'] if row['item']=='minecraft:smooth_stone'))
        self.assertEqual({}, result['carried_stock'])

    def test_partial_counts_are_lower_bound_and_world_mismatch_is_excluded(self):
        partial = self.source('checked-items', smooth_stone=5); partial['complete']=False
        wrong = self.source('another-world', 'depot', smooth_stone=100); wrong['dimension']='minecraft:the_nether'
        result = plan(self.projection(smooth_stone=10), self.audit(partial, wrong), self.catalog)
        self.assertEqual('unknown', result['quantity_status'])
        self.assertEqual({'minecraft:cobblestone':5}, result['acquire'])

    def test_duplicate_source_or_same_chest_with_two_names_is_rejected(self):
        row = self.source()
        with self.assertRaisesRegex(ValueError, 'distinct'):
            plan(self.projection(furnace=1), self.audit(row, row), self.catalog)
        first = self.source('left', 'depot', furnace=1); first['position']=[1,2,3]
        second = {**first, 'key':'second name'}
        with self.assertRaisesRegex(ValueError, 'counted twice'):
            plan(self.projection(furnace=1), self.audit(first, second), self.catalog)
        with self.assertRaisesRegex(ValueError, 'one current backpack'):
            plan(self.projection(furnace=1), self.audit(self.source('first'), self.source('later')), self.catalog)

    def test_unloaded_projection_is_rejected(self):
        projection = self.projection(furnace=1); projection['loaded_chunks_verified']=False
        with self.assertRaisesRegex(ValueError, 'loaded build region'):
            plan(projection, self.audit(self.source()), self.catalog)


if __name__ == '__main__':
    unittest.main()
