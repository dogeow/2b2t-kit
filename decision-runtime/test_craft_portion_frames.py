import copy
import unittest
from unittest.mock import patch
import craft_grid


def scene(time,source,cursor):
    slots=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(46)]
    slots[10]={'slot':10,'item':'minecraft:dark_oak_planks'if source else'minecraft:air','count':source,'max_stack':64}
    return {'phase':'done','time':time,'menu':{'id':6,'type':'CraftingMenu','slots':slots,
            'cursor':{'item':'minecraft:dark_oak_planks'if cursor else'minecraft:air','count':cursor,'max_stack':64}}}


class PortionFramesTests(unittest.TestCase):
    def test_lagging_source_count_never_becomes_the_next_click_precondition(self):
        class Client:
            def __init__(self):
                self.calls=[]
                self.replies=iter([scene(1,5,6),scene(4,5,5),scene(7,6,4)])
                self.frames=iter([scene(2,5,6),scene(3,5,6),scene(5,6,5),scene(6,6,5),scene(8,7,4),scene(9,7,4)])
            def request(self,op,**params):self.calls.append((op,params));return next(self.replies)
            def status(self):return next(self.frames)
        client=Client();initial=scene(0,11,0)
        with patch.object(craft_grid,'k',client),patch('kit_runtime.inventory.time.sleep'):
            result=craft_grid.take_portion(initial,copy.deepcopy(initial['menu']['slots'][10]),4)
        self.assertEqual(result['menu']['cursor']['count'],4)
        self.assertEqual(result['menu']['slots'][10]['count'],7)
        self.assertEqual([p['expected_count']for _,p in client.calls],[11,5,6])
        self.assertEqual(len(client.calls),3)

    def test_unknown_pickup_is_not_retried(self):
        class Client:
            calls=0
            def request(self,*args,**kwargs):self.calls+=1;raise RuntimeError('unknown original pickup')
        client=Client();initial=scene(0,11,0)
        with patch.object(craft_grid,'k',client),self.assertRaisesRegex(RuntimeError,'unknown original'):
            craft_grid.take_portion(initial,initial['menu']['slots'][10],4)
        self.assertEqual(client.calls,1)
