import unittest
from projection_terrain import replacement_stock_item,candidates
import test_projection_terrain as terrain_cases

class FlowClearanceStockTests(unittest.TestCase):
    def test_flow_has_no_inventory_item_requirement(self):
        for level in range(1,16):
            self.assertIsNone(replacement_stock_item('Block{minecraft:water}[level='+str(level)+']'))

    def test_sources_and_solids_keep_stock_gate(self):
        self.assertEqual('minecraft:water',replacement_stock_item('Block{minecraft:water}[level=0]'))
        self.assertEqual('minecraft:stone',replacement_stock_item('Block{minecraft:stone}'))

    def test_flow_clearance_can_be_planned_without_invented_water_items(self):
        audit,state,row=terrain_cases.Tests().fixture();row['expected']='Block{minecraft:water}[level=4]';state['inventory']=[]
        self.assertEqual(1,len(candidates(audit,state)))
        row['expected']='Block{minecraft:water}[level=0]'
        self.assertEqual([],candidates(audit,state))

    def test_nearby_fluid_and_container_checks_are_retained(self):
        for flag in ['adjacent_fluid','block_entity']:
            audit,state,row=terrain_cases.Tests().fixture();row['expected']='Block{minecraft:water}[level=4]';state['inventory']=[];row[flag]=True
            self.assertEqual([],candidates(audit,state))
