import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from stack_recipe import plan_batch,settled_result,execute
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
