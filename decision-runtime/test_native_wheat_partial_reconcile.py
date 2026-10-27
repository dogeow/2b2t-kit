import copy,json,tempfile,unittest
from pathlib import Path
from native_wheat_partial_reconcile import prove,record,reconciled,REASON,HOST_HASHES

class PartialWheatTests(unittest.TestCase):
    def fixture(self):
        cells=[[x,63,2]for x in(1,2,3)];lease={'id':'l','kind':'materials','job_session':'j','world_session':'w'}
        book={'complete':False,'inventory_credit':0,'world_session':'w','cells':cells,
              'pending':{'operation':'planter_wheat_batch','soils':cells},
              'inventory_before':{'minecraft:wheat':5,'minecraft:wheat_seeds':8,'minecraft:diamond_axe':1},
              'scope':{'scan_min':[1,63,2],'scan_max':[3,64,2]}}
        batch={'protocol':1,'total':3,'grain_before':5,'harvest_sent':2,'removed_confirmed':2,
               'plant_sent':2,'replanted_confirmed':2,'cells_server_confirmed':False,
               'crop_positions':[[x,64,2]for x in(1,2,3)]}
        receipt={'id':'r','time':100,'phase':'waiting','detail':REASON,'world_session':'w',
                 'planter_material_batch':batch,'supervision_lease':lease,'runtime_generation':2,'control_revision':4}
        error={'last_request':'r','error':REASON,'native_inflight':None,'unconfirmed_native_request':None}
        blocks=[{'pos':p,'state':'Block{minecraft:farmland}[moisture=7]'}for p in cells]
        blocks +=[{'pos':[x,64,2],'state':f'Block{{minecraft:wheat}}[age={age}]'}for x,age in zip((1,2,3),(1,7,2))]
        frame={'phase':'done','connected':True,'world_session':'w','health':20,'screen':'','manual_movement':False,
               'planter_active':False,'navigating':False,'guard_busy':False,'planter_material_batch':batch,
               'runtime_generation':2,'supervision_lease':lease,'control_revision':4,'scan_start_revision':4,
               'scan_end_revision':4,'scan_cells_read':6,'scan_total_cells':6,'blocks':blocks,'menu':{'cursor':{'count':0}},
               'inventory':[{'slot':0,'item':'minecraft:wheat','count':6},
                            {'slot':1,'item':'minecraft:wheat_seeds','count':9},
                            {'slot':2,'item':'minecraft:diamond_axe','count':1}]}
        return book,receipt,error,[copy.deepcopy({**frame,'time':t})for t in(101,102)]
    def test_retire_only_acknowledged_inputs_without_claiming_the_old_scope_complete(self):
        book,r,e,frames=self.fixture();proof=prove(book,r,e,frames,HOST_HASHES);resolved=record(book,proof)
        self.assertFalse(resolved['complete']);self.assertEqual(0,resolved['inventory_credit'])
        self.assertEqual(1,resolved['partial_inventory_credit']);self.assertEqual(2,proof['confirmed_crop_cycles'])
        self.assertIsNone(resolved['pending']);self.assertTrue(reconciled(resolved));self.assertIsNotNone(book['pending'])
        with self.assertRaises(RuntimeError):record(resolved,proof)
    def test_unacknowledged_or_changed_scope_and_manual_stop_cannot_be_retired(self):
        for change in({'harvest_sent':3},{'removed_confirmed':1},{'plant_sent':3},{'replanted_confirmed':1}):
            book,r,e,frames=self.fixture();r['planter_material_batch'].update(change)
            with self.assertRaises(RuntimeError):prove(book,r,e,frames,HOST_HASHES)
        book,r,e,frames=self.fixture();r['detail']='工具箱停止全部'
        with self.assertRaises(RuntimeError):prove(book,r,e,frames,HOST_HASHES)
        book,r,e,frames=self.fixture();e['unconfirmed_native_request']={'request_id':'r'}
        with self.assertRaises(RuntimeError):prove(book,r,e,frames,HOST_HASHES)
    def test_field_and_inventory_need_two_fresh_conserved_observations(self):
        for mutator in(lambda f:f['blocks'][-1].update(state='Block{minecraft:air}'),
                       lambda f:f['inventory'][0].update(count=7),
                       lambda f:f.update(world_session='other'),lambda f:f.update(time=101)):
            book,r,e,frames=self.fixture();mutator(frames[1])
            with self.assertRaises(RuntimeError):prove(book,r,e,frames,HOST_HASHES)
    def test_registry_unblocks_only_the_exact_pinned_partial_proof(self):
        from material_jobs.native_wheat import unresolved
        book,r,e,frames=self.fixture();resolved=record(book,prove(book,r,e,frames,HOST_HASHES))
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);journal=root/'visit.json';registry=root/'registry.json'
            (root/'native-wheat-active.json').write_text(json.dumps({'journal':str(journal)}))
            journal.write_text(json.dumps(resolved));self.assertFalse(unresolved(registry))
            resolved['partial_stop_proof']['host_hashes']['jar']='other';journal.write_text(json.dumps(resolved))
            self.assertTrue(unresolved(registry))
