from copy import deepcopy
import unittest
from storage_quick_refusal import observable


class RefusalTests(unittest.TestCase):
    def fixture(self):
        c={'action':'transfer','item':'minecraft:iron_ingot','target':256}
        e={'error':'Slot item changed','native_inflight':None,'unconfirmed_native_request':None,'last_request':'r'}
        before={'world_session':'w','inventory':[],'menu':{'id':4}}
        inv=[{'slot':5,'item':'minecraft:iron_ingot','count':64,'max_stack':64},{'slot':27,'item':'minecraft:iron_ingot','count':2,'max_stack':64}]
        event={'op':'slot_click','params':{'kind':'quick_move','button':0,'expected_item':'minecraft:iron_ingot','expected_count':2,'expected_cursor':'minecraft:air','expected_cursor_count':0,'menu_id':4,'slot':0,'task_session':'t'},'phase':'error','detail':'Slot item changed','request_id':'r','world_session':'w','position_before':[1,71.2,2],'position_after':[1,71.2,2],'revision_before':3,'revision_after':3,'health_before':20,'health_after':20,'inventory_delta':{'minecraft:iron_ingot':1}}
        reply={'id':'r','phase':'error','detail':'Slot item changed','world_session':'w','pos':[1,71.2,2],'control_revision':3,'inventory':deepcopy(inv)}
        state={'connected':True,'health':20,'manual_movement':False,'screen':'ContainerScreen','menu':{'type':'ChestMenu','id':4,'cursor':{'count':0},'slots':[{}for _ in range(63)]},'inventory':inv,'movement_keys':{},'world_session':'w','last_request':'r','pos':[1,71.2,2],'control_revision':3}
        return c,e,before,event,reply,state
    def test_late_prior_transfer_is_reconciled_without_replaying_refused_click(self):
        self.assertTrue(observable(*self.fixture(),'w','t'))
        for change in ('unknown','cursor','unsettled','extra','task','deposit','target'):
            c,e,b,event,r,s=self.fixture()
            if change=='unknown':e['unconfirmed_native_request']='r'
            elif change=='cursor':s['menu']['cursor']['count']=1
            elif change=='unsettled':r['inventory'][1]['count']=1
            elif change=='extra':s['inventory'].append({'slot':9,'item':'minecraft:diamond','count':1,'max_stack':64})
            elif change=='task':event['params']['task_session']='other'
            elif change=='deposit':c['deposit']=True
            elif change=='target':c['target']=64
            with self.subTest(change=change):self.assertFalse(observable(c,e,b,event,r,s,'w','t'))


if __name__=='__main__':unittest.main()
