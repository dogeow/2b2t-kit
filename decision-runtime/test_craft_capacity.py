import copy
import unittest
from unittest.mock import patch
from craft_grid import compact_once,output_room


def stack(item='minecraft:air', count=0, tag='', slot=0):
    return {'item':item,'count':count,'max_stack':64,'tag':tag,'slot':slot}


class CapacityTests(unittest.TestCase):
    def state(self, different=False):
        slots=[stack(slot=i) for i in range(10)]+[stack('minecraft:stone',64,slot=i) for i in range(10,46)]
        slots[10]=stack('minecraft:spruce_log',55,'first',10)
        slots[11]=stack('minecraft:spruce_log',7,'second' if different else 'first',11)
        return self.snapshot(slots,stack())

    def snapshot(self, slots, cursor):
        return {'menu':{'type':'CraftingMenu','id':3,'slots':slots,'cursor':{k:v for k,v in cursor.items() if k!='slot'}},
                'inventory':[{**v,'slot':i} for i,v in enumerate(slots[10:]) ]}

    def click(self,s,slot,kind='pickup'):
        s=copy.deepcopy(s);m=s['menu'];a=m['cursor'];b=m['slots'][slot]
        if a['count'] and b['count'] and a['item']==b['item'] and a['tag']==b['tag']:
            b['count']+=a['count'];m['cursor']=stack()
        else:
            m['cursor']=b.copy();m['slots'][slot]={**a,'slot':slot}
        return self.snapshot(m['slots'],m['cursor'])

    def test_fragmented_logs_free_one_real_output_slot(self):
        s=self.state();self.assertEqual(output_room(s,'minecraft:spruce_trapdoor',64),0)
        with patch('craft_grid.click',side_effect=self.click):s,merged=compact_once(s)
        self.assertTrue(merged);self.assertEqual(output_room(s,'minecraft:spruce_trapdoor',64),64)
        self.assertEqual(sum(v['count'] for v in s['inventory'] if v['item']=='minecraft:spruce_log'),62)

    def test_different_components_are_restored_instead_of_forced_to_merge(self):
        original=self.state(True)
        with patch('craft_grid.click',side_effect=self.click):result,merged=compact_once(original)
        self.assertFalse(merged)
        self.assertEqual(result,original)

if __name__=='__main__':unittest.main()
