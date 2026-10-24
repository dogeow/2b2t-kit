import unittest
import copy,json,tempfile
from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace
from material_stack_consolidation import offer,run_inventory,prepare_fetch


class ConsolidationTest(unittest.TestCase):
    def test_full_bag_fragments_need_partial_moves_before_two_slots_can_be_freed(self):
        from test_inventory_session import Client
        with tempfile.TemporaryDirectory()as tmp:
            c=Client();c.state['menu'].update(id=0,type='InventoryMenu')
            c.state['menu']['slots']=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(46)]
            for r in c.state['menu']['slots'][9:45]:r.update(item='minecraft:stone',count=64)
            for slot,count in zip(range(9,14),(44,24,39,39,46)):c.state['menu']['slots'][slot].update(item='minecraft:cobblestone',count=count)
            def status():
                c.state['time']=c.state.get('time',0)+1
                c.state['inventory']=[{**r,'slot':i}for i,r in enumerate(c.state['menu']['slots'][9:45])]
                return copy.deepcopy(c.state)
            c.status=status;original=c.checked
            def checked(*args,**kwargs):original(*args,**kwargs);return status()
            c.checked=checked
            @contextmanager
            def action(name):yield c,Path(tmp)
            result=run_inventory(SimpleNamespace(ensure_client=lambda:c,action=action),'minecraft:cobblestone',2)
            self.assertEqual(2,result['free_slots']);self.assertEqual(0,result['depot_visits'])
            final=status();self.assertEqual([64,64,64],sorted(r['count']for r in final['inventory']if r['item']=='minecraft:cobblestone'))
            self.assertEqual(31*64,sum(r['count']for r in final['inventory']if r['item']=='minecraft:stone'))
            self.assertEqual(0,final['menu']['cursor']['count'])
            book=json.loads((Path(tmp)/'inventory-merge.json').read_text());self.assertTrue(book['complete']);self.assertTrue(any(r['amount']<r['source']['count']for r in book['moves']))
    def test_bottles_merge_in_backpack_without_depot_and_preserve_every_material(self):
        from test_inventory_session import Client
        with tempfile.TemporaryDirectory()as tmp:
            c=Client();c.state['menu'].update(id=0,type='InventoryMenu')
            c.state['menu']['slots']=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(46)]
            for r in c.state['menu']['slots'][9:45]:r.update(item='minecraft:stone',count=64)
            for i in (26,27,28):c.state['menu']['slots'][i].update(item='minecraft:glass_bottle',count=1)
            for i in (35,36):c.state['menu']['slots'][i].update(item='minecraft:air',count=0)
            def status():
                c.state['time']=c.state.get('time',0)+1
                c.state['inventory']=[{**r,'slot':i}for i,r in enumerate(c.state['menu']['slots'][9:45])]
                return copy.deepcopy(c.state)
            c.status=status;original=c.checked
            def checked(*args,**kwargs):original(*args,**kwargs);return status()
            c.checked=checked
            @contextmanager
            def action(name):yield c,Path(tmp)
            backend=SimpleNamespace(ensure_client=lambda:c,action=action)
            before={r['item']:sum(x['count']for x in status()['inventory']if x['item']==r['item'])for r in status()['inventory']}
            result=run_inventory(backend,'minecraft:glass_bottle',4)
            self.assertEqual(4,result['free_slots']);self.assertEqual(0,result['depot_visits'])
            self.assertEqual(4,len(c.calls));self.assertTrue(all(x['kind']=='pickup'for x in c.calls))
            self.assertEqual(0,c.state['menu']['cursor']['count'])
            for item,count in before.items():self.assertEqual(count,sum(r['count']for r in status()['inventory']if r['item']==item))
            book=json.loads((Path(tmp)/'inventory-merge.json').read_text());self.assertTrue(book['complete']);self.assertIsNone(book['pending'])
    def test_fragmented_plain_target_preserves_total_and_frees_two_real_slots(self):
        rows=[{'slot':i,'item':'minecraft:stone','count':64,'max_stack':64}for i in range(36)]
        for i in (2,5,9):rows[i].update(item='minecraft:mud_bricks',count=2)
        rows[-1].update(item='minecraft:air',count=0)
        state={'inventory':rows}
        self.assertEqual(offer(state,'minecraft:mud_bricks',3),{'total':6,'before_stacks':3,'freed_slots':2})
        rows[2]['custom_name']='protected'
        self.assertIsNone(offer(state,'minecraft:mud_bricks',3))

    def test_already_sufficient_workspace_or_full_stacks_do_not_visit_depot(self):
        rows=[{'slot':i,'item':'minecraft:stone','count':64,'max_stack':64}for i in range(36)]
        rows[2].update(item='minecraft:mud_bricks',count=64);rows[5].update(item='minecraft:mud_bricks',count=64)
        rows[-1].update(item='minecraft:air',count=0)
        self.assertIsNone(offer({'inventory':rows},'minecraft:mud_bricks',3))
        for r in rows[-3:]:r.update(item='minecraft:air',count=0)
        self.assertIsNone(offer({'inventory':rows},'minecraft:mud_bricks',3))

    def test_fetch_workspace_merges_multiple_plain_types_without_a_second_client_or_depot(self):
        from test_inventory_session import Client
        with tempfile.TemporaryDirectory()as tmp:
            c=Client();c.out=Path(tmp);c.state['screen']='';c.state['menu'].update(id=0,type='InventoryMenu')
            c.state['menu']['slots']=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(46)]
            for r in c.state['menu']['slots'][9:45]:r.update(item='minecraft:stone',count=64)
            for slot,item,count in[(9,'minecraft:oak_log',11),(10,'minecraft:oak_log',21),(11,'minecraft:emerald',1),(12,'minecraft:emerald',24)]:c.state['menu']['slots'][slot].update(item=item,count=count)
            def status():
                c.state['time']=c.state.get('time',0)+1;c.state['inventory']=[{**r,'slot':i}for i,r in enumerate(c.state['menu']['slots'][9:45])];return copy.deepcopy(c.state)
            c.status=status;original=c.checked
            def checked(*args,**kwargs):original(*args,**kwargs);return status()
            c.checked=checked
            result=prepare_fetch(c,['minecraft:iron_block'])
            self.assertEqual(2,result['free_slots']);self.assertEqual(0,result['depot_visits']);self.assertEqual(2,len(result['merges']))
            final=status();self.assertEqual(32,sum(r['count']for r in final['inventory']if r['item']=='minecraft:oak_log'));self.assertEqual(25,sum(r['count']for r in final['inventory']if r['item']=='minecraft:emerald'));self.assertEqual(0,final['menu']['cursor']['count'])


if __name__=='__main__':unittest.main()
