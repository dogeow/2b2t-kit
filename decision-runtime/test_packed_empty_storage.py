"""Opening empty transport boxes requires a stable server menu, not item presence."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from container_access import wait_container_contents
from packed_supplies import open_box

class EmptyStorageTest(unittest.TestCase):
    def test_opt_in_waits_for_two_stable_empty_menu_frames(self):
        clock=[0.0]; calls=[]
        state={'menu':{'type':'ShulkerBoxMenu','id':7,'cursor':{'count':0},
                       'slots':[{'count':0} for _ in range(63)]}}
        client=SimpleNamespace(request=lambda op:(calls.append(op) or state))
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
            self.assertIs(wait_container_contents(client,'ShulkerBoxMenu',require_nonempty=False),state)
        self.assertGreaterEqual(clock[0],1)
        self.assertGreaterEqual(len(calls),3)

    def test_default_still_rejects_an_empty_menu(self):
        clock=[0.0]
        state={'menu':{'type':'ShulkerBoxMenu','id':7,'cursor':{'count':0},
                       'slots':[{'count':0} for _ in range(63)]}}
        client=SimpleNamespace(request=lambda op:state)
        with patch('container_access.time.monotonic',side_effect=lambda:clock[0]), \
             patch('container_access.time.sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)):
            with self.assertRaisesRegex(RuntimeError,'not acknowledged'):
                wait_container_contents(client,'ShulkerBoxMenu')

    def test_opener_keeps_block_check_and_binding_for_empty_boxes(self):
        c=SimpleNamespace(); state={'menu':{'id':8}}
        with patch('packed_supplies.block',return_value='Block{minecraft:shulker_box}[facing=up]'), \
             patch('packed_supplies.select_container_hand',return_value='main_hand'), \
             patch('packed_supplies.use_with_margin') as interact, \
             patch('packed_supplies.wait_container_contents',return_value=state) as wait, \
             patch('material_storage_index.bind_source') as bind:
            self.assertIs(open_box(c,[1,64,2],'ShulkerBoxMenu',allow_empty=True),state)
            wait.assert_called_once_with(c,'ShulkerBoxMenu',require_nonempty=False)
            interact.assert_called_once()
            bind.assert_called_once_with(c,state,[1,64,2],'minecraft:shulker_box')
            self.assertEqual(c.owned_material_menu,8)

if __name__=='__main__':unittest.main()
