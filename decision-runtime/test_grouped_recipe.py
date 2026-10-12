import copy
import unittest
from unittest.mock import patch
from stack_recipe import plan_batch
from test_stack_recipe import fixture
from kit_runtime.inventory import InventorySession

SPEC={'recipe_id':'black_concrete_powder','output':'minecraft:black_concrete_powder','produces':8,'width':3,
      'ingredients':{'minecraft:sand':[2,3,4,5],'minecraft:gravel':[6,7,8,9],'minecraft:black_dye':[1]}}

class Client:
    def __init__(self,state):self.state=copy.deepcopy(state);self.calls=[];self.clock=1
    def status(self):
        self.clock+=1;self.state['time']=self.clock
        return copy.deepcopy(self.state)
    def checked(self,op,**args):
        self.calls.append((op,args));menu=self.state['menu'];cursor=menu['cursor']
        if op=='distribute':
            assert cursor['count']==args['expected_cursor_count'] and cursor['item']==args['expected_cursor']
            amount=cursor['count']//len(args['slots'])
            for cell in args['slots']:menu['slots'][cell].update(item=cursor['item'],count=amount)
            cursor.update(item='minecraft:air',count=0)
        else:
            row=menu['slots'][args['slot']];assert row['item']==args['expected_item'] and row['count']==args['expected_count']
            if not cursor['count']:
                amount=(row['count']+1)//2 if args.get('button')==1 else row['count']
                cursor.update(item=row['item'],count=amount);row['count']-=amount
                if not row['count']:row['item']='minecraft:air'
            else:
                assert not row['count'];row.update(item=cursor['item'],count=cursor['count']);cursor.update(item='minecraft:air',count=0)
        return self.status()

class GroupedRecipeTest(unittest.TestCase):
    def test_exact_64_stacks_make_128_powder_with_two_group_distribution_commands(self):
        state=fixture([('sand',64),('gravel',64),('black_dye',16)],empty=4)
        plan=plan_batch(state,SPEC,16);self.assertEqual(128,plan['produced']);self.assertEqual(3,len(plan['actions']))
        c=Client(state);session=InventorySession(c)
        with patch('kit_runtime.inventory.time.sleep'):
            for action in plan['actions']:
                cells=action['cells'];source=c.status()['menu']['slots'][action['source']]
                if len(cells)>1:session.distribute_exact(c.status(),source,cells,action['count'])
                else:session.place_cell(c.status(),source,cells[0],action['count'])
        self.assertEqual(6,len(c.calls));self.assertEqual(2,sum(op=='distribute'for op,_ in c.calls))
        self.assertEqual([16]*9,[r['count']for r in c.status()['menu']['slots'][1:10]])
        self.assertEqual(0,c.status()['menu']['cursor']['count'])
    def test_partial_40_and_24_stacks_choose_exact_group_without_ingredient_return_loop(self):
        plan=plan_batch(fixture([('sand',24),('sand',40),('gravel',24),('gravel',40),('black_dye',16)],empty=4),SPEC,16)
        self.assertEqual(10,plan['rounds']);self.assertEqual(3,len(plan['actions']))
        self.assertEqual([40,40],[a['source_count']for a in plan['actions'] if len(a['cells'])>1])
    def test_half_stack_preserves_the_other_half(self):
        c=Client(fixture([('sand',64)],empty=4));session=InventorySession(c)
        with patch('kit_runtime.inventory.time.sleep'):
            result=session.distribute_exact(c.status(),c.status()['menu']['slots'][10],[1,2,3,4],8)
        self.assertEqual(32,result['menu']['slots'][10]['count']);self.assertEqual([8]*4,[r['count']for r in result['menu']['slots'][1:5]])
    def test_predicted_group_then_server_correction_never_replays_distribution(self):
        class Correction(Client):
            def status(self):
                state=super().status()
                if any(op=='distribute'for op,_ in self.calls):state['menu']['slots'][1]['count']=15
                return state
        c=Correction(fixture([('sand',64)],empty=4));session=InventorySession(c)
        with patch('kit_runtime.inventory.time.sleep'),patch('kit_runtime.inventory.time.monotonic',side_effect=[0,0,0,0,10]):
            with self.assertRaisesRegex(RuntimeError,'acknowledgement missing'):
                session.distribute_exact(c.status(),c.status()['menu']['slots'][10],[1,2,3,4],16)
        self.assertEqual(1,sum(op=='distribute'for op,_ in c.calls))
    def test_invalid_occupied_duplicate_and_non_exact_group_never_click(self):
        for cells,amount in (([1,1],16),([True,2],16),([1,2,3,4],10)):
            c=Client(fixture([('sand',64)],empty=4))
            with self.assertRaises(ValueError):InventorySession(c).distribute_exact(c.status(),c.status()['menu']['slots'][10],cells,amount)
            self.assertEqual([],c.calls)

if __name__=='__main__':unittest.main()
