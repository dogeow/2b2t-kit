import copy
import tempfile
import unittest
from pathlib import Path
from survival_recovery import ensure_work_food

class Client:
    world='world';native_inflight=None
    def __init__(self):
        self.state={'world_session':'world','food':17,'health':20,'under_water':False,
                    'guard_armed':True,'manual_movement':False,'screen':'',
                    'inventory':[{'slot':7,'item':'minecraft:cooked_beef','count':4}]}
        self.calls=[];self.confirm=True;self.auto_before_use=False
    def status(self):return copy.deepcopy(self.state)
    def checked(self,op,**params):
        self.calls.append(op)
        if op=='select_item'and self.auto_before_use:self.state['food']=20
        if op=='use_item'and self.confirm:
            self.state['food']=20;self.state['inventory'][0]['count']-=1

class WorkFoodTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.out=Path(self.folder.name);self.c=Client()
    def test_food_count_and_actual_hunger_both_confirm_one_normal_use(self):
        result=ensure_work_food(self.c,self.out)
        self.assertEqual(['select_item','use_item'],self.c.calls)
        self.assertEqual(1,result['food_used']);self.assertEqual(20,result['food_after'])
    def test_full_reserve_and_auto_eat_before_use_do_not_eat_twice(self):
        self.c.state['food']=18;ensure_work_food(self.c,self.out);self.assertEqual([],self.c.calls)
        self.c.state['food']=17;self.c.auto_before_use=True
        result=ensure_work_food(self.c,self.out)
        self.assertEqual(['select_item'],self.c.calls);self.assertEqual(0,result['food_used'])
    def test_unknown_use_is_retained_and_not_repeated(self):
        self.c.confirm=False
        with self.assertRaisesRegex(RuntimeError,'not confirmed'):ensure_work_food(self.c,self.out)
        self.assertEqual(['select_item','use_item'],self.c.calls)
        self.assertIn('use_inflight',(self.out/'work-food-reserve.json').read_text())
        with self.assertRaisesRegex(RuntimeError,'Prior food'):ensure_work_food(self.c,self.out)
        self.assertEqual(['select_item','use_item'],self.c.calls)
    def test_underwater_or_pending_work_prevents_food_dispatch(self):
        self.c.state['under_water']=True
        with self.assertRaises(RuntimeError):ensure_work_food(self.c,self.out)
        self.assertEqual([],self.c.calls)
        self.c.state['under_water']=False;self.c.native_inflight={'request_id':'old'}
        with self.assertRaises(RuntimeError):ensure_work_food(self.c,self.out)
        self.assertEqual([],self.c.calls)

if __name__=='__main__':unittest.main()
