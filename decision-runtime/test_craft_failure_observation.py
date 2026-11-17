import copy
import unittest
from craft_failure_observation import settled


class CraftFailureObservationTest(unittest.TestCase):
    def setUp(self):
        self.command={'action':'manufacture'}
        self.error={'error':'Inventory acknowledgement missing at ingredient_pickup; no action replay','last_request':'r','native_inflight':None,'unconfirmed_native_request':None}
        items=[{'item':'minecraft:iron_block','count':4,'slot':8},{'item':'minecraft:iron_ingot','count':22,'slot':5}]
        empty=[{'item':'minecraft:air','count':0,'slot':i} for i in range(5)]
        self.failure={'detail':self.error['error'],'owned_inventory_crafting':{'world_session':'w','task_session':'t','menu_id':0},'observed':{'world_session':'w','menu_id':0,'cursor':{'count':0},'grid':empty,'inventory':items}}
        self.event={'request_id':'r','op':'slot_click','phase':'done','world_session':'w','params':{'task_session':'t'},'inventory_delta':{},'revision_before':7,'revision_after':7}
        self.first={'time':1,'world_session':'w','connected':True,'health':20,'manual_movement':False,'screen':'','menu':{'type':'InventoryMenu','cursor':{'count':0},'slots':empty},'inventory':items,'supervision_lease':{'job_session':'t'},'last_request':'r','control_revision':7}
        self.second=copy.deepcopy(self.first);self.second['time']=2

    def check(self):
        return settled(self.command,self.error,self.failure,self.event,self.first,self.second,'w','t')

    def test_allows_only_stable_empty_readback(self):
        self.assertTrue(self.check())
        for mutation in ('cursor','grid','inventory','time','manual','event'):
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation=='cursor':self.second['menu']['cursor']['count']=1
                if mutation=='grid':self.second['menu']['slots'][1]['count']=1
                if mutation=='inventory':self.second['inventory'][0]['count']=3
                if mutation=='time':self.second['time']=1
                if mutation=='manual':self.second['manual_movement']=True
                if mutation=='event':self.event['phase']='waiting'
                self.assertFalse(self.check())

    def test_separately_quarantines_only_unrelated_missing_item(self):
        self.failure['recipe']={'ingredients':{'minecraft:iron_block':[1]},'output':'minecraft:iron_ingot'}
        self.failure['observed']['time']=100
        self.failure['observed']['inventory'].append({'item':'minecraft:lantern','count':1,'slot':9})
        self.first['inventory']=copy.deepcopy(self.failure['observed']['inventory'][:-1])
        self.second['inventory']=copy.deepcopy(self.first['inventory'])
        self.first['game_interaction']={'last_interaction_at':101}
        args=(self.command,self.error,self.failure,self.event,self.first,self.second,'w','t')
        self.assertFalse(settled(*args))
        self.assertTrue(settled(*args,{'minecraft:lantern':1}))
        self.assertFalse(settled(*args,{'minecraft:iron_block':1}))
        self.first['game_interaction']['last_interaction_at']=100
        self.assertFalse(settled(*args,{'minecraft:lantern':1}))


if __name__=='__main__':unittest.main()
