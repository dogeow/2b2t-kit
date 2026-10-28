import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from packed_supplies import pad_support_allowed,take_box

GRASS='Block{minecraft:grass_block}[snowy=false]'
TOP='Block{minecraft:cobblestone_slab}[type=top,waterlogged=false]'

class PackedPadSupportTests(unittest.TestCase):
    def test_existing_callers_still_only_admit_grass(self):
        self.assertTrue(pad_support_allowed(GRASS))
        self.assertTrue(pad_support_allowed('Block{minecraft:grass_block}[snowy=true]'))
        for state in [TOP,'Block{minecraft:stone}','Block{minecraft:cobblestone}',None]:
            self.assertFalse(pad_support_allowed(state))

    def test_explicit_support_must_match_exactly(self):
        self.assertTrue(pad_support_allowed(TOP,TOP))
        self.assertTrue(pad_support_allowed('Block{minecraft:cobblestone}','Block{minecraft:cobblestone}'))
        self.assertFalse(pad_support_allowed(GRASS,TOP))
        self.assertFalse(pad_support_allowed(None,TOP))

    def test_bottom_wet_double_container_and_hazard_supports_stay_rejected(self):
        for state in [TOP.replace('top','bottom'),TOP.replace('false','true'),
                      TOP.replace('top','double'),'Block{minecraft:chest}',
                      'Block{minecraft:magma_block}','Block{minecraft:water}[level=0]']:
            with self.subTest(state=state):
                self.assertFalse(pad_support_allowed(state,state))

    def test_changed_support_or_obstructed_pad_never_opens_ender_chest(self):
        with tempfile.TemporaryDirectory() as folder:
            client=Mock();client.out=Path(folder)
            client.status.return_value={'inventory':[{'slot':i,'item':'minecraft:air','count':0}for i in range(36)]}
            for observations in [[GRASS,None,None],[TOP,'Block{minecraft:torch}'],[TOP,None,'Block{minecraft:glass}']]:
                with self.subTest(observations=observations),patch('packed_supplies.block',side_effect=observations),patch('packed_supplies.open_box')as opening:
                    with self.assertRaises(RuntimeError):
                        take_box(client,[0,1,0],[1,1,0],4,{},expected_pad_support=TOP)
                    opening.assert_not_called()
            client.checked.assert_not_called()

    def test_explicit_top_support_passes_only_after_empty_pad_and_headroom_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            client=Mock();client.out=Path(folder)
            client.status.return_value={'inventory':[{'slot':i,'item':'minecraft:air','count':0}for i in range(36)]}
            with patch('packed_supplies.block',side_effect=[TOP,None,None])as read,patch('packed_supplies.open_box',side_effect=RuntimeError('source observation sentinel'))as opening:
                with self.assertRaisesRegex(RuntimeError,'source observation sentinel'):
                    take_box(client,[0,1,0],[1,1,0],4,{},expected_pad_support=TOP)
                self.assertEqual(3,read.call_count)
                opening.assert_called_once_with(client,[0,1,0],'ChestMenu')
            client.checked.assert_not_called()
