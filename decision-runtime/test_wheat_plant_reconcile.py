import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from wheat_plant_reconcile import prove,prove_after_park,reconcile_after_park,HOST,HOST_CLASS_SHA,REJECTION
from potato_farm import _key


class Tests(unittest.TestCase):
    def setUp(self):
        pos=[4,64,8];rows=[{'slot':i,'item':'minecraft:air','count':0}for i in range(43)]
        rows[5].update(item='minecraft:wheat_seeds',count=10)
        hand={'item':'minecraft:wheat_seeds','count':10}
        self.book={'world_session':'world','recent_hurt_at':1,'cells':{_key(pos):{'harvest':{'native_mining_confirmed':True,'remaining_count':0}}},
            'pending':{'operation':'plant','pos':pos,'expected_state':'Block{minecraft:farmland}[moisture=7]',
                'receipt':{'id':'one','phase':'error','detail':REJECTION,'time':10},'before_inventory':rows,
                'before_counts':{'minecraft:wheat_seeds':10},'hand_before':hand}}
        self.reply={'id':'one','phase':'error','detail':REJECTION,'time':10,'kit_version':HOST,
            'world_session':'world','dimension':'minecraft:overworld','control_revision':7,'inventory':rows,'hand':hand}
        self.event={'request_id':'one','op':'interact','phase':'error','detail':REJECTION,
            'params':{'pos':pos,'face':'up','expected_hand':'minecraft:wheat_seeds','expected_state':'Block{minecraft:farmland}[moisture=7]','task_session':'task'},
            'inventory_delta':{},'revision_before':7,'revision_after':7,'position_before':[5,66,9],'position_after':[5,66,9]}
        self.current={'world_session':'world','control_revision':7,'health':20,'recent_hurt_at':1,'screen':'',
            'manual_movement':False,'inventory':rows,'supervision_lease':{'job_session':'task'}}
        self.host={'kit_version':HOST,'class_sha256':HOST_CLASS_SHA}
    def test_exact_pre_use_rejection_has_zero_seed_debit_and_does_not_credit_planting(self):
        result=prove(self.book,self.reply,self.event,self.current,self.host)
        self.assertEqual('rejected_without_use',result['outcome']);self.assertEqual(0,result['seed_debit'])
        self.assertTrue(result['original_attempt_not_done'])
    def test_new_bottle_host_uses_its_exact_unchanged_pre_use_rejection_contract(self):
        from wheat_plant_reconcile import HOST_CONTRACTS
        self.host={'kit_version':'2026.10.10.2','class_sha256':HOST_CONTRACTS['2026.10.10.2']}
        self.reply['kit_version']='2026.10.10.2'
        self.assertEqual(0,prove(self.book,self.reply,self.event,self.current,self.host)['seed_debit'])
        self.reply['kit_version']=HOST
        with self.assertRaises(RuntimeError):prove(self.book,self.reply,self.event,self.current,self.host)
    def test_unknown_host_generic_error_mutation_or_foreign_scope_never_grants_recovery(self):
        for target,changes in [('reply',{'phase':'waiting'}),('reply',{'detail':'unknown'}),
                ('current',{'world_session':'other'}),('current',{'recent_hurt_at':2}),
                ('event',{'inventory_delta':{'minecraft:wheat_seeds':-1}}),('host',{'class_sha256':'unknown'})]:
            values={k:copy.deepcopy(getattr(self,k))for k in ('book','reply','event','current','host')}
            values[target].update(changes)
            with self.assertRaises(RuntimeError):prove(**values)

    def test_gravel_navigation_host_retains_the_exact_pre_use_bridge_contract(self):
        from wheat_plant_reconcile import HOST_CONTRACTS
        self.reply['kit_version']='2026.10.11.1'
        self.host={'kit_version':'2026.10.11.1','class_sha256':HOST_CONTRACTS['2026.10.11.1']}
        self.assertEqual(HOST_CONTRACTS['2026.10.10.3'],self.host['class_sha256'])
        self.assertEqual(0,prove(self.book,self.reply,self.event,self.current,self.host)['seed_debit'])

    def parked(self):
        self.reply.update(health=20,recent_hurt_at=1,manual_movement=False,screen='',
                          supervision_lease={'id':'lease','kind':'materials','job_session':'task',
                                             'world_session':'world','revision':7,'remote_finish':'guard'})
        current={**copy.deepcopy(self.current),'time':22,'control_revision':9,'connected':True,
                 'flight':True,'guard_armed':True,'guard_pve_only':True,'under_water':False,'pos':[5,100,9],
                 'supervision_lease':{'id':'lease','kind':'parking','job_session':'task','world_session':'world',
                                      'revision':9,'remote_finish':'guard','park_target':[5,100,9]}}
        native={'lease':'lease','job_session':'task','action':'KEEP_PVE_GUARD','time':20,
                'snapshot':{'world_session':'world'}}
        finish={**copy.deepcopy(native),'native_receipt':True,'parking_confirmation':copy.deepcopy(current)}
        return current,finish,native

    def test_unchanged_native_park_can_reconcile_the_historical_pre_use_rejection(self):
        current,finish,native=self.parked()
        result=prove_after_park(self.book,self.reply,self.event,current,self.host,finish,native)
        self.assertEqual('rejected_without_use',result['outcome'])
        self.assertTrue(result['original_rejection_frame_is_historical'])
        self.assertEqual(9,result['fresh_unchanged_parking_revision'])
        self.assertTrue(result['original_attempt_not_done'])

    def test_foreign_or_unproved_parking_and_changed_inventory_do_not_clear_original_pending(self):
        current,finish,native=self.parked();before=copy.deepcopy(self.book)
        for target,change in [('current',{'world_session':'other'}),('current',{'guard_armed':False}),
                ('current',{'pos':[7,100,9]}),('current',{'recent_hurt_at':2}),
                ('finish',{'native_receipt':False}),('native',{'lease':'other'}),('native',{'local_verified':True})]:
            values={'current':copy.deepcopy(current),'finish':copy.deepcopy(finish),'native':copy.deepcopy(native)}
            values[target].update(change)
            with self.assertRaises(RuntimeError):
                prove_after_park(self.book,self.reply,self.event,values['current'],self.host,values['finish'],values['native'])
        current['inventory'][5]['count']=9
        with self.assertRaises(RuntimeError):prove_after_park(self.book,self.reply,self.event,current,self.host,finish,native)
        self.assertEqual(before,self.book)

    def test_park_reconciliation_waits_for_distinct_frames_and_preserves_the_original_attempt(self):
        current,finish,native=self.parked();later=copy.deepcopy(current);later['time']=23
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);control=root/'control';control.mkdir()
            journal=root/'harvest.json';journal.write_text(json.dumps(self.book));original=journal.read_bytes()
            (root/'reply-one.json').write_text(json.dumps(self.reply))
            (root/'supervision-receipt-lease.json').write_text(json.dumps(native))
            (control/'stock-safety.json').write_text(json.dumps(finish))
            (control/'events.jsonl').write_text(json.dumps(self.event)+'\n')
            with patch('wheat_plant_reconcile.contract',return_value=self.host), \
                    patch('wheat_plant_reconcile.read_fresh',side_effect=[current,current,later]), \
                    patch('wheat_plant_reconcile.time.sleep'):
                result=reconcile_after_park(root,journal,root/'proof',control)
            saved=json.loads(journal.read_text())
            self.assertEqual('await_replant',saved['pending']['operation'])
            self.assertEqual('plant',saved['rejected_plant_history'][0]['original_pending']['operation'])
            self.assertEqual(original,(root/'proof/original-harvest-journal-before.json').read_bytes())
            self.assertTrue(result['original_attempt_not_done'])
