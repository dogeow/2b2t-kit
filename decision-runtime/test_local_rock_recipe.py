from collections import Counter
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import zipfile

from local_rock_recipe import run,offer
from material_jobs.protocol import JobBlocked
from recipe_catalog import RecipeCatalog


class LocalRockRecipeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        jar=self.root/'recipes.jar'
        with zipfile.ZipFile(jar,'w')as z:
            z.writestr('data/minecraft/recipe/diorite.json',json.dumps({'type':'minecraft:crafting_shaped',
                'pattern':['CQ','QC'],'key':{'C':'minecraft:cobblestone','Q':'minecraft:quartz'},
                'result':{'id':'minecraft:diorite','count':2}}))
        self.held=Counter();self.stored=Counter({'minecraft:diorite':2,'minecraft:quartz':5,'minecraft:cobblestone':20})
        self.client=SimpleNamespace(world='world',status=lambda:{'inventory':[
            {'slot':i,'item':item,'count':count,'max_stack':64}for i,(item,count)in enumerate(self.held.items())]})
        self.backend=SimpleNamespace(profile={'depots':[[1,64,1]],'local_rock_recipes':{'minecraft:diorite':'diorite'}},
            request={'projection_key':'ship'},crafting_catalog=RecipeCatalog(jar),resource_pipeline_context=None)
        def fetch(targets):
            for item,target in targets.items():
                gain=min(max(0,target-self.held[item]),self.stored[item]);self.stored[item]-=gain;self.held[item]+=gain
            return {'phase':'done'if all(self.held[i]>=n for i,n in targets.items())else'waiting'}
        def craft(targets):
            rounds=(targets['minecraft:diorite']-self.held['minecraft:diorite']+1)//2
            self.held['minecraft:quartz']-=rounds*2;self.held['minecraft:cobblestone']-=rounds*2
            self.held['minecraft:diorite']+=rounds*2
            return {'phase':'done'}
        self.backend.fetch=Mock(side_effect=fetch);self.backend.craft=Mock(side_effect=craft)
        self.saved=[{'pos':[1,64,1],'counts':dict(self.stored),'loose_counts':dict(self.stored),'block_id':'minecraft:chest'}]

    def go(self):
        with patch('local_rock_recipe.records',return_value=self.saved):
            return run(self.backend,self.client,'minecraft:diorite',6,self.root)

    def test_finished_stock_plus_real_local_recipe_conserve_all_materials(self):
        result=self.go()
        self.assertEqual((result['phase'],result['produced'],result['inventory_total']),('done',4,6))
        self.assertEqual(self.backend.fetch.call_args_list[1].args[0],{'minecraft:cobblestone':4,'minecraft:quartz':4})
        self.assertEqual((self.held['minecraft:quartz'],self.held['minecraft:cobblestone']),(0,0))
        book=json.loads((self.root/'local-rock-recipe.json').read_text());self.assertTrue(book['complete'])
        self.assertIsNone(book['pending']);self.assertEqual(book['warehouse_inventory_credit'],0)
        self.assertIsNone(self.backend.resource_pipeline_context)

    def test_insufficient_recorded_inputs_do_not_begin_or_invent_output(self):
        self.saved[0]['loose_counts']['minecraft:quartz']=1
        self.assertIsNone(self.go());self.backend.fetch.assert_not_called();self.backend.craft.assert_not_called()

    def test_offer_bounds_large_projection_deficit_by_existing_local_recipe_inputs(self):
        self.backend.root=self.root;self.backend.latest=self.client.status()
        with patch('local_rock_recipe.records',return_value=self.saved):
            self.assertEqual(offer(self.backend,'minecraft:diorite',35),6)
        self.assertFalse(self.held);self.backend.fetch.assert_not_called();self.backend.craft.assert_not_called()

    def test_unknown_craft_is_retained_and_never_replayed(self):
        self.backend.craft=Mock(return_value={'phase':'waiting'})
        with self.assertRaises(JobBlocked):self.go()
        self.assertEqual(json.loads((self.root/'local-rock-recipe.json').read_text())['pending'],'craft')
        with self.assertRaises(JobBlocked):self.go()
        self.backend.craft.assert_called_once();self.assertEqual(self.backend.fetch.call_count,2)


if __name__=='__main__':unittest.main()
