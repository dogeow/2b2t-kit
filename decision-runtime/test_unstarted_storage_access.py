import unittest, copy
from unstarted_storage_access import observable


class Tests(unittest.TestCase):
    def fixture(self):
        inventory=[{'slot':0,'item':'minecraft:emerald','count':6}]
        c={'action':'exchange'}
        error={'error':'High house storage has no registered same-level return to the door exit','type':'StockBlocked','native_inflight':None,'unconfirmed_native_request':None,'last_request':'move'}
        baseline={'phase':'done','world_session':'w','inventory':inventory,'control_revision':1}
        base={'phase':'done','world_session':'w','health_before':20,'health_after':20,'revision_before':1,'revision_after':1,'inventory_delta':{},'params':{'task_session':'t'}}
        clicks=[]
        for slot,cursor,delta in ((14,'minecraft:air',-1),(12,'minecraft:emerald',1)):
            e=copy.deepcopy(base);e.update(op='slot_click',inventory_delta={'minecraft:emerald':delta});e['params'].update(menu_id=0,slot=slot,kind='pickup',button=0,expected_item='minecraft:emerald',expected_count=1 if slot==14 else 5,expected_cursor=cursor,expected_cursor_count=0 if slot==14 else 1);clicks.append(e)
        move=copy.deepcopy(base);move.update(op='navigate',request_id='move',position_after=[4,95,2],revision_after=2)
        state={'world_session':'w','connected':True,'health':20,'manual_movement':False,'screen':'','inventory':inventory,'menu':{'type':'InventoryMenu','id':0,'cursor':{'count':0}},'movement_keys':{},'control_revision':2,'last_request':'move','pos':[4,95,2]}
        return c,error,baseline,clicks+[move],state
    def test_completed_guarded_main_inventory_merge_and_movement_are_observable(self):
        self.assertTrue(observable(*self.fixture(),'w','t'))
    def test_container_use_unknown_click_or_changed_stock_never_qualifies(self):
        for mode in ('interact','container','drop','unguarded','unconfirmed','delta','cursor','stock','revision'):
            a=copy.deepcopy(self.fixture())
            if mode=='interact':a[3][-1]['op']='interact'
            elif mode=='container':a[3][0]['params']['menu_id']=4
            elif mode=='drop':a[3][0]['params']['slot']=-999
            elif mode=='unguarded':del a[3][0]['params']['expected_cursor']
            elif mode=='unconfirmed':a[3][0]['phase']='waiting'
            elif mode=='delta':a[3][1]['inventory_delta']={}
            elif mode=='cursor':a[4]['menu']['cursor']['count']=1
            elif mode=='stock':a[4]['inventory']=[{'slot':0,'item':'minecraft:emerald','count':7}]
            else:a[4]['control_revision']=3
            with self.subTest(mode=mode):self.assertFalse(observable(*a,'w','t'))


if __name__=='__main__':unittest.main()
