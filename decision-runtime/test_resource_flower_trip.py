import copy
import unittest
from material_jobs.resource_flower_trip import current_source,survey_bounds,descent_station

class FlowerSourceTest(unittest.TestCase):
    def setUp(self):
        self.low=[100,62,100];self.high=[115,77,115]
        self.profile={'protected_regions':[{'min':[0,50,0],'max':[10,90,10]}]}
        self.state={'projection_selection':{}}
        self.reply={'id':'fresh','world_session':'world','phase':'done','time':1000,
            'scan_cells_read':4096,'scan_total_cells':4096,'unloaded_chunks':0,
            'blocks':[{'pos':[104,64,104],'state':'Block{minecraft:white_tulip}',
                'fluid':False,'solid':False,'block_entity':False}]}
    def source(self,r=None,p=None):
        return current_source(r or self.reply,'world','fresh','minecraft:white_tulip',
            self.low,self.high,p or self.profile,self.state)
    def test_live_native_flower_record_routes_without_any_cached_inventory_credit(self):
        result=self.source();self.assertEqual([[104,64,104]],result['verified_flower_positions'])
        self.assertTrue(result['authorized']);self.assertEqual(0,result['cached_inventory_credit'])
    def test_old_world_request_incomplete_volume_or_unloaded_chunk_is_never_a_source(self):
        for change in [{'id':'old'},{'world_session':'old'},{'phase':'waiting'},
                       {'scan_cells_read':4095},{'scan_total_cells':4095},{'unloaded_chunks':1}]:
            with self.subTest(change=change),self.assertRaises(RuntimeError):self.source({**self.reply,**change})
    def test_protected_footprint_or_structure_is_not_authorized_as_wild_flower_ground(self):
        with self.assertRaises(RuntimeError):self.source(p={'protected_regions':[{'min':[90,50,90],'max':[120,90,120]}]})
        r=copy.deepcopy(self.reply);r['blocks'].append({'pos':[105,64,104],
            'state':'Block{minecraft:chest}','fluid':False,'solid':True,'block_entity':True})
        with self.assertRaises(RuntimeError):self.source(r)
    def test_duplicate_and_outside_positions_do_not_become_valid_flower_counts(self):
        for point in ([104,64,104],[116,64,104]):
            r=copy.deepcopy(self.reply);row=copy.deepcopy(r['blocks'][0]);row['pos']=point;r['blocks'].append(row)
            with self.assertRaises(RuntimeError):self.source(r)
    def test_smaller_source_is_scanned_as_its_own_candidate_bounded_volume(self):
        box={'min':[100,62,100],'max':[107,77,107]}
        self.assertEqual((box['min'],box['max']),survey_bounds({'tile':[100,100]},62,box))
        for invalid in [{'min':[99,62,100],'max':[107,77,107]},
                        {'min':[100,62,100],'max':[116,77,107]}]:
            with self.assertRaises(ValueError):survey_bounds({'tile':[100,100]},62,invalid)
    def test_descent_chooses_an_observed_open_column_instead_of_crossing_a_tree_canopy(self):
        region={'min':[100,62,100],'max':[107,77,107],'verified_flower_positions':[[102,64,102],[105,64,105]]}
        reply={'id':'sky','world_session':'world','phase':'done','scan_cells_read':64*254,
            'scan_total_cells':64*254,'blocks':[{'pos':[102,72,102],'passable':False,'fluid':False,'block_entity':False}]}
        self.assertEqual([105.5,66.75,105.5],descent_station(reply,'world','sky',region,[102.5,220,102.5]))
        reply['blocks'].append({'pos':[105,72,105],'passable':False,'fluid':False,'block_entity':False})
        with self.assertRaises(RuntimeError):descent_station(reply,'world','sky',region,[102.5,220,102.5])
    def test_incomplete_or_old_sky_scan_cannot_authorize_a_descent(self):
        region={'min':[100,62,100],'max':[107,77,107],'verified_flower_positions':[[102,64,102]]}
        reply={'id':'sky','world_session':'old','phase':'done','scan_cells_read':64*254,
            'scan_total_cells':64*254,'blocks':[]}
        with self.assertRaises(RuntimeError):descent_station(reply,'world','sky',region,[102.5,220,102.5])

if __name__=='__main__':unittest.main()
