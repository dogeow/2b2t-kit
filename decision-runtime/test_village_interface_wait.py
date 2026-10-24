from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from village_interface_wait import idle_foreign_merchant,idle_interface_transition


def fixture():
    client=SimpleNamespace(world='w',task='t',last='r',heartbeat=SimpleNamespace(id='lease'),
        native_inflight=None,unconfirmed_native_request=None,
        last_terminal_evidence={'request_id':'r','op':'select_item','phase':'done',
            'task_session':'t','world_session':'w','revision_after':4})
    state={'screen':'MerchantScreen','menu':{'type':'MerchantMenu','material_owned':False,
        'cursor':{'item':'minecraft:paper','count':24}},'connected':True,'world_session':'w',
        'health':20,'guard_armed':True,'guard_pve_only':True,'manual_movement':False,
        'movement_keys':{'forward':False,'back':False,'jump':False,'sneak':False},
        'last_request':'r','control_revision':4,'supervision_lease':{'id':'lease','kind':'materials',
            'job_session':'t','world_session':'w','revision':4}}
    return client,state


class IdleForeignMerchantTests(TestCase):
    def test_closed_between_status_and_raw_rechecks_without_finishing_owner(self):
        c,s=fixture();s['screen']='';s['menu']={'type':'InventoryMenu','material_owned':False}
        original=deepcopy(s)
        self.assertTrue(idle_interface_transition(c,s));self.assertEqual(original,s)

    def test_other_unowned_processing_windows_can_wait_without_adoption(self):
        for screen,kind in [('MerchantScreen','MerchantMenu'),('LoomScreen','LoomMenu'),('StonecutterScreen','StonecutterMenu')]:
            c,s=fixture();s.update(screen=screen,menu={'type':kind,'material_owned':False})
            self.assertTrue(idle_interface_transition(c,s))
            s['menu']['material_owned']=True
            self.assertFalse(idle_interface_transition(c,s))

    def test_closed_screen_does_not_relax_unknown_health_or_control_fences(self):
        for change in ({'health':19},{'connected':False},{'manual_movement':True},
                       {'control_revision':5},{'supervision_lease':None},{'pending_scan':{}},
                       {'native_material_busy':True},{'world_session':'other'}):
            c,s=fixture();s.update(screen='',**change)
            self.assertFalse(idle_interface_transition(c,s))
        c,s=fixture();s['screen']=''
        self.assertFalse(idle_interface_transition(c,s,retained_failure=True))
        c.unconfirmed_native_request={'request_id':'original'}
        self.assertFalse(idle_interface_transition(c,s))

    def test_empty_idle_world_input_can_wait_with_the_users_cursor_untouched(self):
        c,s=fixture();original=deepcopy(s)
        self.assertTrue(idle_foreign_merchant(c,s));self.assertEqual(original,s)

    def test_manual_movement_stop_disconnect_world_change_and_health_never_wait(self):
        for change in({'manual_movement':True},{'supervision_lease':None},{'connected':False},
                       {'world_session':'other'},{'control_revision':5},{'health':19},
                       {'guard_armed':False},{'guard_pve_only':False},
                       {'movement_keys':{'forward':True}},{'navigating':True},
                       {'native_material_busy':True},{'pending_scan':'scan'}):
            with self.subTest(change=change):
                c,s=fixture();self.assertFalse(idle_foreign_merchant(c,{**s,**change}))

    def test_unknown_native_or_retained_failed_transaction_never_becomes_an_interface_pause(self):
        for attr in('native_inflight','unconfirmed_native_request'):
            c,s=fixture();setattr(c,attr,{'request_id':'original'});self.assertFalse(idle_foreign_merchant(c,s))
        c,s=fixture();self.assertFalse(idle_foreign_merchant(c,s,retained_failure=True))
        c.last_terminal_evidence['request_id']='other';self.assertFalse(idle_foreign_merchant(c,s))

    def test_owned_merchant_and_other_screen_types_retain_their_existing_rules(self):
        c,s=fixture();s['menu']['material_owned']=True;self.assertFalse(idle_foreign_merchant(c,s))
        for screen in('InventoryScreen','PauseScreen','ChatScreen',''):
            c,s=fixture();s['screen']=screen;self.assertFalse(idle_foreign_merchant(c,s))
