"""Native 2x2 diorite batching, output capacity and exact retained inputs."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from recipe_catalog import RecipeCatalog
from material_manufacture import _inventory_batch, manufacture
from craft_grid import InventoryCapacity
from test_material_manufacture import InventoryCraftClient


class DioriteClient(InventoryCraftClient):
    def status(self):
        state = super().status()
        valid = all(self.slots[i]['count'] and self.slots[i]['item'] == item
                    for item, cells in self.spec['ingredients'].items() for i in cells)
        self.slots[0].update(item=self.spec['output'] if valid else 'minecraft:air',
                             count=self.spec['produces'] if valid else 0)
        state['menu']['slots'] = deepcopy(self.slots)
        return state


class BulkDioriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog = RecipeCatalog('/Applications/.minecraft/versions/26.1.2/26.1.2.jar')
        self.spec = self.catalog.choose('minecraft:diorite',
                                       {'minecraft:cobblestone':234, 'minecraft:quartz':234}, 2)

    def client(self, counts=(64,64,64,42), existing=13):
        c = DioriteClient(Path(self.temp.name), stock={'minecraft:diorite':existing})
        c.spec = self.spec
        for i, (item, n) in enumerate([(item,n) for item in ('minecraft:cobblestone','minecraft:quartz')
                                      for n in counts], start=10):
            c.slots[i].update(item=item, count=n)
        return c

    def test_native_catalog_and_full_cells_make128_in_one_shift_batch(self):
        self.assertEqual({'minecraft:cobblestone':[1,4], 'minecraft:quartz':[2,3]}, self.spec['ingredients'])
        self.assertEqual(2, self.spec['produces'])
        batch = _inventory_batch(self.client().status(), self.spec, 245)
        self.assertEqual((64,128), (batch['rounds'],batch['produced']))
        self.assertEqual(4, len(batch['actions']))

    def test_partial_stacks_make232_in_three_batches_and_keep_two_each(self):
        c = self.client()
        c.slots[30].update(item='minecraft:diamond_sword', count=1, max_stack=1, durability=877)
        protected = deepcopy(c.slots[30])
        with patch('kit_runtime.inventory.time.sleep'), patch('material_manufacture.time.sleep'):
            result = manufacture(c, self.catalog, {'minecraft:diorite':245},
                                 keep={'minecraft:cobblestone':2,'minecraft:quartz':2})
        self.assertTrue(result['complete'])
        for item,n in [('diorite',245),('cobblestone',2),('quartz',2)]:
            self.assertEqual(n, sum(r['count'] for r in c.slots[9:45] if r['item']=='minecraft:'+item))
        self.assertEqual(3, sum(p['slot']==0 and p['kind']=='quick_move' for op,p in c.calls))
        self.assertEqual(protected, c.slots[30])
        self.assertFalse(c.cursor['count'])
        self.assertFalse(any(r['count'] for r in c.slots[1:5]))

    def test_two_output_without_space_refuses_before_any_click(self):
        c = self.client(counts=(64,64), existing=0)
        for row in c.slots[9:45]:
            if not row['count']:row.update(item='minecraft:diamond_sword', count=1, max_stack=1)
        with self.assertRaises(InventoryCapacity):_inventory_batch(c.status(), self.spec, 2)
        self.assertEqual([], c.calls)


if __name__ == '__main__':unittest.main()
