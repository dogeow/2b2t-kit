import unittest
from craft_recipe import pin_chest_planks, pin_furnace_cobblestone


class TagRecipeTest(unittest.TestCase):
    def test_mixed_tag_resolution_keeps_all_eight_chest_cells(self):
        plan = {'output': 'minecraft:chest', 'ingredients': {
            'minecraft:oak_planks': [1, 2, 3, 4, 6, 7, 8],
            'minecraft:spruce_planks': [9]}, 'produces': 1}
        pinned = pin_chest_planks(plan, 'minecraft:spruce_planks')
        self.assertEqual(pinned['ingredients'], {'minecraft:spruce_planks': [1, 2, 3, 4, 6, 7, 8, 9]})
        self.assertEqual(plan['ingredients']['minecraft:spruce_planks'], [9])

    def test_missing_cell_is_not_silently_accepted(self):
        plan = {'output': 'minecraft:chest', 'ingredients': {'minecraft:oak_planks': [1, 2, 3, 4, 6, 7, 8]}}
        with self.assertRaises(ValueError): pin_chest_planks(plan, 'minecraft:spruce_planks')

    def test_furnace_tag_alternative_keeps_the_whole_ring(self):
        plan = {'output': 'minecraft:furnace', 'ingredients': {
            'minecraft:cobblestone': [1, 2, 3, 4, 6, 7],
            'minecraft:cobbled_deepslate': [8, 9]}}
        pinned = pin_furnace_cobblestone(plan)
        self.assertEqual(pinned['ingredients'], {'minecraft:cobblestone': [1, 2, 3, 4, 6, 7, 8, 9]})
        self.assertEqual(plan['ingredients']['minecraft:cobbled_deepslate'], [8, 9])


if __name__ == '__main__': unittest.main()
