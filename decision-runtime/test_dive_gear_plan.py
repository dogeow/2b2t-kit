import unittest

from dive_gear_plan import plan


def item(name, ench=(), stored=(), **other):
    return {'item': name, 'count': 1,
            'enchantments': [{'id': 'minecraft:'+key, 'level': level} for key, level in ench],
            'stored_enchantments': [{'id': 'minecraft:'+key, 'level': level} for key, level in stored],
            **other}


class DiveGearPlanTest(unittest.TestCase):
    def test_chooses_actual_underwater_performance_over_unenchanted_shell(self):
        boxes = [{'slot': 4, 'item': 'minecraft:shulker_box', 'count': 1,
                  'contains': [item('minecraft:turtle_helmet'),
                               item('minecraft:diamond_helmet', [('aqua_affinity', 1), ('respiration', 3)]),
                               item('minecraft:diamond_boots', [('depth_strider', 3)]),
                               item('minecraft:diamond_shovel', [('efficiency', 5), ('silk_touch', 1)]),
                               item('minecraft:enchanted_book', stored=[('aqua_affinity', 1)]),
                               item('minecraft:potion', water_breathing=True)]}]
        result = plan(boxes)
        self.assertEqual('minecraft:diamond_helmet', result['best']['helmet']['item']['item'])
        self.assertEqual(3, result['best']['boots']['item']['enchantments'][0]['level'])
        self.assertEqual(4, result['best']['shovel']['ender_slot'])
        self.assertEqual(1, len(result['books']['aqua_affinity']))
        self.assertEqual(1, len(result['water_breathing_potions']))

    def test_reports_missing_equipment_without_inventing_an_enchantment(self):
        result = plan([{'slot': 0, 'item': 'minecraft:shulker_box', 'count': 1,
                        'contains': [item('minecraft:turtle_scute', count=3)]}])
        self.assertIsNone(result['best']['helmet'])
        self.assertEqual(3, result['turtle_scutes_observed'])
        self.assertEqual({}, result['books'])


if __name__ == '__main__': unittest.main()
