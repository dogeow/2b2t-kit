from copy import deepcopy
import unittest
from anvil_preview_recovery import returnable
from test_anvil_preview_refusal import fixture
from anvil_enchant_preview import menu_slot


def partial():
    c,err,b,e,r,s=fixture();mid=62
    err['error']='Original preview/input observation unconfirmed; no click replay'
    b.update(pending={'stage':'place_input','source':menu_slot(c['left_slot']),'cell':0},
             menu_id=mid,level_before=30,lease_id='lease',control_revision=3)
    slots=[dict(slot=i,item='minecraft:air',count=0)for i in range(39)]
    slots[0]={**c['expected_left'],'slot':0}
    slots[menu_slot(c['right_slot'])]={**deepcopy(c['expected_right']),'slot':menu_slot(c['right_slot'])}
    s.update(screen='AnvilScreen',interface_paused=False,inventory_interface_paused=False,
             experience_level=30,supervision_lease={'id':'lease'})
    s['menu'].update(type='AnvilMenu',id=mid,slots=slots)
    cert=dict(type='AnvilMenu',id=mid,world_session='w',task_session='t',lease_id='lease',control_revision=3)
    pickup=deepcopy(e);place=deepcopy(e)
    for event,slot,item,count,cursor,cc in ((pickup,menu_slot(c['left_slot']),c['expected_left']['item'],1,'minecraft:air',0),
                                          (place,0,'minecraft:air',0,c['expected_left']['item'],1)):
        event.update(op='slot_click',phase='done')
        event['params']=dict(task_session='t',menu_id=mid,slot=slot,kind='pickup',button=0,
                             expected_item=item,expected_count=count,expected_cursor=cursor,expected_cursor_count=cc)
    return [c,err,b,[pickup,place],s,cert]


class RecoveryTests(unittest.TestCase):
    def test_only_exact_first_placement_can_be_returned(self):
        self.assertTrue(returnable(*partial(),'w','t'))
        for change in ('unknown','input2','output','cursor','changed','cost','lease','request','stage','pickup','world'):
            c,err,b,events,s,cert=deepcopy(partial())
            if change=='unknown':err['unconfirmed_native_request']='r'
            elif change=='input2':s['menu']['slots'][1]={'item':'minecraft:enchanted_book','count':1}
            elif change=='output':s['menu']['slots'][2]={'item':'minecraft:wooden_shovel','count':1}
            elif change=='cursor':s['menu']['cursor']['count']=1
            elif change=='changed':s['menu']['slots'][0]['durability']=50
            elif change=='cost':s['experience_level']=29
            elif change=='lease':cert['lease_id']='other'
            elif change=='request':s['last_request']='other'
            elif change=='stage':b['pending']['cell']=1
            elif change=='pickup':events[-1]['phase']='waiting'
            elif change=='world':events[-1]['world_session']='other'
            with self.subTest(change=change):self.assertFalse(returnable(c,err,b,events,s,cert,'w','t'))


if __name__=='__main__':unittest.main()
