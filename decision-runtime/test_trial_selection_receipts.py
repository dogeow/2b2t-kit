import copy
import json
from pathlib import Path
import tempfile
import unittest

from singleplayer_trial_hot_update import unresolved_mutations, install_and_restart
from trial_selection_receipts import capture_select_item_receipt, known_select_item_receipt
from test_singleplayer_trial_hot_update import isolated_legacy_setup


def selector(root):
    fixture=isolated_legacy_setup(root)
    game,reg,state,bundle,commands,native,checks,output,legacy,archive=fixture
    request={'id':'trial-selector','op':'select_item','server':'singleplayer','world_id':reg['world_id'],
        'world_session':state['world_session'],'dimension':state['dimension'],'trial_id':reg['trial_id'],
        'run_id':reg['run_id'],'local_trial':True,'local_survival':True,
        'expected_revision':state['control_revision'],'expires_at':state['time']-10_000,
        'item':'minecraft:wooden_sword','site':state['pos']}
    stock=[{'slot':slot,'item':'minecraft:air','count':0,'max_stack':1} for slot in range(43)]
    held={'item':'minecraft:wooden_sword','count':1,'max_stack':1,'durability':59,'max_durability':59}
    stock[5]={'slot':5,**held}
    menu=[{'slot':slot,'item':'minecraft:air','count':0,'max_stack':1} for slot in range(46)]
    menu[41]={'slot':41,**held}
    state.update(id=request['id'],last_request=request['id'],op='settle',phase='done',
        detail='server state available',guard_busy=False,selected_slot=5,hand=held,inventory=stock,
        menu={'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0,'max_stack':1},'slots':menu})
    original={**copy.deepcopy(state),'time':request['expires_at']-500,'native':True,'request_id':request['id']}
    source=root/'sdk-proof.json';source.write_text(json.dumps({'receipts':[original]}))
    automation=game/'config/twob2tkit/automation'
    (automation/'request.json').write_text(json.dumps(request))
    options={'reader':lambda _:copy.deepcopy(state),'wall_time':lambda:(state['time']+100)/1000}
    return fixture,request,source,options


class SelectionReceiptTests(unittest.TestCase):
    def test_copied_sdk_result_and_fresh_witness_resolve_only_selector_not_old_chop(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture,request,source,options=selector(Path(temp))
            game,reg,state,bundle,commands,native,checks,output,legacy,archive=fixture
            frozen={path:path.read_bytes() for path in (archive,output/'checkpoint.json',output/'journal.jsonl')}
            self.assertEqual(2,len(unresolved_mutations(game,reg,state,json.loads((output/'checkpoint.json').read_text()))))
            value=capture_select_item_receipt(game,source,**options)
            self.assertEqual('local_settled_selection_not_server_block_ack',value['confirmation_scope'])
            self.assertFalse(value['server_block_acknowledged'])
            self.assertEqual('settle',value['native_result']['op'])
            self.assertGreater(value['current_witness']['time'],request['expires_at'])
            self.assertFalse((game/'config/twob2tkit/automation/reply-trial-selector.json').exists())
            pending=unresolved_mutations(game,reg,state,json.loads((output/'checkpoint.json').read_text()))
            self.assertEqual([legacy['id']],[row['id'] for row in pending])
            for path,data in frozen.items():self.assertEqual(data,path.read_bytes())
            self.assertEqual(value,capture_select_item_receipt(game,source,**options))
            # Native pause leaves an already finished settle frame intact;
            # there is no active child to turn into a waiting receipt.
            def pause_completed_selector(unused,command):
                phase=state['phase']
                result=native(unused,command)
                if command=='pause':state['phase']=phase
                return result
            checks['native']=pause_completed_selector
            proof=install_and_restart(game,bundle,**checks)
            self.assertTrue(proof['legacy_material_review_preserved'])
            self.assertEqual(['pause','cancel','start'],commands)
            # A new native run still recognizes the immutable past selection,
            # while retaining the older genuinely unknown chop.
            new_reg=json.loads((game/'config/twob2tkit/singleplayer-trial/registry.json').read_text())
            self.assertEqual([legacy['id']],[row['id'] for row in unresolved_mutations(game,new_reg,state,
                json.loads((output/'checkpoint.json').read_text()))])

    def test_late_only_or_changed_native_scope_menu_hand_inputs_or_revision_stays_unknown(self):
        for change in ('late_only','proof_missing','proof_duplicate','proof_not_native','proof_revision',
                       'proof_id','proof_scope','proof_hand','current_stale','current_id','current_run',
                       'current_session','current_dimension','current_revision','current_op','current_phase',
                       'current_detail','current_hand','current_selected','menu_open','cursor','grid','menu_hand',
                       'movement','manual','child','guard','different_request_item','different_request_revision',
                       'different_op','different_host'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                fixture,request,source,options=selector(Path(temp))
                game,reg,state,bundle,commands,native,checks,output,legacy,archive=fixture
                body=json.loads(source.read_text());first=body['receipts'][0]
                if change=='late_only': first['time']=state['time']
                elif change=='proof_missing': body['receipts']=[]
                elif change=='proof_duplicate': body['receipts'].append(copy.deepcopy(first))
                elif change=='proof_not_native': first['native']=False
                elif change=='proof_revision': first['control_revision']+=1
                elif change=='proof_id': first['id']='trial-other'
                elif change=='proof_scope': first['trial_identity']['run_id']='foreign'
                elif change=='proof_hand': first['hand']['durability']-=1
                elif change=='current_stale': state['time']-=10_000;options['wall_time']=lambda:(first['time']+20_000)/1000
                elif change=='current_id': state['last_request']='trial-other'
                elif change=='current_run': state['trial_identity']['run_id']='foreign'
                elif change=='current_session': state['world_session']='foreign'
                elif change=='current_dimension': state['dimension']='minecraft:the_nether'
                elif change=='current_revision': state['control_revision']+=1
                elif change=='current_op': state['op']='select_item'
                elif change=='current_phase': state['phase']='waiting'
                elif change=='current_detail': state['detail']='not acknowledged'
                elif change=='current_hand': state['hand']['durability']-=1
                elif change=='current_selected': state['selected_slot']=4
                elif change=='menu_open': state['menu']['id']=7
                elif change=='cursor': state['menu']['cursor']={'item':'minecraft:stick','count':1}
                elif change=='grid': state['menu']['slots'][1]={'slot':1,'item':'minecraft:stick','count':1}
                elif change=='menu_hand': state['menu']['slots'][41]['count']=2
                elif change=='movement': state['movement_keys']['forward']=True
                elif change=='manual': state['manual_movement']=True
                elif change=='child': state['chopping']=True
                elif change=='guard': state['guard_busy']=True
                elif change=='different_request_item': request['item']='minecraft:stone_sword'
                elif change=='different_request_revision': request['expected_revision']+=1
                elif change=='different_op': request['op']='slot_click'
                elif change=='different_host': state['kit_version']='unknown'
                source.write_text(json.dumps(body))
                (game/'config/twob2tkit/automation/request.json').write_text(json.dumps(request))
                with self.assertRaises(RuntimeError):capture_select_item_receipt(game,source,**options)
                self.assertFalse((output/'native-selection-receipts/trial-selector.json').exists())
                self.assertFalse(commands)

    def test_fingerprint_alteration_or_other_controller_invalidates_existing_selector_ledger(self):
        for change in ('request_fingerprint','ledger_native','ledger_witness','ledger_scope','symlink','controller'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as temp:
                fixture,request,source,options=selector(Path(temp))
                game,reg,state,bundle,commands,native,checks,output,legacy,archive=fixture
                capture_select_item_receipt(game,source,**options)
                path=output/'native-selection-receipts/trial-selector.json'
                value=json.loads(path.read_text())
                if change=='request_fingerprint':
                    request['background_ok']=True
                    (game/'config/twob2tkit/automation/request.json').write_text(json.dumps(request))
                elif change=='ledger_native': value['native_result']['time']=request['expires_at']+1
                elif change=='ledger_witness': value['current_witness']['hand']['durability']=3
                elif change=='ledger_scope': value['request']['run_id']='foreign'
                elif change=='symlink':
                    saved=path.with_suffix('.saved');path.rename(saved);path.symlink_to(saved)
                elif change=='controller': state['last_request']='trial-other'
                if change in {'ledger_native','ledger_witness','ledger_scope'}:path.write_text(json.dumps(value))
                pending=unresolved_mutations(game,reg,state,json.loads((output/'checkpoint.json').read_text()))
                self.assertIn(request['id'],[row['id'] for row in pending])


if __name__=='__main__':
    unittest.main()
