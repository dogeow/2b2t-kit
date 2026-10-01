"""Projection snow planning uses the bounded direct layer harvester."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from material_jobs.planning import plan
from projection_material_plan import ProcessingCatalog


class SnowPlanningTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        jar = Path(self.temp.name) / 'recipes.jar'
        with zipfile.ZipFile(jar, 'w') as archive:
            archive.writestr('data/minecraft/recipe/snow.json', json.dumps({
                'type': 'minecraft:crafting_shaped', 'pattern': ['###'],
                'key': {'#': 'minecraft:snow_block'},
                'result': {'id': 'minecraft:snow', 'count': 6}}))
            archive.writestr('data/minecraft/recipe/snow_block.json', json.dumps({
                'type': 'minecraft:crafting_shaped', 'pattern': ['##', '##'],
                'key': {'#': 'minecraft:snowball'},
                'result': {'id': 'minecraft:snow_block'}}))
        self.catalog = ProcessingCatalog(jar)

    def test_58_layers_choose_direct_silk_harvest_instead_of_120_snowballs(self):
        result = plan(self.catalog, {'minecraft:snow': 58}, {})
        actions = [step for step in result['steps'] if step['kind'] != 'reserve']
        self.assertEqual([{'kind': 'acquire', 'item': 'minecraft:snow', 'count': 58,
                           'reason': 'Base supply; compare with verified conversion recipes'}], actions)
        self.assertEqual({'minecraft:snow': 58}, result['missing_supplies'])

    def test_existing_snow_blocks_still_use_installed_vanilla_recipe(self):
        result = plan(self.catalog, {'minecraft:snow': 58}, {'minecraft:snow_block': 30})
        actions = [step for step in result['steps'] if step['kind'] != 'reserve']
        self.assertEqual(('craft', 'minecraft:snow', 60, {'minecraft:snow_block': 30}),
                         (actions[0]['kind'], actions[0]['item'], actions[0]['produced'],
                          actions[0]['ingredients']))
        self.assertEqual({}, result['missing_supplies'])


if __name__ == '__main__':
    unittest.main()
