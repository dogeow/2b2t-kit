import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from stack_recipe import plan_batch,settled_result,execute,supported,DYE_RECIPES
from craft_grid import InventoryCapacity


def fixture(contents,empty=0):
    slots=[{'slot':i,'item':'minecraft:air','count':0} for i in range(10)]
    values=list(contents)+[('air',0)]*empty
    values += [('diamond_sword',1)]*(36-len(values))
    for i,(item,amount) in enumerate(values):slots.append({'slot':i+10,'item':'minecraft:'+item,'count':amount,'max_stack':64})
    return snapshot(slots)


def snapshot(slots):
    return {'menu':{'id':3,'type':'CraftingMenu','cursor':{'item':'minecraft:air','count':0},'slots':slots},
            'inventory':[{**v,'slot':i} for i,v in enumerate(slots[10:])]}

SPEC={'recipe_id':'white_concrete_powder','output':'minecraft:white_concrete_powder','produces':8,
      'ingredients':{'minecraft:sand':[1,2,3,4],'minecraft:gravel':[5,6,7,8],'minecraft:white_dye':[9]}}

class StackRecipeTest(unittest.TestCase):
    def test_furnishing_batches_preserve_real_input_and_output_counts(self):
        specs=[
          ({'recipe_id':'book','output':'minecraft:book','produces':1,'width':3,
            'ingredients':{'minecraft:paper':[1,2,4],'minecraft:leather':[5]}},
           [('paper',64),('paper',10),('leather',24)],21),
          ({'recipe_id':'bookshelf','output':'minecraft:bookshelf','produces':1,'width':3,
            'ingredients':{'minecraft:oak_planks':[1,2,3,7,8,9],'minecraft:book':[4,5,6]}},
           [('oak_planks',48),('book',24)],8),
          ({'recipe_id':'flower_pot','output':'minecraft:flower_pot','produces':1,'width':3,
            'ingredients':{'minecraft:brick':[1,3,5]}},[('brick',30)],10)]
        for spec,contents,rounds in specs:
            self.assertTrue(supported(spec));before=fixture(contents,empty=2)
            batch=plan_batch(before,spec,24 if spec['output']=='minecraft:book'else rounds)
            self.assertEqual(rounds,batch['rounds'])
            after=copy.deepcopy(before)
            used={item:rounds*len(cells)for item,cells in spec['ingredients'].items()}
            for row in after['menu']['slots'][10:]:
                take=min(row['count'],used.get(row['item'],0));used[row['item']]=used.get(row['item'],0)-take;row['count']-=take
                if not row['count']:row['item']='minecraft:air'
            empty=next(r for r in after['menu']['slots'][10:]if not r['count']);empty.update(item=spec['output'],count=rounds)
            after=snapshot(after['menu']['slots'])
            self.assertTrue(settled_result(before,after,spec,batch))
            empty['count']-=1;after=snapshot(after['menu']['slots'])
            self.assertFalse(settled_result(before,after,spec,batch))

    def test_furnishing_allowlist_rejects_other_shapes_remainders_and_wrong_counts(self):
        spec={'recipe_id':'book','output':'minecraft:book','produces':1,'width':2,
              'ingredients':{'minecraft:paper':[1,2,3],'minecraft:leather':[4]}}
        self.assertTrue(supported(spec))
        for change in ({'recipe_id':'custom_book'},{'produces':True},{'produces':2},{'width':True},
                       {'ingredients':{'minecraft:paper':[1,2],'minecraft:leather':[3]}},
                       {'ingredients':{'minecraft:paper':[1,2,3],'minecraft:milk_bucket':[4]}}):
            self.assertFalse(supported({**spec,**change}))
        shelf={'recipe_id':'bookshelf','output':'minecraft:bookshelf','produces':1,'width':3,
               'ingredients':{'minecraft:oak_planks':[1,2,3],'minecraft:spruce_planks':[7,8,9],'minecraft:book':[4,5,6]}}
        self.assertTrue(supported(shelf));self.assertFalse(supported({**shelf,'width':2}))
        self.assertFalse(supported({**shelf,'ingredients':{'minecraft:stone':[1,2,3,7,8,9],'minecraft:book':[4,5,6]}}))

    def test_dye_allowlist_requires_exact_recipe_output_inputs_and_normalized_cells(self):
        for recipe_id,(color,produces,inputs) in DYE_RECIPES.items():
            for width in (2,3):
                ingredients={}
                for i,item in enumerate(inputs):
                    ingredients.setdefault('minecraft:'+item,[]).append((i//2)*width+i%2+1)
                spec={'recipe_id':recipe_id,'output':f'minecraft:{color}_dye','produces':produces,
                      'width':width,'ingredients':ingredients}
                self.assertTrue(supported(spec),(recipe_id,width))
                for change in ({'recipe_id':'unknown_dye_recipe'},{'produces':produces+1},
                               {'produces':True},{'width':True},{'width':1},
                               {'ingredients':{**ingredients,'minecraft:water_bucket':[4]}}):
                    self.assertFalse(supported({**spec,**change}),(recipe_id,change))
                wrong=copy.deepcopy(ingredients);first=next(iter(wrong));wrong[first][0]=True
                self.assertFalse(supported({**spec,'ingredients':wrong}))
        self.assertFalse(supported({'recipe_id':'black_dye','output':'minecraft:gray_dye',
                                    'produces':1,'width':2,'ingredients':{'minecraft:ink_sac':[1]}}))

    def test_gray_dye_batch_preserves_exact_black_white_consumption(self):
        spec={'recipe_id':'gray_dye','output':'minecraft:gray_dye','produces':2,'width':3,
              'ingredients':{'minecraft:black_dye':[1],'minecraft:white_dye':[2]}}
        before=fixture([('black_dye',9),('white_dye',10)],empty=2)
        batch=plan_batch(before,spec,8)
        self.assertEqual((8,16),(batch['rounds'],batch['produced']))
        after=fixture([('black_dye',1),('white_dye',2),('gray_dye',16)],empty=1)
        self.assertTrue(settled_result(before,after,spec,batch))
        after['inventory'][1]['count']=3
        self.assertFalse(settled_result(before,after,spec,batch))

    def test_colored_powder_batch_keeps_color_exact_grid_and_material_conservation(self):
        spec={'output':'minecraft:black_concrete_powder','produces':8,'width':3,
              'ingredients':{'minecraft:sand':[2,3,4,5],'minecraft:gravel':[6,7,8,9],'minecraft:black_dye':[1]}}
        self.assertTrue(supported(spec))
        before=fixture([('sand',32)]*4+[('gravel',32)]*4+[('black_dye',32)])
        batch=plan_batch(before,spec,32);self.assertEqual((32,256),(batch['rounds'],batch['produced']))
        after=fixture([('black_concrete_powder',64)]*4,empty=5)
        self.assertTrue(settled_result(before,after,spec,batch))
        after['inventory'][0].update(item='minecraft:sand',count=32)
        self.assertFalse(settled_result(before,after,spec,batch))
        for change in ({'produces':4},{'width':2},
                       {'ingredients':{**spec['ingredients'],'minecraft:black_dye':[True]}},
                       {'ingredients':{'minecraft:sand':[1,2,3,4],'minecraft:gravel':[5,6,7,8],'minecraft:red_dye':[9]}},
                       {'ingredients':{**spec['ingredients'],'minecraft:gravel':[6,7,8,8]}},
                       {'ingredients':{**spec['ingredients'],'minecraft:water_bucket':[9]}}):
            self.assertFalse(supported({**spec,**change}))
    def test_colored_terracotta_batch_uses_eight_plain_blocks_and_matching_center_dye(self):
        spec={'output':'minecraft:green_terracotta','produces':8,'width':3,
              'ingredients':{'minecraft:terracotta':[1,2,3,4,6,7,8,9],'minecraft:green_dye':[5]}}
        self.assertTrue(supported(spec))
        batch=plan_batch(fixture([('terracotta',32)]*8+[('green_dye',32)]),spec,32)
        self.assertEqual(256,batch['produced'])
        for change in ({'produces':1},{'width':2},
                       {'ingredients':{'minecraft:terracotta':[1,2,3,4,5,7,8,9],'minecraft:green_dye':[6]}},
                       {'ingredients':{'minecraft:terracotta':[1,2,3,4,6,7,8,9],'minecraft:blue_dye':[5]}}):
            self.assertFalse(supported({**spec,**change}))

    def test_acacia_and_dark_oak_planks_batch_exact_species_and_consumption(self):
        for species in ('acacia','dark_oak'):
            raw='minecraft:'+species+'_log';output='minecraft:'+species+'_planks'
            spec={'output':output,'produces':4,'width':3,'ingredients':{raw:[1]}}
            self.assertTrue(supported(spec))
            before=fixture([(species+'_log',64)],empty=3)
            batch=plan_batch(before,spec,32)
            self.assertEqual((32,128,1),(batch['rounds'],batch['produced'],len(batch['actions'])))
            after=fixture([(species+'_log',32),(species+'_planks',64),(species+'_planks',64)],empty=1)
            self.assertTrue(settled_result(before,after,spec,batch))
            after['inventory'][0]['count']=64
            self.assertFalse(settled_result(before,after,spec,batch))
            for change in ({'produces':1},{'produces':True},{'width':1},
                           {'ingredients':{'minecraft:oak_log':[1]}},
                           {'ingredients':{raw:[True]}},
                           {'ingredients':{raw:[1,2]}},
                           {'ingredients':{raw:[1],'minecraft:water_bucket':[2]}}):
                self.assertFalse(supported({**spec,**change}))

    def test_coarse_dirt_batch_requires_exact_four_output_and_two_of_each_input(self):
        spec={'output':'minecraft:coarse_dirt','produces':4,'width':2,
              'ingredients':{'minecraft:dirt':[1,4],'minecraft:gravel':[2,3]}}
        self.assertTrue(supported(spec))
        for change in ({'produces':1},{'width':1},
                {'ingredients':{'minecraft:dirt':[1],'minecraft:gravel':[2,3]}},
                {'ingredients':{'minecraft:dirt':[1,2],'minecraft:gravel':[2,3]}}):
            self.assertFalse(supported({**spec,**change}))
    def test_mud_bulk_allowlist_requires_exact_no_remainder_inputs_and_outputs(self):
        packed={'output':'minecraft:packed_mud','produces':1,'width':2,
                'ingredients':{'minecraft:mud':[1],'minecraft:wheat':[2]}}
        self.assertTrue(supported(packed))
        for change in ({'produces':2},{'width':1},
                       {'ingredients':{'minecraft:mud':[1],'minecraft:water_bucket':[2]}},
                       {'ingredients':{'minecraft:mud':[1],'minecraft:wheat':[1]}}):
            self.assertFalse(supported({**packed,**change}))
        bricks={'output':'minecraft:mud_bricks','produces':4,'width':2,
                'ingredients':{'minecraft:packed_mud':[1,2,3,4]}}
        self.assertTrue(supported(bricks));self.assertTrue(supported({**bricks,'width':3,'ingredients':{'minecraft:packed_mud':[1,2,4,5]}}))
        self.assertFalse(supported({**bricks,'produces':1}))
        self.assertFalse(supported({**bricks,'ingredients':{'minecraft:mud':[1,2,3,4]}}))
    def test_wood_bulk_allowlist_requires_the_exact_no_remainder_four_to_three_recipe(self):
        good={'output':'minecraft:cherry_wood','produces':3,'width':2,
              'ingredients':{'minecraft:cherry_log':[1,2,3,4]}}
        self.assertTrue(supported(good))
        self.assertTrue(supported({**good,'width':3,'ingredients':{'minecraft:cherry_log':[1,2,4,5]}}))
        for changes in ({'produces':4},{'width':None},
                        {'ingredients':{'minecraft:cherry_log':[1,2,3,3]}},
                        {'ingredients':{'minecraft:oak_log':[1,2,3,4]}},
                        {'output':'minecraft:stripped_cherry_wood'}):
            self.assertFalse(supported({**good,**changes}))

    def test_inputs_moved_to_grid_create_required_output_capacity(self):
        s=fixture([('sand',32)]*4+[('gravel',32)]*4+[('white_dye',32)])
        p=plan_batch(s,SPEC,32)
        self.assertEqual(256,p['produced']);self.assertEqual(9,len(p['actions']))
    def test_half_stack_sources_are_reused_with_exact_expected_counts(self):
        s=fixture([('sand',64)]*2+[('gravel',64)]*2+[('white_dye',32)],empty=2)
        p=plan_batch(s,SPEC,32)
        self.assertEqual(32,p['rounds']);self.assertEqual([64,32,64,32],[a['source_count'] for a in p['actions'][:4]])
    def test_does_not_assume_partial_input_stack_releases_slot(self):
        s=fixture([('sand',63)]*4+[('gravel',63)]*4+[('white_dye',63)])
        with self.assertRaises(InventoryCapacity):plan_batch(s,SPEC,32)
    def test_stone_block_recipe_spans_partial_stacks_without_losing_remainders(self):
        spec={'output':'minecraft:polished_andesite','produces':4,'ingredients':{'minecraft:andesite':[1,2,4,5]}}
        p=plan_batch(fixture([('andesite',64),('andesite',64),('andesite',8)],empty=4),spec,34)
        self.assertEqual(32,p['rounds']);self.assertEqual(128,p['produced'])
        self.assertEqual(128,sum(a['count'] for a in p['actions']))
    def test_furnace_hollow_center_stays_empty(self):
        spec={'output':'minecraft:furnace','produces':1,'ingredients':{'minecraft:cobblestone':[1,2,3,4,6,7,8,9]}}
        p=plan_batch(fixture([('cobblestone',64)]*3+[('cobblestone',12)],empty=4),spec,17)
        self.assertEqual(17,p['produced']);self.assertNotIn(5,[a['cell'] for a in p['actions']])
    def test_duplicate_grid_cells_rejected_without_mutation(self):
        s=fixture([],empty=36);before=copy.deepcopy(s)
        with self.assertRaises(ValueError):plan_batch(s,{**SPEC,'ingredients':{'minecraft:sand':[1,1]}})
        self.assertEqual(before,s)
    def test_output_without_matching_input_consumption_is_not_completion(self):
        before=fixture([('sand',32)]*4+[('gravel',32)]*4+[('white_dye',32)],empty=4)
        after=copy.deepcopy(before);after['inventory'][-1].update(item=SPEC['output'],count=64)
        self.assertFalse(settled_result(before,after,SPEC,{'produced':64,'rounds':8}))
    def test_delayed_output_receipt_never_replays_the_quick_move(self):
        spec={'recipe_id':'white_dye','output':'minecraft:white_dye','produces':1,'ingredients':{'minecraft:bone_meal':[1]}}
        before=fixture([('bone_meal',32)],empty=1);placed=copy.deepcopy(before)
        placed['menu']['slots'][10].update(item='minecraft:air',count=0)
        placed['menu']['slots'][1].update(item='minecraft:bone_meal',count=32)
        placed['menu']['slots'][0].update(item=spec['output'],count=1)
        final=copy.deepcopy(before);final['menu']['slots'][10].update(item=spec['output'],count=32);final=snapshot(final['menu']['slots'])
        with tempfile.TemporaryDirectory() as tmp:
            class Client:
                out=Path(tmp);calls=0
                def status(self):self.calls+=1;return before if self.calls==1 else final
            clicks=[]
            def click(state,slot,kind='pickup'):
                clicks.append((slot,kind));return placed
            with patch('stack_recipe.InventorySession.place_cell',return_value=placed),patch('stack_recipe.InventorySession.click',side_effect=click),patch('stack_recipe.InventorySession.wait_grid',return_value=placed),patch('stack_recipe.InventorySession.wait_recipe',return_value=placed),patch('stack_recipe.time.sleep'):
                r=execute(Client(),spec,32)
            self.assertEqual(32,r['inventory'][0]['count']);self.assertEqual(1,clicks.count((0,'quick_move')))

if __name__=='__main__':unittest.main()

class SmallCellTest(unittest.TestCase):
    def test_one_item_uses_three_clicks_and_restores_source_stack(self):
        from stack_recipe import place_cell
        import craft_grid,craft_recipe
        initial=fixture([('cobblestone',64)],empty=2);state=copy.deepcopy(initial);calls=[]
        class Client:
            def status(self):return state
            def checked(self,op,**args):return self.request(op,**args)
            def request(self,op,**args):
                calls.append(args);slot=state['menu']['slots'][args['slot']];cursor=state['menu']['cursor']
                if args.get('button',0)==1:
                    slot['item']=cursor['item'];slot['count']+=1;cursor['count']-=1
                else:
                    slot['item'],cursor['item']=cursor['item'],slot['item'];slot['count'],cursor['count']=cursor['count'],slot['count']
                state['phase']='done';return state
        c=Client()
        with patch.object(craft_grid,'k',c),patch.object(craft_recipe,'k',c):result=place_cell(c,state,copy.deepcopy(state['menu']['slots'][10]),1,1)
        self.assertEqual(3,len(calls));self.assertEqual(1,result['menu']['slots'][1]['count']);self.assertEqual(63,result['menu']['slots'][10]['count']);self.assertEqual(0,result['menu']['cursor']['count'])

class GoldenAppleBatchTest(unittest.TestCase):
    def test_sixteen_apples_use_exactly_128_gold_in_one_bounded_workbench_batch(self):
        state=fixture([('gold_ingot',64),('gold_ingot',64),('apple',16)],empty=2)
        spec={'output':'minecraft:golden_apple','produces':1,'width':3,
              'ingredients':{'minecraft:gold_ingot':[1,2,3,4,6,7,8,9],'minecraft:apple':[5]}}
        before=copy.deepcopy(state)
        batch=plan_batch(state,spec,32)
        self.assertEqual((16,16),(batch['rounds'],batch['produced']))
        self.assertEqual(128,sum(a['count']for a in batch['actions']if a['item']=='minecraft:gold_ingot'))
        self.assertEqual(16,sum(a['count']for a in batch['actions']if a['item']=='minecraft:apple'))
        self.assertEqual(before,state)
