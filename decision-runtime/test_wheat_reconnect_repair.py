import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from material_jobs.wheat_reconnect_repair import historical_removal,run
from material_jobs.protocol import JobBlocked
from potato_farm import FarmWait


class HistoricalRemovalTest(unittest.TestCase):
    def setUp(self):
        self.receipt={'id':'materials-old','world_session':'old','phase':'done','server_confirmed':True,
            'outcome_pending':False,'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
            'server_update_seen':True,'server_observed_state':'Block{minecraft:air}',
            'native_sequence':36,'server_ack_sequence':36,'mining_target':[27,65,70]}
        self.book={'world_session':'old','pending':{'operation':'await_loot','native_mining_confirmed':True,
            'crop_removed':True,'pos':[27,64,70],'native_mining_receipt':copy.deepcopy(self.receipt)}}
        self.reply={**self.receipt,'player_uuid':'player','server':'simpcraft.com:25565','dimension':'minecraft:overworld'}
        self.state={'world_session':'new','player_uuid':'player','server':'simpcraft.com','dimension':'minecraft:overworld'}

    def test_exact_historical_server_removal_can_authorize_only_current_cell_inspection(self):
        before=copy.deepcopy(self.book)
        pending,pos=historical_removal(self.book,self.reply,self.state)
        self.assertEqual([27,64,70],pos);self.assertEqual('await_loot',pending['operation'])
        self.assertEqual(before,self.book)

    def test_unknown_mining_planting_or_other_player_cannot_authorize_repair(self):
        cases=[('book',{'pending':{**self.book['pending'],'operation':'plant'}}),
               ('book',{'pending':{**self.book['pending'],'native_mining_confirmed':False}}),
               ('reply',{'server_confirmed':False}),('reply',{'outcome_pending':True}),
               ('reply',{'server_ack_sequence':35}),('reply',{'mining_target':[28,65,70]}),
               ('state',{'player_uuid':'other'}),('state',{'world_session':'old'}),
               ('state',{'server':'another.server'})]
        for target,change in cases:
            values={'book':copy.deepcopy(self.book),'reply':copy.deepcopy(self.reply),'state':copy.deepcopy(self.state)}
            values[target].update(change)
            with self.subTest(target=target,change=change),self.assertRaises(JobBlocked):historical_removal(**values)


class CurrentRestorationTest(HistoricalRemovalTest):
    def setUp(self):
        super().setUp()
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.journal=self.root/'old-harvest.json'
        self.book['pending'].update(receipt={'id':'materials-old'},before_counts={'minecraft:wheat':1},
            observed_drop_totals={'minecraft:wheat':1},current_loot=[],owned_loot=[])
        self.journal.write_text(json.dumps(self.book))
        (self.root/'reply-materials-old.json').write_text(json.dumps(self.reply))
        self.registry=self.root/'farm'/'registry.json';self.registry.parent.mkdir()
        self.registry.write_text(json.dumps({'scope':{'server':'simpcraft.com','layout':{'crop':'wheat'}}}))
        self.pointer=self.registry.parent/'harvest-active.json'
        self.pointer.write_text(json.dumps({'journal':str(self.journal)}))
        self.original=self.journal.read_bytes();self.original_pointer=self.pointer.read_bytes()
        self.state.update(pos=[27.5,65.6,70.5],inventory=[{'slot':0,'item':'minecraft:wheat','count':2},
            {'slot':1,'item':'minecraft:wheat_seeds','count':10}],entities=[])
        self.crop='Block{minecraft:wheat}[age=2]';self.stamp=100;self.seed_uses=0
        def scan(*args,**kwargs):
            self.stamp+=1
            rows=[{'pos':[27,64,70],'state':'Block{minecraft:farmland}[moisture=7]','fluid':False}]
            if self.crop:rows.append({'pos':[27,65,70],'state':self.crop})
            return {'phase':'done','world_session':'new','time':self.stamp,'blocks':rows}
        def request(op,**kwargs):
            self.assertEqual('interact',op);self.seed_uses+=1;self.crop='Block{minecraft:wheat}[age=0]'
            self.state['inventory'][1]['count']-=1
            return {'phase':'done','id':'new-seed'}
        self.c=SimpleNamespace(world='new',root=self.root,status=lambda:copy.deepcopy(self.state),
            checked=Mock(side_effect=scan),request=Mock(side_effect=request))
        self.layout={'cells':[[27,64,70]],'center':[27,64,70],'radius':2}

    def execute(self):
        # The real registry iterator yields exactly two entries, request/path.
        with patch('material_jobs.registered_wheat.registered_fields',return_value=iter([({'crop':'wheat'},self.registry)])), \
             patch('material_jobs.wheat_reconnect_repair.plan',return_value=self.layout), \
             patch('material_jobs.wheat_reconnect_repair._registered_wheat')as gate, \
             patch('material_jobs.wheat_reconnect_repair.make_plant_access',return_value=Mock())as access, \
             patch('work_access.approach_faces'):
            result=run(self.c,self.journal,self.root/'restoration')
        return result,gate,access

    def test_already_present_current_crop_advances_pointer_without_seed_or_old_receipt_credit(self):
        result,gate,access=self.execute()
        self.assertTrue(result['complete']);self.assertEqual(0,result['new_reseed'])
        self.assertEqual(0,self.seed_uses);access.assert_not_called()
        self.assertIsNone(gate.call_args.kwargs['known_replant'])
        self.assertEqual(self.original,self.journal.read_bytes())
        self.assertFalse(result['historical_receipt_reclassified'])
        current=Path(json.loads(self.pointer.read_text())['journal'])
        self.assertEqual(result,json.loads(current.read_text()))

    def test_empty_original_cell_requires_exact_seed_delta_and_two_new_crop_frames(self):
        self.crop=None
        result,gate,access=self.execute()
        self.assertEqual(1,self.seed_uses);self.assertEqual(1,result['new_reseed'])
        self.assertEqual(2,len(result['frames']));self.assertEqual(9,self.state['inventory'][1]['count'])
        self.assertEqual(self.original,self.journal.read_bytes())
        self.assertEqual([27,64,70],gate.call_args_list[0].kwargs['known_replant'])
        self.assertEqual(2,gate.call_count)

    def test_unknown_new_seed_use_retains_new_pending_and_original_active_pointer(self):
        self.crop=None;self.c.request=Mock(return_value={'phase':'waiting','id':'unknown-seed'})
        with self.assertRaises(JobBlocked):self.execute()
        self.assertEqual(self.original,self.journal.read_bytes())
        self.assertEqual(self.original_pointer,self.pointer.read_bytes())
        book=json.loads((self.root/'restoration/current-cell-restoration.json').read_text())
        self.assertEqual('new_seed_use',book['pending']['kind']);self.assertFalse(book['complete'])

    def test_stored_recovered_grain_uses_pickup_proof_without_new_grain_credit(self):
        self.state['inventory'][0]['count']=0
        self.book['pending']['owned_loot']=[{'uuid':'known','item':'minecraft:wheat','count':1}]
        self.journal.write_text(json.dumps(self.book));self.original=self.journal.read_bytes()
        capture=self.root/'actual-pickup.json';capture.write_text(json.dumps({'picked':True,'source_absent':True,
            'no_crop_mined':True,'drop_uuid':'known','before':1,'after':2}))
        with patch('material_jobs.registered_wheat.registered_fields',return_value=iter([({'crop':'wheat'},self.registry)])), \
             patch('material_jobs.wheat_reconnect_repair.plan',return_value=self.layout), \
             patch('material_jobs.wheat_reconnect_repair._registered_wheat'):
            result=run(self.c,self.journal,self.root/'restoration',pickup_proof=capture)
        self.assertTrue(result['historically_recovered_grain_may_be_stored'])
        self.assertEqual(0,result['grain_inventory_credit']);self.assertEqual(self.original,self.journal.read_bytes())

    def test_changed_other_field_corners_are_not_claimed_repaired_by_single_cell_proof(self):
        frames=[{'time':101},{'time':102}]
        with patch('material_jobs.registered_wheat.registered_fields',return_value=iter([({'crop':'wheat'},self.registry)])), \
             patch('material_jobs.wheat_reconnect_repair.plan',return_value=self.layout), \
             patch('material_jobs.wheat_reconnect_repair._registered_wheat',side_effect=FarmWait('WAIT_SOIL','other corner lowered')), \
             patch('material_jobs.wheat_reconnect_repair.current_existing_cell',return_value=frames):
            result=run(self.c,self.journal,self.root/'restoration')
        self.assertFalse(result['whole_registered_field_verified'])
        self.assertEqual('original_single_harvested_cell',result['verification_scope'])
        self.assertEqual('WAIT_SOIL',result['field_maintenance_required']['code'])
        self.assertEqual(0,self.seed_uses);self.assertEqual(self.original,self.journal.read_bytes())


if __name__=='__main__':unittest.main()
