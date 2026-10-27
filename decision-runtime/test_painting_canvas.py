import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from painting_canvas import sides,restore


class OriginalCanvasTest(unittest.TestCase):
    def test_spacers_are_outside_original_three_by_three_canvas(self):
        p={'pos':[761014.5,68.5,797833.03125],'width':3,'height':3,'facing':3}
        self.assertEqual([[761012,68,797833],[761016,68,797833]],sides(p))
        self.assertTrue(all(x<761013 or x>761015 for x,y,z in sides(p)))

    def test_completed_slow_pickup_is_confirmed_before_old_deadline(self):
        class Client:
            world='world';last='';stock=0;removed=False
            def status(self):
                return {'stock':self.stock,'entities':[] if self.stock else [
                    {'type':'minecraft:item','pos':[.5,.5,.5],
                     'stack':{'item':'minecraft:spruce_planks','count':1}}]}
            def checked(self,op,**kw):
                if op=='mine_block':self.removed=True
                self.last=op;return {'phase':'done'}
        c=Client();book={'pending':None,'world_session':'world','placed':[[0,0,0]],'inventory_before':1}
        clock=[0]
        def pickup(*a,**kw):
            c.stock=1;clock[0]=8;return True
        with TemporaryDirectory() as d,patch('painting_canvas.inventory_counts',lambda s:Counter({'minecraft:spruce_planks':s['stock']})),patch('painting_canvas.cell_at',lambda *_:{'state':'Block{minecraft:air}'if c.removed else 'Block{minecraft:spruce_planks}'}),patch('painting_canvas.collect_drop',side_effect=pickup),patch('painting_canvas.time.monotonic',side_effect=lambda:clock[0]):
            result=restore(c,book,Path(d),c.status)
        self.assertTrue(result['restored'])
        self.assertEqual([[0,0,0]],result['recovered'])
        self.assertIsNone(result['pending'])
