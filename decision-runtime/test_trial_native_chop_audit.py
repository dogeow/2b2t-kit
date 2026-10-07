import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from singleplayer_trial_bridge import Paused
from singleplayer_trial_hot_update import unresolved_mutations
from trial_native_chop import record_interrupted_chop_audit, known_chop_receipt


def evidence(game):
    game=Path(game).resolve();save=game/'saves/Trial';save.mkdir(parents=True)
    automation=game/'config/twob2tkit/automation';automation.mkdir(parents=True)
    zone=ZoneInfo('Asia/Taipei')
    def stamp(clock):
        return int(datetime.fromisoformat('2026-10-07T'+clock).replace(tzinfo=zone).timestamp()*1000)
    registry={'protocol':1,'enabled':True,'trial_id':'trial-a','run_id':'run-a',
        'world_id':str(save),'world_name':'Trial','allow_death_respawn':True,'goal':'defeat_ender_dragon'}
    stock=[{'slot':slot,'item':'minecraft:air','count':0} for slot in range(36)]
    stock[0]={'slot':0,'item':'minecraft:oak_log','count':2}
    stock[1]={'slot':1,'item':'minecraft:dirt','count':2}
    request={'id':'trial-abort','op':'chop','server':'singleplayer','local_trial':True,'local_survival':True,
        'world_id':str(save),'world_session':'session-a','dimension':'minecraft:overworld',
        'trial_id':'trial-a','run_id':'run-a','expected_revision':4,'item':'minecraft:oak_log',
        'target_count':3,'tree_limit':1,'seconds':240,'expires_at':stamp('16:50:02'),
        'site':[9.500,63,-73.673]}
    before={'time':stamp('17:01:38'),'connected':True,'server':'singleplayer','game_mode':'survival',
        'singleplayer_trial_protocol':1,'tree_survey_protocol':1,'kit_version':'2026.10.7.6',
        'dimension':request['dimension'],'world_id':str(save),'world_name':'Trial',
        'world_session':'session-a','control_revision':5,'last_request':request['id'],'id':request['id'],
        'trial_identity':{'registered':True,'process_alive':True,'trial_id':'trial-a','run_id':'run-a',
                          'world_id':str(save)},'phase':'running','op':'chop',
        'health':14,'food':17,'on_ground':False,'manual_movement':False,'screen':'',
        'inventory':stock,'chopping':True,'chopper_remaining':33,'chopper_platforms':0,
        'chopper_verified_trees':0,'movement_keys':{'forward':False,'back':False,'jump':False,'sneak':False}}
    after=copy.deepcopy(before)
    after.update(time=stamp('17:01:40'),phase='waiting',chopping=False,on_ground=True,chopper_remaining=0,
                 detail='singleplayer trial action paused; receipt retained')
    pause={'protocol':1,'id':'trial-api-pause','command':'pause','world_id':str(save),
           'world_session':'session-a','expected_revision':5,'expires_at':stamp('17:01:53')}
    receipt={'id':pause['id'],'protocol':1,'phase':'done','trial_identity':copy.deepcopy(before['trial_identity'])}
    log=('16:49:52 1.9.51 start player=9.500,63.000,-73.673 range=32 walk=true leaves=false pickup=true\n'
         '16:49:53 1.9.51 lock-tree logs=33 base=-14,65,-72 player=9.500,63.000,-73.673\n'
         '16:49:53 1.9.51 air-work-plan cell=BlockPos{x=-11, y=65, z=-73} floating=false coverage=33 remaining=33 nodes=33\n'
         '17:01:39 1.9.51 stop reason=当前单人试验已停止挖树 chopped=0 trees=0 loot=0\n')
    (automation/'request.json').write_text(json.dumps(request))
    return game,automation,registry,request,before,after,pause,receipt,log


class NativeChopAuditTest(unittest.TestCase):
    def test_verified_pause_audit_preserves_unknown_and_never_claims_zero_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            game,root,registry,request,before,after,pause,receipt,log=evidence(temp)
            intent=(root/'request.json').read_bytes()
            journal=root.parent/'singleplayer-trial/worker/journal.jsonl'
            journal.parent.mkdir(parents=True);journal.write_text('unknown chop retained\n')
            value=record_interrupted_chop_audit(root,request,before,after,pause,receipt,log,current=after)
            self.assertEqual('audited_native_chop_interruption',value['outcome'])
            self.assertFalse(value['native_completed'])
            self.assertFalse(value['zero_blocks_verified'])
            self.assertEqual(0,value['native_counters']['chopped_logs'])
            self.assertEqual(intent,(root/'request.json').read_bytes())
            self.assertEqual('unknown chop retained\n',journal.read_text())
            self.assertFalse((root/'reply-trial-abort.json').exists())
            pending=unresolved_mutations(game,registry,after)
            self.assertEqual(1,len(pending))
            self.assertIsNone(known_chop_receipt(game,registry,pending[0],after))
            self.assertEqual(value,record_interrupted_chop_audit(root,request,before,after,pause,receipt,log,current=after))

    def test_changed_scope_pause_inventory_inputs_or_log_rejects_without_audit_file(self):
        for change in ('no_pause_request','wrong_pause_id','wrong_pause_command','pause_error','pause_trial',
                       'pause_run','pause_world','pause_session','pause_revision','before_id','after_id',
                       'after_session','after_run','after_revision','after_stopped','after_ground',
                       'after_inventory','partial_inventory','before_platform','after_platform',
                       'after_keys','after_manual','after_screen','after_dead','after_trees',
                       'current_foreign','current_revision','current_inventory','missing_current',
                       'log_missing_start','log_missing_stop','log_duplicate_start','log_extra_event',
                       'log_chopped','log_trees','log_loot','log_time','log_site','log_locked_count','log_floating'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                game,root,registry,request,before,after,pause,receipt,log=evidence(temp)
                current=copy.deepcopy(after)
                if change=='no_pause_request': pause={}
                elif change=='wrong_pause_id': receipt['id']='trial-api-other'
                elif change=='wrong_pause_command': pause['command']='cancel'
                elif change=='pause_error': receipt['phase']='error'
                elif change=='pause_trial': receipt['trial_identity']['trial_id']='foreign'
                elif change=='pause_run': receipt['trial_identity']['run_id']='foreign'
                elif change=='pause_world': pause['world_id']+='-other'
                elif change=='pause_session': pause['world_session']='foreign'
                elif change=='pause_revision': pause['expected_revision']+=1
                elif change=='before_id': before['id']='trial-other'
                elif change=='after_id': after['last_request']='trial-other'
                elif change=='after_session': after['world_session']='foreign'
                elif change=='after_run': after['trial_identity']['run_id']='foreign'
                elif change=='after_revision': after['control_revision']+=1
                elif change=='after_stopped': after['phase']='stopped'
                elif change=='after_ground': after['on_ground']=False
                elif change=='after_inventory': after['inventory'][0]['count']+=1
                elif change=='partial_inventory': after['inventory'].pop()
                elif change=='before_platform': before['chopper_platforms']=1
                elif change=='after_platform': after['chopper_platforms']=1
                elif change=='after_keys': after['movement_keys']['forward']=True
                elif change=='after_manual': after['manual_movement']=True
                elif change=='after_screen': after['screen']='InventoryScreen'
                elif change=='after_dead': after['health']=0
                elif change=='after_trees': after['chopper_verified_trees']=1
                elif change=='current_foreign': current['trial_identity']['run_id']='foreign'
                elif change=='current_revision': current['control_revision']+=1
                elif change=='current_inventory': current['inventory'][1]['count']+=1
                elif change=='missing_current': current=None
                elif change=='log_missing_start': log='\n'.join(log.splitlines()[1:])+'\n'
                elif change=='log_missing_stop': log='\n'.join(log.splitlines()[:-1])+'\n'
                elif change=='log_duplicate_start': log=log.splitlines()[0]+'\n'+log
                elif change=='log_extra_event': log=log.replace('17:01:39','16:50:00 1.9.51 periodic action=MINE\n17:01:39')
                elif change=='log_chopped': log=log.replace('chopped=0','chopped=1')
                elif change=='log_trees': log=log.replace('trees=0','trees=1')
                elif change=='log_loot': log=log.replace('loot=0','loot=1')
                elif change=='log_time': log=log.replace('17:01:39','16:55:00')
                elif change=='log_site': log=log.replace('start player=9.500','start player=9.600')
                elif change=='log_locked_count': log=log.replace('lock-tree logs=33','lock-tree logs=32')
                elif change=='log_floating': log=log.replace('floating=false','floating=true')
                with self.assertRaises(Paused):
                    record_interrupted_chop_audit(root,request,before,after,pause,receipt,log,current=current)
                self.assertFalse((root.parent/'singleplayer-trial/worker/native-chop-interruptions/trial-abort.json').exists())

    def test_real_manual_takeover_artifact_cannot_be_relabelled_as_pause_termination(self):
        with tempfile.TemporaryDirectory() as temp:
            game,root,registry,request,before,after,pause,receipt,log=evidence(temp)
            # A later saved frame after manual takeover is not the missing
            # native pause frame, even when it still names the same chop.
            after.update(phase='stopped',detail='手动移动接管',control_revision=7,on_ground=False)
            after['trial_identity'].update(run_id='',process_alive=False)
            with self.assertRaises(Paused):
                record_interrupted_chop_audit(root,request,before,after,pause,receipt,log,current=after)


if __name__=='__main__':
    unittest.main()
