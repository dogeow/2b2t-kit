from copy import deepcopy
from types import SimpleNamespace
import unittest
from recipe_catalog import Recipe
from projection_smelting_batch import offer


class CarriedSmeltingBatchTest(unittest.TestCase):
    def fixture(self,raw=68,output=2):
        deep='minecraft:deepslate';source='minecraft:cobbled_deepslate'
        rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1}for i in range(43)]
        rows[0]={'slot':0,'item':deep,'count':output,'max_stack':64}
        for slot in (1,2):
            count=min(raw,64);raw-=count
            if count:rows[slot]={'slot':slot,'item':source,'count':count,'max_stack':64}
        recipe=Recipe('smelting/deepslate',deep,1,3,((1,(source,)),),'minecraft:smelting')
        backend=SimpleNamespace(request={'mode':'projection','flat_map':{'schema':1}},
            latest={'inventory':rows},profile={'minimum_projection_trip_stack':64,'furnace_positions':[[1,64,1],[2,64,1]]},
            catalog=SimpleNamespace(recipes={deep:[recipe]},smelting={recipe.id:{'cooking_ticks_per_recipe':200}}))
        return backend,deep

    def test_68_carried_inputs_offer_70_total_instead_of_fetching_for_130(self):
        backend,item=self.fixture()
        self.assertEqual(70,offer(backend,item,181))

    def test_whole_stack_or_exact_tail_preserves_trip_policy(self):
        backend,item=self.fixture(raw=32)
        self.assertIsNone(offer(backend,item,181))
        self.assertEqual(22,offer(backend,item,22))
        backend,item=self.fixture(raw=128)
        self.assertEqual(130,offer(backend,item,181))

    def test_incomplete_metadata_packed_and_offhand_stock_do_not_offer_raw_credit(self):
        original,item=self.fixture()
        for change in ('incomplete','named','offhand','item_mode','no_bank','invalid_trip'):
            backend=deepcopy(original)
            if change=='incomplete':backend.latest['inventory'].pop()
            if change=='named':backend.latest['inventory'][1]['custom_name']='keep'
            if change=='offhand':backend.latest['inventory'][1],backend.latest['inventory'][40]=backend.latest['inventory'][40],backend.latest['inventory'][1];backend.latest['inventory'][1]['slot']=1;backend.latest['inventory'][40]['slot']=40
            if change=='item_mode':backend.request['mode']='item'
            if change=='no_bank':backend.profile['furnace_positions']=[]
            if change=='invalid_trip':backend.profile['minimum_projection_trip_stack']=True
            self.assertIsNone(offer(backend,item,181),change)

if __name__=='__main__':unittest.main()
