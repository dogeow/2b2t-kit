import copy,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from equipment_swap import equip


class ArmorExchangeTest(unittest.TestCase):
    def client(self,unknown=False):
        empty={'item':'minecraft:air','count':0,'max_stack':1};rows=[{'slot':i,**empty}for i in range(46)]
        rows[8].update(item='minecraft:netherite_boots',count=1,max_stack=1,durability=470,enchantments=[{'id':'minecraft:protection','level':4}]);rows[12].update(item='minecraft:golden_boots',count=1,max_stack=1,durability=91)
        state={'time':1,'world_session':'w','control_revision':1,'health':20,'guard_armed':True,
            'supervision_lease':{'kind':'materials','job_session':'j','world_session':'w','revision':1},
            'menu':{'type':'InventoryMenu','id':0,'cursor':copy.deepcopy(empty),'slots':rows}}
        calls=[]
        def status():state['time']+=1;return copy.deepcopy(state)
        def checked(op,**kw):
            calls.append((op,kw))
            if unknown:raise RuntimeError('unknown original click')
            i=kw['slot'];row=state['menu']['slots'][i];cursor=state['menu']['cursor'];state['menu']['slots'][i]={'slot':i,**cursor};state['menu']['cursor']={k:v for k,v in row.items()if k!='slot'};return status()
        c=SimpleNamespace(world='w',task='j',status=status,checked=checked);return c,state,calls
    def test_original_enchanted_boots_are_preserved_on_swap_and_exact_restoration(self):
        c,state,calls=self.client();old=copy.deepcopy(state['menu']['slots'][8])
        with tempfile.TemporaryDirectory()as d,patch('kit_runtime.inventory.time.sleep'):
            first=equip(c,8,'minecraft:golden_boots',Path(d)/'wear',c.status)
            self.assertEqual('minecraft:golden_boots',state['menu']['slots'][8]['item']);self.assertEqual(old['enchantments'],state['menu']['slots'][12]['enchantments'])
            second=equip(c,8,'minecraft:netherite_boots',Path(d)/'restore',c.status,expected_source=first['original_armor'])
        self.assertTrue(second['complete']);self.assertEqual(old,state['menu']['slots'][8]);self.assertEqual(6,len(calls))
    def test_unknown_click_never_attempts_another_click_or_cleanup(self):
        c,state,calls=self.client(True)
        with tempfile.TemporaryDirectory()as d,patch('kit_runtime.inventory.time.sleep'),self.assertRaisesRegex(RuntimeError,'unknown'):
            equip(c,8,'minecraft:golden_boots',Path(d)/'unknown',c.status)
        self.assertEqual(1,len(calls));self.assertEqual('minecraft:netherite_boots',state['menu']['slots'][8]['item'])
