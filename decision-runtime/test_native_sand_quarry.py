import unittest
import tempfile
from unittest.mock import patch
from native_sand_quarry import choose_quarry,recover_quarry_drops,preparation_target,select_region


def fixture():
    rows=[]
    for x in range(4):
        for z in range(4):
            rows.append({'pos':[x,64,z],'state':'Block{minecraft:stone}','solid':True})
            for y in range(65,69):
                rows.append({'pos':[x,y,z],'state':'Block{minecraft:sand}','solid':True})
    return rows


class NativeSandQuarryTest(unittest.TestCase):
    def test_empty_space_above_sand_does_not_force_a_high_climb(self):
        choice={'max':[3,68,3]}
        target=preparation_target([1.5,69,1.5],choice,fixture())
        self.assertEqual([1.5,71.25,1.5],target)
        self.assertIsNone(preparation_target([1.5,75,1.5],choice,fixture()))

    def test_local_obstacle_requires_only_its_clearance(self):
        rows=fixture()+[{'pos':[1,74,1],'state':'Block{minecraft:stone}','passable':False}]
        self.assertEqual(77.25,preparation_target([1.5,69,1.5],{'max':[3,68,3]},rows)[1])

    def test_model_only_receives_regions_with_verified_supported_sand(self):
        class Client:
            options=None
            def request(self,op,**params):
                return {'blocks':fixture() if params['min'][0]<0 else []}
            def status(self):return {'pos':[1,90,1],'inventory':[]}
            def advise(self,goal,options,scene):self.options=options;return {'id':'one','choice':'dry'}
        client=Client()
        with tempfile.TemporaryDirectory() as tmp:
            key,decision=select_region(client,{'dry':([0,65,0],[3,70,3]),'empty':([20,65,0],[23,70,3])},40,tmp)
        self.assertEqual('dry',key);self.assertEqual({'dry','wait'},set(client.options))

    def test_model_wait_does_not_begin_a_quarry(self):
        class Client:
            def request(self,op,**params):
                self.assert_scan(op);return {'blocks':fixture()}
            def assert_scan(self,op):
                if op!='scan':raise AssertionError('Advisor must not execute game actions')
            def status(self):return {'pos':[1,90,1],'inventory':[]}
            def advise(self,*args):return {'id':'one','choice':'wait'}
        with tempfile.TemporaryDirectory() as tmp:
            key,_=select_region(Client(),{'dry':([0,65,0],[3,70,3])},40,tmp)
        self.assertIsNone(key)

    def test_cleanup_only_picks_observed_sand_near_the_quarry(self):
        class Client:
            count=0
            def status(self):
                return {'health':20,'guard_armed':True,'under_water':False,'pos':[1,69,1],
                    'inventory':[{'slot':0,'item':'minecraft:sand','count':self.count}],
                    'entities':([{'uuid':'sand','type':'minecraft:item','pos':[1,69,1],
                                  'stack':{'item':'minecraft:sand','count':2}}] if not self.count else [])+
                               [{'uuid':'other','type':'minecraft:item','pos':[1,69,1],
                                 'stack':{'item':'minecraft:diamond','count':1}},
                                {'uuid':'far','type':'minecraft:item','pos':[20,69,20],
                                 'stack':{'item':'minecraft:sand','count':5}}]}
        client=Client()
        def pickup(*args,**kwargs):client.count=2;return True
        with patch('native_sand_quarry.collect_drop',side_effect=pickup) as action:
            result=recover_quarry_drops(client,[0,65,0],[3,70,3])
        self.assertEqual({'attempted':1,'recovered':2},result)
        self.assertEqual('sand',action.call_args.args[1]['uuid'])

    def test_finds_supported_sand_box_with_two_distinct_y_corners(self):
        choice=choose_quarry(fixture(),[0,65,0],[3,70,3],[1,90,1])
        self.assertEqual(64,choice['sand'])
        self.assertEqual([0,65,0],choice['min'])
        self.assertEqual([3,68,3],choice['max'])
        self.assertLess(choice['min'][1],choice['max'][1])
    def test_water_or_container_in_buffer_prevents_quarry(self):
        for obstacle in ({'pos':[4,66,1],'state':'Block{minecraft:water}','fluid':True},
                         {'pos':[1,69,1],'state':'Block{minecraft:chest}','block_entity':True}):
            self.assertIsNone(choose_quarry(fixture()+[obstacle],[0,65,0],[3,70,3],[1,90,1]))
    def test_does_not_include_foreign_solid_blocks_in_excavation(self):
        rows=fixture();rows.append({'pos':[1,66,1],'state':'Block{minecraft:stone}','solid':True})
        choice=choose_quarry(rows,[0,65,0],[3,70,3],[1,90,1])
        self.assertIsNotNone(choice)
        self.assertGreater(choice['min'][1],66)
