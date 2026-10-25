import copy
import unittest
from village_resource_health import check


class ResourceHealthTests(unittest.TestCase):
    def setUp(self):
        self.state = {'connected': True, 'world_session': 'current', 'health': 20,
                      'manual_movement': False, 'screen': '',
                      'loaded_villagers': {'villagers': [
                          {'uuid': 'foreign', 'health': 11, 'pos': [934., 64., 774.]}]}}

    def checked(self, state):
        return check(state, 'current', {'founder'}, [984, 63, 804], [1034, 69, 818])

    def test_unrelated_injured_resident_does_not_block_a_healthy_resource_trip(self):
        self.assertIs(self.checked(self.state), self.state)

    def test_known_resident_is_protected_even_away_from_home(self):
        self.state['loaded_villagers']['villagers'][0]['uuid'] = 'founder'
        with self.assertRaisesRegex(RuntimeError, 'Protected village'):
            self.checked(self.state)

    def test_resident_only_guard_keeps_the_same_scope_during_owned_transaction(self):
        from village_resource_health import check_residents
        self.state['screen']='MerchantScreen'
        self.assertIs(check_residents(self.state,{'founder'},[984,63,804],[1034,69,818]),self.state)
        with self.assertRaises(RuntimeError):self.checked(self.state)
        self.state['loaded_villagers']['villagers'][0]['uuid']='founder'
        with self.assertRaisesRegex(RuntimeError,'Protected village'):
            check_residents(self.state,{'founder'},[984,63,804],[1034,69,818])

    def test_new_unlisted_child_in_home_area_is_also_protected(self):
        self.state['loaded_villagers']['villagers'][0].update(uuid='new-child', pos=[1000., 64., 811.])
        with self.assertRaisesRegex(RuntimeError, 'Protected village'):
            self.checked(self.state)

    def test_player_injury_world_change_manual_takeover_ui_and_safety_holds_stop(self):
        for mutation in ({'health': 19}, {'world_session': 'old'}, {'connected': False},
                         {'manual_movement': True}, {'screen': 'InventoryScreen'},
                         {'health_recovery_hold': True}, {'safety_hold': {'active': True}}):
            with self.subTest(mutation=mutation):
                state = copy.deepcopy(self.state); state.update(mutation)
                with self.assertRaises(RuntimeError): self.checked(state)

    def test_unknown_location_and_missing_scope_never_silently_exclude_a_villager(self):
        self.state['loaded_villagers']['villagers'][0]['pos'] = None
        with self.assertRaises(RuntimeError): self.checked(self.state)
        with self.assertRaises(ValueError): check(self.state, 'current', set(), [0, 0, 0], [1, 1, 1])

    def test_exact_owned_storage_certificate_allows_transfer_observation_and_cleanup(self):
        state = copy.deepcopy(self.state)
        state.update(screen='ContainerScreen', interface_paused=False,
                     inventory_interface_paused=False, control_revision=7,
                     menu={'type': 'ChestMenu', 'id': 3, 'cursor': {'count': 0}},
                     supervision_lease={'kind': 'materials', 'id': 'lease',
                                        'job_session': 'task', 'world_session': 'current'})
        cert = {'type': 'ChestMenu', 'id': 3, 'world_session': 'current',
                'lease_id': 'lease', 'task_session': 'task', 'control_revision': 7}
        def observed(s, c):
            return check(s, 'current', {'founder'}, [984, 63, 804], [1034, 69, 818], owned_menu=c)
        self.assertIs(observed(state, cert), state)
        for mutation in ({'id': 4}, {'world_session': 'old'}, {'lease_id': 'foreign'},
                         {'task_session': 'foreign'}, {'control_revision': 6}, {'type': 'CraftingMenu'}):
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                observed(state, {**cert, **mutation})
        for mutation in ({'manual_movement': True}, {'health_recovery_hold': True},
                         {'interface_paused': True}, {'health': 19}):
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                observed({**state, **mutation}, cert)
        state['menu']['cursor']['count'] = 1
        with self.assertRaises(RuntimeError): observed(state, cert)

    def test_anvil_requires_explicit_name_tag_intent_and_unchanged_owner(self):
        state = copy.deepcopy(self.state)
        state.update(screen='AnvilScreen', interface_paused=False,
                     inventory_interface_paused=False, control_revision=7,
                     menu={'type': 'AnvilMenu', 'id': 9, 'cursor': {'count': 0}},
                     supervision_lease={'kind': 'materials', 'id': 'lease',
                                        'job_session': 'task', 'world_session': 'current'})
        cert = {'type': 'AnvilMenu', 'id': 9, 'world_session': 'current',
                'lease_id': 'lease', 'task_session': 'task', 'control_revision': 7,
                'purpose': 'name_tag_rename', 'source_request': 'our-anvil-open'}
        def observed(s, c):
            return check(s, 'current', {'founder'}, [984, 63, 804], [1034, 69, 818], owned_menu=c)
        self.assertIs(observed(state, cert), state)
        for mutation in ({'purpose': None}, {'source_request': ''}, {'id': 10},
                         {'lease_id': 'other'}, {'control_revision': 8}):
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                observed(state, {**cert, **mutation})
        with self.assertRaises(RuntimeError): observed(state, None)
        state['menu']['cursor']['count'] = 1
        with self.assertRaises(RuntimeError): observed(state, cert)

    def test_shulker_observation_requires_exact_owned_window_and_preserves_resident_guard(self):
        state=copy.deepcopy(self.state)
        state.update(screen='ShulkerBoxScreen',interface_paused=False,inventory_interface_paused=False,
                     control_revision=7,menu={'type':'ShulkerBoxMenu','id':3,'cursor':{'count':0}},
                     supervision_lease={'kind':'materials','id':'lease','job_session':'task','world_session':'current'})
        cert={'type':'ShulkerBoxMenu','id':3,'world_session':'current','task_session':'task',
              'lease_id':'lease','control_revision':7}
        def observe(s,c):return check(s,'current',{'founder'},[984,63,804],[1034,69,818],owned_menu=c)
        self.assertIs(observe(state,cert),state)
        for mutation in ({'id':4},{'world_session':'old'},{'task_session':'other'},
                         {'lease_id':'other'},{'control_revision':8}):
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):observe(state,{**cert,**mutation})
        with self.assertRaises(RuntimeError):observe(state,None)
        state['loaded_villagers']['villagers'][0]['uuid']='founder'
        with self.assertRaisesRegex(RuntimeError,'Protected village'):observe(state,cert)

    def test_only_exact_native_owned_known_villager_empty_merchant_can_continue(self):
        state = copy.deepcopy(self.state)
        state.update(screen='MerchantScreen', interface_paused=False,
                     inventory_interface_paused=False,
                     supervision_lease={'kind': 'materials', 'id': 'lease',
                                        'job_session': 'task', 'world_session': 'current'},
                     menu={'type': 'MerchantMenu', 'id': 46, 'material_owned': True,
                           'cursor': {'count': 0}, 'slots': [{'count': 0}] * 3,
                           'merchant': {'protocol': 1, 'owned': True, 'menu_id': 46,
                                        'owner_task': 'task', 'villager_uuid': 'founder',
                                        'opening_request_id': 'known-open'}})
        self.assertIs(self.checked(state), state)
        for mutation in ({'owned': False}, {'menu_id': 47}, {'owner_task': 'other'},
                         {'villager_uuid': 'unknown'}, {'opening_request_id': ''}):
            bad = copy.deepcopy(state); bad['menu']['merchant'].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                self.checked(bad)
        for key, value in [('material_owned', False), ('cursor', {'count': 1}),
                           ('slots', [{'count': 1}, {'count': 0}, {'count': 0}])]:
            bad = copy.deepcopy(state); bad['menu'][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError): self.checked(bad)
        for mutation in ({'health': 19}, {'manual_movement': True}, {'interface_paused': True}):
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                self.checked({**state, **mutation})


class ExactHealthEvidenceTests(unittest.TestCase):
    def failure(self, health=18):
        from village_resource_health import ProtectedResidentHealthError
        state={'time':123,'connected':True,'world_session':'world','health':20,
               'manual_movement':False,'screen':'','loaded_villagers':{'villagers':[
                   {'uuid':'keeper','health':health,'pos':[2.,64.,3.]}]}}
        with self.assertRaises(ProtectedResidentHealthError) as caught:
            check(state,'world',{'keeper'},[0,63,0],[4,68,4])
        return state,caught.exception
    def test_exception_preserves_original_offender_even_after_input_changes(self):
        state,error=self.failure();state['loaded_villagers']['villagers'][0].update(health=20,uuid='replacement')
        self.assertEqual(error.resident['uuid'],'keeper');self.assertEqual(error.resident['health'],18)
        self.assertEqual(error.snapshot['loaded_villagers']['villagers'][0]['health'],18)
        self.assertIn('uuid=keeper',str(error));self.assertIn('health=18',str(error))
    def test_missing_or_unexpected_health_still_stops_without_claiming_cause(self):
        for value in [None,19.99,21]:
            with self.subTest(value=value):self.assertEqual(self.failure(value)[1].resident['health'],value)
    def test_record_is_exact_local_and_never_overwrites_previous_failure(self):
        import tempfile,json
        from village_resource_health import record_health_failure
        state,error=self.failure()
        with tempfile.TemporaryDirectory()as directory:
            first=record_health_failure(directory,error);original=first.read_bytes();second=record_health_failure(directory,error)
            self.assertNotEqual(first,second);self.assertEqual(first.read_bytes(),original)
            data=json.loads(original);self.assertEqual(data['original_snapshot'],state)
            self.assertEqual(data['resident'],error.resident);self.assertEqual(data['game_operations'],0)
            self.assertFalse(data['safety_lock_cleared']);self.assertFalse(data['reconnect_authorized'])
    def test_unrelated_error_cannot_be_recorded_as_observed_resident_health(self):
        import tempfile
        from village_resource_health import record_health_failure
        with tempfile.TemporaryDirectory()as directory,self.assertRaises(TypeError):record_health_failure(directory,RuntimeError('other'))


if __name__ == '__main__': unittest.main()
