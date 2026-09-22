"""Exercise real crafting orchestration against a tiny, stateful vanilla-slot model."""
import tempfile
import unittest
from survival import Runner
from survival_bridge import Paused,inventory

def stack(name='air',n=0):return {'item':'minecraft:'+name,'count':n}

class Slots:
    def __init__(self,items):
        self.root='test';self.world='Trial';self.origin=[0,1,0];self.calls=0;self.grid=2
        self.slots=[stack() for _ in range(46)];self.cursor=stack()
        for i,(name,n) in enumerate(items.items(),9):self.slots[i]=stack(name,n)
        self.state=self.read()
    def read(self):
        self.state={'inventory':[s.copy() for s in self.slots[9:45]],'menu':{'id':0,'type':'InventoryMenu','cursor':self.cursor.copy(),
                   'slots':[dict(s,slot=i) for i,s in enumerate(self.slots)]}}
        return self.state
    def close(self):pass
    def click(self,i,kind='pickup',button=0):
        self.calls+=1
        if i==0 and kind=='quick_move':
            out=self.slots[0].copy()
            for target in range(9,45):
                if self.slots[target]['count']==0 or self.slots[target]['item']==out['item']:
                    self.slots[target]={'item':out['item'],'count':self.slots[target]['count']+out['count']};break
            for j in range(1,5):
                if self.slots[j]['count']:
                    self.slots[j]['count']-=1
                    if not self.slots[j]['count']:self.slots[j]=stack()
        elif button==1:
            assert self.cursor['count']>0 and self.slots[i]['count']==0
            self.slots[i]={'item':self.cursor['item'],'count':1};self.cursor['count']-=1
            if not self.cursor['count']:self.cursor=stack()
        else:
            self.cursor,self.slots[i]=self.slots[i],self.cursor
        cells=[self.slots[j]['item'].removeprefix('minecraft:') if self.slots[j]['count'] else 'air' for j in range(1,5)]
        self.slots[0]=stack()
        if cells==['oak_log','air','air','air']:self.slots[0]=stack('oak_planks',4)
        elif cells==['oak_planks']*4:self.slots[0]=stack('crafting_table',1)
        elif cells==['oak_planks','air','oak_planks','air']:self.slots[0]=stack('stick',4)
        return self.read()

class CraftingTests(unittest.TestCase):
    def test_logs_become_table_without_losing_remainder_or_cursor_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Slots({'oak_log':3});r=Runner(b,None,tmp)
            plank=r.planks(8)
            r.craft('crafting_table',{(0,0):plank,(0,1):plank,(1,0):plank,(1,1):plank},2)
            self.assertEqual(inventory(b.read()),{'oak_log':1,'oak_planks':4,'crafting_table':1})
            self.assertEqual(b.cursor['count'],0)
            self.assertTrue(all(s['count']==0 for s in b.slots[1:5]))
    def test_wrong_recipe_output_stops_and_preserves_ingredients(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Slots({'oak_log':2});r=Runner(b,None,tmp)
            with self.assertRaisesRegex(Paused,'输出不符'):r.craft('diamond',{(0,0):'oak_log'},2)
            self.assertEqual(b.slots[1]['item'],'minecraft:oak_log')
            self.assertEqual(sum(s['count'] for s in b.slots[1:] if s['item']=='minecraft:oak_log'),2)
    def test_occupied_grid_and_insufficient_materials_do_not_click(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Slots({'oak_planks':1});r=Runner(b,None,tmp)
            with self.assertRaises(Paused):r.craft('stick',{(0,0):'oak_planks',(1,0):'oak_planks'},2)
            self.assertEqual(b.calls,0)
            b.slots[1]=stack('diamond',1)
            with self.assertRaises(Paused):r.craft('oak_planks',{(0,0):'oak_log'},2)
            self.assertEqual(b.calls,0)

if __name__=='__main__':unittest.main()
