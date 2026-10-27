import copy
import unittest
from independent_boat_stock import validate,validate_recovery,validate_identity,validate_carried


class IndependentBoatStockTests(unittest.TestCase):
    def fixture(self):
        inventory = lambda oak, boat: [{'slot': 0, 'item': 'minecraft:oak_planks', 'count': oak},
                                        {'slot': 1, 'item': 'minecraft:oak_boat', 'count': boat}]
        state = {'time': 300, 'world_session': 'w', 'inventory': inventory(0, 1),
                 'loaded_villagers': {'villagers': [{'uuid': 'candidate', 'health': 20, 'is_baby': False,
                                                    'villager': {'entity_xp': 0, 'level': 1}}]}}
        command = {'action': 'boat_place', 'item': 'minecraft:oak_boat', 'support': [30, 64, 30],
                   'stand': [30, 64, 28], 'allowed_passengers': ['candidate']}
        certificate = {'world_session': 'w', 'task_session': 'task', 'created_at': 250,
                       'old_journal_sha256': 'original', 'consumed_by': None,
                       **{k: command[k] for k in ('item', 'support', 'stand', 'allowed_passengers')}}
        before = {'world_session': 'w', 'time': 100, 'inventory': inventory(5, 0)}
        after = {'world_session': 'w', 'time': 200, 'inventory': inventory(0, 1)}
        return [state, {'job_session': 'task'}, command, {'journal_sha256': 'original'},
                {'item': 'minecraft:dark_oak_boat', 'support': [1, 63, 1]}, certificate, before,
                {'action': 'manufacture', 'targets': {'minecraft:oak_boat': 1}}, {'complete': True}, after]

    def test_new_species_distant_site_and_exact_new_craft_can_proceed(self):
        validate(*self.fixture())
    def test_crafted_empty_receiver_still_needs_exact_conserved_crafting_evidence(self):
        a=self.fixture();s,lease,command,marker,old,cert=a[:6]
        s.update(connected=True,health=20,manual_movement=False,screen='');lease.update(kind='materials',world_session='w')
        command.update(allowed_passengers=[],purpose='iron_farm_zombie_capture');cert.update(allowed_passengers=[],purpose='iron_farm_zombie_capture',kind='crafted')
        validate(*a)
        for key,value in [('complete',False)]:
            bad=copy.deepcopy(a);bad[8][key]=value
            with self.assertRaises(RuntimeError):validate(*bad)
        bad=copy.deepcopy(a);bad[9]['inventory'][0]['count']=1
        with self.assertRaises(RuntimeError):validate(*bad)
    def test_pre_owner_carried_different_species_is_only_an_empty_receiver_not_old_input_credit(self):
        a=self.fixture()[:6];s,l,c,m,o,cert=a
        s.update(connected=True,health=20,manual_movement=False,screen='',server='s',dimension='d',player_uuid='p')
        l.update(kind='materials',world_session='w');c.update(allowed_passengers=[],purpose='iron_farm_zombie_capture')
        cert.update(allowed_passengers=[],purpose=c['purpose'],kind='observed_carried')
        source=copy.deepcopy(s);source['time']=100
        validate_carried(*a,source)
        for patch in ({'world_session':'other'},{'supervision_lease':{'id':'foreign'}},{'inventory':[]},{'time':400}):
            with self.subTest(patch=patch),self.assertRaises(RuntimeError):validate_carried(*a,{**source,**patch})
        bad=copy.deepcopy(a);bad[4]['item']='minecraft:oak_boat'
        with self.assertRaises(RuntimeError):validate_carried(*bad,source)

    def test_empty_bait_receiver_is_recovered_stock_only_and_never_passenger_authority(self):
        a=self.fixture()[:6];s,lease,command,marker,old,cert=a
        s.update(connected=True,health=20,manual_movement=False,screen='')
        lease.update(kind='materials',world_session='w')
        command.update(allowed_passengers=[],purpose='iron_farm_zombie_capture')
        cert.update(allowed_passengers=[],purpose='iron_farm_zombie_capture',kind='recovered')
        self.assertEqual(validate_identity(*a),'minecraft:oak_boat')
        for patch in ({'kind':'unknown'},{'purpose':'other'},{'allowed_passengers':['candidate']},{'consumed_by':'previous'}):
            bad=copy.deepcopy(a);bad[5].update(patch)
            with self.assertRaises(RuntimeError):validate_identity(*bad)
        for patch in ({'manual_movement':True},{'health':19},{'connected':False},{'screen':'InventoryScreen'}):
            bad=copy.deepcopy(a);bad[0].update(patch)
            with self.assertRaises(RuntimeError):validate_identity(*bad)

    def test_family_pair_requires_two_distinct_observed_healthy_untraded_adults(self):
        a=self.fixture();s,lease,command,marker,old,cert=a[:6]
        second=copy.deepcopy(s['loaded_villagers']['villagers'][0]);second['uuid']='second';s['loaded_villagers']['villagers'].append(second)
        command.update(allowed_passengers=['candidate','second'],purpose='family_pair_transport')
        cert.update(allowed_passengers=['candidate','second'],purpose='family_pair_transport')
        validate(*a)
        for change in ('purpose','duplicate','missing','injured','traded'):
            bad=copy.deepcopy(a)
            if change=='purpose':bad[2].pop('purpose')
            if change=='duplicate':bad[2]['allowed_passengers']=bad[5]['allowed_passengers']=['candidate','candidate']
            if change=='missing':bad[0]['loaded_villagers']['villagers'].pop()
            if change=='injured':bad[0]['loaded_villagers']['villagers'][1]['health']=19
            if change=='traded':bad[0]['loaded_villagers']['villagers'][1]['villager']['entity_xp']=1
            with self.subTest(change=change),self.assertRaises(RuntimeError):validate(*bad)

    def test_known_recovered_item_can_be_reused_without_replaying_old_quarantine(self):
        a=self.fixture();boat={'uuid':'new-boat','type':'minecraft:oak_boat','passengers':[{'uuid':'previous-candidate'}]}
        proof={'complete':True,'pending':None,'world_session':'w','health':20,'boat_and_lead_recovered':True,
               'boat_before':boat,'boat_removed_two_frames':[100,200],
               'inventory_before':{'minecraft:lead':1},'inventory_after':{'minecraft:lead':2,'minecraft:oak_boat':1},
               'boat_recovery_request':'recover'}
        placed={'complete':True,'pending':None,'world_session':'w','item':'minecraft:oak_boat','boat':boat,
                'before':{'minecraft:oak_boat':1},'after':{}}
        intent={'action':'boat_place','item':'minecraft:oak_boat','independent_stock':'certificate'}
        recovery={'action':'native','op':'recover_boat','params':{'expected_uuid':'new-boat','expected_passenger_uuids':['previous-candidate']}}
        reply={'id':'recover','world_session':'w','phase':'done'}
        args=a[:6]+[proof,placed,intent,recovery,reply];validate_recovery(*args)
        for key,value in [('complete',False),('boat_and_lead_recovered',False),('inventory_after',{})]:
            with self.subTest(key=key):
                bad=copy.deepcopy(args);bad[6][key]=value
                with self.assertRaises(RuntimeError):validate_recovery(*bad)
        bad=copy.deepcopy(args);bad[9]['params']['expected_uuid']='another-boat'
        with self.assertRaises(RuntimeError):validate_recovery(*bad)

    def test_same_species_same_site_old_stock_and_reuse_stay_fenced(self):
        for change in ('same_species', 'near_old', 'used', 'expired', 'world', 'stock', 'crafted', 'traded', 'baby', 'consumed_extra'):
            with self.subTest(change=change):
                a = self.fixture()
                if change == 'same_species': a[4]['item'] = 'minecraft:oak_boat'
                if change == 'near_old': a[4]['support'] = [29, 64, 29]
                if change == 'used': a[5]['consumed_by'] = 'previous-command'
                if change == 'expired': a[0]['time'] = 999999
                if change == 'world': a[9]['world_session'] = 'other'
                if change == 'stock': a[6]['inventory'][1]['count'] = 1
                if change == 'crafted': a[8]['complete'] = False
                if change == 'traded': a[0]['loaded_villagers']['villagers'][0]['villager']['entity_xp'] = 1
                if change == 'baby': a[0]['loaded_villagers']['villagers'][0]['is_baby'] = True
                if change == 'consumed_extra': a[9]['inventory'].append({'slot': 2, 'item': 'minecraft:dirt', 'count': 1})
                with self.assertRaises(RuntimeError): validate(*a)


if __name__ == '__main__':
    unittest.main()
