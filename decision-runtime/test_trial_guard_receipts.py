import copy
import json
from pathlib import Path
import tempfile
import unittest

from singleplayer_trial_hot_update import unresolved_mutations, install_and_restart
from trial_selection_receipts import capture_guard_receipt
from test_singleplayer_trial_hot_update import isolated_legacy_setup


def guard(root,inherited='walk_path'):
    fixture=isolated_legacy_setup(root)
    game,reg,state,bundle,commands,native,checks,output,legacy,archive=fixture
    request={'id':'trial-guard-setup','op':'guard','server':'singleplayer','world_id':reg['world_id'],
        'world_session':state['world_session'],'dimension':state['dimension'],'trial_id':reg['trial_id'],
        'run_id':reg['run_id'],'local_trial':True,'local_survival':True,'pve_only':True,
        'expected_revision':state['control_revision'],'expires_at':state['time']-10_000,'site':state['pos']}
    state.update(id=request['id'],last_request=request['id'],op=inherited,phase='done',
        detail='guard modules enabled',guard_busy=False,guard_armed=True,guard_pve_only=True,
        health_recovery_hold=False,safety_hold={'active':False,'escaping':False},
        menu={'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0}})
    original={**copy.deepcopy(state),'time':request['expires_at']-500,'native':True,'request_id':request['id']}
    journal=output/'material-review-runs'/reg['run_id']/'journal.jsonl'
    event={'time':original['time']+5,'event':'legacy_review_guard_verified','trial_id':reg['trial_id'],
           'run_id':reg['run_id'],'pending':[legacy],'native_receipt':original}
    with journal.open('a') as stream:stream.write(json.dumps(event)+'\n')
    (game/'config/twob2tkit/automation/request.json').write_text(json.dumps(request))
    options={'reader':lambda _:copy.deepcopy(state),'wall_time':lambda:(state['time']+100)/1000}
    return fixture,request,journal,event,options


class GuardReceiptTests(unittest.TestCase):
    def test_completed_guard_setup_with_inherited_op_does_not_resolve_material_chop(self):
        for inherited in ('','settle','walk_path','guard'):
            with self.subTest(inherited=inherited),tempfile.TemporaryDirectory() as temp:
                fixture,request,journal,event,options=guard(Path(temp),inherited)
                game,reg,state,bundle,commands,native,checks,output,legacy,archive=fixture
                frozen={path:path.read_bytes() for path in (archive,output/'checkpoint.json',output/'journal.jsonl')}
                checkpoint=json.loads((output/'checkpoint.json').read_text())
                self.assertEqual(2,len(unresolved_mutations(game,reg,state,checkpoint)))
                value=capture_guard_receipt(game,journal,**options)
                self.assertEqual('native_local_pve_guard_setup_not_material_outcome',value['confirmation_scope'])
                self.assertFalse(value['server_block_acknowledged'])
                self.assertEqual(inherited,value['inherited_native_operation'])
                self.assertGreater(value['current_witness']['time'],request['expires_at'])
                self.assertFalse((game/'config/twob2tkit/automation/reply-trial-guard-setup.json').exists())
                self.assertEqual([legacy['id']],[row['id'] for row in unresolved_mutations(game,reg,state,checkpoint)])
                self.assertEqual(value,capture_guard_receipt(game,journal,**options))
                for path,data in frozen.items():self.assertEqual(data,path.read_bytes())
                def native_completed_guard(unused,command):
                    phase=state['phase'];result=native(unused,command)
                    if command=='pause':state['phase']=phase
                    return result
                checks['native']=native_completed_guard
                proof=install_and_restart(game,bundle,**checks)
                self.assertTrue(proof['legacy_material_review_preserved'])
                self.assertEqual(['pause','cancel','start'],commands)
                new_reg=json.loads((game/'config/twob2tkit/singleplayer-trial/registry.json').read_text())
                self.assertEqual([legacy['id']],[row['id'] for row in unresolved_mutations(game,new_reg,state,checkpoint)])

    def test_guard_requires_original_valid_window_journal_and_fresh_exact_setup(self):
        for change in ('late_only','missing_event','duplicate','not_native','wrong_event_run','wrong_event_trial',
                       'source_id','source_revision','source_flag','source_scope','source_effect',
                       'current_stale','current_id','current_run','current_session','current_dimension',
                       'current_revision','current_op_changed','current_phase','current_detail','unarmed','not_pve',
                       'busy','recovery_hold','safety_hold','escaping','movement','manual','menu','cursor',
                       'child','dead','host','request_not_pve','different_op','request_revision'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                fixture,request,journal,event,options=guard(Path(temp))
                game,reg,state,bundle,commands,native,checks,output,legacy,archive=fixture
                receipt=event['native_receipt']
                if change=='late_only': receipt['time']=state['time']
                elif change=='missing_event':event['event']='worker_wait'
                elif change=='not_native':receipt['native']=False
                elif change=='wrong_event_run':event['run_id']='foreign'
                elif change=='wrong_event_trial':event['trial_id']='foreign'
                elif change=='source_id':receipt['id']='trial-other'
                elif change=='source_revision':receipt['control_revision']+=1
                elif change=='source_flag':receipt['guard_pve_only']=False
                elif change=='source_scope':receipt['world_session']='foreign'
                elif change=='source_effect':receipt['detail']='not set up'
                elif change=='current_stale':state['time']-=10_000;options['wall_time']=lambda:(receipt['time']+20_000)/1000
                elif change=='current_id':state['last_request']='trial-other'
                elif change=='current_run':state['trial_identity']['run_id']='foreign'
                elif change=='current_session':state['world_session']='foreign'
                elif change=='current_dimension':state['dimension']='minecraft:the_nether'
                elif change=='current_revision':state['control_revision']+=1
                elif change=='current_op_changed':state['op']='settle'
                elif change=='current_phase':state['phase']='waiting'
                elif change=='current_detail':state['detail']='not set up'
                elif change=='unarmed':state['guard_armed']=False
                elif change=='not_pve':state['guard_pve_only']=False
                elif change=='busy':state['guard_busy']=True
                elif change=='recovery_hold':state['health_recovery_hold']=True
                elif change=='safety_hold':state['safety_hold']['active']=True
                elif change=='escaping':state['safety_hold']['escaping']=True
                elif change=='movement':state['movement_keys']['forward']=True
                elif change=='manual':state['manual_movement']=True
                elif change=='menu':state['menu']['id']=3
                elif change=='cursor':state['menu']['cursor']={'item':'minecraft:stick','count':1}
                elif change=='child':state['chopping']=True
                elif change=='dead':state['health']=0
                elif change=='host':state['kit_version']='unknown'
                elif change=='request_not_pve':request['pve_only']=False
                elif change=='different_op':request['op']='chop'
                elif change=='request_revision':request['expected_revision']+=1
                lines=journal.read_text().splitlines()[:-1]
                lines.append(json.dumps(event))
                if change=='duplicate':lines.append(json.dumps(event))
                journal.write_text('\n'.join(lines)+'\n')
                (game/'config/twob2tkit/automation/request.json').write_text(json.dumps(request))
                with self.assertRaises(RuntimeError):capture_guard_receipt(game,journal,**options)
                self.assertFalse((output/'native-guard-receipts/trial-guard-setup.json').exists())
                self.assertFalse(commands)

    def test_tampered_guard_ledger_or_changed_envelope_does_not_hide_unknown(self):
        for change in ('request_fingerprint','native_expiry','witness_effect','scope','symlink','other_controller'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                fixture,request,journal,event,options=guard(Path(temp))
                game,reg,state,bundle,commands,native,checks,output,legacy,archive=fixture
                capture_guard_receipt(game,journal,**options)
                path=output/'native-guard-receipts/trial-guard-setup.json';value=json.loads(path.read_text())
                if change=='request_fingerprint':
                    request['background_ok']=True
                    (game/'config/twob2tkit/automation/request.json').write_text(json.dumps(request))
                elif change=='native_expiry':value['native_result']['time']=request['expires_at']+1
                elif change=='witness_effect':value['current_witness']['guard_armed']=False
                elif change=='scope':value['request']['run_id']='foreign'
                elif change=='symlink':
                    saved=path.with_suffix('.saved');path.rename(saved);path.symlink_to(saved)
                elif change=='other_controller':state['last_request']='trial-other'
                if change in {'native_expiry','witness_effect','scope'}:path.write_text(json.dumps(value))
                checkpoint=json.loads((output/'checkpoint.json').read_text())
                self.assertIn(request['id'],[row['id'] for row in unresolved_mutations(game,reg,state,checkpoint)])


if __name__=='__main__':
    unittest.main()
