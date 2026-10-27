import copy
import unittest
from unstarted_feeding_enclosure import observable, DETAIL


class Tests(unittest.TestCase):
    def fixture(self):
        command={'action':'feed_village_founders','min':[1,64,2],'max':[4,67,5],'quotas':{'v':3}}
        error={'error':DETAIL,'type':'RuntimeError','native_inflight':None,'unconfirmed_native_request':None,'last_request':'s'}
        book={'complete':False,'pending':None,'pending_food':None,'receipts':[],'required':{'v':3},'delivered':{'v':0},'error':"RuntimeError('"+DETAIL+"')",'world_session':'w'}
        event={'world_session':'w','request_id':'s','op':'scan','phase':'done','params':{'min':[1,63,2],'max':[4,67,5],'details':True,'task_session':'t'},'inventory_delta':{},'position_before':[2,65,3],'position_after':[2,65,3],'revision_before':7,'revision_after':7,'health_before':20,'health_after':20}
        state={'world_session':'w','last_request':'s','phase':'done','supervision_lease':{'job_session':'t','kind':'materials','world_session':'w'},'pos':[2,65,3],'control_revision':7,'health':20,'inventory':[{'slot':1,'item':'minecraft:bread','count':3}],'connected':True,'manual_movement':False,'screen':'','menu':{'cursor':{'count':0}},'movement_keys':{'forward':False}}
        return command,error,book,event,state,'w','t'

    def test_exact_geometry_refusal_admits_read_only_observation(self):
        self.assertTrue(observable(*self.fixture()))

    def test_any_food_intent_receipt_or_debit_remains_fenced(self):
        for mode in ('intent','food','receipt','credit','debit','unknown'):
            a=copy.deepcopy(self.fixture())
            if mode=='intent':a[2]['pending']={'op':'villager_bread_drop'}
            elif mode=='food':a[2]['pending_food']={'target':'v'}
            elif mode=='receipt':a[2]['receipts']=[{'id':'drop'}]
            elif mode=='credit':a[2]['delivered']['v']=1
            elif mode=='debit':a[4]['inventory'][0]['count']=2
            else:a[1]['unconfirmed_native_request']='drop'
            with self.subTest(mode=mode):self.assertFalse(observable(*a))

    def test_changed_bounds_owner_or_position_cannot_settle_original(self):
        for mode in ('bounds','owner','position','operation'):
            a=copy.deepcopy(self.fixture())
            if mode=='bounds':a[3]['params']['max']=[5,67,5]
            elif mode=='owner':a[4]['supervision_lease']['job_session']='other'
            elif mode=='position':a[4]['pos']=[3,65,3]
            else:a[3]['op']='villager_bread_drop'
            with self.subTest(mode=mode):self.assertFalse(observable(*a))


if __name__=='__main__':unittest.main()
