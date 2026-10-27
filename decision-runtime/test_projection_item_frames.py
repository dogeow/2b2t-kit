import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from projection_item_frames import place,geometry

class FrameTest(unittest.TestCase):
    def expected(self):return {'type':'minecraft:item_frame','pos':[10.5,72.5,20.03125],'facing':3,'invisible':False,'item_rotation':4,'item':{'id':'minecraft:white_banner','count':1,'patterns':[]}}
    def client(self,uncertain=False):
        e=self.expected()
        class C:
            world='world';last='';actual=None;stamp=0;uses=0;stock=Counter({'minecraft:item_frame':2,'minecraft:white_banner':2})
            def status(self):return {'stock':self.stock,'projection_selection':{'key':'key','min':[0,60,0],'max':[30,90,30]},'entities':[]if self.actual is None else [{**self.actual,'id':7}]}
            def request(self,op,**kw):
                self.stamp+=1
                return {'projection_audit':{'placement_key':'key','loaded_chunks_verified':True,'observed_at':self.stamp,'decorations':[]if self.actual is None else [self.actual.copy()]}}
            def checked(self,op,**kw):
                self.last=op
                if op=='interact':self.stock['minecraft:item_frame']-=1;self.actual={**e,'uuid':'new','item_rotation':0,'item':{'id':'minecraft:air','count':0}}
                elif op=='interact_entity':
                    self.uses+=1
                    if not self.actual['item']['count']:self.stock['minecraft:white_banner']-=1;self.actual={**self.actual,'item':e['item']}
                    else:self.actual={**self.actual,'item_rotation':self.actual['item_rotation']+1}
                    if uncertain:raise RuntimeError('unknown receipt')
                return {'phase':'done'}
        return C()
    def run_frame(self,c):
        with TemporaryDirectory()as d,patch('projection_item_frames.inventory_counts',lambda s:s['stock']),patch('projection_item_frames.cell_at',return_value={'solid':True,'fluid':False,'block_entity':False,'state':'Block{minecraft:white_concrete}'}),patch('projection_item_frames.approach_faces'):
            return place(c,self.expected(),Path(d)/'frame',c.status)
    def test_support_and_pose_are_on_original_visible_side(self):
        anchor,face,pose=geometry(self.expected());self.assertEqual([10,72,19],anchor);self.assertEqual('south',face);self.assertEqual([10.5,71.3,22.03125],pose)
    def test_place_insert_and_four_acknowledged_rotations(self):
        c=self.client();r=self.run_frame(c);self.assertTrue(r['complete']);self.assertEqual(5,c.uses);self.assertEqual(4,r['actual']['item_rotation']);self.assertEqual(1,c.stock['minecraft:item_frame']);self.assertEqual(1,c.stock['minecraft:white_banner'])
    def test_unknown_insertion_never_replayed_or_followed_by_rotation(self):
        c=self.client(True)
        with self.assertRaisesRegex(RuntimeError,'unknown receipt'):self.run_frame(c)
        self.assertEqual(1,c.uses)
