import unittest
from unittest.mock import patch
from container_access import open_grounded_chest


class FakeClient:
    def __init__(self, clock, blocked=False):
        self.clock=clock;self.blocked=blocked;self.opened_at=None;self.actions=[]
    def status(self):return {'hand':{'item':'minecraft:diamond_sword'}}
    def checked(self,op,**params):
        self.actions.append((op,params))
        if op=='interact':self.opened_at=self.clock[0]
        return {'phase':'done'}
    def request(self,op,**params):
        if op=='scan':
            rows=[{'pos':[1,64,2],'state':'Block{minecraft:chest}[facing=south]'}]
            if self.blocked:rows.append({'pos':[1,66,2],'state':'Block{minecraft:stone}'})
            return {'blocks':rows}
        opened=self.opened_at is not None and self.clock[0]-self.opened_at>=6
        return {'health':20,'on_ground':True,'velocity':[0,0,0],
                'menu':{'type':'ChestMenu' if opened else 'InventoryMenu','id':7,'cursor':{'count':0},
                        'slots':[{'item':'minecraft:stone','count':1}]+[{'count':0} for _ in range(36)]}}


class ContainerAccessTest(unittest.TestCase):
    def test_open_menu_waits_for_delayed_item_contents(self):
        clock=[0.0]
        class DelayedContents(FakeClient):
            def request(self,op,**params):
                result=super().request(op,**params)
                if op=='snapshot' and self.opened_at is not None and clock[0]-self.opened_at<9:
                    result['menu']['slots']=[{'count':0} for _ in range(63)]
                return result
        client=DelayedContents(clock)
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda duration:clock.__setitem__(0,clock[0]+duration)):
            result=open_grounded_chest(client,[1,64,2])
        self.assertGreaterEqual(clock[0],10)
        self.assertEqual(1,result['menu']['slots'][0]['count'])

    def test_late_server_open_is_awaited_without_leaving_the_chest(self):
        clock=[0.0];client=FakeClient(clock)
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda duration:clock.__setitem__(0,clock[0]+duration)):
            result=open_grounded_chest(client,[1,64,2])
        self.assertEqual('ChestMenu',result['menu']['type'])
        self.assertEqual(7,client.owned_material_menu)
        self.assertEqual(['approach_block','walk','interact'],[name for name,_ in client.actions])
        self.assertFalse(client.actions[1][1]['restore_flight'])
        self.assertEqual(.65,client.actions[0][1]['stand_distance'])

    def test_obstructed_landing_is_rejected_before_movement(self):
        client=FakeClient([0],blocked=True)
        with self.assertRaisesRegex(RuntimeError,'obstructed'):open_grounded_chest(client,[1,64,2])
        self.assertEqual([],client.actions)

    def test_explicit_inventory_sweep_accepts_a_stable_empty_chest(self):
        clock=[0.0]
        class EmptyChest(FakeClient):
            def request(self,op,**params):
                result=super().request(op,**params)
                if op=='snapshot':result['menu']['slots']=[{'count':0} for _ in range(63)]
                return result
        client=EmptyChest(clock)
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda duration:clock.__setitem__(0,clock[0]+duration)):
            result=open_grounded_chest(client,[1,64,2],allow_empty=True)
        self.assertEqual('ChestMenu',result['menu']['type']);self.assertGreaterEqual(clock[0],7)
        self.assertEqual(0,sum(row['count'] for row in result['menu']['slots']))
