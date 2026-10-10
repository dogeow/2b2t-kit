import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from material_jobs.mud_batch import carried_visit_target
from material_jobs.engine import MaterialJob


class MudVisitTest(unittest.TestCase):
    def setUp(self):
        self.request={'mode':'projection','context':{'world_session':'w'}}
        self.profile={'mud_station':{'authorized':True},'mud_bucket_source':{'authorized':True}}
        self.state={'world_session':'w','bottle_water_protocol':1,'inventory':[
            {'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(36)]}
        self.state['inventory'][0].update(item='minecraft:mud_bricks',count=2)
        self.state['inventory'][1].update(item='minecraft:glass_bottle',count=1)

    def offer(self,final=690):return carried_visit_target(self.request,self.profile,self.state,'minecraft:mud_bricks',final)

    def test_real16_cell_visit_stays_bounded_by_actual_remaining_target(self):
        before=copy.deepcopy(self.state)
        self.assertEqual(18,self.offer());self.assertEqual(5,self.offer(5))
        self.assertEqual(before,self.state)

    def test_scheduler_uses_real_leaf_workspace_instead_of_full_recipe_peak(self):
        job=MaterialJob.__new__(MaterialJob);job.request=self.request
        job.backend=SimpleNamespace(profile=self.profile);job.snapshot=self.state
        job._plan=Mock(side_effect=AssertionError('full recipe peak is not this bounded worker'))
        self.assertEqual(18,job._fit_batch('minecraft:mud_bricks',690))
        self.assertEqual(5,job._fit_batch('minecraft:mud_bricks',5));job._plan.assert_not_called()

    def test_full_named_stacked_bottle_foreign_world_and_item_jobs_do_not_offer(self):
        original=copy.deepcopy(self.state)
        for kind in ('full','named','bottles','world','item'):
            self.state=copy.deepcopy(original);self.request['mode']='projection'
            if kind=='full':
                for r in self.state['inventory'][2:]:r.update(item='minecraft:stone',count=64)
            elif kind=='named':self.state['inventory'][0]['name']='reserved'
            elif kind=='bottles':self.state['inventory'][1]['count']=2
            elif kind=='world':self.state['world_session']='other'
            else:self.request['mode']='item'
            self.assertIsNone(self.offer())
