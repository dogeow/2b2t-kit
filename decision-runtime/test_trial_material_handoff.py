"""A source swap retains legal SDK progress and player construction, never old stock templates."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from kit_runtime.inventory import InventorySession
from singleplayer_trial import TrialWorker as Worker
from singleplayer_trial_bridge import Paused
from trial_material_handoff import (KIND, claim_handoff, file_hash, observe_handoff,
                                    scene_bounds, validate_handoff, verify_scene)
from trial_safety_preparation import _layout
from test_trial_inventory_confirmation import NativeInventory
from test_singleplayer_trial import native_scan_fields, row


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True);path.write_text(json.dumps(value, allow_nan=False))
    return {'path':str(path),'sha256':file_hash(path)}


def full_view(state):
    view=copy.deepcopy(state['menu']);view.update(inventory=copy.deepcopy(state['inventory']),state_id=4,
        quickcraft_status=0,world_id=state['world_id'],dimension=state['dimension'],
        player_uuid=state['player_uuid'],observed_at=state['time'],game_time=state['time']//50)
    for stack in [view['cursor'],*view['slots'],*view['inventory']]:
        stack['stack_data']={'id':stack['item'],'count':stack['count']}
    return view


class ReadBridge:
    def __init__(self, state, root, registry, blocks):
        self.state=state;self.root=root;self.registry=registry;self.world='Trial';self.origin=state['pos']
        self.session=state['world_session'];self.revision=state['control_revision'];self.blocks=blocks
        self.halted=False;self.pending_mutations={};self.active=None;self.last_inventory_probe=None
        self.historical_inventory_pending={};self.requests=[]
    def read(self):
        self.state['time']=int(time.time()*1000);return copy.deepcopy(self.state)
    def request(self, op, **args):
        self.requests.append((op,args));before=self.read();request={'id':'trial-read-'+str(len(self.requests)),
            'op':op,'world_id':before['world_id'],'world_session':self.session,'dimension':before['dimension'],
            'expected_revision':self.revision,'trial_id':self.registry['trial_id'],'run_id':self.registry['run_id']}
        self.state.update(id=request['id'],last_request=request['id'],op=op,phase='done')
        result=self.read()
        if op=='scan':
            bounded=[row for row in self.blocks if all(args['min'][i]<=row['pos'][i]<=args['max'][i] for i in range(3))]
            result.update(native_scan_fields({**request,**args},self.revision,blocks=copy.deepcopy(bounded)))
        elif op=='inventory_probe':
            result['inventory_probe']={'protocol':1,'request_id':request['id'],'world_session':self.session,
                'control_revision':self.revision,'scope_current':True,'server_observed':True,
                'audit_scope':'current_state_only_not_historical_dispatch','client':full_view(result),'server':full_view(result)}
            self.last_inventory_probe={'result':result,'envelope':request,'before':before}
        else:raise AssertionError('Handoff sent a non-read action: '+op)
        return result


class SourceMaterialHandoffTests(unittest.TestCase):
    def fixture(self, game):
        game=Path(game).resolve();native=NativeInventory(game);source_bridge=native.bridge()
        # One real bridge+SDK commit exercises the same frozen contract used
        # for all 20 observed production commits; no timer receipt can settle it.
        session=InventorySession(SimpleNamespace(checked=source_bridge.request,status=source_bridge.read,
            sdk_inventory_confirmation=True,commit_inventory_click=source_bridge.commit_inventory_click))
        initial=source_bridge.read();picked=session.click(initial,11)
        session._wait(picked,0,lambda menu:menu['cursor']['count']==1 and menu['slots'][11]['count']==0,'pickup')
        sdk_id=next(iter(source_bridge.receipts))['id']
        source_run=native.registry['run_id'];reg={**native.registry,'run_id':'new-native-run'}
        current=copy.deepcopy(native.current);current.update(world_session='same-live-session',control_revision=8,
            pos=[.5,63,2.5],phase='done',op='guard',manual_movement=False,screen='',game_version='26.1.2',
            health=12.333,food=16,movement_keys={'forward':False,'back':False,'jump':False,'sneak':False},
            chopping=False,navigating=False,borer_active=False,printing=False)
        current['trial_identity'].update(run_id=reg['run_id'],process_alive=True)
        current['menu']['slots'].append({'slot':45,'item':'minecraft:air','count':0,'max_stack':1})
        current['menu']['cursor']={'item':'minecraft:air','count':0,'max_stack':1}
        current['menu']['slots'][11]={'slot':11,'item':'minecraft:air','count':0,'max_stack':1}
        current['inventory']=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(43)]
        for i,item,count in [(0,'dirt',23),(1,'dark_oak_door',3),(2,'cobblestone',45)]:
            current['inventory'][i].update(item='minecraft:'+item,count=count,max_stack=64)
            current['menu']['slots'][36+i]=copy.deepcopy({**current['inventory'][i],'slot':36+i})
        old=[{'id':'trial-old-chop','op':'chop','world_id':reg['world_id'],'trial_id':reg['trial_id'],
              'run_id':'retired-run','world_session':'retired-session','dimension':current['dimension']},
             {'id':'trial-old-inventory','op':'slot_click','world_id':reg['world_id'],'trial_id':reg['trial_id'],
              'run_id':'retired-run','world_session':'retired-session','dimension':current['dimension']}]
        plan={'schema':1,'world_id':reg['world_id'],'dimension':current['dimension'],**_layout([0,63,0]),
              'door_item':'dark_oak_door','verified':False}
        checkpoint={'schema':1,'world_id':reg['world_id'],'trial_id':reg['trial_id'],'source_run_id':source_run,
            'world_session':current['world_session'],'game_version':'26.1.2','material_baseline_id':'baseline-source',
            'unresolved_native':[],'historical_unresolved_native':old,
            'owned':{'-1,63,-1':'dirt','-1,63,0':'dirt'},'stations':{'crafting_table':[4,63,4]},
            'small_shelter':plan,'camp':None,'excluded':[[0,62,0],[-40,62,-40]],'camp_completed':False,
            'station_anchor':None,'log_drops':{},'explored':[],'tried_grids':[],'rejected_routes':[]}
        baseline={'schema':1,'source':'fresh_kit_physical_baseline','newbaseline_id':'baseline-source',
            'run_id':source_run,**{k:current[k] for k in ['world_id','world_session','dimension']},
            'trial_id':reg['trial_id'],'legacy_pending':old,'historical_effects_unresolved':True,
            'old_action_completed':False,'old_action_replayed':False,'forbidden_request_ids':[r['id'] for r in old],
            'inventory_review_verified_ids':['trial-old-inventory'],
            'inventory':[{'slot':0,'item':'minecraft:dirt','count':21}],
            'review':{'request':{'frozen_legacy':{}},'report':{'decision':'fresh_replan_allowed','historical_effects_unresolved':True}}}
        output=game/'worker';root=game/'trial';root.mkdir();cp_ref=write(output/'source/checkpoint.json',checkpoint)
        baseline_ref=write(output/'source/baseline.json',baseline)
        status_ref=write(output/'source/stopped-worker.json',{'phase':'stopped','run_id':source_run,'pid':99_999_999,
            'material_baseline_id':'baseline-source','material_baseline_session':current['world_session']})
        frozen={r['path']:r['sha256'] for r in [cp_ref,baseline_ref,status_ref]}
        for folder in ['pending','receipts']:
            p=native.root/'trial-sdk-inventory'/folder/(sdk_id+'.json');frozen[str(p)]=file_hash(p)
        # The source commit occurred in this same MCU connection; freeze the
        # exact real records with that source session for this synthetic run.
        intent_path=native.root/'trial-sdk-inventory/pending'/(sdk_id+'.json')
        receipt_path=native.root/'trial-sdk-inventory/receipts'/(sdk_id+'.json')
        intent=json.loads(intent_path.read_text());receipt=json.loads(receipt_path.read_text())
        intent['envelope']['world_session']=current['world_session'];intent['before']['world_session']=current['world_session']
        receipt['native_result']['world_session']=current['world_session'];receipt['native_result']['inventory_click_receipt']['world_session']=current['world_session']
        intent_path.write_text(json.dumps(intent));receipt['intent_sha256']=file_hash(intent_path);receipt_path.write_text(json.dumps(receipt))
        frozen[str(intent_path)]=file_hash(intent_path);frozen[str(receipt_path)]=file_hash(receipt_path)
        stopped=copy.deepcopy(current);stopped['trial_identity'].update(run_id='',process_alive=False,detail='手动移动接管')
        hid='handoff-'+'a'*32
        manifest={'schema':1,'kind':KIND,'id':hid,'world_id':reg['world_id'],'trial_id':reg['trial_id'],
            **{k:current[k] for k in ['world_session','dimension','game_version','kit_version']},
            'source_run_id':source_run,'source_worker_pid':99_999_999,'source_worker_exited':True,'source_parent_pid':777777,
            'bundle_sha256':'b'*64,'baseline':baseline_ref,'checkpoint':cp_ref,'frozen':frozen,
            'sdk_inventory_confirmed_ids':[sdk_id],'historical_pending':old,
            'lifecycle_kind':'manual_stopped_same_session','source_stopped_native':stopped,
            'source_worker_status':status_ref,'operator_current_native':stopped,
            'protected_player_work':{k:checkpoint[k] for k in ['owned','stations','small_shelter','excluded','camp']}}
        reference=write(output/'source-material-handoffs'/(hid+'.json'),manifest)
        pointer=output/'source-material-handoff.json';write(pointer,reference)
        blocks=[row((x,62,z),'grass_block') for x in range(-3,7) for z in range(-3,7)]
        blocks.extend([row((-1,63,-1),'dirt'),row((-1,63,0),'dirt'),row((4,63,4),'crafting_table')])
        bridge=ReadBridge(current,native.root,reg,blocks)
        worker=SimpleNamespace(game=game,root=root,output=output,automation=native.root,registry=reg,run_id=reg['run_id'],
            parent_pid=777777,native_start_run=reg['run_id'],command='start',bridge=bridge,legacy_pending=old,
            legacy_evidence={},legacy_journal=output/'material-review-runs'/reg['run_id']/'journal.jsonl',
            material_rebaseline=None,source_handoff_id=None,source_handoff_waiting=False,
            checkpoint_signature=None,failures={},failure_contexts={},publish=Mock(),event=Mock())
        worker.install_material_baseline=Worker.install_material_baseline.__get__(worker)
        return worker,current,manifest,pointer,reference,checkpoint

    def test_fresh_user_supplied_stock_does_not_revert_to_old_21_dirt_template(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game)
            checked=validate_handoff(worker,state,process_alive=lambda pid:False);baseline=observe_handoff(worker,checked)
            self.assertEqual(23,baseline['inventory'][0]['count']);self.assertEqual(45,baseline['inventory'][2]['count'])
            self.assertEqual([('scan'),('inventory_probe')],[op for op,args in worker.bridge.requests])
            self.assertTrue(baseline['historical_effects_unresolved']);self.assertFalse(baseline['old_action_replayed'])

    def test_installed_handoff_preserves_owned_walls_partial_house_and_distant_exclusions(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            baseline=observe_handoff(worker,checked);worker.install_material_baseline(baseline,source_handoff_checkpoint=cp)
            self.assertEqual(cp['owned'],worker.skills.owned);self.assertEqual(cp['small_shelter'],worker.skills.small_shelter)
            self.assertEqual(cp['stations'],worker.skills.stations);self.assertIn((-40,62,-40),worker.skills.excluded)
            self.assertEqual('new-native-run',worker.material_rebaseline['run_id'])

    def test_parent_connection_source_or_current_unknown_blocks_the_handoff(self):
        for kind in ['parent','session','same-run','pending','alive']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as game:
                worker,state,manifest,pointer,ref,cp=self.fixture(game)
                if kind=='parent':worker.parent_pid+=1
                if kind=='session':worker.bridge.session='new-connection'
                if kind=='same-run':worker.run_id=manifest['source_run_id']
                if kind=='pending':worker.bridge.pending_mutations={'trial-current-unknown':{}}
                with self.assertRaises(Paused):validate_handoff(worker,state,process_alive=lambda pid:kind=='alive')
                self.assertEqual([],worker.bridge.requests)

    def test_changed_prior_evidence_and_missing_sdk_commit_are_not_admitted(self):
        for kind in ['checkpoint','sdk']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as game:
                worker,state,manifest,pointer,ref,cp=self.fixture(game)
                path=Path(manifest['checkpoint']['path']) if kind=='checkpoint' else worker.automation/'trial-sdk-inventory/receipts'/(manifest['sdk_inventory_confirmed_ids'][0]+'.json')
                path.write_text('{}')
                with self.assertRaises(Paused):validate_handoff(worker,state,process_alive=lambda pid:False)

    def test_absent_manual_owned_walls_are_reconciled_only_in_the_derived_plan(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            frozen=Path(manifest['checkpoint']['path']).read_bytes()
            worker.bridge.blocks=[r for r in worker.bridge.blocks if r['pos'] not in ([-1,63,-1],[-1,63,0])]
            baseline=observe_handoff(worker,checked);derived=checked['derived_checkpoint']
            self.assertEqual({},baseline['current_owned']);self.assertEqual({},derived['owned'])
            self.assertEqual(cp['owned'],checked['checkpoint']['owned']);self.assertEqual(frozen,Path(manifest['checkpoint']['path']).read_bytes())
            self.assertEqual(cp['small_shelter'],derived['small_shelter'])
            protected={tuple(p) for p in derived['excluded']}
            self.assertTrue({tuple(p) for p in cp['small_shelter']['layout']+cp['small_shelter']['floor']}<=protected)
            self.assertEqual(2,len(baseline['reconciled_absent_owned']))
            self.assertTrue(all(r['actual']=='air' and r['attribution']=='unresolved' and r['old_placement_ack_confirmed'] is False for r in baseline['reconciled_absent_owned']))
            worker.install_material_baseline(baseline,source_handoff_checkpoint=derived)
            self.assertEqual({},worker.skills.owned);self.assertEqual(cp['small_shelter'],worker.skills.small_shelter)
            self.assertEqual(23,baseline['inventory'][0]['count'])
            self.assertEqual(['scan','inventory_probe'],[op for op,args in worker.bridge.requests])

    def test_existing_manual_owned_wall_is_preserved_beside_an_absent_wall(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            worker.bridge.blocks=[r for r in worker.bridge.blocks if r['pos']!=[-1,63,-1]]
            baseline=observe_handoff(worker,checked)
            self.assertEqual({'-1,63,0':'dirt'},baseline['current_owned'])

    def test_foreign_solid_container_and_nonreplaceable_plants_are_rejected(self):
        for name,changes in [('stone',{}),('chest',{'block_entity':True}),('short_grass',{'replaceable':False,'passable':True}),('short_grass',{'replaceable':True,'passable':True,'fluid':True})]:
            with self.subTest(name=name,changes=changes),tempfile.TemporaryDirectory() as game:
                worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
                worker.bridge.blocks=[r for r in worker.bridge.blocks if r['pos']!=[-1,63,-1]]
                worker.bridge.blocks.append({**row((-1,63,-1),name),**changes})
                with self.assertRaisesRegex(Paused,'owned block changed'):observe_handoff(worker,checked)
                self.assertEqual(['scan'],[op for op,args in worker.bridge.requests])

    def test_normal_warm_handoff_cannot_reconcile_an_absent_claimed_block(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            checked['manifest']['lifecycle_kind']='native_pause_cancel'
            worker.bridge.blocks=[r for r in worker.bridge.blocks if r['pos']!=[-1,63,-1]]
            with self.assertRaisesRegex(Paused,'owned block changed'):observe_handoff(worker,checked)

    def test_existing_grass_earth_walls_keep_their_owned_cells_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            original=Path(manifest['checkpoint']['path']).read_bytes()
            for entry in worker.bridge.blocks:
                if entry['pos'] in ([-1,63,-1],[-1,63,0]):entry['state']='Block{minecraft:grass_block}[snowy=false]'
            baseline=observe_handoff(worker,checked)
            self.assertEqual({'-1,63,-1':'grass_block','-1,63,0':'grass_block'},baseline['current_owned'])
            self.assertEqual([],baseline['reconciled_absent_owned']);self.assertEqual(2,len(baseline['observed_owned_variants']))
            self.assertEqual(original,Path(manifest['checkpoint']['path']).read_bytes())
            self.assertEqual(cp['small_shelter'],checked['derived_checkpoint']['small_shelter'])
            self.assertEqual(['scan','inventory_probe'],[op for op,args in worker.bridge.requests])

    def test_actual_64_cell_fixture_preserves_both_positive_grass_wall_cells(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/handoff-current-grass-walls.json').read_text())
        cp=fixture['checkpoint'];scan=fixture['scan'];bounds=fixture['bounds']
        world=verify_scene(cp,scan,bounds,scan['control_revision'],'fixture-save','minecraft:overworld',manual_reconcile=True)
        self.assertEqual(64,scan['scan_cells_read'])
        self.assertEqual({'9,63,-79','9,63,-78'},{r['key'] for r in world.observed_owned_variants})
        self.assertEqual([],world.reconciled_absent_owned)

    def test_manual_missing_table_rebinds_positive_current_table_and_keeps_old_point_protected(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            original=Path(manifest['checkpoint']['path']).read_bytes()
            worker.bridge.blocks=[r for r in worker.bridge.blocks if r['pos']!=[4,63,4]]
            worker.bridge.blocks.append(row((2,63,2),'crafting_table'))
            baseline=observe_handoff(worker,checked)
            self.assertEqual({'crafting_table':[2,63,2]},baseline['current_stations'])
            derived=checked['derived_checkpoint'];self.assertIn([4,63,4],derived['excluded'])
            self.assertEqual(cp['small_shelter'],derived['small_shelter']);self.assertEqual(cp['owned'],derived['owned'])
            self.assertEqual(original,Path(manifest['checkpoint']['path']).read_bytes())
            self.assertEqual('unresolved',baseline['reconciled_stations'][0]['attribution'])
            worker.install_material_baseline(baseline,source_handoff_checkpoint=derived)
            self.assertEqual({'crafting_table':[2,63,2]},worker.skills.stations)
            self.assertEqual(['scan','inventory_probe'],[op for op,args in worker.bridge.requests])

    def test_actual_396_cell_fixture_rebinds_current_cave_table_without_claiming_old_origin(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/handoff-current-cave-table.json').read_text())
        scan=fixture['scan'];world=verify_scene(fixture['checkpoint'],scan,fixture['bounds'],scan['control_revision'],
            'fixture-save','minecraft:overworld',manual_reconcile=True,position=fixture['position'])
        self.assertEqual(396,scan['scan_cells_read'])
        change=world.reconciled_stations[0];self.assertEqual([20,63,-65],change['previous'])
        self.assertEqual('air',change['actual_previous']);self.assertEqual([12,57,-66],change['current'])
        self.assertEqual('unresolved',change['attribution']);self.assertFalse(change['old_placement_ack_confirmed'])

    def test_manual_missing_station_without_a_positive_replacement_is_explicitly_missing(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            worker.bridge.blocks=[r for r in worker.bridge.blocks if r['pos']!=[4,63,4]]
            baseline=observe_handoff(worker,checked)
            self.assertEqual({},baseline['current_stations']);self.assertIsNone(baseline['reconciled_stations'][0]['current'])
            self.assertIn([4,63,4],checked['derived_checkpoint']['excluded'])

    def test_foreign_solid_at_old_station_is_never_overwritten_or_rebound(self):
        for name,extra in [('stone',{}),('chest',{'block_entity':True})]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as game:
                worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
                worker.bridge.blocks=[r for r in worker.bridge.blocks if r['pos']!=[4,63,4]]
                worker.bridge.blocks.extend([{**row((4,63,4),name),**extra},row((2,63,2),'crafting_table')])
                with self.assertRaisesRegex(Paused,'station changed'):observe_handoff(worker,checked)
                self.assertEqual(['scan'],[op for op,args in worker.bridge.requests])

    def test_incomplete_scan_cannot_make_missing_walls_mean_air(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            original=worker.bridge.request
            def request(op,**args):
                result=original(op,**args)
                if op=='scan':result['scan_cells_read']-=1
                return result
            worker.bridge.request=request
            with self.assertRaisesRegex(Paused,'scan is incomplete'):observe_handoff(worker,checked)

    def test_superseding_an_unclaimed_manifest_keeps_all_source_authority(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game)
            new=copy.deepcopy(manifest);new.update(id='handoff-'+'c'*32,bundle_sha256='d'*64,original_manifest_ref=ref)
            new['frozen'][ref['path']]=ref['sha256']
            updated=write(Path(ref['path']).parent/(new['id']+'.json'),new);write(pointer,updated)
            checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            self.assertEqual(manifest['source_run_id'],checked['manifest']['source_run_id'])
            self.assertEqual(ref,checked['manifest']['original_manifest_ref'])
            claim=worker.output/'source-material-handoff-claims'/(manifest['id']+'.json');write(claim,{'run_id':'previous-target'})
            with self.assertRaisesRegex(Paused,'claimed'):validate_handoff(worker,state,process_alive=lambda pid:False)

    def test_stock_changed_after_operator_handback_is_not_silently_rebased(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            worker.bridge.state['inventory'][2]['count']=44
            with self.assertRaisesRegex(Paused,'fresh stock'):observe_handoff(worker,checked)

    def test_the_same_manifest_cannot_grant_a_second_run(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game);checked=validate_handoff(worker,state,process_alive=lambda pid:False)
            baseline=observe_handoff(worker,checked);first=claim_handoff(worker,checked,baseline)
            self.assertFalse(first['old_action_completed']);self.assertFalse(first['old_action_replayed'])
            with self.assertRaisesRegex(Paused,'already claimed'):claim_handoff(worker,checked,baseline)

    def test_acceptance_waits_for_explicit_native_resume_before_any_material_macro(self):
        with tempfile.TemporaryDirectory() as game:
            worker,state,manifest,pointer,ref,cp=self.fixture(game)
            self.assertTrue(Worker.accept_source_material_handoff(worker,state))
            self.assertTrue(worker.source_handoff_waiting);self.assertFalse(Worker.material_replan_enabled(worker))
            self.assertEqual('waiting_material_handoff',worker.publish.call_args.args[0])
            self.assertEqual(cp['owned'],worker.skills.owned)


if __name__=='__main__':unittest.main()
