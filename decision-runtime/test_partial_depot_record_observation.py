import copy, unittest
from partial_depot_record_observation import observable


class Tests(unittest.TestCase):
    def fixture(self):
        inv=lambda n:[{'slot':0,'item':'minecraft:oak_planks','count':n}]
        cmd={'action':'exchange','positions':[[1,64,0],[2,64,0],[3,64,0]],'withdraw':{'minecraft:oak_planks':6}}
        err={'error':'Storage position has no current scoped Kit record','native_inflight':None,'unconfirmed_native_request':None,'last_request':'close'}
        baseline={'phase':'done','world_session':'w','time':100,'inventory':inv(0)}
        visits=[{'pos':[1,64,0],'at_ms':101,'before':{},'after':{'minecraft:oak_planks':3}}, {'pos':[2,64,0],'at_ms':102,'before':{'minecraft:oak_planks':3},'after':{'minecraft:oak_planks':5}}]
        state={'last_request':'close','world_session':'w','time':104,'inventory':inv(5),'health':20,'pos':[2.5,65,0],'control_revision':7,'connected':True,'manual_movement':False,'screen':'','menu':{'type':'InventoryMenu','cursor':{'count':0}},'movement_keys':{}}
        event={'request_id':'close','world_session':'w','op':'close_menu','phase':'done','inventory_delta':{},'params':{'task_session':'t'},'revision_before':7,'revision_after':7,'position_before':state['pos'],'position_after':state['pos'],'health_before':20,'health_after':20}
        return cmd,err,baseline,visits,event,state
    def test_two_real_transfers_are_retained_without_completing_or_replaying_exchange(self):
        self.assertTrue(observable(*self.fixture(),'w','t'))
    def test_unknown_input_foreign_route_changed_stock_or_unclosed_menu_is_retained(self):
        for mode in ('unknown','route','chain','loss','stock','menu','world','event','time'):
            a=copy.deepcopy(self.fixture())
            if mode=='unknown':a[1]['native_inflight']={'id':'pending'}
            elif mode=='route':a[3][1]['pos']=[9,64,0]
            elif mode=='chain':a[3][1]['before']['minecraft:oak_planks']=4
            elif mode=='loss':a[3][1]['after']['minecraft:oak_planks']=2
            elif mode=='stock':a[5]['inventory'][0]['count']=6
            elif mode=='menu':a[5]['screen']='ContainerScreen'
            elif mode=='world':a[4]['world_session']='other'
            elif mode=='event':a[4]['inventory_delta']={'minecraft:emerald':1}
            else:a[3][1]['at_ms']=99
            with self.subTest(mode=mode):self.assertFalse(observable(*a,'w','t'))


if __name__=='__main__':unittest.main()
