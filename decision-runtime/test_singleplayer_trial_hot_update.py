import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from material_worker_release import build
from singleplayer_trial_hot_update import (install_and_restart, load_checkpoint,
                                          restore_checkpoint, unresolved_mutations)
from singleplayer_trial import TrialSkills
from singleplayer_trial_bridge import TrialBridge
from trial_native_chop import record_chop_receipt


def setup(root):
    game = (root / 'game').resolve()
    save = game / 'saves/Trial'
    save.mkdir(parents=True)
    trial = game / 'config/twob2tkit/singleplayer-trial'
    trial.mkdir(parents=True)
    automation = game / 'config/twob2tkit/automation'
    automation.mkdir()
    reg = {'protocol': 1, 'trial_id': 'trial-a', 'run_id': 'run-a', 'world_id': str(save),
           'world_name': 'Trial', 'enabled': True, 'allow_death_respawn': True, 'goal': 'defeat_ender_dragon'}
    (trial / 'registry.json').write_text(json.dumps(reg))
    state = {'time': int(time.time() * 1000), 'connected': True, 'server': 'singleplayer',
             'world_id': str(save), 'world_name': 'Trial', 'world_session': 'world-a',
             'singleplayer_trial_protocol': 1, 'singleplayer_trial_api_protocol': 1,
             'game_mode': 'survival', 'game_version': '26.1.2', 'health': 20, 'food': 20,
             'control_revision': 3, 'last_request': 'old', 'phase': 'done', 'screen': '',
             'manual_movement': False, 'pos': [.5, 70, .5], 'player_dead': False,
             'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False},
             'trial_identity': {'registered': True, 'process_alive': True,
                                'trial_id': 'trial-a', 'run_id': 'run-a', 'world_id': str(save)}}
    source = root / 'source'
    source.mkdir()
    for file in ('material_jobs_cli.py', 'material_jobs_backend.py', 'singleplayer_trial.py',
                 'singleplayer_trial_bridge.py', 'singleplayer_experience.py', 'singleplayer_trial_cli.py',
                 'singleplayer_trial_hot_update.py', 'trial_surface_recovery.py', 'survival_cooking.py',
                 'trial_safety_preparation.py', 'trial_safety_routing.py', 'trial_native_chop.py'):
        (source / file).write_text('VALUE = "new verified worker"\n')
    (source / 'singleplayer_trial_capabilities.py').write_text('VALUE = "only registered macros"\n')
    bundle = root / 'worker.zip'
    build(source, bundle)
    installed = game / 'config/twob2tkit/material-worker'
    installed.mkdir()
    (installed / 'old.py').write_text('old source preserved')
    commands = []
    def native(unused, command):
        commands.append(command)
        state['time'] += 10
        if command == 'pause':
            state['phase'] = 'waiting'
        elif command == 'cancel':
            state['trial_identity'] = {**state['trial_identity'], 'process_alive': False, 'run_id': ''}
        elif command == 'start':
            state['trial_identity'] = {**state['trial_identity'], 'process_alive': True, 'run_id': 'run-new'}
            state['phase'] = 'done'
            (trial / 'registry.json').write_text(json.dumps({**reg, 'run_id': 'run-new'}))
        identity = dict(state['trial_identity'])
        # Native cancel retains the issuing run in its receipt even when the
        # later idle snapshot reports an exited process and an empty run.
        if command == 'cancel':
            identity['run_id'] = reg['run_id']
        return {'phase': 'done', 'trial_identity': identity}
    return game, reg, state, bundle, commands, native


def historical_hold(game, state):
    record = {'active': True, 'reason': 'old health exit', 'time': state['time'] - 60_000,
              'health': 11.5, 'escape_result': 'old obstacle', 'rise': 0.0,
              'server': 'singleplayer', 'dimension': 'minecraft:overworld', 'player': 'player-a'}
    path = game / 'config/twob2tkit/automation/safety-hold.json'
    path.write_text(json.dumps(record))
    state.update(kit_version='2026.10.7.6', dimension=record['dimension'], player_uuid=record['player'],
                 safety_hold={**{k: record[k] for k in ('reason', 'time', 'health', 'escape_result', 'rise')},
                              'active': False, 'escaping': False, 'detail': ''},
                 guard_busy=False, health_recovery_hold=False, guard_armed=True, guard_pve_only=True)
    return path, record


def verified_chop(game, reg, state):
    stock=[{'slot':slot,'item':'minecraft:air','count':0} for slot in range(36)]
    stock[0]={'slot':0,'item':'minecraft:oak_log','count':1}
    stock[1]={'slot':1,'item':'minecraft:dirt','count':2}
    before={**state,'kit_version':'2026.10.7.6','tree_survey_protocol':1,
            'dimension':'minecraft:overworld','on_ground':True,'inventory':stock,
            'chopping':False,'chopper_remaining':0,'chopper_platforms':0,'chopper_verified_trees':1}
    sent={'id':'trial-chop','op':'chop','local_trial':True,'local_survival':True,
          'world_id':reg['world_id'],'world_session':state['world_session'],
          'dimension':before['dimension'],'trial_id':reg['trial_id'],'run_id':reg['run_id'],
          'expected_revision':state['control_revision'],'item':'minecraft:oak_log','target_count':4,
          'tree_limit':1,'seconds':240}
    after=json.loads(json.dumps(before))
    after.update(id=sent['id'],last_request=sent['id'],op='chop',phase='done',
                 control_revision=sent['expected_revision']+1,time=before['time']+1)
    after['inventory'][0]['count']=7
    automation=game/'config/twob2tkit/automation'
    (automation/'request.json').write_text(json.dumps(sent))
    record_chop_receipt(automation,sent,before,after)
    state.clear();state.update(after)
    path=automation.parent/'singleplayer-trial/worker/native-chop-receipts/trial-chop.json'
    return sent,path


def mining_reply(reg, **changes):
    return {'id': 'trial-mine', 'op': 'mine_block', 'world_id': reg['world_id'],
            'world_session': 'world-a', 'server': 'singleplayer', 'phase': 'waiting',
            'trial_identity': {'trial_id': reg['trial_id'], 'run_id': reg['run_id']},
            'detail': 'mining target is occluded', 'mining_target': [3, 70, 1],
            'native_sequence': -1, 'server_ack_sequence': -1, 'outcome_pending': False,
            'server_update_seen': False, 'server_confirmed': False,
            'requested_confirmation_scope': 'single_target_server_block_update_and_native_sequence_ack',
            'confirmation_scope': 'none',
            'movement_keys': {'forward': False, 'back': False, 'jump': False, 'sneak': False}, **changes}


class HotUpdateTests(unittest.TestCase):
    def test_native_chop_ledger_confirms_exact_terminal_without_fabricating_host_reply(self):
        with tempfile.TemporaryDirectory() as temp:
            game,reg,state,bundle,commands,native=setup(Path(temp))
            sent,path=verified_chop(game,reg,state)
            mailbox=game/'config/twob2tkit/automation/request.json'
            original=mailbox.read_bytes();ledger=path.read_bytes()
            self.assertEqual([],unresolved_mutations(game,reg,state))
            self.assertFalse((mailbox.parent/'reply-trial-chop.json').exists())
            proof=install_and_restart(game,bundle,reader=lambda _:dict(state),native=native,
                import_checker=Mock(),worker_checker=lambda:False)
            self.assertEqual(['pause','cancel','start'],commands)
            self.assertTrue(proof['new_worker_native_confirmed'])
            self.assertEqual(original,mailbox.read_bytes())
            self.assertEqual(ledger,path.read_bytes())
            self.assertFalse((mailbox.parent/'reply-trial-chop.json').exists())

    def test_previous_run_chop_ledger_is_rechecked_after_new_start(self):
        with tempfile.TemporaryDirectory() as temp:
            game,reg,state,bundle,commands,native=setup(Path(temp))
            sent,path=verified_chop(game,reg,state)
            new_reg={**reg,'run_id':'run-new'}
            state['trial_identity']={**state['trial_identity'],'run_id':'run-new'}
            state['time']+=10
            self.assertEqual([],unresolved_mutations(game,new_reg,state))
            path.unlink()
            pending=unresolved_mutations(game,new_reg,state)
            self.assertEqual(1,len(pending))
            self.assertEqual(reg['run_id'],pending[0]['run_id'])
            self.assertEqual(reg['world_id'],pending[0]['world_id'])
            self.assertEqual(reg['trial_id'],pending[0]['trial_id'])
            self.assertEqual(state['dimension'],pending[0]['dimension'])

    def test_checkpoint_keeps_completed_chop_identity_after_read_only_mailbox(self):
        with tempfile.TemporaryDirectory() as temp:
            game,reg,state,bundle,commands,native=setup(Path(temp))
            sent,path=verified_chop(game,reg,state)
            checkpoint={'unresolved_native':[dict(sent)]}
            mailbox=game/'config/twob2tkit/automation/request.json'
            mailbox.write_text(json.dumps({**sent,'id':'trial-scan','op':'scan'}))
            state.update(last_request='trial-scan',op='scan',time=state['time']+1,
                         control_revision=state['control_revision']+1)
            self.assertEqual([],unresolved_mutations(game,reg,state,checkpoint))
            path.unlink()
            self.assertEqual([sent],unresolved_mutations(game,reg,state,checkpoint))

    def test_unknown_or_mismatched_chop_ledger_never_clears_pending_intent(self):
        for change in ('missing','corrupt','source','request_id','request_world','request_trial','request_run',
                       'request_session','request_dimension','native_id','native_revision','native_host',
                       'native_time','pending','platform','remaining','inventory','gained',
                       'current_time','current_revision','current_world','current_trial','current_run',
                       'current_session','current_dimension','current_manual','symlink','unsafe_host_reply'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                game,reg,state,bundle,commands,native=setup(Path(temp))
                sent,path=verified_chop(game,reg,state)
                ledger=json.loads(path.read_text())
                if change=='missing': path.unlink()
                elif change=='corrupt': path.write_text('invalid json')
                elif change=='symlink':
                    saved=path.with_suffix('.saved');path.rename(saved);path.symlink_to(saved)
                elif change=='current_time': state['time']=ledger['native_result']['time']-1
                elif change=='current_revision': state['control_revision']=ledger['native_result']['control_revision']-1
                elif change=='current_world': state['world_id']=state['world_id']+'-other'
                elif change=='current_trial': state['trial_identity']={**state['trial_identity'],'trial_id':'other'}
                elif change=='current_run': state['trial_identity']={**state['trial_identity'],'run_id':'foreign'}
                elif change=='current_session': state['world_session']='foreign'
                elif change=='current_dimension': state['dimension']='minecraft:the_nether'
                elif change=='current_manual': state['manual_movement']=True
                elif change=='unsafe_host_reply':
                    reply=game/'config/twob2tkit/automation/reply-trial-chop.json'
                    reply.write_text(json.dumps({'id':sent['id'],'op':'chop','world_session':sent['world_session'],
                                                'phase':'waiting','outcome_pending':True}))
                else:
                    if change=='source': ledger['source']='claimed_done'
                    elif change=='request_id': ledger['request']['id']='trial-other'
                    elif change=='request_world': ledger['request']['world_id']+='-other'
                    elif change=='request_trial': ledger['request']['trial_id']='other'
                    elif change=='request_run': ledger['request']['run_id']='other'
                    elif change=='request_session': ledger['request']['world_session']='other'
                    elif change=='request_dimension': ledger['request']['dimension']='minecraft:the_nether'
                    elif change=='native_id': ledger['native_result']['id']='trial-other'
                    elif change=='native_revision': ledger['native_result']['control_revision']+=1
                    elif change=='native_host': ledger['native_result']['kit_version']='2026.10.7.5'
                    elif change=='native_time': ledger['native_result']['time']=ledger['before']['time']-1
                    elif change=='pending': ledger['native_result']['outcome_pending']=True
                    elif change=='platform': ledger['native_result']['chopper_platforms']=1
                    elif change=='remaining': ledger['native_result']['chopper_remaining']=1
                    elif change=='inventory': ledger['native_result']['inventory'][0]['count']+=1
                    elif change=='gained': ledger['gained']+=1
                    path.write_text(json.dumps(ledger))
                pending=unresolved_mutations(game,reg,state)
                self.assertEqual(1,len(pending))
                self.assertEqual(sent['id'],pending[0]['id'])
                self.assertEqual(sent['run_id'],pending[0]['run_id'])
                self.assertFalse(commands)

    def test_missing_native_chop_adapter_rejects_bundle_before_pause(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game,reg,state,bundle,commands,native=setup(root)
            (root/'source/trial_native_chop.py').unlink()
            build(root/'source',bundle)
            with self.assertRaisesRegex(RuntimeError,'lifecycle modules'):
                install_and_restart(game,bundle,reader=lambda _:dict(state),native=native,
                    import_checker=Mock(),worker_checker=lambda:False)
            self.assertEqual([],commands)

    def test_start_receipt_can_precede_fresh_snapshot_without_replaying_start(self):
        with tempfile.TemporaryDirectory() as temp:
            game,reg,state,bundle,commands,native=setup(Path(temp))
            path,hold=historical_hold(game,state)
            original=path.read_bytes()
            delayed=None
            start_reads=0
            def lifecycle(unused,command):
                nonlocal delayed
                if command=='start': delayed=json.loads(json.dumps(state))
                result=native(unused,command)
                if command=='cancel': state['safety_hold']={**state['safety_hold'],'active':True}
                if command=='start': state['safety_hold']={**state['safety_hold'],'active':False}
                return result
            def reader(unused):
                nonlocal start_reads
                if delayed is not None:
                    start_reads+=1
                    if start_reads<=2: return json.loads(json.dumps(delayed))
                return dict(state)
            with patch('singleplayer_trial_hot_update.time.time',return_value=state['time']/1000+1):
                proof=install_and_restart(game,bundle,reader=reader,native=lifecycle,
                    installer=Mock(return_value={'installed':'source'}),import_checker=Mock(),
                    worker_checker=lambda:False,sleeper=lambda _:None)
            self.assertEqual(['pause','cancel','start'],commands)
            self.assertEqual(3,start_reads)
            self.assertTrue(proof['start_receipt_confirmed'])
            self.assertTrue(proof['new_worker_native_confirmed'])
            self.assertEqual('run-new',proof['after_run_id'])
            self.assertEqual(original,path.read_bytes())

    def test_delayed_start_observation_never_allows_new_hold_or_foreign_control(self):
        for change in ('disk','metadata','session','dimension','host','player','manual','keys',
                       'guard','escaping','other_run','old_worker_alive','after_receipt_time'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                game,reg,state,bundle,commands,native=setup(Path(temp))
                path,hold=historical_hold(game,state)
                delayed=None
                receipt_at=state['time']+1000
                def lifecycle(unused,command):
                    nonlocal delayed
                    if command=='start': delayed=json.loads(json.dumps(state))
                    result=native(unused,command)
                    if command=='cancel': state['safety_hold']={**state['safety_hold'],'active':True}
                    if command=='start':
                        state['safety_hold']={**state['safety_hold'],'active':False}
                        if change=='disk': path.write_text(json.dumps({**hold,'time':hold['time']+1}))
                        elif change=='metadata': delayed['safety_hold']['time']+=1
                        elif change=='session': delayed['world_session']='foreign-session'
                        elif change=='dimension': delayed['dimension']='minecraft:the_nether'
                        elif change=='host': delayed['kit_version']='other'
                        elif change=='player': delayed['player_uuid']='other'
                        elif change=='manual': delayed['manual_movement']=True
                        elif change=='keys': delayed['movement_keys']['forward']=True
                        elif change=='guard': delayed['guard_busy']=True
                        elif change=='escaping': delayed['safety_hold']['escaping']=True
                        elif change=='other_run': delayed['trial_identity']['run_id']='foreign-run'
                        elif change=='old_worker_alive': delayed['trial_identity']['process_alive']=True
                        elif change=='after_receipt_time': delayed['time']=receipt_at+1
                    return result
                def reader(unused): return json.loads(json.dumps(delayed or state))
                with patch('singleplayer_trial_hot_update.time.time',return_value=receipt_at/1000):
                    with self.assertRaises(RuntimeError):
                        install_and_restart(game,bundle,reader=reader,native=lifecycle,
                            installer=Mock(return_value={'installed':'source'}),import_checker=Mock(),
                            worker_checker=lambda:False,sleeper=lambda _:None)
                self.assertEqual(['pause','cancel','start'],commands)
                interrupted=json.loads((game/'config/twob2tkit/singleplayer-trial/hot-update-interrupted.json').read_text())
                self.assertTrue(interrupted['start_receipt_confirmed'])
                self.assertEqual('run-new',interrupted['after_run_id'])
                self.assertFalse(interrupted['automatic_retry_allowed'])

    def test_cancel_reveals_same_historical_hold_and_waits_for_exit_before_source_swap(self):
        with tempfile.TemporaryDirectory() as temp:
            game,reg,state,bundle,commands,native=setup(Path(temp))
            hold_path,hold=historical_hold(game,state)
            original=hold_path.read_bytes()
            cancelled_reads=0
            observations=[]
            def lifecycle(unused,command):
                reply=native(unused,command)
                if command=='cancel':
                    state['trial_identity']={**state['trial_identity'],'process_alive':True,'run_id':reg['run_id']}
                    state['safety_hold']={**state['safety_hold'],'active':True}
                if command=='start':
                    state['safety_hold']={**state['safety_hold'],'active':False}
                return reply
            def reader(unused):
                nonlocal cancelled_reads
                if commands and commands[-1]=='cancel':
                    cancelled_reads+=1
                    observations.append(state['trial_identity']['process_alive'])
                    if cancelled_reads>=3:
                        state['trial_identity']={**state['trial_identity'],'process_alive':False,'run_id':''}
                return dict(state)
            def installer(unused_bundle,unused_game,**kwargs):
                self.assertFalse(state['trial_identity']['process_alive'])
                self.assertGreaterEqual(cancelled_reads,3)
                self.assertFalse(kwargs['running']())
                return {'installed':'verified source only'}
            proof=install_and_restart(game,bundle,reader=reader,native=lifecycle,installer=installer,
                import_checker=Mock(),worker_checker=lambda:False,sleeper=lambda _:None)
            self.assertEqual(['pause','cancel','start'],commands)
            self.assertEqual([True,True,True],observations[:3])
            self.assertEqual(original,hold_path.read_bytes())
            self.assertTrue(proof['historical_hold_preserved'])
            self.assertEqual(hold['time'],proof['historical_hold_time'])
            self.assertFalse(proof['minecraft_restarted'])
            self.assertFalse(proof['native_actions_replayed'])

    def test_new_health_record_after_cancel_never_installs_or_restarts(self):
        for change in ('disk','native_metadata','escaping','dimension','player','version','other_run','manual',
                       'keys','guard_busy','death','screen','not_registered','server'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                game,reg,state,bundle,commands,native=setup(Path(temp))
                hold_path,hold=historical_hold(game,state)
                installer=Mock()
                def lifecycle(unused,command):
                    result=native(unused,command)
                    if command=='cancel':
                        state['safety_hold']={**state['safety_hold'],'active':True}
                        if change=='disk': hold_path.write_text(json.dumps({**hold,'time':hold['time']+1}))
                        elif change=='native_metadata': state['safety_hold']['time']+=1
                        elif change=='escaping': state['safety_hold']['escaping']=True
                        elif change=='dimension': state['dimension']='minecraft:the_nether'
                        elif change=='player': state['player_uuid']='player-b'
                        elif change=='version': state['kit_version']='2026.10.7.7'
                        elif change=='other_run': state['trial_identity']['run_id']='foreign-run'
                        elif change=='manual': state['manual_movement']=True
                        elif change=='keys': state['movement_keys']={**state['movement_keys'],'forward':True}
                        elif change=='guard_busy': state['guard_busy']=True
                        elif change=='death': state['health']=0
                        elif change=='screen': state['screen']='InventoryScreen'
                        elif change=='not_registered': state['trial_identity']['registered']=False
                        elif change=='server': state['server']='server.example'
                    return result
                with self.assertRaises(RuntimeError):
                    install_and_restart(game,bundle,reader=lambda _:dict(state),native=lifecycle,installer=installer,
                        import_checker=Mock(),worker_checker=lambda:False)
                self.assertEqual(['pause','cancel'],commands)
                installer.assert_not_called()

    def test_historical_hold_must_be_exempted_before_pause_and_match_disk_metadata(self):
        for change in ('already_active','missing_disk','symlink','different_metadata','different_player',
                       'different_dimension','different_server','different_host'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                game,reg,state,bundle,commands,native=setup(Path(temp))
                hold_path,hold=historical_hold(game,state)
                if change=='already_active': state['safety_hold']['active']=True
                elif change=='missing_disk': hold_path.unlink()
                elif change=='symlink':
                    target=hold_path.with_suffix('.saved');hold_path.rename(target);hold_path.symlink_to(target)
                elif change=='different_metadata': hold_path.write_text(json.dumps({**hold,'reason':'other exit'}))
                elif change=='different_player': hold_path.write_text(json.dumps({**hold,'player':'player-b'}))
                elif change=='different_dimension': hold_path.write_text(json.dumps({**hold,'dimension':'minecraft:the_nether'}))
                elif change=='different_server': hold_path.write_text(json.dumps({**hold,'server':'server.example'}))
                elif change=='different_host': state['kit_version']='unknown'
                installer=Mock()
                def lifecycle(unused,command):
                    result=native(unused,command)
                    if command=='cancel': state['safety_hold']={**state['safety_hold'],'active':True}
                    return result
                with self.assertRaises(RuntimeError):
                    install_and_restart(game,bundle,reader=lambda _:dict(state),native=lifecycle,installer=installer,
                        import_checker=Mock(),worker_checker=lambda:False)
                self.assertEqual([] if change=='already_active' else ['pause','cancel'],commands)
                installer.assert_not_called()

    def test_changed_hold_even_when_native_trial_exempts_it_stops_before_cancel(self):
        with tempfile.TemporaryDirectory() as temp:
            game,reg,state,bundle,commands,native=setup(Path(temp))
            path,hold=historical_hold(game,state)
            def lifecycle(unused,command):
                result=native(unused,command)
                if command=='pause': path.write_text(json.dumps({**hold,'time':hold['time']+1}))
                return result
            with self.assertRaisesRegex(RuntimeError,'record changed'):
                install_and_restart(game,bundle,reader=lambda _:dict(state),native=lifecycle,
                    import_checker=Mock(),worker_checker=lambda:False)
            self.assertEqual(['pause'],commands)

    def test_cancel_receipt_and_old_worker_exit_are_required_before_start(self):
        for change in ('receipt_run','receipt_trial','receipt_world','receipt_error','worker_alive_before_start'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                game,reg,state,bundle,commands,native=setup(Path(temp))
                historical_hold(game,state)
                checker=Mock(return_value=False)
                installer=Mock(return_value={'installed':'source'})
                def lifecycle(unused,command):
                    result=native(unused,command)
                    if command=='cancel':
                        state['safety_hold']={**state['safety_hold'],'active':True}
                        if change=='receipt_run': result['trial_identity']['run_id']='wrong'
                        elif change=='receipt_trial': result['trial_identity']['trial_id']='wrong'
                        elif change=='receipt_world': result['trial_identity']['world_id']='/other/world'
                        elif change=='receipt_error': result['phase']='error'
                    return result
                if change=='worker_alive_before_start': checker.return_value=True
                with self.assertRaises(RuntimeError):
                    install_and_restart(game,bundle,reader=lambda _:dict(state),native=lifecycle,installer=installer,
                        import_checker=Mock(),worker_checker=checker)
                self.assertEqual(['pause','cancel'],commands)
                if change!='worker_alive_before_start': installer.assert_not_called()

    def test_known_host_recovery_only_hold_allows_source_swap_without_clearing_it(self):
        with tempfile.TemporaryDirectory() as temp:
            game,reg,state,bundle,commands,native=setup(Path(temp))
            state.update(kit_version='2026.10.7.5',health=17.7,food=17,
                         guard_busy=True,health_recovery_hold=True,guard_armed=True,guard_pve_only=True)
            proof=install_and_restart(game,bundle,reader=lambda _:dict(state),native=native,
                                      import_checker=Mock(),worker_checker=lambda:False)
            self.assertEqual(['pause','cancel','start'],commands)
            self.assertTrue(state['health_recovery_hold'])
            self.assertTrue(state['guard_busy'])
            self.assertEqual(17.7,state['health'])
            self.assertFalse(proof['minecraft_restarted'])

    def test_real_or_unproven_guard_activity_still_prevents_source_swap(self):
        for changes in ({'health_recovery_hold':False},{'guard_pve_only':False},
                        {'kit_version':'unknown'},{'screen':'InventoryScreen'},
                        {'under_water':True},{'safety_hold':{'active':True}},
                        {'movement_keys':{'forward':True,'back':False,'jump':False,'sneak':False}}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as temp:
                game,reg,state,bundle,commands,native=setup(Path(temp))
                state.update(kit_version='2026.10.7.5',health=17.7,food=17,
                             guard_busy=True,health_recovery_hold=True,guard_armed=True,guard_pve_only=True)
                state.update(changes)
                with self.assertRaises(RuntimeError):
                    install_and_restart(game,bundle,reader=lambda _:dict(state),native=native,
                                        import_checker=Mock(),worker_checker=lambda:False)
                self.assertEqual([],commands)

    def test_missing_recovery_module_is_rejected_before_pause(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game,reg,state,bundle,commands,native=setup(root)
            (root/'source/trial_surface_recovery.py').unlink()
            build(root/'source',bundle)
            with self.assertRaisesRegex(RuntimeError,'lifecycle modules'):
                install_and_restart(game,bundle,reader=lambda _:dict(state),native=native,
                                    import_checker=lambda *args:None,worker_checker=lambda:False)
            self.assertEqual([],commands)

    def test_missing_dynamic_checkpoint_dependency_is_rejected_before_pause(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);game,reg,state,bundle,commands,native=setup(root)
            (root/'source/singleplayer_trial_hot_update.py').unlink()
            build(root/'source',bundle)
            with self.assertRaisesRegex(RuntimeError,'lifecycle modules'):
                install_and_restart(game,bundle,reader=lambda _:dict(state),native=native,
                                    import_checker=lambda *args:None,worker_checker=lambda:False)
            self.assertEqual([],commands)
    def test_verified_worker_swap_restarts_only_worker_and_preserves_trial_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            game, reg, state, bundle, commands, native = setup(root)
            trial = game / 'config/twob2tkit/singleplayer-trial'
            (trial / 'experience').mkdir()
            experience = trial / 'experience/private.sqlite3'
            experience.write_bytes(b'unchanged experience')
            (trial / 'worker/bootstrap').mkdir(parents=True)
            journal = trial / 'worker/journal.jsonl'
            journal.write_text('native history\n')
            (trial / 'worker/bootstrap/status.json').write_text(json.dumps({
                'world_id': reg['world_id'], 'world_name': reg['world_name'],
                'camp': [0, 70, 0], 'stations': {'crafting_table': [4, 70, 0]},
                'inventory': {'diamond': 99}, 'camp_completed': True}))
            proof = install_and_restart(game, bundle, python=Path('/usr/bin/python3'),
                reader=lambda _: dict(state), native=native, import_checker=Mock(), worker_checker=lambda: False)
            self.assertEqual(['pause', 'cancel', 'start'], commands)
            self.assertFalse(proof['minecraft_restarted'])
            self.assertFalse(proof['native_actions_replayed'])
            self.assertFalse(proof['native_completion_claimed'])
            self.assertTrue(proof['checkpoint_preserved'])
            self.assertEqual('run-new', proof['after_run_id'])
            self.assertEqual(b'unchanged experience', experience.read_bytes())
            self.assertEqual('native history\n', journal.read_text())
            self.assertEqual('old source preserved', (Path(proof['installation']['backup']) / 'old.py').read_text())
            checkpoint = json.loads((trial / 'worker/checkpoint.json').read_text())
            self.assertNotIn('inventory', checkpoint)
            self.assertNotIn('camp_completed', checkpoint)
            self.assertEqual({'crafting_table': [4, 70, 0]}, checkpoint['stations'])

    def test_server_health_hold_other_run_or_pressed_keys_never_resume(self):
        cases = ({'server': 'server.example'}, {'health': 0}, {'safety_hold': {'active': True}},
                 {'trial_identity': {'registered': True, 'process_alive': True, 'trial_id': 'trial-a', 'run_id': 'other', 'world_id': 'ignored'}})
        for changes in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as temp:
                game, reg, state, bundle, commands, native = setup(Path(temp))
                state.update(changes)
                with self.assertRaises(RuntimeError):
                    install_and_restart(game, bundle, reader=lambda _: dict(state), native=native,
                                        import_checker=Mock(), worker_checker=lambda: False)
                self.assertEqual([], commands)
                self.assertEqual('old source preserved', (game / 'config/twob2tkit/material-worker/old.py').read_text())

    def test_unknown_dispatched_mine_is_preserved_without_pause_or_install(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            automation = game / 'config/twob2tkit/automation'
            request = {'id': 'trial-mine', 'op': 'mine_block', 'local_trial': True,
                       'trial_id': reg['trial_id'], 'world_id': reg['world_id'],
                       'world_session': 'world-a', 'pos': [3, 70, 1]}
            (automation / 'request.json').write_text(json.dumps(request))
            reply = automation / 'reply-trial-mine.json'
            reply.write_text(json.dumps(mining_reply(reg, native_sequence=8, outcome_pending=True)))
            original = reply.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'Unconfirmed'):
                install_and_restart(game, bundle, reader=lambda _: dict(state), native=native,
                                    import_checker=Mock(), worker_checker=lambda: False)
            self.assertEqual([], commands)
            self.assertEqual(original, reply.read_bytes())
            self.assertTrue((game / 'config/twob2tkit/material-worker/old.py').is_file())

    def test_confirmed_zero_sequence_mine_preflight_refusal_is_not_pending_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            automation = game / 'config/twob2tkit/automation'
            (automation / 'request.json').write_text(json.dumps({'id': 'trial-mine', 'op': 'mine_block',
                'local_trial': True, 'trial_id': reg['trial_id'], 'world_id': reg['world_id'],
                'world_session': 'world-a', 'pos': [3, 70, 1]}))
            (automation / 'reply-trial-mine.json').write_text(json.dumps(mining_reply(reg)))
            self.assertEqual([], unresolved_mutations(game, reg, state))
            proof = install_and_restart(game, bundle, python='/usr/bin/python3', reader=lambda _: dict(state),
                native=native, import_checker=Mock(), worker_checker=lambda: False)
            self.assertTrue(proof['new_worker_native_confirmed'])

    def test_world_change_during_pause_stops_before_cancel_or_replace(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            def changed(unused, command):
                result = native(unused, command)
                state['world_session'] = 'foreign-world'
                return result
            with self.assertRaises(RuntimeError):
                install_and_restart(game, bundle, reader=lambda _: dict(state), native=changed,
                                    import_checker=Mock(), worker_checker=lambda: False)
            self.assertEqual(['pause'], commands)
            self.assertTrue((game / 'config/twob2tkit/material-worker/old.py').is_file())

    def test_install_failure_never_replays_start_or_native_action(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            with self.assertRaises(OSError):
                install_and_restart(game, bundle, reader=lambda _: dict(state), native=native,
                    import_checker=Mock(), worker_checker=lambda: False,
                    installer=Mock(side_effect=OSError('disk failure')))
            self.assertEqual(['pause', 'cancel'], commands)
            proof = json.loads((game / 'config/twob2tkit/singleplayer-trial/hot-update-interrupted.json').read_text())
            self.assertFalse(proof['automatic_retry_allowed'])
            self.assertFalse(proof['resume_confirmed'])


class CheckpointTests(unittest.TestCase):
    def test_second_world_never_loads_first_world_coordinates_or_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            checkpoint = game / 'config/twob2tkit/singleplayer-trial/worker/checkpoint.json'
            checkpoint.parent.mkdir()
            checkpoint.write_text(json.dumps({'schema': 1, 'world_id': '/some/other/save',
                'trial_id': reg['trial_id'], 'game_version': '26.1.2', 'camp': [999, 70, 999]}))
            self.assertIsNone(load_checkpoint(game, reg, state))

    def test_stations_and_camp_completion_require_actual_native_block_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            game, reg, state, bundle, commands, native = setup(Path(temp))
            class Bridge:
                world = reg['world_name']
                root = game / 'config/twob2tkit/automation'
                calls = []
                def __init__(self): self.state = state
                def read(self): return self.state
                def request(self, op, **args):
                    self.calls.append((op, args))
                    rows = []
                    if args['min'] == args['max'] == [4, 70, 0]:
                        rows = [{'pos': [4, 70, 0], 'state': 'Block{minecraft:crafting_table}', 'solid': True}]
                    return {'blocks': rows}
            bridge = Bridge()
            skills = TrialSkills(bridge, game)
            checkpoint = {'schema': 1, 'world_id': reg['world_id'], 'trial_id': reg['trial_id'],
                'game_version': '26.1.2', 'stations': {'crafting_table': [4, 70, 0], 'furnace': [5, 70, 0]},
                'camp': [0, 70, 0], 'camp_completed': True, 'inventory': {'diamond': 99}}
            restored = restore_checkpoint(skills, checkpoint, reg, state)
            self.assertEqual({'crafting_table': [4, 70, 0]}, skills.stations)
            self.assertIsNone(skills.camp)
            self.assertFalse(skills.camp_completed)
            self.assertFalse(restored['inventory_restored'])
            self.assertFalse(restored['native_request_replayed'])
            self.assertTrue(all(op == 'scan' for op, args in bridge.calls))


if __name__ == '__main__':
    unittest.main()
