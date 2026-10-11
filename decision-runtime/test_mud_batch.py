import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from material_jobs.mud_batch import carried_visit_target,visit_cells
from material_jobs.engine import MaterialJob


class MudVisitTest(unittest.TestCase):
    def test_configured64_visit_makes_a_full_stack_without_exceeding_the_real_remaining_target(self):
        self.profile['mud_station']['cells_per_visit']=64
        self.assertEqual(66,self.offer());self.assertEqual(20,self.offer(20))
        self.request['flat_map']={'mud_cells_per_visit':32}
        self.assertEqual(34,self.offer())
        for bad in (0,3,65,128,True,16.0):
            self.request['flat_map']['mud_cells_per_visit']=bad
            with self.assertRaises(ValueError):visit_cells(self.request,self.profile)

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

    def test_full_named_foreign_world_and_item_jobs_do_not_offer(self):
        original=copy.deepcopy(self.state)
        for kind in ('full','named','world','item'):
            self.state=copy.deepcopy(original);self.request['mode']='projection'
            if kind=='full':
                for r in self.state['inventory'][2:]:r.update(item='minecraft:stone',count=64)
            elif kind=='named':self.state['inventory'][0]['name']='reserved'
            elif kind=='world':self.state['world_session']='other'
            else:self.request['mode']='item'
            self.assertIsNone(self.offer())

    def test_bottle_stack_uses_real_output_workspace_instead_of_disabling_bulk_visit(self):
        self.state['inventory'][1]['count']=3
        self.assertEqual(self.offer(),18)
        for r in self.state['inventory'][2:]:r.update(item='minecraft:stone',count=64)
        for r in self.state['inventory'][-3:]:r.update(item='minecraft:air',count=0)
        self.assertEqual(self.offer(),18)
        self.state['inventory'][-3].update(item='minecraft:stone',count=64)
        self.assertIsNone(self.offer())

    def test_crossing_output_stack_preserves_three_workspace_slots(self):
        self.state['inventory'][0]['count']=50
        for r in self.state['inventory'][2:]:r.update(item='minecraft:stone',count=64)
        for r in self.state['inventory'][-4:]:r.update(item='minecraft:air',count=0)
        self.assertEqual(self.offer(),66)
        self.state['inventory'][-4].update(item='minecraft:stone',count=64)
        self.assertIsNone(self.offer())
