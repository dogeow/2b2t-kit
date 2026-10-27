from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from anvil_preview_refusal import observable, DETAIL
from village_queue import VillageQueue


def fixture():
    left = {'item': 'minecraft:wooden_shovel', 'count': 1, 'durability': 59, 'slot': 4}
    right = {'item': 'minecraft:enchanted_book', 'count': 1, 'slot': 5,
             'stored_enchantments': [{'id': 'minecraft:silk_touch', 'level': 1}]}
    c = dict(id='preview', action='anvil_enchant_preview', pos=[1,65,2], face='south',
             left_slot=4, right_slot=5, expected_left=left, expected_right=right,
             expected_enchantments={'minecraft:silk_touch': 1})
    err = dict(error=DETAIL, native_inflight=None, unconfirmed_native_request=None, last_request='r')
    b = dict(complete=False, pending={'stage':'open_owned_anvil'}, output_clicks=0,
             experience_spent=0, world_session='w', task_session='t', anvil=c['pos'],
             left=left, right=right, expected_enchantments=c['expected_enchantments'],
             input_source_slots={'left':4, 'right':5})
    e = dict(op='interact', phase='error', detail=DETAIL, request_id='r', world_session='w',
             params=dict(task_session='t', pos=c['pos'], face='south',
                         expected_state='Block{minecraft:anvil}[facing=south]',
                         expected_hand='minecraft:netherite_sword'),
             inventory_delta={}, position_before=[1,65,4], position_after=[1,65,4],
             revision_before=3, revision_after=3, health_before=20, health_after=20)
    r = dict(id='r', phase='error', detail=DETAIL, world_session='w', pos=[1,65,4], control_revision=3)
    s = dict(last_request='r', world_session='w', pos=[1,65,4], control_revision=3, health=20,
             connected=True, manual_movement=False, screen='', movement_keys={},
             menu={'type':'InventoryMenu', 'id':0, 'cursor':{'count':0}}, inventory=deepcopy([left,right]))
    return deepcopy([c,err,b,e,r,s])


class RefusalTests(unittest.TestCase):
    def test_only_unchanged_pre_window_refusal_is_observable(self):
        self.assertTrue(observable(*fixture(), 'w', 't'))
        for change in ('opening','input','unknown','pending','move','book','face','health','keys','menu','request','delta'):
            c,err,b,e,r,s = fixture()
            if change=='opening': b['menu_id']=4
            elif change=='input': b['pending']={'stage':'place_left'}
            elif change=='unknown': err['unconfirmed_native_request']='r'
            elif change=='pending': r['outcome_pending']=True
            elif change=='move': s['pos']=[2,65,4]
            elif change=='book': s['inventory'][1]['stored_enchantments'][0]['id']='minecraft:mending'
            elif change=='face': e['params']['face']='up'
            elif change=='health': s['health']=19
            elif change=='keys': s['movement_keys']['forward']=True
            elif change=='menu': s['screen']='AnvilScreen'
            elif change=='request': s['last_request']='different'
            elif change=='delta': e['inventory_delta']={'minecraft:enchanted_book':-1}
            with self.subTest(change=change):
                self.assertFalse(observable(c,err,b,e,r,s,'w','t'))

    def test_queue_only_sends_snapshot_and_preserves_failed_journals(self):
        for unsafe in (False,True):
            with tempfile.TemporaryDirectory() as folder:
                q=VillageQueue.__new__(VillageQueue); q.out=Path(folder);q.root=q.out/'runtime'
                q.root.mkdir();q.world='w';q.lease={'job_session':'t'}
                c,err,b,e,r,s=fixture()
                if unsafe: b['opening_request']='possibly-opened'
                d=q.out/c['id'];(d/'actual-zero-xp-anvil-preview').mkdir(parents=True)
                (q.out/'control').mkdir()
                files={q.out/'command.json':c,d/'error.json':err,
                       d/'actual-zero-xp-anvil-preview/preview.json':b,
                       q.root/'reply-r.json':r}
                for p,v in files.items():p.write_text(json.dumps(v))
                (q.out/'control/events.jsonl').write_text(json.dumps(e)+'\n')
                before={p:p.read_bytes() for p in files};sent=[]
                q.status=lambda:s
                def native(op):
                    self.assertEqual(q._anvil_preview_open_read,'preview')
                    sent.append(op);return {'id':'snapshot-r'}
                q.native=native
                if unsafe:
                    with self.assertRaises(RuntimeError):q.observe_unopened_anvil_preview()
                    self.assertEqual(sent,[])
                else:
                    q.observe_unopened_anvil_preview()
                    self.assertEqual(sent,['snapshot']);self.assertIsNone(q._anvil_preview_open_read)
                    proof=json.loads((q.out/'anvil-preview-open-refusal-observation.json').read_text())
                    self.assertEqual(proof['output_clicks'],0)
                    self.assertFalse(proof['original_request_replayed'])
                self.assertEqual(before,{p:p.read_bytes() for p in files})


if __name__=='__main__':unittest.main()
