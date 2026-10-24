from copy import deepcopy
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from anvil_enchant_combine import run
from anvil_enchant_preview import menu_slot,enchantments
from test_anvil_enchant_preview import Client,book,seed,empty


class CombineClient(Client):
    def __init__(self,*args,fail_output=False,**kwargs):
        super().__init__(*args,**kwargs);self.fail_output=fail_output
        self.inventory[0]={**book('minecraft:efficiency',5),'slot':0}
    def sync(self):
        super().sync()
        if self.menu and self.menu['slots'][0]['count'] and self.menu['slots'][1]['count']:
            left,right=self.menu['slots'][:2]
            output={**deepcopy(left),'slot':2}
            output['stored_enchantments']=[{'id':k,'level':v}for k,v in {**enchantments(left),**enchantments(right)}.items()]
            self.menu['slots'][2]=output if self.cost<40 else empty(2)
    def checked(self,op,**params):
        if op=='slot_click'and params['slot']==2:
            self.calls.append((op,deepcopy(params)))
            if self.fail_output:raise RuntimeError('output acknowledgement unknown')
            self.sync();slots=self.menu['slots']
            destination=next(r['slot']for r in slots[3:]if not r['count'])
            slots[destination]={**deepcopy(slots[2]),'slot':destination}
            slots[0]=empty(0);slots[1]=empty(1);slots[2]=empty(2);self.level-=self.cost
            return self.status()|{'id':'output-r'}
        result=super().checked(op,**params)
        return (result or {})|{'id':'r-'+str(len(self.calls))}


class CombineTests(unittest.TestCase):
    def invoke(self,client,out,cost=2):
        return run(client,[1,2,3],0,1,book('minecraft:efficiency',5),book(),
                   {'minecraft:efficiency':5,'minecraft:mending':1},cost,out)
    def test_one_exact_book_merge_spends_only_the_previewed_cost_and_conserves_inventory(self):
        with tempfile.TemporaryDirectory()as d,patch('anvil_enchant_preview.time.sleep'):
            c=CombineClient(d,cost=2);result=self.invoke(c,Path(d)/'merge')
            self.assertTrue(result['complete']);self.assertEqual(c.level,28);self.assertIsNone(c.menu)
            outputs=[p for op,p in c.calls if op=='slot_click'and p['slot']==2]
            self.assertEqual(len(outputs),1);self.assertEqual(outputs[0]['kind'],'quick_move')
            self.assertEqual(result['experience_levels_spent'],2)
            self.assertTrue(result['visible_inventory_conserved'])
    def test_unknown_output_is_never_repeated_or_closed(self):
        with tempfile.TemporaryDirectory()as d,patch('anvil_enchant_preview.time.sleep'):
            c=CombineClient(d,cost=2,fail_output=True)
            with self.assertRaisesRegex(RuntimeError,'unknown'):self.invoke(c,Path(d)/'merge')
            self.assertEqual(len([1 for op,p in c.calls if op=='slot_click'and p['slot']==2]),1)
            self.assertFalse(any(op=='close_menu'for op,p in c.calls));self.assertEqual(c.level,30)
    def test_cost_mismatch_never_takes_output(self):
        with tempfile.TemporaryDirectory()as d,patch('anvil_enchant_preview.time.sleep'),patch('anvil_enchant_preview.time.monotonic',side_effect=itertools.count(step=.1)):
            c=CombineClient(d,cost=3)
            with self.assertRaisesRegex(RuntimeError,'unconfirmed'):self.invoke(c,Path(d)/'merge',cost=2)
            self.assertFalse(any(op=='slot_click'and p['slot']==2 for op,p in c.calls));self.assertEqual(c.level,30)
    def test_unaffordable_or_illegal_plans_send_no_input(self):
        for cost in (31,40,True):
            with self.subTest(cost=cost),tempfile.TemporaryDirectory()as d:
                c=CombineClient(d)
                with self.assertRaises(ValueError):self.invoke(c,Path(d)/'merge',cost=cost)
                self.assertEqual(c.calls,[])


if __name__=='__main__':unittest.main()
