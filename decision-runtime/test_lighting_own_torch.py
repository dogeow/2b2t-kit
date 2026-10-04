from copy import deepcopy
import tempfile
import time
import unittest
from unittest.mock import patch

import kit_cli
import lighting_cli as lighting
import lighting_entity_reconcile as reconcile
from potato_farm import ENTITY_SCOPE_AT_SCAN_END
from test_lighting_cli import FakeClient, LOW, HIGH, snapshot, inventory
from test_lighting_entity_reconcile import fixture


def torch_row():
    return {'pos':[2,64,2],'state':'Block{minecraft:torch}','solid':False,
            'passable':True,'fluid':False,'block_entity':False}


def placement(world='world-a',task='task-a'):
    return {'target':[2,64,2],'state':'verified','later_verified_frames':2,
            'world_session':world,'task_session':task,'before_stock':8,'after_stock':7,
            'before_time':10,'after_time':20,'interaction_request':'place-id',
            'evidence_scope':lighting.EVIDENCE}


def own_fixture():
    pending,state,report,events,reply=fixture()
    pending.update(error=reconcile.OWN_TORCH_ERROR)
    pending['native_request'].update(world_session='world',task_session='task',lease_id='lease',base_revision=3)
    pending['uncertain_request']=deepcopy(pending['native_request'])
    state['pos']=[2.5,140,2.5];state['supervision_lease']['park_target']=list(state['pos'])
    report.update(world_session='world',task_session='task',placed=[placement('world','task')])
    events[1].update(params={'min':[2,64,2],'max':[2,67,2],'details':True},
                     inventory_delta={},revision_before=3,revision_after=3)
    events[-1].update(params={'task_session':'task','target':list(state['pos']),'air_only':True},
                      position_before=[2.5,65.5,2.5],inventory_delta={})
    reply.update(scan_started_at=25,scan_ended_at=26,scan_start_revision=3,scan_end_revision=3,
                 scan_cells_read=4,scan_total_cells=4,blocks=[torch_row()],
                 scan_entities=[],scan_entity_scope=ENTITY_SCOPE_AT_SCAN_END)
    return pending,state,report,events,reply


def recovery_fixture():
    pending,state,report,events,reply=own_fixture();now=int(time.time()*1000)
    old=deepcopy(state);old['time']=now-9000
    state.update(control_revision=7,movement_keys={'forward':False,'jump':False})
    state['supervision_lease'].update(id='new-lease',job_session='new-task',revision=7)
    state['supervision_safety'].update(lease='new-lease',job_session='new-task')
    new=deepcopy(state);new['time']=now-1000
    samples=[{'time':now-7000+i*250,'world_session':'world','control_revision':6,
              'pos':list(old['pos']),'health':20,'food':20,'manual_movement':False,
              'movement_keys':{'forward':False,'jump':False},'screen':'','detail':'用户界面接管'}for i in range(21)]
    release=deepcopy(state);release.update(supervision_lease=None,control_revision=6,food=20,
        id='prelease',phase='done',time=now-1500,scan_started_at=now-1600,scan_ended_at=now-1500,
        scan_start_revision=6,scan_end_revision=6,scan_cells_read=385,scan_total_cells=385)
    check=deepcopy(reply);check.update(id='fresh-torch',control_revision=7,
        scan_cells_read=1,scan_total_cells=1,scan_start_revision=7,scan_end_revision=7,
        scan_started_at=now-500,scan_ended_at=now-400)
    inv={'world_session':'world','time':now-200,'inventory':inventory(7)}
    maintenance_events=[{'op':'scan','phase':'done','request_id':'prelease','world_session':'world',
        'inventory_delta':{},'position_before':old['pos'],'position_after':old['pos']},
        {'op':'material_session','phase':'done','world_session':'world','inventory_delta':{},
         'position_before':old['pos'],'position_after':old['pos'],
         'params':{'task_session':'new-task','supervision_lease':'new-lease'}}]
    recovery={'schema':1,'kind':'own_torch_preflight_new_maintenance_parking',
        'maintenance_parking':new,'idle_handoff':{'world_session':'world',
            'purpose':'new_maintenance_parking_after_ui_closed_no_original_work_replay','idle_samples':samples},
        'prelease_scan':release,'maintenance_events':maintenance_events,
        'current_torch_checks':[{'target':[2,64,2],'actual':check,'inventory':inv}]}
    return (pending,state,report,events,reply),recovery,old


def healthy_recovery_fixture():
    args,recovery,old=recovery_fixture();pending,state,report,events,reply=args;now=state['time']
    identity={'server':'example.test','dimension':'minecraft:overworld','player_uuid':'same-player',
              'projection_selection':{'key':'same-projection'},'recent_hurt_at':1}
    old.update(deepcopy(identity));previous=recovery['maintenance_parking'];previous.update(deepcopy(identity))
    previous['inventory']=inventory(7)
    logout_snapshot=deepcopy(previous);logout_snapshot.pop('supervision_lease')
    logout_snapshot.update(time=now-899,pos=[2.5,137.9,2.5],movement_keys={'sneak':True},food=20)
    recovery.update(kind='own_torch_preflight_healthy_host_recovery',healthy_logout={
        'lease':'new-lease','job_session':'new-task','cause':'parking_invalid','action':'LOGOUT',
        'time':now-900,'confirmed':True,'confirmed_at':now-890,'confirmation':'network_disconnect_event',
        'snapshot':logout_snapshot})
    state.update(deepcopy(identity));state.update(world_session='new-world',control_revision=9,kit_version='2026.10.4.1')
    state['supervision_lease'].update(world_session='new-world',id='current-lease',job_session='current-task',revision=9)
    state['supervision_safety'].update(lease='current-lease',job_session='current-task')
    current=deepcopy(state);current['time']=now-600;recovery['current_parking']=current
    check=recovery['current_torch_checks'][0]
    for frame in (check['actual'],check['inventory']):
        frame.update(deepcopy(identity));frame.update(world_session='new-world',control_revision=9,
            supervision_lease=deepcopy(state['supervision_lease']),health=20,manual_movement=False,screen='')
    check['actual'].update(scan_start_revision=9,scan_end_revision=9)
    return args,recovery,old


def publication_lag_fixture():
    args,recovery,old=healthy_recovery_fixture();previous=recovery['maintenance_parking']
    previous.update(under_water=False)
    previous['supervision_lease']['parked_at']=previous['time']-16
    previous['supervision_safety']=deepcopy(old['supervision_safety'])
    full=deepcopy(previous);full['time']+=1
    confirmation={key:deepcopy(previous[key])for key in ('time','world_session','control_revision',
        'supervision_lease','connected','health','manual_movement','flight','guard_armed','guard_pve_only',
        'pos','under_water')}
    recovery['maintenance_finish']={'lease':'new-lease','job_session':'new-task',
        'cause':'controller_finished','action':'KEEP_PVE_GUARD','time':previous['time']-16,
        'native_receipt':True,'snapshot':full,'parking_confirmation':confirmation}
    return args,recovery,old


class OwnTorchTests(unittest.TestCase):
    def test_current_same_batch_noncolliding_torch_allows_native_air_only_move(self):
        class Moving(FakeClient):
            def __init__(self,root):super().__init__(root);self.pos=[2.5,65.5,2.5];self.moves=[]
            def request(self,op,**params):
                if op=='snapshot':return {**snapshot(),'pos':self.pos}
                if op=='scan':return {'phase':'done','world_session':self.world,'blocks':[torch_row()],
                    'scan_entities':[],'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END}
                return super().request(op,**params)
            def checked(self,op,**params):
                if op=='navigate':self.moves.append(params);self.pos=params['target'];return {'phase':'done'}
                return super().checked(op,**params)
        with tempfile.TemporaryDirectory()as folder:
            c=Moving(folder);run=lighting.LightingRun(c,LOW,HIGH,1,folder,snapshot())
            run.report['placed']=[placement()];run.move([2.5,64.5,2.5])
            self.assertEqual(1,len(c.moves));self.assertTrue(c.moves[0]['air_only'])

    def test_unknown_foreign_old_scope_or_colliding_torch_never_admitted(self):
        for change in ({'world_session':'other'},{'task_session':'other'},{'state':'interaction_intent'},
                       {'later_verified_frames':1},{'after_stock':6},{'after_time':200}):
            self.assertFalse(lighting.verified_own_torch(torch_row(),[placement()|change],'world-a','task-a',100))
        for change in ({'passable':False},{'solid':True},{'fluid':True},{'block_entity':True},
                       {'state':'Block{minecraft:wall_torch}[facing=north]'},{'pos':[3,64,2]}):
            self.assertFalse(lighting.verified_own_torch(torch_row()|change,[placement()],'world-a','task-a',100))

    def test_own_torch_terminal_preflight_counts_original_placement_only(self):
        self.assertEqual(1,reconcile.validate_pending(*own_fixture()))

    def test_other_obstacle_entities_partial_scan_or_later_mutation_preserves_pending(self):
        for change in ('foreign','colliding','entity','partial','mutation','lateral_park'):
            args=list(own_fixture())
            if change=='foreign':args[4]['blocks'][0]['pos']=[3,64,2]
            elif change=='colliding':args[4]['blocks'][0]['passable']=False
            elif change=='entity':args[4]['scan_entities']=[{'type':'minecraft:cow'}]
            elif change=='partial':args[4]['scan_cells_read']=3
            elif change=='mutation':args[3][-1]['inventory_delta']={'minecraft:torch':-1}
            else:args[3][-1]['position_before']=[10,65,10]
            with self.subTest(change=change),self.assertRaises((ValueError,lighting.LightingBlocked)):
                reconcile.validate_pending(*args)

    def test_interface_release_requires_real_thin_samples_and_distinct_native_maintenance(self):
        args,recovery,old=recovery_fixture()
        self.assertEqual(1,reconcile.validate_pending(*args,maintenance_recovery=recovery,original_parking=old))
        self.assertNotEqual(old['supervision_lease']['id'],args[1]['supervision_lease']['id'])
        with self.assertRaises(ValueError):reconcile.validate_pending(*args)

    def test_missing_release_witness_short_idle_stock_change_and_foreign_owner_block(self):
        for change in ('short_idle','missing_full','foreign','stock','unknown_scan','move','old_owner'):
            args,recovery,old=recovery_fixture()
            if change=='short_idle':recovery['idle_handoff']['idle_samples']=recovery['idle_handoff']['idle_samples'][-2:]
            elif change=='missing_full':recovery['prelease_scan'].pop('flight')
            elif change=='foreign':recovery['maintenance_parking']['supervision_lease']['job_session']='foreign'
            elif change=='stock':recovery['current_torch_checks'][0]['inventory']['inventory']=inventory(8)
            elif change=='unknown_scan':recovery['current_torch_checks'][0]['actual']['phase']='waiting'
            elif change=='move':recovery['maintenance_events'][0]['position_after']=[3.5,140,2.5]
            else:recovery['maintenance_parking']['supervision_lease']['id']='lease'
            with self.subTest(change=change),self.assertRaises(ValueError):
                reconcile.validate_pending(*args,maintenance_recovery=recovery,original_parking=old)

    def test_central_cli_routes_explicit_own_torch_category(self):
        with patch('lighting_regions_cli.main',return_value=0)as main:
            self.assertEqual(0,kit_cli.main(['lighting','reconcile-own-torch','--profile','/profile','--out','/out']))
        self.assertEqual('reconcile-own-torch',main.call_args.args[0][-1])

    def test_healthy_host_recovery_distinguishes_old_and_new_world_and_owner(self):
        args,recovery,old=healthy_recovery_fixture()
        self.assertEqual(1,reconcile.validate_pending(*args,maintenance_recovery=recovery,original_parking=old))
        self.assertEqual('world',old['world_session']);self.assertEqual('new-world',args[1]['world_session'])
        self.assertEqual('lease',old['supervision_lease']['id'])
        self.assertEqual('current-lease',args[1]['supervision_lease']['id'])

    def test_health_exit_unknown_logout_old_host_or_changed_identity_never_reconciles(self):
        for change in ('health_cause','health_loss','hold','new_hurt','unconfirmed','old_host','player','server','projection','world','old_reply'):
            args,recovery,old=healthy_recovery_fixture()
            if change=='health_cause':recovery['healthy_logout']['cause']='low_health'
            elif change=='health_loss':recovery['healthy_logout']['snapshot']['health']=18
            elif change=='hold':recovery['healthy_logout']['snapshot']['safety_hold']={'active':True}
            elif change=='new_hurt':recovery['healthy_logout']['snapshot']['recent_hurt_at']=args[1]['time']
            elif change=='unconfirmed':recovery['healthy_logout']['confirmed']=False
            elif change=='old_host':args[1]['kit_version']='2026.10.3.2'
            elif change=='player':args[1]['player_uuid']='different-player'
            elif change=='server':args[1]['server']='another.test'
            elif change=='projection':args[1]['projection_selection']['key']='changed'
            elif change=='world':recovery['current_torch_checks'][0]['actual']['world_session']='world'
            else:recovery['current_torch_checks'][0]['actual']['id']=args[0]['native_request']['request_id']
            with self.subTest(change=change),self.assertRaises(ValueError):
                reconcile.validate_pending(*args,maintenance_recovery=recovery,original_parking=old)

    def test_exact_native_finish_proves_lagging_historical_global_metadata_without_editing_it(self):
        args,recovery,old=publication_lag_fixture();raw=deepcopy(recovery['maintenance_parking'])
        self.assertFalse(reconcile._native_park(raw,'world'))
        self.assertEqual(1,reconcile.validate_pending(*args,maintenance_recovery=recovery,original_parking=old))
        self.assertEqual(raw,recovery['maintenance_parking'])
        self.assertEqual('lease',recovery['maintenance_parking']['supervision_safety']['lease'])

    def test_forged_finish_or_mismatched_confirmation_cannot_replace_publication_proof(self):
        for change in ('origin','action','owner','task','time','world','revision','pose','health','flight','input'):
            args,recovery,old=publication_lag_fixture();finish=recovery['maintenance_finish']
            if change=='origin':finish['native_receipt']=False
            elif change=='action':finish['action']='LOGOUT'
            elif change=='owner':finish['lease']='other'
            elif change=='task':finish['job_session']='other'
            elif change=='time':finish['time']+=1
            elif change=='world':finish['parking_confirmation']['world_session']='other'
            elif change=='revision':finish['parking_confirmation']['control_revision']+=1
            elif change=='pose':finish['parking_confirmation']['pos'][0]+=2
            elif change=='health':finish['snapshot']['health']=19
            elif change=='flight':finish['snapshot']['flight']=False
            else:finish['snapshot']['movement_keys']['jump']=True
            with self.subTest(change=change),self.assertRaises(ValueError):
                reconcile.validate_pending(*args,maintenance_recovery=recovery,original_parking=old)

    def test_historical_finish_does_not_relax_fresh_current_host_parking_metadata(self):
        args,recovery,old=publication_lag_fixture()
        recovery['current_parking']['supervision_safety']=None
        with self.assertRaises(ValueError):
            reconcile.validate_pending(*args,maintenance_recovery=recovery,original_parking=old)


if __name__=='__main__':unittest.main()
