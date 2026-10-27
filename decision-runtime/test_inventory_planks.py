from pathlib import Path
import json
import tempfile
import unittest
from inventory_planks import craft_one


class InventoryPlankTests(unittest.TestCase):
    def state(self):
        slots=[{'slot':i,'item':'minecraft:air','count':0}for i in range(46)]
        slots[9]={'slot':9,'item':'minecraft:dark_oak_log','count':17}
        return {'inventory':[{'slot':0,'item':'minecraft:dark_oak_log','count':17}],
                'menu':{'type':'InventoryMenu','id':0,'slots':slots,'cursor':{'item':'minecraft:air','count':0}}}
    def test_foreign_cursor_never_starts_a_click(self):
        with tempfile.TemporaryDirectory()as d:
            s=self.state();s['menu']['cursor']={'item':'minecraft:diamond','count':1}
            class Queue:
                world='w'
                def native(self,*args,**kwargs):raise AssertionError('no input authorized')
            p=Path(d)/'proof.json'
            with self.assertRaises(RuntimeError):craft_one(Queue(),lambda:s,p)
            self.assertFalse(p.exists())
    def test_unknown_click_is_retained_and_never_replayed(self):
        with tempfile.TemporaryDirectory()as d:
            s=self.state();calls=[]
            class Queue:
                world='w'
                def native(self,op,**params):calls.append(op);raise RuntimeError('unknown original receipt')
            p=Path(d)/'proof.json'
            with self.assertRaisesRegex(RuntimeError,'unknown original'):craft_one(Queue(),lambda:s,p)
            self.assertEqual(calls,['slot_click']);book=json.loads(p.read_text())
            self.assertFalse(book['complete']);self.assertIsNotNone(book['pending'])


if __name__=='__main__':unittest.main()
