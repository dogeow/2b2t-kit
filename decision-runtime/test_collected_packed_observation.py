from copy import deepcopy
import unittest
from collected_packed_observation import observable,DETAIL
from test_anvil_enchant_preview import book


def fixture():
    target=book();item='minecraft:shulker_box';w='w';t='t'
    c={'action':'take_packed_equipment','box_slot':14,'expected_stack':target}
    error={'error':DETAIL,'native_inflight':None,'unconfirmed_native_request':None,'last_request':'scan'}
    record={'stage':'broken','world_session':w,'slot':14,'item':item,'initial_counts':{'minecraft:enchanted_book':2},
            'remaining_counts':{'minecraft:enchanted_book':1},'taken':{'minecraft:enchanted_book':1},'drop_uuid':'drop',
            'source':{'slot':14,'item':item,'count':1,'counts':{'minecraft:enchanted_book':2}},
            'ownership_preflight':{'world_session':w,'cursor_clean':True,'inventory':[]},
            'exact_stacks':{'minecraft:enchanted_book':target}}
    event={'op':'scan','phase':'done','world_session':w,'params':{'task_session':t},'request_id':'scan',
           'position_before':[1,64,2],'position_after':[1,64,2],'revision_before':3,'revision_after':3,
           'inventory_delta':{},'health_before':20,'health_after':20}
    reply={'id':'scan','phase':'done','world_session':w,'pos':[1,64,2],'control_revision':3}
    state={'connected':True,'world_session':w,'health':20,'manual_movement':False,'screen':'','pos':[1,64,2],
           'last_request':'scan','control_revision':3,'movement_keys':{},'entities':[],
           'menu':{'id':0,'type':'InventoryMenu','cursor':{'count':0}},
           'inventory':[{**deepcopy(target),'slot':5},{'item':item,'slot':13,'count':1,'contains':[book()]}]}
    return deepcopy([c,error,record,event,reply,state])


class CollectedPackedTests(unittest.TestCase):
    def test_observation_requires_exact_conserved_box_and_settled_original_native_terminal(self):
        self.assertTrue(observable(*fixture(),'w','t'))
        for change in ('unknown','remaining','book','delta','revision','world','drop','extra_box','pending'):
            c,error,record,event,reply,state=fixture()
            if change=='unknown':error['unconfirmed_native_request']='native'
            elif change=='remaining':state['inventory'][1]['contains']=[]
            elif change=='book':state['inventory'][0]['stored_enchantments'][0]['id']='minecraft:silk_touch'
            elif change=='delta':event['inventory_delta']={'minecraft:shulker_box':1}
            elif change=='revision':state['control_revision']=4
            elif change=='world':reply['world_session']='other'
            elif change=='drop':state['entities']=[{'uuid':'drop'}]
            elif change=='extra_box':state['inventory'].append({'slot':14,'item':'minecraft:shulker_box','count':1,'contains':[]})
            elif change=='pending':state['navigating']=True
            with self.subTest(change=change):self.assertFalse(observable(c,error,record,event,reply,state,'w','t'))


if __name__=='__main__':unittest.main()
