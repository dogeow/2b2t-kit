import copy,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from material_jobs import pointed_dripstone_pipeline as m
from material_jobs.protocol import JobBlocked


class PointedPipelineTests(unittest.TestCase):
    def site(self):return {'owned':True,'server':'s','dimension':'minecraft:overworld','minimum_y':61,
        'air_bounds':{'min':[0,61,0],'max':[19,123,22]},'approach':[5.5,120.,5.5],'exit':[5.5,120.,5.5],
        'joined_columns':[{'root':[5,70,6],'stand_column':[5,5]}],'growth_roots':[[5,70,6]]}
    def setup_client(self,root,held=6):
        state={'world_session':'w','server':'s','dimension':'minecraft:overworld','health':20,'food':20,
               'guard_armed':True,'guard_pve_only':True,'guard_busy':False,'under_water':False,'manual_movement':False,
               'projection_selection':{'key':'house'},'pos':[5.5,74.2,5.5],
               'inventory':[{'slot':0,'item':m.ITEM,'count':held}],'entities':[]}
        profile={'renewable_pointed_dripstone':self.site()}
        c=SimpleNamespace(world='w',root=root,status=lambda:copy.deepcopy(state),checked=Mock())
        backend=SimpleNamespace(client=c,profile=profile,request={'mode':'item','targets':{m.ITEM:8},'context':{'world_session':'w'}})
        c.pointed_backend=backend;return c,profile,state
    def test_owned_site_rejects_foreign_duplicate_or_unbounded_configuration(self):
        current={'server':'s','dimension':'minecraft:overworld'}
        for change in ({'owned':False},{'server':'other'}, {'growth_roots':[[5,70,6],[5,70,6]]},
                       {'air_bounds':{'min':[0,0,0],'max':[100,319,100]}}, {'joined_columns':[None]}):
            with self.subTest(change=change),self.assertRaises(JobBlocked):
                m.farm({'renewable_pointed_dripstone':{**self.site(),**change}},current)
    def test_same_native_client_can_fall_back_to_two_current_downward_segments(self):
        with tempfile.TemporaryDirectory()as d:
            c,p,state=self.setup_client(Path(d));calls=[]
            def gather(client,roots,minimum,out,checkpoint,**kwargs):
                self.assertIs(c,client);self.assertEqual(2,kwargs['max_segments']);calls.append(roots)
                state['inventory'][0]['count']=8;return {'actual_gained':2}
            with patch.object(m,'column',side_effect=JobBlocked('not joined')),patch.object(m,'_scan',return_value=[]),\
                 patch.object(m,'growth_column',return_value={'chain':[{}, {}, {}]}),patch.object(m,'harvest',side_effect=gather),\
                 patch.object(m,'_travel')as travel,patch.object(m,'exit_farm'),\
                 patch.object(m,'settled_state',side_effect=lambda c:c.status()):
                result=m.run(c,p,m.ITEM,8,Path(d)/'run',lambda:None)
            self.assertEqual('done',result['phase']);self.assertEqual(8,result['actual_held']);self.assertEqual(1,len(calls))
            travel.assert_not_called();self.assertEqual(2,result['downward_actual_gain'])
    def test_invalid_mode_cannot_move_or_create_an_operation_journal(self):
        with tempfile.TemporaryDirectory()as d:
            c,p,state=self.setup_client(Path(d));c.pointed_backend.request['mode']='projection'
            with patch.object(m,'exit_farm')as exit_route,patch.object(m,'_travel')as travel,self.assertRaises(JobBlocked):
                m.run(c,p,m.ITEM,8,Path(d)/'run',lambda:None)
            exit_route.assert_not_called();travel.assert_not_called();self.assertFalse((Path(d)/'run').exists())
    def test_carried_goal_needs_no_travel_or_harvest(self):
        with tempfile.TemporaryDirectory()as d:
            c,p,state=self.setup_client(Path(d),held=8)
            with patch.object(m,'harvest')as gather,patch.object(m,'exit_farm')as exit_route:
                result=m.run(c,p,m.ITEM,8,Path(d)/'run',lambda:None)
            self.assertEqual('done',result['phase']);gather.assert_not_called();exit_route.assert_not_called()
