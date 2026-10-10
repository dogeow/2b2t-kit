import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch

from material_jobs.registered_wheat import registered_fields,run
from material_plan import inventory_counts
from potato_harvest import _registered_wheat,run as native_harvest
from test_wheat_harvest import WheatHarvestClient,REQUEST,WHEAT
from test_potato_harvest import Clock


class Tests(unittest.TestCase):
    def test_registered_native_pickup_uses_the_exact_known_drop_and_rejects_outside_the_field(self):
        from material_jobs.registered_wheat import make_registered_pickup
        c=self.c;layout=json.loads(self.c.registry.read_text())['scope']['layout'];p=layout['cells'][0]
        drop={'uuid':'known','id':1,'type':'minecraft:item','pos':[p[0]+.5,p[1]+1,p[2]+.5],
              'stack':{'item':'minecraft:wheat','count':1},'remaining_count':1}
        with patch('drop_collection.collect_drop',return_value=True)as collect:
            callback=make_registered_pickup(layout['center'])
            self.assertTrue(callback(c,drop,c.status()));self.assertEqual('known',collect.call_args.args[1]['uuid'])
        drop['pos'][0]+=100
        with patch('drop_collection.collect_drop')as collect:
            from potato_farm import FarmWait
            with self.assertRaises(FarmWait):callback(c,drop,c.status())
            collect.assert_not_called()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.c=WheatHarvestClient(self.root);self.clock=Clock()
        self.backend=SimpleNamespace(ensure_client=lambda:self.c,fetch=Mock(return_value={'phase':'waiting'}),
                                     prepare_travel=Mock())
        def checked(op,**kw):
            if op=='navigate':
                self.c.extra['pos']=list(kw['target']);return {'phase':'done'}
            return self.c.request(op,**kw)
        self.c.checked=Mock(side_effect=checked)

    def execute(self,target=4):
        def harvest(*args,**kw):
            return native_harvest(*args,**kw,sleep=self.clock.sleep,monotonic=self.clock.monotonic)
        with patch('material_jobs.navigation.lift_for_travel'), \
                patch('material_jobs.navigation.settled_state',return_value=self.c.status()), \
                patch('material_jobs.acquisition._travel'), \
                patch('material_jobs.registered_wheat.make_registered_pickup',return_value=None), \
                patch('material_jobs.registered_wheat.make_plant_access',return_value=None), \
                patch('material_jobs.registered_wheat.harvest',side_effect=harvest):
            return run(self.backend,target,self.root/'source',lambda:None)

    def test_borrow_existing_registry_harvests_four_actual_grains_and_replants_exact_cells(self):
        original=self.c.registry.read_bytes();planting=self.c.plant_journal.read_bytes()
        result=self.execute();self.assertEqual('done',result['phase'],result)
        self.assertEqual(4,result['gained']);self.assertTrue(result['registered_field_replanted'])
        self.assertEqual(4,inventory_counts(self.c.status())[WHEAT])
        self.assertEqual(original,self.c.registry.read_bytes());self.assertEqual(planting,self.c.plant_journal.read_bytes())
        actions=[op for op,_ in self.c.calls if op in ('mine_block','interact')]
        self.assertEqual(4,actions.count('mine_block'));self.assertEqual(4,actions.count('interact'))

    def test_small_field_batch_does_not_claim_a_larger_carried_goal(self):
        result=self.execute(8);self.assertEqual(('waiting','SOURCE_BATCH',4),(result['phase'],result['code'],result['after']))

    def test_original_pending_planting_blocks_all_new_actions(self):
        b=json.loads(self.c.plant_journal.read_text());b['pending']={'operation':'plant'}
        self.c.plant_journal.write_text(json.dumps(b));before=self.c.plant_journal.read_bytes()
        result=self.execute();self.assertEqual('WAIT_RECONCILE',result['code'])
        self.assertFalse(self.c.calls);self.assertEqual(before,self.c.plant_journal.read_bytes())

    def test_source_world_is_reverified_without_rewriting_the_original_planting_world(self):
        for p in (self.c.registry,self.c.plant_journal):
            b=json.loads(p.read_text());b['world_session']='old';p.write_text(json.dumps(b))
        original=self.c.registry.read_bytes();planting=self.c.plant_journal.read_bytes()
        result=self.execute();self.assertEqual('done',result['phase'],result)
        self.assertEqual(original,self.c.registry.read_bytes());self.assertEqual(planting,self.c.plant_journal.read_bytes())

    def test_immature_registered_field_has_no_seed_fetch_flight_or_harvest(self):
        for row in self.c.rows.values():
            if 'minecraft:wheat}' in row['state']:row['state']='Block{minecraft:wheat}[age=3]'
        result=self.execute();self.assertEqual('WAIT_GROWTH',result['code'])
        self.backend.fetch.assert_not_called();self.backend.prepare_travel.assert_not_called()
        self.assertFalse(any(op in ('mine_block','interact')for op,_ in self.c.calls))
        self.assertFalse((self.c.registry.parent/'harvest-active.json').exists())

    def test_insufficient_seeds_preserve_four_seed_reserve_and_do_not_mine(self):
        self.c.inv[10]['count']=1
        result=self.execute();self.assertEqual('WAIT_SEED',result['code'])
        self.backend.fetch.assert_called_once_with({'minecraft:wheat_seeds':5})
        self.backend.prepare_travel.assert_not_called()
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.calls))

    def test_unresolved_harvest_is_not_exposed_as_a_safe_generic_source_wait(self):
        self.c.pickup_delay=None
        result=self.execute();self.assertEqual('WAIT_RECONCILE',result['code'],result)
        books=list((self.root/'source').rglob('wheat-harvest-*.json'))
        self.assertTrue(json.loads(books[0].read_text())['pending'])
        self.assertEqual(1,sum(op=='mine_block'for op,_ in self.c.calls))

    def test_wrong_server_or_missing_registration_never_creates_a_field(self):
        self.c.server='other:25565'
        self.assertEqual([],list(registered_fields(self.c)))
        self.assertEqual('WAIT_REGISTERED_FARM',self.execute()['code']);self.assertFalse(self.c.calls)

    def test_read_only_preflight_does_not_replace_the_active_harvest_pointer(self):
        old=self.root/'old-harvest.json';old.write_text('{"pending":null}')
        active=self.c.registry.parent/'harvest-active.json';active.write_text(json.dumps({'journal':str(old)}))
        before=active.read_bytes()
        _registered_wheat(self.c,{**REQUEST,'reverify_registered_field':True},self.root/'preflight.json',bind_active=False)
        self.assertEqual(before,active.read_bytes())
        self.assertFalse(any(op in ('mine_block','interact')for op,_ in self.c.calls))

    def test_one_missing_registered_cell_borrows_existing_maintenance_then_rechecks_the_full_field(self):
        from potato_farm import plan
        from test_potato_farm import row
        pos=plan(REQUEST)['cells'][0];above=[pos[0],pos[1]+1,pos[2]];self.c.rows.pop(tuple(above))
        planting=self.c.plant_journal.read_bytes();registry=self.c.registry.read_bytes()
        def maintenance(c,reg,cells,out,checkpoint,**options):
            self.assertIs(c,self.c);self.assertEqual(self.c.registry,reg);self.assertEqual([pos],cells)
            self.assertTrue(options['allow_move']);c.inv[10]['count']-=1
            c.rows[tuple(above)]=row(above,'Block{minecraft:wheat}[age=0]',False)
            return {'phase':'done','pending':False,'new_reseed':1}
        with patch('farm_reseed.run',side_effect=maintenance)as reseed:
            result=self.execute();self.assertEqual('done',result['phase'],result);reseed.assert_called_once()
        self.assertEqual(4,result['gained']);self.assertEqual(planting,self.c.plant_journal.read_bytes())
        self.assertEqual(registry,self.c.registry.read_bytes())
        proof=json.loads((self.root/'source/field-00/existing-field-maintenance/registered-reseed-result.json').read_text())
        self.assertEqual(0,proof['grain_inventory_credit']);self.assertFalse(proof['old_harvest_replayed'])

    def test_missing_crop_maintenance_keeps_four_seeds_and_never_replays_unknown_maintenance(self):
        from potato_farm import plan
        pos=plan(REQUEST)['cells'][0];self.c.rows.pop((pos[0],pos[1]+1,pos[2]));self.c.inv[10]['count']=4
        with patch('farm_reseed.run')as reseed:
            self.assertEqual('WAIT_SEED',self.execute()['code']);reseed.assert_not_called()
        self.c.inv[10]['count']=8
        with patch('farm_reseed.run',return_value={'phase':'waiting','pending':True,'new_reseed':0})as reseed:
            self.assertEqual('WAIT_RECONCILE',self.execute()['code']);reseed.assert_called_once()
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.calls))

    def test_known_rejected_planting_reuses_original_partial_batch_and_restores_it(self):
        from wheat_plant_reconcile import HOST_CONTRACTS
        from potato_farm import plan
        original_request=self.c.request
        def reject_plant(op,**kw):
            if op=='interact' and kw.get('expected_hand')=='minecraft:wheat_seeds':
                self.c.last='rejected-plant'
                return {**self.c.status(),'phase':'error','id':self.c.last,
                        'detail':'Target interaction face is occluded or out of reach'}
            return original_request(op,**kw)
        self.c.request=reject_plant
        request={**REQUEST,'cells':plan(REQUEST)['cells'][:4],'reverify_registered_field':True}
        result=native_harvest(self.c,request,self.root/'original-harvest',
                              sleep=self.clock.sleep,monotonic=self.clock.monotonic)
        journal=Path(result['journal']);b=json.loads(journal.read_text());pending=b['pending']
        self.assertEqual('plant',pending['operation'])
        proof=self.root/'verified-rejection.json'
        proof.write_text(json.dumps({'proof':{'outcome':'rejected_without_use','world_session':self.c.world,
                    'original_attempt_not_done':True,'seed_debit':0,'pos':pending['pos'],
                    'host_contract':{'kit_version':'2026.10.10.2','class_sha256':HOST_CONTRACTS['2026.10.10.2']}}}))
        b['rejected_plant_history']=[{'original_pending':pending,'proof':str(proof)}]
        b['pending']={'operation':'await_replant','pos':pending['pos'],
                      'pre_drop_ids':pending.get('pre_drop_ids',[]),'prior_plant_rejected_without_use':str(proof)}
        journal.write_text(json.dumps(b));self.c.request=original_request
        recovered=self.execute();self.assertEqual('done',recovered['phase'],recovered)
        self.assertEqual((1,4,3),(recovered['before'],recovered['after'],recovered['gained']))
        final=json.loads(journal.read_text());self.assertIsNone(final['pending'])
        self.assertEqual(4,sum(v.get('replanted')is True for v in final['cells'].values()))
        self.assertEqual('plant',final['rejected_plant_history'][0]['original_pending']['operation'])

    def test_known_await_loot_reuses_original_harvest_without_a_second_break_of_that_cell(self):
        from potato_farm import plan
        self.c.pickup_delay=None
        request={**REQUEST,'cells':plan(REQUEST)['cells'][:4],'reverify_registered_field':True}
        first=native_harvest(self.c,request,self.root/'original-harvest',
                            sleep=self.clock.sleep,monotonic=self.clock.monotonic)
        journal=Path(first['journal']);saved=json.loads(journal.read_text());pos=saved['pending']['pos']
        self.assertEqual('await_loot',saved['pending']['operation'])
        self.c.pickup_delay=1;self.c.pending_pickup=1
        result=self.execute();self.assertEqual('done',result['phase'],result)
        self.assertEqual(4,inventory_counts(self.c.status())[WHEAT])
        self.assertEqual(1,sum(op=='mine_block'and kw['pos']==[pos[0],pos[1]+1,pos[2]]for op,kw in self.c.calls))
        self.assertIsNone(json.loads(journal.read_text())['pending'])


if __name__=='__main__':unittest.main()
