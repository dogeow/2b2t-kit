import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from material_jobs.opportunistic_plants import survey


class OpportunisticPlantsTest(unittest.TestCase):
    def client(self,biome='minecraft:desert',complete=True):
        c=SimpleNamespace(world='world',last=None,actions=[])
        def request(op,**kw):
            c.last='read-'+str(len(c.actions));c.actions.append((op,kw))
            if op=='scan_snow_biomes':
                return {'id':c.last,'world_session':'world','snow_biome_survey':{
                    'loaded_samples':1,'samples':[{'pos':[100,64,100],'biome':biome}]}}
            return {'id':c.last,'world_session':'world','phase':'done',
                'scan_cells_read':3072 if complete else 10,'scan_total_cells':3072,
                'blocks':[{'pos':[100,65,100],'state':'Block{minecraft:cactus}'}]}
        c.request=request;return c
    def test_cactus_is_observed_without_inventory_credit_or_mining(self):
        with tempfile.TemporaryDirectory()as t:
            c=self.client();r=survey(c,lambda:{'pos':[100.5,220,100.5]},Path(t)/'result.json')
            self.assertEqual(1,len(r['plants']));self.assertEqual(0,r['inventory_credit'])
            self.assertEqual(['scan_snow_biomes','scan'],[op for op,_ in c.actions])
    def test_ocean_is_not_used_for_cactus_block_search(self):
        with tempfile.TemporaryDirectory()as t:
            c=self.client('minecraft:deep_ocean');r=survey(c,lambda:{'pos':[100.5,220,100.5]},Path(t)/'result.json')
            self.assertEqual([],r['plants']);self.assertEqual(1,len(c.actions))
    def test_partial_patch_does_not_become_a_cactus_source(self):
        with tempfile.TemporaryDirectory()as t:
            c=self.client(complete=False);r=survey(c,lambda:{'pos':[100.5,220,100.5]},Path(t)/'result.json')
            self.assertEqual([],r['plants']);self.assertFalse(r['patches'][0]['complete'])
    def test_player_takeover_prevents_any_read_dispatch(self):
        with tempfile.TemporaryDirectory()as t:
            c=self.client()
            def checkpoint():raise RuntimeError('manual')
            with self.assertRaisesRegex(RuntimeError,'manual'):survey(c,checkpoint,Path(t)/'result.json')
            self.assertEqual([],c.actions)

    def test_flower_forest_scan_reaches_below_tree_crown(self):
        with tempfile.TemporaryDirectory()as t:
            c=self.client('minecraft:flower_forest');old=c.request
            def request(op,**kw):
                if op=='scan_snow_biomes':
                    r=old(op,**kw);r['snow_biome_survey']['samples'][0]['pos'][1]=80;return r
                c.last='read-'+str(len(c.actions));c.actions.append((op,kw))
                total=256*(kw['max'][1]-kw['min'][1]+1)
                return {'id':c.last,'world_session':'world','phase':'done',
                    'scan_cells_read':total,'scan_total_cells':total,
                    'blocks':[{'pos':[100,65,100],'state':'Block{minecraft:rose_bush}[half=lower]'}]}
            c.request=request;r=survey(c,lambda:{'pos':[100.5,220,100.5]},Path(t)/'result.json')
            self.assertEqual(62,c.actions[1][1]['min'][1]);self.assertEqual(88,c.actions[1][1]['max'][1])
            self.assertEqual(1,len(r['plants']));self.assertEqual(0,r['inventory_credit'])

if __name__=='__main__':unittest.main()
