import unittest
from projection_potted_plants import completed_balance,anchors


class PottedMaterialProofTest(unittest.TestCase):
    def test_existing_pane_wall_is_a_real_placement_face_without_a_full_floor(self):
        wall={'pos':[2,66,3],'state':'Block{minecraft:glass_pane}[east=true,north=false,south=false,waterlogged=false,west=true]','solid':False,'fluid':False,'block_entity':False}
        self.assertEqual([('south',wall)],anchors([2,66,4],[wall]))
        self.assertEqual([],anchors([2,66,4],[{**wall,'fluid':True}]))
        self.assertEqual([],anchors([2,66,4],[{**wall,'block_entity':True}]))
    def test_empty_pot_intermediate_is_not_a_completed_plant(self):
        before={'minecraft:flower_pot':10,'minecraft:fern':8}
        self.assertFalse(completed_balance(before,{'minecraft:flower_pot':9,'minecraft:fern':8},'minecraft:fern'))

    def test_both_materials_required_once(self):
        before={'minecraft:flower_pot':10,'minecraft:fern':8}
        self.assertTrue(completed_balance(before,{'minecraft:flower_pot':9,'minecraft:fern':7},'minecraft:fern'))
        self.assertFalse(completed_balance(before,{'minecraft:flower_pot':8,'minecraft:fern':7},'minecraft:fern'))
