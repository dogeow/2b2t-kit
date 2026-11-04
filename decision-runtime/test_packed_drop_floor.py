import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from packed_supplies import observe_drop_floor,require_drop_floor_unchanged,take_box

PAD=[10,64,20]
GRASS='Block{minecraft:grass_block}[snowy=false]'
TOP='Block{minecraft:cobblestone_slab}[type=top,waterlogged=false]'

class DropFloorTests(unittest.TestCase):
    def test_complete_flat_dry_catch_surface_is_observed_cell_by_cell(self):
        cells=observe_drop_floor(None,PAD,lambda c,p:TOP)
        self.assertEqual(9,len(cells));self.assertEqual(9,len({tuple(v['pos'])for v in cells}))
        self.assertEqual({63},{v['pos'][1]for v in cells})
        require_drop_floor_unchanged(None,PAD,cells,lambda c,p:TOP)

    def test_the_incident_single_support_and_every_missing_corner_are_rejected(self):
        for absent in [None,[9,63,19],[11,63,21],[10,63,19]]:
            def read(c,p):
                return TOP if (p==[10,63,20]if absent is None else p!=absent)else None
            with self.subTest(absent=absent),self.assertRaisesRegex(RuntimeError,'catch floor'):
                observe_drop_floor(None,PAD,read)

    def test_water_containers_heat_and_lower_surfaces_do_not_catch_at_the_pinned_height(self):
        for bad in ['Block{minecraft:water}[level=0]','Block{minecraft:chest}',
                    'Block{minecraft:magma_block}',TOP.replace('top','bottom'),
                    TOP.replace('false','true'),'Block{minecraft:sand}']:
            with self.subTest(bad=bad),self.assertRaises(RuntimeError):
                observe_drop_floor(None,PAD,lambda c,p:bad if p==[11,63,21]else TOP)

    def test_even_an_allowed_replacement_is_a_changed_original_floor(self):
        before=observe_drop_floor(None,PAD,lambda c,p:TOP)
        with self.assertRaisesRegex(RuntimeError,'floor changed'):
            require_drop_floor_unchanged(None,PAD,before,lambda c,p:GRASS)

    def test_edge_gap_prevents_even_opening_the_ender_box(self):
        with tempfile.TemporaryDirectory()as folder:
            c=Mock();c.out=Path(folder);c.status.return_value={'inventory':[{'slot':i,'item':'minecraft:air','count':0}for i in range(36)]}
            def read(client,pos):return TOP if pos==[10,63,20]else None
            with patch('packed_supplies.block',side_effect=read),patch('packed_supplies.open_box')as opening:
                with self.assertRaisesRegex(RuntimeError,'catch floor'):
                    take_box(c,[1,64,1],PAD,5,{'minecraft:iron_block':4},expected_pad_support=TOP)
                opening.assert_not_called();c.checked.assert_not_called()

    def test_floor_removed_after_tool_selection_leaves_box_intact(self):
        from test_packed_supplies import EquipmentWithdrawalTest
        fixture=EquipmentWithdrawalTest()
        with tempfile.TemporaryDirectory()as folder:
            c=fixture.client(folder);checked=c.checked
            def changed(op,**params):
                result=checked(op,**params)
                if op=='select_item'and params['item']=='minecraft:diamond_pickaxe':c.floor_missing=True
                return result
            c.checked=changed
            with self.assertRaisesRegex(RuntimeError,'catch floor'):fixture.run_withdrawal(c,4)
            record=json.loads((c.out/'packed-transfer-active.json').read_text())
            self.assertEqual('withdrawn',record['stage']);self.assertEqual(9,len(record['drop_catch_floor']))
            self.assertTrue(c.placed);self.assertFalse(c.returned)
            self.assertFalse(any(op in ('recover_shulker','mine_block','collect_item')for op,_ in c.actions))

if __name__=='__main__':unittest.main()
