from copy import deepcopy
import time
import unittest
from lighting_entity_reconcile import validate_pending, ERROR, GUARD_ERROR


def fixture():
    pending={'error':ERROR,'stage':'lighting','handoff':'late_owned_native_parking_observed_read_only',
        'world_session':'world','task_session':'task','lease':'lease',
        'native_request':{'op':'scan','request_id':'scan-id','expected_revision':3}}
    pending['uncertain_request']=deepcopy(pending['native_request'])
    state={'connected':True,'world_session':'world','health':20,'manual_movement':False,
        'guard_armed':True,'guard_pve_only':True,'flight':True,'screen':'','control_revision':5,
        'time':int(time.time()*1000),'pos':[0,140,0],
        'supervision_lease':{'kind':'parking','id':'lease','job_session':'task','revision':5,'park_target':[0,140,0]},
        'supervision_safety':{'action':'KEEP_PVE_GUARD','lease':'lease','job_session':'task'}}
    placement={'state':'verified','later_verified_frames':2,'world_session':'world','task_session':'task',
        'before_stock':8,'after_stock':7,'interaction_request':'place-id'}
    report={'park_native_confirmed':True,'placed':[placement]}
    events=[{'op':'interact','phase':'done','world_session':'world','request_id':'place-id','inventory_delta':{'minecraft:torch':-1}},
            {'op':'scan','phase':'done','world_session':'world','request_id':'scan-id'},
            {'op':'navigate','phase':'done','world_session':'world','request_id':'park-id'}]
    reply={'id':'scan-id','phase':'done','world_session':'world','control_revision':3}
    return pending,state,report,events,reply


class ReconcileTest(unittest.TestCase):
    def test_only_verified_partial_is_counted_not_region_completion(self):
        self.assertEqual(1,validate_pending(*fixture()))
    def test_changed_world_manual_control_or_foreign_owner_preserves_pending(self):
        for key,value in (('world_session','other'),('manual_movement',True),('health',18),('control_revision',6)):
            with self.subTest(key=key):
                args=list(fixture());args[1][key]=value
                with self.assertRaises(ValueError):validate_pending(*args)
    def test_unconfirmed_scan_or_other_failure_is_never_cleared(self):
        for change in ('scan_waiting','error','unknown_native'):
            with self.subTest(change=change):
                args=list(fixture())
                if change=='scan_waiting':args[4]['phase']='waiting'
                elif change=='error':args[0]['error']='unknown placement'
                else:args[0]['uncertain_request']['op']='interact'
                with self.assertRaises(ValueError):validate_pending(*args)
    def test_extra_mutation_after_preflight_and_unknown_placement_block(self):
        for change in ('extra_mutation','unknown','stock_changed'):
            with self.subTest(change=change):
                args=list(fixture())
                if change=='extra_mutation':args[3].append({'op':'interact','phase':'done','world_session':'world'})
                elif change=='unknown':args[2]['placed'][0]['state']='interaction_intent'
                else:args[3][0]['inventory_delta']['minecraft:torch']=-2
                with self.assertRaises(ValueError):validate_pending(*args)
    def test_guard_wait_accepts_only_exact_read_only_snapshot_not_a_mutation(self):
        args=list(fixture());args[0]['error']=GUARD_ERROR
        args[0]['native_request']['op']='snapshot';args[0]['uncertain_request']['op']='snapshot'
        args[3][1].update(op='snapshot',phase=None);args[4]['phase']=None
        self.assertEqual(1,validate_pending(*args))
        args[0]['native_request']['op']='interact';args[0]['uncertain_request']['op']='interact'
        with self.assertRaises(ValueError):validate_pending(*args)

    def test_failed_internal_cleanup_requires_an_exact_separate_original_task_park_proof(self):
        args=list(fixture());args[0]['error']=GUARD_ERROR;args[0]['handoff']=None
        args[0]['native_request']['op']='snapshot';args[0]['uncertain_request']['op']='snapshot'
        args[2].update(placed=[],park_native_confirmed=None);args[3]=args[3][1:]
        args[3][0].update(op='snapshot',phase=None);args[4]['phase']=None
        with self.assertRaises(ValueError):validate_pending(*args)
        self.assertEqual(0,validate_pending(*args,external_parking=deepcopy(args[1])))
        bad=deepcopy(args[1]);bad['supervision_lease']['job_session']='foreign'
        with self.assertRaises(ValueError):validate_pending(*args,external_parking=bad)
        self.assertIsNone(args[2]['park_native_confirmed'])

    def test_zero_placement_external_park_may_retain_partial_read_without_calling_it_completed(self):
        args=list(fixture());args[0]['error']=GUARD_ERROR;args[0]['handoff']=None
        args[0]['native_request']['op']='snapshot';args[0]['uncertain_request']['op']='snapshot'
        args[2].update(placed=[],park_native_confirmed=None);args[3]=args[3][1:]
        args[3][0].update(op='snapshot',phase=None);args[4]['phase']=None
        args[3].insert(0,{'op':'scan','phase':'waiting','world_session':'world','request_id':'partial',
            'inventory_delta':{},'detail':'scan stopped; partial records retained: Server chunk is not loaded: 1 2'})
        self.assertEqual(0,validate_pending(*args,external_parking=deepcopy(args[1])))
        self.assertEqual('waiting',args[3][0]['phase'])
        args[3][0]['op']='interact'
        with self.assertRaises(ValueError):validate_pending(*args,external_parking=deepcopy(args[1]))

    def test_current_parking_target_and_freshness_are_required(self):
        for key,value in (('pos',[0,135,0]),('time',1)):
            args=list(fixture());args[1][key]=value
            with self.assertRaises(ValueError):validate_pending(*args)


if __name__=='__main__':unittest.main()
