import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import time
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from singleplayer_trial_bridge import Paused
from trial_inventory_audit import (archive_failed_pickup,file_hash,historical_pending,
                                   validate_inventory_review)


def fixture(root):
    game=(root/'game').resolve();world=str(game/'saves/Trial')
    output=game/'config/twob2tkit/singleplayer-trial/worker';output.mkdir(parents=True)
    automation=output.parent.parent/'automation';automation.mkdir()
    original={'id':'trial-old-pickup','op':'slot_click','server':'singleplayer','world_id':world,
        'world_session':'old-session','trial_id':'trial-a','run_id':'old-run','dimension':'minecraft:overworld',
        'local_trial':True,'local_survival':True,'expected_revision':66,'expires_at':1500,
        'menu_id':0,'slot':11,'kind':'pickup','button':0,'expected_item':'minecraft:dark_oak_log',
        'expected_count':1,'expected_cursor':'minecraft:air','expected_cursor_count':0}
    inventory=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(43)]
    inventory[0].update(item='minecraft:dirt',count=23)
    inventory[11].update(item='minecraft:dark_oak_log',count=1)
    menu={'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0,'max_stack':1},
          'slots':[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(46)]}
    menu['slots'][11].update(item='minecraft:dark_oak_log',count=1)
    failed={'time':2000,'world_id':world,'world_session':'old-session','dimension':'minecraft:overworld',
        'player_uuid':'player-a','id':original['id'],'last_request':original['id'],'op':'settle','phase':'done',
        'detail':'server state available','control_revision':66,'inventory':inventory,'menu':menu,
        'trial_identity':{'world_id':world,'trial_id':'trial-a','run_id':'old-run','process_alive':True}}
    (automation/'request.json').write_text(json.dumps(original))
    manifest=archive_failed_pickup(game,failed,old_worker_pid=401,old_jvm_pid=402)
    registry={'world_id':world,'trial_id':'trial-a','run_id':'new-run'}
    state={'time':3000,'world_id':world,'world_session':'new-session','dimension':'minecraft:overworld',
           'control_revision':3,'inventory':copy.deepcopy(inventory),'menu':copy.deepcopy(menu)}
    pending,frozen=historical_pending(output,registry,state)
    def artifact(name,value):
        path=(root/(name+'.json')).resolve();path.write_text(json.dumps(value));return {'path':str(path),'sha256':file_hash(path)}
    saved={**copy.deepcopy(failed),'chopping':False,'navigating':False,'printing':False,'borer_active':False,
           'trial_identity':{**failed['trial_identity'],'process_alive':False,'run_id':''}}
    disconnected={**saved,'connected':False}
    quit_reply={'phase':'done','trial_identity':copy.deepcopy(saved['trial_identity'])}
    log=(root/'save.log').resolve();log.write_text('Saving players\nSaving worlds\n(world): All chunks are saved\n'
        '(DIM-1): All chunks are saved\n(DIM1): All chunks are saved\nAll dimensions are saved\n')
    exit_state={'exit_code':0,'exit_type':'NORMAL','old_jvm_alive_now':False,'old_jvm_pid':402,
        'world_id':world,'world_session':'old-session','run_id':'old-run',
        'save_log':{'path':str(log),'sha256':file_hash(log)}}
    side={'id':0,'type':'InventoryMenu','state_id':0,'quickcraft_status':0,
          'world_id':world,'dimension':'minecraft:overworld','player_uuid':'player-a',
          'observed_at':3000,'game_time':12345,
          'cursor':copy.deepcopy(menu['cursor']),'slots':copy.deepcopy(menu['slots']),
          'inventory':copy.deepcopy(inventory)}
    for row in [side['cursor'],*side['slots'],*side['inventory']]:
        row['stack_data']={'id':row['item'],'count':row['count'],'components':{}}
    probe_request={'id':'trial-inventory-probe','op':'inventory_probe','world_id':world,'world_session':'new-session',
        'dimension':'minecraft:overworld','server':'singleplayer','run_id':'new-run','trial_id':'trial-a',
        'expected_revision':3,'expires_at':13000}
    probe={'id':probe_request['id'],'op':'inventory_probe','phase':'done','outcome_pending':False,'time':3000,'inventory_probe':{'protocol':1,
        'request_id':probe_request['id'],'world_session':'new-session','control_revision':3,'scope_current':True,
        'server_observed':True,'audit_scope':'current_state_only_not_historical_dispatch',
        'client':copy.deepcopy(side),'server':copy.deepcopy(side)}}
    review={'schema':1,'kind':'operator_retired_inventory_review','decision':'fresh_inventory_replan_allowed',
        'historical_effects_unresolved':True,'old_action_completed':False,'old_action_replayed':False,
        'old_worker_pid':401,'old_jvm_pid':402,'manifest':manifest,'artifacts':{
            'before_save':artifact('before',saved),'after_save':artifact('after',disconnected),
            'normal_quit':artifact('quit',quit_reply),'normal_exit':artifact('exit',exit_state)}}
    reference=artifact('review',review)
    worker=SimpleNamespace(registry=registry,run_id='new-run',parent_pid=900,legacy_pending=pending,
                           inventory_review_probe=probe,inventory_review_probe_request=probe_request)
    return worker,state,reference,review,output,original,frozen


class InventoryAuditTests(unittest.TestCase):
    def test_saved_native_quit_and_hmcl_stop_allow_replan_without_inventing_exit_code(self):
        for change in (None,'missing_save','quit_command','quit_id','quit_expiry','no_stop','stop_pid','stop_scope',
                       'stop_time','stop_hash','old_alive','new_probe_missing'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);worker,state,reference,review,output,original,frozen=fixture(root)
                def artifact(name,value):
                    path=(root/(name+'.json')).resolve();path.write_text(json.dumps(value));return {'path':str(path),'sha256':file_hash(path)}
                quit_ref=review['artifacts']['normal_quit'];quit_path=Path(quit_ref['path'])
                quit_reply=json.loads(quit_path.read_text());quit_reply.update(protocol=1,id='trial-api-retire')
                quit_path.write_text(json.dumps(quit_reply));quit_ref['sha256']=file_hash(quit_path)
                request={'protocol':1,'command':'quit_game','id':quit_reply['id'],'expires_at':17000}
                clock=datetime.fromtimestamp(2.5,ZoneInfo('Asia/Taipei')).strftime('%H:%M:%S')
                log=(root/'hmcl-stop.txt').resolve();log.write_text(f'[{clock}] ProcessStoppedEvent\n')
                stopped={'source':'hmcl_process_stopped_event_excerpt','event':'ProcessStoppedEvent','old_jvm_pid':402,
                    'world_id':original['world_id'],'world_session':original['world_session'],'run_id':original['run_id'],
                    'stopped_at':2500,'log_excerpt':{'path':str(log),'sha256':file_hash(log)}}
                exit_ref=review['artifacts']['normal_exit'];exit_path=Path(exit_ref['path']);exit_state=json.loads(exit_path.read_text())
                exit_state.update(source='verified_native_saved_quit_and_terminated_process',exit_code=None,exit_type='unobserved')
                alive=lambda _:False
                if change=='quit_command':request['command']='open_world'
                elif change=='quit_id':request['id']='other'
                elif change=='quit_expiry':request['expires_at']=1000
                elif change=='no_stop':log.write_text('launcher still running\n');stopped['log_excerpt']['sha256']=file_hash(log)
                elif change=='stop_pid':stopped['old_jvm_pid']=777
                elif change=='stop_scope':stopped['world_session']='other'
                elif change=='stop_time':stopped['stopped_at']=1000
                elif change=='stop_hash':stopped['log_excerpt']['sha256']='0'*64
                elif change=='old_alive':alive=lambda pid:pid==402
                elif change=='new_probe_missing':worker.inventory_review_probe=None
                elif change=='missing_save':
                    save=Path(exit_state['save_log']['path']);save.write_text('Saving players only\n');exit_state['save_log']['sha256']=file_hash(save)
                exit_state.update(quit_request=artifact('quit-request',request),launcher_stopped=artifact('stopped',stopped))
                exit_path.write_text(json.dumps(exit_state));exit_ref['sha256']=file_hash(exit_path)
                path=Path(reference['path']);path.write_text(json.dumps(review));reference['sha256']=file_hash(path)
                if change:
                    with self.assertRaises(Paused):validate_inventory_review(worker,reference,state,alive)
                else:
                    value=validate_inventory_review(worker,reference,state,alive)
                    self.assertTrue(value['historical_effects_unresolved'])
                    self.assertIsNone(json.loads(exit_path.read_text())['exit_code'])
                    self.assertFalse(value['old_action_completed'])

    def test_real_new_start_discovers_mailbox_pickup_manifest_and_old_chop_without_replay(self):
        from test_trial_legacy_material_review import LegacyMaterialReviewTests
        from trial_material_rebaseline import submit_review
        with tempfile.TemporaryDirectory() as game:
            worker,current,registry,chop,old_files,chop_bytes,dispatched=LegacyMaterialReviewTests.fixture(self,game)
            chop_archive=worker.output/'legacy-material-intents'/(chop['id']+'.request.json')
            chop_archive.parent.mkdir(parents=True);chop_archive.write_bytes(chop_bytes)
            original={'id':'trial-old-pickup','op':'slot_click','server':'singleplayer','world_id':registry['world_id'],
                'world_session':'old-inventory-session','trial_id':registry['trial_id'],'run_id':'old-inventory-run',
                'dimension':'minecraft:overworld','local_trial':True,'local_survival':True,'expected_revision':66,
                'expires_at':1000,'menu_id':0,'slot':11,'kind':'pickup','button':0,
                'expected_item':'minecraft:dark_oak_log','expected_count':1,'expected_cursor':'minecraft:air','expected_cursor_count':0}
            inventory=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(43)]
            inventory[0].update(item='minecraft:dirt',count=23);inventory[11].update(item='minecraft:dark_oak_log',count=1)
            menu={'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0},
                  'slots':[{'slot':i,'item':'minecraft:air','count':0} for i in range(46)]}
            menu['slots'][11].update(item='minecraft:dark_oak_log',count=1)
            failed={**copy.deepcopy(current),'id':original['id'],'last_request':original['id'],'op':'settle','phase':'done',
                'detail':'server state available','control_revision':66,'world_session':original['world_session'],
                'trial_identity':{**current['trial_identity'],'run_id':original['run_id']},'inventory':inventory,'menu':menu}
            content=(json.dumps(original,indent=3)+'\n').encode()
            (worker.automation/'request.json').write_bytes(content)
            manifest=archive_failed_pickup(game,failed,old_worker_pid=401,old_jvm_pid=402)
            # Real host initialization adopts the existing mailbox ID as its
            # request cursor and never re-dispatches that historical envelope.
            current.update(last_request=original['id'],id=original['id'])
            actual_reader=worker.reader
            def reader(root):
                mailbox=json.loads((worker.automation/'request.json').read_text())
                if mailbox['id']==original['id']:
                    current['time']=int(time.time()*1000);return copy.deepcopy(current)
                return actual_reader(root)
            worker.reader=reader
            worker.cycle()
            self.assertEqual({'chop','slot_click'},{row['op'] for row in worker.legacy_pending})
            inv=next(row for row in worker.legacy_pending if row['op']=='slot_click')
            self.assertEqual(manifest['path'],inv['inventory_manifest'])
            self.assertEqual(['guard'],[row['op'] for row in dispatched])
            self.assertEqual(content,(worker.output/'legacy-material-intents'/(original['id']+'.request.json')).read_bytes())
            for path,data in old_files.items():self.assertEqual(data,path.read_bytes())
            report=worker.output/'test-chop-report.json';report.write_text('{}')
            inventory_report=worker.output/'test-inventory-review.json';inventory_report.write_text('{}')
            with patch('decisions.status',return_value=copy.deepcopy(current)):
                request=submit_review(game,report,inventory_review=inventory_report)
            expected={str(path):digest for path,digest in worker.legacy_evidence.items()}
            expected[str(chop_archive)]=file_hash(chop_archive)
            self.assertEqual(expected,request['frozen_legacy'])

    def test_new_physical_stock_review_preserves_historical_unknown_not_done(self):
        with tempfile.TemporaryDirectory() as temp:
            worker,state,reference,review,output,original,frozen=fixture(Path(temp))
            before={path:path.read_bytes() for path in frozen}
            value=validate_inventory_review(worker,reference,state,lambda _:False)
            self.assertEqual(original['id'],value['request_id'])
            self.assertTrue(value['historical_effects_unresolved'])
            self.assertFalse(value['old_action_completed']);self.assertFalse(value['old_action_replayed'])
            for path,data in before.items():self.assertEqual(data,path.read_bytes())
            self.assertFalse((output.parent.parent/'automation'/('reply-'+original['id']+'.json')).exists())

    def test_partial_or_different_server_cursor_grid_stock_codec_or_scope_never_admits(self):
        for change in ('cursor','grid','stock','dirt22','partial','codec','menu_slot_codec','quickcraft','probe_id',
                       'request_id','revision','run','trial','session','world','dimension','stale','scope_current',
                       'server_missing','historical_claim','old_alive','exit_pid','exit_scope','save_log'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                worker,state,reference,review,output,original,frozen=fixture(Path(temp))
                probe=worker.inventory_review_probe;server=probe['inventory_probe']['server']
                alive=lambda _:False
                if change=='cursor':server['cursor'].update(item='minecraft:dark_oak_log',count=1)
                elif change=='grid':server['slots'][1].update(item='minecraft:dark_oak_log',count=1)
                elif change=='stock':server['inventory'][11]['count']=0
                elif change=='dirt22':server['inventory'][0]['count']=22
                elif change=='partial':server['inventory'].pop()
                elif change=='codec':server['inventory'][11]['stack_data']['components']['custom_data']='changed'
                elif change=='menu_slot_codec':server['slots'][11]['stack_data']['components']['custom_data']='changed'
                elif change=='quickcraft':server['quickcraft_status']=1
                elif change=='probe_id':probe['id']='foreign'
                elif change=='request_id':probe['inventory_probe']['request_id']='foreign'
                elif change=='revision':probe['inventory_probe']['control_revision']=4
                elif change=='run':worker.inventory_review_probe_request['run_id']='foreign'
                elif change=='trial':worker.inventory_review_probe_request['trial_id']='foreign'
                elif change=='session':probe['inventory_probe']['world_session']='foreign'
                elif change=='world':server['world_id']='/other/world'
                elif change=='dimension':server['dimension']='minecraft:the_nether'
                elif change=='stale':probe['time']=0;state['time']=5000
                elif change=='scope_current':probe['inventory_probe']['scope_current']=False
                elif change=='server_missing':probe['inventory_probe']['server_observed']=False
                elif change=='historical_claim':review['old_action_completed']=True
                elif change=='old_alive':alive=lambda pid:pid==402
                elif change in ('exit_pid','exit_scope','save_log'):
                    ref=review['artifacts']['normal_exit'];path=Path(ref['path']);value=json.loads(path.read_text())
                    if change=='exit_pid':value['old_jvm_pid']=999
                    elif change=='exit_scope':value['world_session']='foreign'
                    else:
                        log=Path(value['save_log']['path']);log.write_text('Saving players only\n');value['save_log']['sha256']=file_hash(log)
                    path.write_text(json.dumps(value));ref['sha256']=file_hash(path)
                path=Path(reference['path']);path.write_text(json.dumps(review));reference['sha256']=file_hash(path)
                with self.assertRaises(Paused):validate_inventory_review(worker,reference,state,alive)

    def test_same_connection_or_modified_manifest_is_not_historical_admission(self):
        with tempfile.TemporaryDirectory() as temp:
            worker,state,reference,review,output,original,frozen=fixture(Path(temp))
            state['world_session']=original['world_session']
            with self.assertRaises(Paused):historical_pending(output,worker.registry,state)
            manifest=Path(review['manifest']['path']);value=json.loads(manifest.read_text());value['old_action_completed']=True
            manifest.write_text(json.dumps(value))
            with self.assertRaises(Paused):historical_pending(output,worker.registry,{'world_session':'new-session'})


if __name__=='__main__':unittest.main()
