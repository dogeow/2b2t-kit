"""Offline material conservation and no-replay coverage; no game client is created."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from material_jobs import wood_pipeline as wood


class Client:
    def __init__(self, directory, stock=None):
        self.world = 'world'; self.out = Path(directory); self.held = dict(stock or {})
        self.depot = {}; self.health = 20; self.chopping = False; self.hurt = 0
    def status(self):
        rows = []
        for item, count in self.held.items():
            while count:
                amount = min(64, count); count -= amount
                rows.append({'slot': len(rows), 'item': item, 'count': amount, 'max_stack': 64})
        rows.extend({'slot': i, 'item': 'minecraft:air', 'count': 0, 'max_stack': 64} for i in range(len(rows), 36))
        return {'world_session': self.world, 'connected': True, 'server': 'example',
                'dimension': 'minecraft:overworld', 'health': self.health, 'food': 20,
                'guard_armed': True, 'guard_pve_only': True, 'manual_movement': False,
                'under_water': False, 'inventory': rows, 'chopping': self.chopping,
                'chopper_remaining': 0, 'chopper_platforms': 0,
                'navigating': False, 'borer_active': False, 'printing': False, 'guard_busy': False,
                'native_material_busy': False, 'recent_hurt_at': self.hurt,
                'menu': {'cursor': {'count': 0}}}


class Catalog:
    def __init__(self, species):
        self.raw = 'minecraft:' + species + '_log'; self.output = 'minecraft:' + species + '_planks'
        self.recipes = {self.output: [SimpleNamespace(count=4, cells=((1, (self.raw,)),))]}
    def candidates(self, output, stock, width):
        return [{'recipe_id': 'actual_' + output.split(':')[1], 'output': output,
                 'produces': 4, 'ingredients': {self.raw: [1]}}]


class Backend:
    def __init__(self, c, profile, species='oak'):
        self.client = c; self.profile = profile; self.root = c.out / 'automation'
        self.request = {'mode': 'item'}; self.crafting_catalog = Catalog(species); self.calls = []
    def prepare_travel(self):self.calls.append(('prepare',))
    def stage_near_base(self, depots):self.calls.append(('stage',))
    def fetch(self, targets):
        self.calls.append(('fetch', targets))
        for item, target in targets.items():
            take = min(max(0, target - self.client.held.get(item, 0)), self.client.depot.get(item, 0))
            self.client.held[item] = self.client.held.get(item, 0) + take
            self.client.depot[item] = self.client.depot.get(item, 0) - take
        missing = {i: n - self.client.held.get(i, 0) for i, n in targets.items() if self.client.held.get(i, 0) < n}
        return {'phase': 'waiting' if missing else 'done', 'missing': missing}
    def craft(self, targets):
        self.calls.append(('craft', targets))
        for item, target in targets.items():
            n = (target - self.client.held.get(item, 0)) // 4
            raw = self.crafting_catalog.raw
            self.client.held[raw] -= n
            self.client.held[item] = self.client.held.get(item, 0) + 4 * n
        return {'phase': 'done', 'complete': True}


def audited(c, depots, items):
    return {'world_session': c.world, 'complete': True, 'counts': {i: c.depot.get(i, 0) for i in items}}


def deposited(c, depots, deposit):
    for item, keep in deposit.items():
        moved = max(0, c.held.get(item, 0) - keep)
        c.held[item] -= moved; c.depot[item] = c.depot.get(item, 0) + moved
    return {'complete': True}


class WoodPipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.profile = {'server': 'example', 'dimension': 'minecraft:overworld',
                        'depots': [[1,64,2]], 'resource_regions': []}
        self.patches = [patch.object(wood, 'audit', side_effect=audited),
                        patch.object(wood, 'exchange', side_effect=deposited)]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def client(self, held=None, species='oak'):
        c = Client(self.base, held); c.wood_backend = Backend(c, self.profile, species)
        return c
    def run_pipeline(self, c, item, count, name='run'):
        return wood.run(c, self.profile, item, count, self.base / name, lambda: None)

    def test_all_five_real_log_to_four_plank_families_use_absolute_craft_targets(self):
        for family in wood.SPECIES:
            with self.subTest(family=family):
                raw, output = 'minecraft:' + family + '_log', 'minecraft:' + family + '_planks'
                c = self.client({raw:16}, family)
                result = self.run_pipeline(c, output, 48, family)
                self.assertEqual('done',result['phase']);self.assertEqual(48,c.depot[output])
                self.assertEqual(4,c.held[raw]);self.assertIn(('craft',{output:48}),c.wood_backend.calls)

    def test_rounding_surplus_is_kept_and_only_goal_amount_is_deposited(self):
        c=self.client({'minecraft:oak_log':2})
        result=self.run_pipeline(c,'minecraft:oak_planks',5)
        self.assertEqual('done',result['phase']);self.assertEqual(5,c.depot['minecraft:oak_planks'])
        self.assertEqual(3,c.held['minecraft:oak_planks']);self.assertEqual(0,c.held['minecraft:oak_log'])

    def test_small_existing_raw_batch_makes_real_progress_without_unknown_source(self):
        c=self.client({'minecraft:oak_log':3})
        result=self.run_pipeline(c,'minecraft:oak_planks',100)
        self.assertEqual('batch_delivered',result['code']);self.assertEqual(12,c.depot['minecraft:oak_planks'])
        self.assertFalse(any(call[0]=='fetch' for call in c.wood_backend.calls))

    def test_existing_finished_is_deposited_before_any_craft_or_collection(self):
        c=self.client({'minecraft:oak_planks':20,'minecraft:oak_log':16})
        result=self.run_pipeline(c,'minecraft:oak_planks',16)
        self.assertEqual('done',result['phase']);self.assertEqual(4,c.held['minecraft:oak_planks'])
        self.assertFalse(any(call[0] in ('craft','fetch') for call in c.wood_backend.calls))

    def test_raw_logs_already_in_depots_are_not_withdrawn_to_fake_new_delivery(self):
        c=self.client();c.depot['minecraft:oak_log']=8
        result=self.run_pipeline(c,'minecraft:oak_log',16)
        self.assertEqual('wait_source',result['code']);self.assertEqual(8,c.depot['minecraft:oak_log'])
        self.assertFalse(any(call[0]=='fetch' for call in c.wood_backend.calls))

    def test_missing_bound_backend_does_not_create_another_controller(self):
        c=self.client();c.wood_backend.client=None
        self.assertEqual('wait_source',self.run_pipeline(c,'minecraft:oak_planks',16)['code'])
        self.assertEqual([],c.wood_backend.calls)

    def test_incomplete_or_wrong_recipe_is_never_guessed(self):
        c=self.client({'minecraft:oak_log':16});c.wood_backend.crafting_catalog=None
        self.assertEqual('wait_source',self.run_pipeline(c,'minecraft:oak_planks',16)['code'])
        self.assertFalse(any(call[0]=='craft' for call in c.wood_backend.calls))

    def test_unknown_craft_receipt_retains_pending_and_cannot_be_replayed(self):
        c=self.client({'minecraft:oak_log':16})
        def uncertain(targets):c.wood_backend.calls.append(('unknown_craft',targets));return {'phase':'waiting'}
        c.wood_backend.craft=uncertain
        self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_planks',16)['code'])
        before=len(c.wood_backend.calls)
        self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_planks',16)['code'])
        self.assertEqual(before,len(c.wood_backend.calls))

    def test_wrong_craft_output_delta_cannot_be_deposited_or_credited(self):
        c=self.client({'minecraft:oak_log':16})
        def wrong(_):c.held['minecraft:oak_planks']=15;c.held['minecraft:oak_log']=12;return {'phase':'done'}
        c.wood_backend.craft=wrong
        self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_planks',16)['code'])
        self.assertEqual(0,c.depot.get('minecraft:oak_planks',0))

    def test_depot_conservation_failure_keeps_pending_receipt(self):
        c=self.client({'minecraft:oak_planks':16})
        def wrong(c,depots,deposit):c.held['minecraft:oak_planks']=0;return {'complete':True}
        with patch.object(wood,'exchange',side_effect=wrong):
            self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_planks',16)['code'])
        job=json.loads((self.base/'run'/'wood-pipeline.json').read_text())
        self.assertEqual('deposit',job['pending']['kind'])

    def test_external_depot_change_is_not_silently_counted_on_resume(self):
        c=self.client({'minecraft:oak_planks':16})
        self.run_pipeline(c,'minecraft:oak_planks',32)
        c.depot['minecraft:oak_planks']=20
        self.assertEqual('wait_depot',self.run_pipeline(c,'minecraft:oak_planks',32)['code'])

    def test_other_scope_or_target_does_not_overwrite_old_journal(self):
        c=self.client({'minecraft:oak_planks':16})
        self.run_pipeline(c,'minecraft:oak_planks',16)
        path=self.base/'run'/'wood-pipeline.json';before=path.read_bytes()
        self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_planks',32)['code'])
        self.assertEqual(before,path.read_bytes())

    def test_verified_small_tree_goal_wait_uses_real_native_done_ledger(self):
        directory=self.base/'acquisition';directory.mkdir()
        c=self.client()
        (directory/'acquisition-oak_log.json').write_text(json.dumps({'world_session':c.world,'item':'minecraft:oak_log',
            'visited':{'root':{'state':'progress','native_phase':'done','before':0,'after':5,'gained':5}}}))
        self.assertTrue(wood._known_chop({'phase':'waiting'},directory,c,'minecraft:oak_log',0,5))
        self.assertFalse(wood._known_chop({'phase':'waiting'},directory,c,'minecraft:oak_log',0,6))

    def test_existing_native_acquisition_keeps_the_same_client_and_real_regrowth_receipt(self):
        c=self.client()
        region={'item':'minecraft:oak_log','min':[0,48,0],'max':[5,100,5],'source':'natural_survey'}
        self.profile['resource_regions']=[region]
        original=json.loads(json.dumps(self.profile))
        regrowth={'planted':True,'growth_confirmed':False,'stage':'sapling_kept_no_bone_meal'}
        def acquire(client,item,target,profile,directory,checkpoint):
            self.assertIs(c,client);self.assertEqual(16,target)
            self.assertEqual([region],profile['resource_regions'])
            client.held[item]=17
            return {'phase':'done','gained':17,'regrowth':regrowth}
        with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
             patch('material_jobs.acquisition.acquire',side_effect=acquire):
            result=self.run_pipeline(c,'minecraft:oak_planks',64)
        self.assertEqual('done',result['phase']);self.assertEqual(64,c.depot['minecraft:oak_planks'])
        self.assertEqual(1,c.held['minecraft:oak_log']);self.assertEqual(original,self.profile)
        job=json.loads((self.base/'run'/'wood-pipeline.json').read_text())
        receipt=next(r['receipt'] for r in job['batches'] if r['kind']=='acquire')
        self.assertEqual(regrowth,receipt['regrowth'])
        self.assertFalse(receipt['regrowth']['growth_confirmed'])

    def test_unconfirmed_native_tree_never_gets_a_new_batch_directory_or_deposit(self):
        c=self.client();self.profile['resource_regions']=[{'item':'minecraft:oak_log','min':[0,48,0],'max':[5,100,5]}]
        with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
             patch('material_jobs.acquisition.acquire',return_value={'phase':'waiting','code':'route_uncertain'}) as acquire:
            self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_planks',64)['code'])
            self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_planks',64)['code'])
        self.assertEqual(1,acquire.call_count);self.assertEqual(0,c.depot.get('minecraft:oak_planks',0))

    def test_discovery_does_not_invent_or_update_the_callers_resource_profile(self):
        c=self.client();self.profile.update(search_origin=[0,100,0],search_radius=256)
        before=json.loads(json.dumps(self.profile))
        with patch('material_jobs.discovery.discover',return_value=None) as discover:
            self.assertEqual('wait_source',self.run_pipeline(c,'minecraft:oak_planks',64)['code'])
        self.assertEqual(1,discover.call_count);self.assertEqual(before,self.profile)
        self.assertFalse(any(call[0]=='craft' for call in c.wood_backend.calls))

    def sourcing_profile(self):
        self.profile.update(search_origin=[0,140,0],search_radius=256,resource_regions=[
            {'item':'minecraft:oak_log','min':[0,48,0],'max':[5,100,5]},
            {'item':'minecraft:oak_log','min':[10,48,0],'max':[15,100,5]}])

    def empty_source(self,c,item,target,profile,directory,checkpoint,visited=None):
        directory.mkdir(parents=True,exist_ok=True)
        (directory/('acquisition-'+item.split(':')[-1]+'.json')).write_text(json.dumps({
            'schema':1,'world_session':c.world,'item':item,
            'visited':{} if visited is None else visited}))
        return {'phase':'blocked','code':'no_safe_candidate'}

    def test_all_configured_empty_sources_advance_eight_tile_frontier_once_without_reharvesting(self):
        self.sourcing_profile();c=self.client();original=json.loads(json.dumps(self.profile))
        def discover(client,item,profile,directory,checkpoint,max_tiles):
            self.assertIs(c,client);self.assertEqual(8,max_tiles)
            self.assertEqual(self.base/'run'/'discovery',directory)
            self.assertEqual([],profile['resource_regions'])
            self.assertEqual(2,len(profile['protected_regions']))
            call=discover.calls;discover.calls+=1
            c.material_search_progress={'new_tiles':8,'scanned_total':8*(call+1),'has_more':call==0}
            return None
        discover.calls=0
        with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
             patch('material_jobs.acquisition.acquire',side_effect=self.empty_source) as acquire,\
             patch('material_jobs.discovery.discover',side_effect=discover) as search:
            for _ in range(3):self.assertEqual('wait_source',self.run_pipeline(c,'minecraft:oak_log',16)['code'])
        self.assertEqual(1,acquire.call_count);self.assertEqual(2,search.call_count)
        self.assertEqual(original,self.profile)
        job=json.loads((self.base/'run'/'wood-pipeline.json').read_text())
        self.assertEqual(2,len(job['empty_sources']));self.assertIsNone(job['pending'])
        self.assertEqual([8,16],[r['receipt']['progress']['scanned_total'] for r in job['batches'] if r['kind']=='discover'])

    def test_fresh_discovered_source_is_journal_only_and_used_in_next_known_batch(self):
        self.sourcing_profile();c=self.client();original=json.loads(json.dumps(self.profile))
        found={'item':'minecraft:oak_log','min':[80,48,80],'max':[85,100,85],
               'source':'natural_survey','world_session':c.world}
        def acquire(client,item,target,profile,directory,checkpoint):
            if acquire.calls==0:
                acquire.calls+=1;return self.empty_source(client,item,target,profile,directory,checkpoint)
            self.assertEqual([found|{'pipeline_world_session':c.world}],profile['resource_regions'])
            client.held[item]=16;return {'phase':'done','gained':16}
        acquire.calls=0
        with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
             patch('material_jobs.acquisition.acquire',side_effect=acquire) as harvest,\
             patch('material_jobs.discovery.discover',return_value=found) as discover:
            self.assertEqual('source_discovered',self.run_pipeline(c,'minecraft:oak_log',16)['code'])
            self.assertEqual(1,harvest.call_count)
            self.assertEqual('done',self.run_pipeline(c,'minecraft:oak_log',16)['phase'])
        self.assertEqual(2,harvest.call_count);self.assertEqual(1,discover.call_count)
        self.assertEqual(original,self.profile);self.assertEqual(16,c.depot['minecraft:oak_log'])

    def test_partial_unknown_or_changed_inventory_never_changes_source(self):
        self.sourcing_profile()
        cases=({'state':'inflight'},{'state':'route_hold','route_code':'guard_displaced'},
               {'state':'progress','native_phase':'done','gained':1},
               {'state':'no_progress','native_phase':'waiting'})
        for i,entry in enumerate(cases):
            with self.subTest(entry=entry):
                c=self.client()
                def acquire(client,item,target,profile,directory,checkpoint):
                    return self.empty_source(client,item,target,profile,directory,checkpoint,{'root':entry})
                with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
                     patch('material_jobs.acquisition.acquire',side_effect=acquire),\
                     patch('material_jobs.discovery.discover') as discover:
                    self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_log',16,'partial'+str(i))['code'])
                discover.assert_not_called()
        c=self.client()
        def pickup(client,item,target,profile,directory,checkpoint):
            result=self.empty_source(client,item,target,profile,directory,checkpoint)
            client.held['minecraft:gravel']=1;return result
        with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
             patch('material_jobs.acquisition.acquire',side_effect=pickup),\
             patch('material_jobs.discovery.discover') as discover:
            self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_log',16)['code'])
        discover.assert_not_called()

    def test_damage_or_native_busy_during_empty_survey_blocks_discovery_and_replay(self):
        self.sourcing_profile()
        for i,damage in enumerate((True,False)):
            c=self.client()
            def acquire(client,item,target,profile,directory,checkpoint):
                result=self.empty_source(client,item,target,profile,directory,checkpoint)
                if damage:client.hurt+=1
                else:client.chopping=True
                return result
            with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
                 patch('material_jobs.acquisition.acquire',side_effect=acquire) as harvest,\
                 patch('material_jobs.discovery.discover') as discover:
                self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_log',16,'hold'+str(i))['code'])
                self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_log',16,'hold'+str(i))['code'])
            self.assertEqual(1,harvest.call_count);discover.assert_not_called()

    def test_discovery_guard_hold_damage_or_foreign_world_is_not_adopted(self):
        self.sourcing_profile()
        for i,kind in enumerate(('guard','damage','world')):
            c=self.client()
            def discover(*args,**kwargs):
                if kind=='guard':
                    c.material_search_progress={'guard_hold':{'code':'guard_displaced'}};return None
                if kind=='damage':c.health=19;c.hurt=1;return None
                return {'item':'minecraft:oak_log','min':[80,48,80],'max':[85,100,85],
                        'source':'natural_survey','world_session':'other-world'}
            with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
                 patch('material_jobs.acquisition.acquire',side_effect=self.empty_source),\
                 patch('material_jobs.discovery.discover',side_effect=discover) as search:
                self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_log',16,'discoveryhold'+str(i))['code'])
                self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_log',16,'discoveryhold'+str(i))['code'])
            self.assertEqual(1,search.call_count)
            job=json.loads((self.base/('discoveryhold'+str(i))/'wood-pipeline.json').read_text())
            self.assertEqual([],job['sources']);self.assertEqual('discover',job['pending']['kind'])

    def test_repeated_empty_candidate_is_recorded_without_repeat_harvest_or_search(self):
        self.sourcing_profile();c=self.client()
        found={**self.profile['resource_regions'][0],'source':'natural_survey'}
        with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
             patch('material_jobs.acquisition.acquire',side_effect=self.empty_source) as acquire,\
             patch('material_jobs.discovery.discover',return_value=found) as discover:
            self.assertEqual('wait_source',self.run_pipeline(c,'minecraft:oak_log',16)['code'])
            self.assertEqual('wait_source',self.run_pipeline(c,'minecraft:oak_log',16)['code'])
        self.assertEqual(1,acquire.call_count);self.assertEqual(1,discover.call_count)
        job=json.loads((self.base/'run'/'wood-pipeline.json').read_text())
        self.assertEqual([],job['sources'])
        self.assertEqual('repeated_empty_source',job['discovery_exhausted']['minecraft:oak_log']['reason'])

    def test_empty_source_ledger_with_pending_or_foreign_world_cannot_authorize_discovery(self):
        self.sourcing_profile()
        for i,changes in enumerate(({'pending':{'kind':'chop'}},{'world_session':'another-world'})):
            c=self.client()
            def acquire(client,item,target,profile,directory,checkpoint):
                result=self.empty_source(client,item,target,profile,directory,checkpoint)
                path=directory/('acquisition-'+item.split(':')[-1]+'.json')
                ledger=json.loads(path.read_text());ledger.update(changes);path.write_text(json.dumps(ledger))
                return result
            with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
                 patch('material_jobs.acquisition.acquire',side_effect=acquire),\
                 patch('material_jobs.discovery.discover') as discover:
                self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_log',16,'ledgerhold'+str(i))['code'])
            discover.assert_not_called()

    def test_world_change_never_reuses_source_or_empty_frontier_journal(self):
        self.sourcing_profile();c=self.client()
        c.material_search_progress={'new_tiles':8,'scanned_total':8,'has_more':True}
        with patch('material_jobs.equipment.prepare',return_value={'phase':'done'}),\
             patch('material_jobs.acquisition.acquire',side_effect=self.empty_source),\
             patch('material_jobs.discovery.discover',return_value=None):
            self.assertEqual('wait_source',self.run_pipeline(c,'minecraft:oak_log',16)['code'])
        path=self.base/'run'/'wood-pipeline.json';before=path.read_bytes();calls=list(c.wood_backend.calls)
        c.world='new-world'
        with patch('material_jobs.discovery.discover') as discover:
            self.assertEqual('wait_receipt',self.run_pipeline(c,'minecraft:oak_log',16)['code'])
        self.assertEqual(before,path.read_bytes());self.assertEqual(calls,c.wood_backend.calls)
        discover.assert_not_called()

    def test_stockpile_backend_cannot_run_projection_fetch_priority(self):
        c=self.client({'minecraft:oak_log':16});c.wood_backend.request['mode']='projection'
        self.assertEqual('wait_source',self.run_pipeline(c,'minecraft:oak_planks',64)['code'])
        self.assertEqual([],c.wood_backend.calls)


if __name__=='__main__':unittest.main()
