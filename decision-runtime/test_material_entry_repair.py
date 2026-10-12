import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from material_jobs.entry_repair import choose,observe


def rows(wet=False):
    result=[]
    for x in range(-3,9):
        for z in range(-3,9):
            for y in range(-1,26):
                if 7<=y<=14:continue
                name='diorite' if (x,z,y)in((2,2,4),(3,2,4)) else 'stone'
                result.append({'pos':[x,y,z],'state':'Block{minecraft:'+name+'}',
                               'solid':True,'passable':False,'fluid':False,'block_entity':False})
            if wet:result.append({'pos':[x,26,z],'state':'Block{minecraft:water}[level=0]',
                                  'solid':False,'passable':False,'fluid':True,'block_entity':False})
    return result


class EntryRepairTest(unittest.TestCase):
    def setUp(self):
        self.region={'item':'minecraft:diorite','min':[0,0,0],'max':[5,9,5],
                     'source':'natural_survey','surface_y':9}
        self.profile={'protected_regions':[],'dimension':'minecraft:overworld'}

    def test_supported_seam_replaces_false_ground_height_without_stock_credit(self):
        result=choose(rows(),self.region,[3,35,3],self.profile,{})
        self.assertIsNotNone(result);r=result['region']
        self.assertGreaterEqual(r['max'][1],15)
        self.assertLessEqual(r['max'][1]-r['min'][1]+1,18)
        self.assertEqual(r['max'][1]+1,r['access_shaft']['min'][1])
        self.assertEqual(2,result['observed_target_blocks']);self.assertEqual(0,result['inventory_credit'])
        self.assertEqual([0,0,0],self.region['min']);self.assertEqual(9,self.region['surface_y'])

    def test_water_and_protected_footprint_are_rejected(self):
        self.assertIsNone(choose(rows(True),self.region,[3,35,3],self.profile,{}))
        self.profile['protected_regions']=[{'min':[-3,-1,-3],'max':[9,30,9]}]
        self.assertIsNone(choose(rows(),self.region,[3,35,3],self.profile,{}))

    def test_incomplete_native_scan_preserves_source_without_any_navigation(self):
        state={'pos':[3,35,3],'projection_selection':{}}
        c=SimpleNamespace(world='w',rev=3,status=lambda:state,
                          checked=Mock(return_value={'world_session':'w','scan_cells_read':0,
                                                     'scan_total_cells':0,'control_revision':3}))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError,'incomplete'):
                observe(c,self.region,self.profile,Path(tmp)/'new-dir')
        self.assertEqual('scan',c.checked.call_args.args[0]);self.assertEqual(1,c.checked.call_count)
    def test_legacy_wide_sand_site_is_rejected_before_any_block_scan(self):
        c=SimpleNamespace(world='w',status=Mock(),checked=Mock())
        region={'item':'minecraft:sand','min':[0,64,0],'max':[25,78,34],'source':'previous_authorized_sand_site'}
        with tempfile.TemporaryDirectory()as tmp:proof=observe(c,region,self.profile,Path(tmp))
        self.assertIsNone(proof['planned']);c.status.assert_not_called();c.checked.assert_not_called()


if __name__=='__main__':unittest.main()
