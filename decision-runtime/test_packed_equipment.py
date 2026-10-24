from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from packed_supplies import matching_source,matching_count
from packed_equipment import take
from test_anvil_enchant_preview import book,empty


class PackedEquipmentTests(unittest.TestCase):
    def test_exact_filter_does_not_accept_extra_curse_lower_level_or_other_affixes(self):
        wanted=book('minecraft:efficiency',5)
        wrong=book('minecraft:efficiency',4)
        extra=deepcopy(wanted);extra['stored_enchantments'].append({'id':'minecraft:vanishing_curse','level':1})
        good={**deepcopy(wanted),'slot':22}
        rows=[wrong,extra,book(),good]
        exact={wanted['item']:wanted}
        self.assertEqual(matching_source(rows,wanted['item'],exact_stacks=exact),good)
        self.assertEqual(matching_count(rows,wanted['item'],exact_stacks=exact),1)
        self.assertIsNone(matching_source(rows[:-1],wanted['item'],exact_stacks=exact))
    def test_explicit_box_and_exact_stack_reach_existing_guarded_transaction(self):
        with tempfile.TemporaryDirectory()as d:
            profile=Path(d)/'profile.json';profile.write_text(json.dumps({'server':'simpcraft.com','dimension':'minecraft:overworld','ender_chest':[1,64,2],'shulker_pad':[3,64,2]}))
            wanted=book('minecraft:efficiency',5);initial={'dimension':'minecraft:overworld','inventory':[empty(i)for i in range(36)]}
            final=deepcopy(initial);final['inventory'][9]={**wanted,'slot':9}
            c=Mock(server='simpcraft.com');c.status.side_effect=[initial,final]
            boxes=[empty(i)for i in range(27)];boxes[14]={'item':'minecraft:shulker_box','count':1,'contains':[wanted]}
            with patch('packed_equipment.open_box',return_value={'menu':{'slots':boxes}}),patch('packed_equipment.take_box',return_value={'stage':'returned'})as take_box:
                result=take(c,profile,14,wanted)
            self.assertTrue(result['complete'])
            take_box.assert_called_once_with(c,[1,64,2],[3,64,2],14,{'minecraft:enchanted_book':1},exact_stacks={'minecraft:enchanted_book':wanted})
            c.checked.assert_called_once_with('close_menu')


if __name__=='__main__':unittest.main()
