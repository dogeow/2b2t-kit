"""Full deterministic material loops against an in-memory backend, never Minecraft."""
from collections import Counter
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

from material_jobs import MaterialJob, JobPaused
from material_jobs.protocol import JobBlocked
from material_jobs.planning import plan
from material_jobs_cli import serve
from projection_material_plan import ProcessingCatalog


class FakeBackend:
    def __init__(self, catalog, held=None, depot=None, projection=None):
        self.catalog = catalog
        self.held, self.depot = Counter(held or {}), Counter(depot or {})
        self.projection = Counter(projection or {})
        self.total = sum(self.projection.values())
        self.matched = 0
        self.calls, self.finish_count = [], 0
        self.health, self.manual, self.connected, self.hold = 20, False, True, False
        self.world, self.revision = 'world', 1
        self.harden_chunk = None
        self.lie = False
        self.unsupported = set()
        self.pause_smelt = False
        self.pending = None
        self.on_finish = None
        self.stack_sizes = {'minecraft:'+item:64 for item in ('sand','gravel','white_dye','white_concrete',
                            'white_concrete_powder','furnace','iron_ingot','raw_iron','cobblestone','stone','smooth_stone','blast_furnace','coal',
                            'bone_block','bone_meal','lily_of_the_valley')}

    def observe(self):
        rows = []
        for item, total in self.held.items():
            while total:
                size=self.stack_sizes.get(item,64);count = min(size, total)
                rows.append({'slot':len(rows), 'item':item, 'count':count, 'max_stack':size})
                total -= count
        rows += [{'slot':slot, 'item':'minecraft:air', 'count':0, 'max_stack':64}
                 for slot in range(len(rows), 36)]
        return {'connected':self.connected, 'server':'example.test:25565', 'dimension':'minecraft:overworld',
                'world_session':self.world, 'control_revision':self.revision, 'health':self.health,
                'manual_movement':self.manual, 'safety_hold':{'active':self.hold},
                'native_task_session':'fake-native-owner', 'inventory':rows,'target_stack_sizes':self.stack_sizes,
                'pending_material_work':self.pending is not None,
                'projection_audit':{'placement_key':'ship', 'loaded_chunks_verified':True,
                                    'matched':self.matched, 'total':self.total,
                                    'replacement_items':dict(+self.projection)}}

    def stock(self):
        return dict(+self.held)

    def fetch(self, targets):
        self.calls.append(('fetch', dict(targets)))
        for item, amount in targets.items():
            moved = min(max(0, amount-self.held[item]), self.depot[item])
            self.depot[item] -= moved
            self.held[item] += moved
        return {'phase':'done' if all(self.held[i]>=n for i,n in targets.items()) else 'waiting',
                'detail':'Only actual depot items were transferred'}

    def acquire(self, item, target):
        self.calls.append(('acquire', item, target))
        if item in self.unsupported:
            return {'phase':'blocked', 'detail':'No approved acquisition capability for '+item}
        if not self.lie:
            self.held[item] = target
        return {'phase':'done'}

    def craft(self, targets):
        self.calls.append(('craft', dict(targets)))
        recipe_plan = plan(self.catalog, targets, self.held)
        for step in recipe_plan['steps']:
            if step['kind'] == 'reserve':
                continue
            if step['kind'] != 'craft':
                raise AssertionError('Scheduler attempted crafting before prerequisites were acquired')
            for item, amount in step['ingredients'].items():
                if self.held[item] < amount:
                    raise AssertionError('Fake backend cannot invent ingredients')
                self.held[item] -= amount
            self.held[step['item']] += step['produced']
        return {'phase':'done'}

    def smelt(self, recipe, target):
        self.calls.append(('smelt', recipe['output'], target))
        count = target-self.held[recipe['output']]
        if self.held[recipe['source']] < count:
            raise AssertionError('No actual furnace input')
        self.held[recipe['source']] -= count
        if self.pause_smelt:
            self.pause_smelt = False
            self.pending = (recipe['output'], count)
            raise JobPaused('Paused while owned furnace is still processing')
        self.held[recipe['output']] += count
        return {'phase':'done'}

    def harden(self, item, target):
        count = target-self.held[item]
        if self.harden_chunk:
            count = min(count, self.harden_chunk)
        self.calls.append(('harden', item, count, target))
        if self.held[item+'_powder'] < count:
            raise AssertionError('No concrete powder')
        self.held[item+'_powder'] -= count
        self.held[item] += count
        return {'phase':'done' if self.held[item]>=target else 'waiting'}

    def build(self, key):
        placed = 0
        for item, count in list(self.projection.items()):
            amount = min(count, self.held[item])
            self.held[item] -= amount
            self.projection[item] -= amount
            placed += amount
        self.calls.append(('build', key, placed))
        self.matched += placed
        return {'phase':'done'}

    def finish(self):
        self.finish_count += 1
        if self.on_finish:
            self.on_finish()


class MaterialJobsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        jar = self.root/'recipes.jar'
        with zipfile.ZipFile(jar, 'w') as archive:
            def recipe(name, count, ingredients):
                archive.writestr('data/minecraft/recipe/'+name+'.json', json.dumps({
                    'type':'minecraft:crafting_shapeless', 'ingredients':['minecraft:'+i for i in ingredients],
                    'result':{'id':'minecraft:'+name, 'count':count}}))
            recipe('white_concrete_powder', 8, ['sand']*4+['gravel']*4+['white_dye'])
            recipe('furnace', 1, ['cobblestone']*8)
            recipe('blast_furnace', 1, ['iron_ingot']*5+['furnace']+['smooth_stone']*3)
            for source, output in [('cobblestone','stone'),('stone','smooth_stone')]:
                archive.writestr('data/minecraft/recipe/'+output+'.json', json.dumps({
                    'type':'minecraft:smelting', 'ingredient':'minecraft:'+source,
                    'result':{'id':'minecraft:'+output}, 'cookingtime':200}))
        self.catalog = ProcessingCatalog(jar)

    def add_recipes(self):
        with zipfile.ZipFile(self.catalog.jar,'a') as archive:
            archive.writestr('data/minecraft/recipe/iron_from_raw.json',json.dumps({
                'type':'minecraft:smelting','ingredient':'minecraft:raw_iron','result':{'id':'minecraft:iron_ingot'},'cookingtime':200}))
            for name,item,count,source in [('white_dye_from_flower','white_dye',1,'lily_of_the_valley'),
                                           ('white_dye_from_bone_meal','white_dye',1,'bone_meal'),
                                           ('bone_meal_from_block','bone_meal',9,'bone_block')]:
                archive.writestr('data/minecraft/recipe/'+name+'.json',json.dumps({
                    'type':'minecraft:crafting_shapeless','ingredients':['minecraft:'+source],
                    'result':{'id':'minecraft:'+item,'count':count}}))
            archive.writestr('data/minecraft/recipe/bone_block.json',json.dumps({
                'type':'minecraft:crafting_shapeless','ingredients':['minecraft:bone_meal']*9,
                'result':{'id':'minecraft:bone_block','count':1}}))
        self.catalog=ProcessingCatalog(self.catalog.jar)

    def add_oak_trapdoor_recipes(self):
        with zipfile.ZipFile(self.catalog.jar,'a') as archive:
            archive.writestr('data/minecraft/recipe/oak_planks.json',json.dumps({
                'type':'minecraft:crafting_shapeless','ingredients':['minecraft:oak_log'],
                'result':{'id':'minecraft:oak_planks','count':4}}))
            archive.writestr('data/minecraft/recipe/oak_trapdoor.json',json.dumps({
                'type':'minecraft:crafting_shaped','pattern':['###','###'],
                'key':{'#':'minecraft:oak_planks'},
                'result':{'id':'minecraft:oak_trapdoor','count':2}}))
        self.catalog=ProcessingCatalog(self.catalog.jar)

    def request(self, item='white_concrete', count=64, *, projection=False):
        return {'schema':1, 'id':'test-job', 'mode':'projection' if projection else 'item',
                'targets':{'minecraft:'+item:count}, 'projection_key':'ship' if projection else None,
                'context':{'server':'example.test', 'dimension':'minecraft:overworld',
                           'world_session':'world', 'expected_revision':1, 'start_pos':[0,64,0]},
                'created_at':1000}

    def job(self, backend, request=None, name='job'):
        return MaterialJob(request or self.request(), self.root/name, backend)

    def test_leaf_stock_fetch_then_acquire_craft_and_harden_without_ai(self):
        b = FakeBackend(self.catalog, depot={'minecraft:sand':32, 'minecraft:white_dye':8})
        j = self.job(b)
        result = j.run()
        self.assertEqual('completed', result['state'])
        self.assertEqual(64, b.held['minecraft:white_concrete'])
        self.assertEqual(0, result['ai_calls'])
        self.assertEqual([('acquire','minecraft:gravel',32)], [c for c in b.calls if c[0]=='acquire'])
        self.assertTrue(any(c[0]=='craft' for c in b.calls))
        self.assertTrue(any(c[0]=='harden' for c in b.calls))
        self.assertEqual(1, b.finish_count)
        self.assertFalse((j.out/'inflight.json').exists())
        self.assertTrue(list((j.out/'receipts').glob('*.json')))

    def test_fetched_finished_output_skips_production(self):
        b = FakeBackend(self.catalog, depot={'minecraft:white_concrete':64})
        self.assertEqual('completed', self.job(b).run()['state'])
        self.assertEqual(['fetch'], [c[0] for c in b.calls])

    def test_new_search_coverage_continues_without_inventing_collected_items(self):
        b=FakeBackend(self.catalog);original=b.acquire;calls=[]
        def acquire(item,count):
            calls.append(count)
            if len(calls)<3:
                self.assertEqual(0,b.held[item])
                return {'phase':'waiting','search_progress':{'new_tiles':8,'scanned_total':len(calls)*8,'has_more':True}}
            return original(item,count)
        b.acquire=acquire
        result=self.job(b,self.request(item='gravel',count=64)).run()
        self.assertEqual('completed',result['state']);self.assertEqual(3,len(calls))
        self.assertEqual(64,b.held['minecraft:gravel'])


    def test_long_batch_hud_counts_received_items_without_premature_completion(self):
        b=FakeBackend(self.catalog,held={'minecraft:white_concrete':20})
        job=self.job(b,self.request(count=32));job.checkpoint()
        progress=json.loads((job.out/'status.json').read_text())
        self.assertEqual(20,progress['done']);self.assertEqual(32,progress['total'])
        self.assertFalse(progress['terminal']);self.assertNotEqual('completed',progress['state'])

    def test_smelting_dependencies_are_completed_before_blast_furnace_craft(self):
        b = FakeBackend(self.catalog, held={'minecraft:furnace':2,'minecraft:iron_ingot':10,'minecraft:cobblestone':6})
        result = self.job(b, self.request('blast_furnace',2)).run()
        self.assertEqual('completed', result['state'], result)
        self.assertEqual(2,b.held['minecraft:blast_furnace'])
        self.assertEqual([('smelt','minecraft:stone',6),('smelt','minecraft:smooth_stone',6)], [c for c in b.calls if c[0]=='smelt'])
        self.assertEqual([], [c for c in b.calls if c[0]=='acquire'])

    def test_finished_intermediate_depot_stock_reduces_raw_iron_before_mining(self):
        self.add_recipes()
        b = FakeBackend(self.catalog, depot={'minecraft:furnace':17, 'minecraft:iron_ingot':29,
                                            'minecraft:smooth_stone':51})
        result = self.job(b, self.request('blast_furnace',17)).run()
        self.assertEqual('completed', result['state'], result)
        self.assertEqual(17, b.held['minecraft:blast_furnace'])
        self.assertEqual([('acquire','minecraft:raw_iron',56)], [c for c in b.calls if c[0]=='acquire'])
        self.assertEqual([('smelt','minecraft:iron_ingot',85)], [c for c in b.calls if c[0]=='smelt'])
        self.assertEqual([('craft',{'minecraft:blast_furnace':17})], [c for c in b.calls if c[0]=='craft'])
        intermediary = next(c[1] for c in b.calls if c[0]=='fetch' and 'minecraft:iron_ingot' in c[1])
        self.assertEqual(17, intermediary['minecraft:furnace'])
        self.assertEqual(85, intermediary['minecraft:iron_ingot'])
        self.assertEqual(51, intermediary['minecraft:smooth_stone'])

    def test_partial_intermediate_receipt_does_not_repeat_fetch_when_dependency_dict_shrinks(self):
        self.add_recipes()
        b = FakeBackend(self.catalog, depot={'minecraft:furnace':17, 'minecraft:iron_ingot':29,
                                            'minecraft:smooth_stone':51})
        self.job(b, self.request('blast_furnace',17)).run()
        self.assertEqual(1, sum('minecraft:iron_ingot' in c[1] for c in b.calls if c[0]=='fetch'))
        self.assertEqual(1, sum('minecraft:furnace' in c[1] for c in b.calls if c[0]=='fetch'))

    def test_intermediate_warehouse_hints_do_not_become_actual_stock(self):
        self.add_recipes()
        b = FakeBackend(self.catalog, held={'minecraft:furnace':17,'minecraft:smooth_stone':51})
        original = b.observe
        b.observe = lambda:{**original(), 'warehouse_stock_hint':{'minecraft:iron_ingot':85}}
        result = self.job(b, self.request('blast_furnace',17)).run()
        self.assertEqual('completed', result['state'], result)
        self.assertEqual([('acquire','minecraft:raw_iron',85)], [c for c in b.calls if c[0]=='acquire'])

    def deepslate_backend(self,depot):
        with zipfile.ZipFile(self.catalog.jar,'a') as archive:
            for source,output in [('cobbled_deepslate','polished_deepslate'),('polished_deepslate','deepslate_bricks'),('deepslate_bricks','deepslate_tiles')]:
                archive.writestr('data/minecraft/recipe/'+output+'.json',json.dumps({
                    'type':'minecraft:crafting_shaped','pattern':['##','##'],'key':{'#':'minecraft:'+source},
                    'result':{'id':'minecraft:'+output,'count':4}}))
        self.catalog=ProcessingCatalog(self.catalog.jar)
        b=FakeBackend(self.catalog,depot=depot)
        b.stack_sizes.update({'minecraft:'+item:64 for item in ('cobbled_deepslate','polished_deepslate','deepslate_bricks','deepslate_tiles')})
        return b

    def test_tiles_fetch_only_bricks_when_both_dependency_layers_are_in_stock(self):
        b=self.deepslate_backend({'minecraft:deepslate_bricks':128,'minecraft:polished_deepslate':128})
        result=self.job(b,self.request('deepslate_tiles',128)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual(128,b.depot['minecraft:polished_deepslate'])
        self.assertEqual(0,b.held['minecraft:polished_deepslate'])
        self.assertFalse(any('minecraft:polished_deepslate' in c[1] for c in b.calls if c[0]=='fetch'))
        self.assertEqual([('craft',{'minecraft:deepslate_tiles':128})],[c for c in b.calls if c[0]=='craft'])

    def test_tiles_descend_to_polished_only_after_nearer_layer_was_unavailable(self):
        b=self.deepslate_backend({'minecraft:polished_deepslate':128})
        self.assertEqual('completed',self.job(b,self.request('deepslate_tiles',128)).run()['state'])
        fetches=[c[1] for c in b.calls if c[0]=='fetch']
        self.assertLess(fetches.index({'minecraft:deepslate_bricks':128}),fetches.index({'minecraft:polished_deepslate':128}))
        self.assertFalse(any('minecraft:polished_deepslate' in c and 'minecraft:deepslate_bricks' in c for c in fetches))
        self.assertFalse([c for c in b.calls if c[0]=='acquire'])

    def test_partial_bricks_replan_reduces_next_layer_before_fetching(self):
        b=self.deepslate_backend({'minecraft:deepslate_bricks':64,'minecraft:polished_deepslate':128})
        self.assertEqual('completed',self.job(b,self.request('deepslate_tiles',128)).run()['state'])
        self.assertEqual(64,b.depot['minecraft:polished_deepslate'])
        fetches=[c[1] for c in b.calls if c[0]=='fetch']
        self.assertIn({'minecraft:polished_deepslate':64},fetches)
        self.assertNotIn({'minecraft:polished_deepslate':128},fetches)

    def test_blast_furnace_does_not_fetch_unsmelted_stone_when_smooth_stone_exists(self):
        self.add_recipes()
        b=FakeBackend(self.catalog,depot={'minecraft:furnace':17,'minecraft:iron_ingot':85,'minecraft:smooth_stone':51,'minecraft:stone':51})
        result=self.job(b,self.request('blast_furnace',17)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual(51,b.depot['minecraft:stone'])
        self.assertFalse(any('minecraft:stone' in c[1] for c in b.calls if c[0]=='fetch'))
        self.assertFalse([c for c in b.calls if c[0] in ('acquire','smelt')])

    def test_blast_furnace_checks_stone_after_missing_smooth_stone_is_observed(self):
        self.add_recipes()
        b=FakeBackend(self.catalog,depot={'minecraft:furnace':17,'minecraft:iron_ingot':85,'minecraft:stone':51})
        self.assertEqual('completed',self.job(b,self.request('blast_furnace',17)).run()['state'])
        fetches=[c[1] for c in b.calls if c[0]=='fetch']
        stone=next(i for i,c in enumerate(fetches) if 'minecraft:stone' in c)
        smooth=next(i for i,c in enumerate(fetches) if 'minecraft:smooth_stone' in c)
        self.assertGreater(stone,smooth)
        self.assertEqual([('smelt','minecraft:smooth_stone',51)],[c for c in b.calls if c[0]=='smelt'])

    def test_fetch_cache_is_per_item_absolute_count_with_new_larger_demand_allowed(self):
        b = FakeBackend(self.catalog)
        job = self.job(b, self.request('sand',64))
        job._observe()
        self.assertTrue(job._fetch({'minecraft:iron_ingot':85,'minecraft:smooth_stone':51}))
        self.assertFalse(job._fetch({'minecraft:iron_ingot':56}))
        self.assertFalse(job._fetch({'minecraft:smooth_stone':51}))
        self.assertTrue(job._fetch({'minecraft:iron_ingot':86,'minecraft:smooth_stone':50}))
        self.assertEqual({'minecraft:iron_ingot':86}, b.calls[-1][1])

    def test_projection_collects_full_batches_instead_of_building_every_eight(self):
        b = FakeBackend(self.catalog, held={'minecraft:white_concrete':8},
                        depot={'minecraft:white_concrete_powder':376}, projection={'minecraft:white_concrete':384})
        b.harden_chunk=8
        result=self.job(b,self.request(count=384,projection=True)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual([256,128],[c[2] for c in b.calls if c[0]=='build'])
        self.assertEqual((384,384),(result['done'],result['total']))
        self.assertLessEqual(max(c[1].get('minecraft:white_concrete_powder',0) for c in b.calls if c[0]=='fetch'),256)

    def test_verified_finished_depot_materials_build_before_old_mining_prerequisite(self):
        deep, smooth, polished = ('minecraft:'+name for name in ('cobbled_deepslate','smooth_stone','polished_andesite'))
        b = FakeBackend(self.catalog, projection={deep:128, smooth:200, polished:100})
        b.stack_sizes.update({deep:64, polished:64})
        ordinary_fetch = b.fetch
        def fetch(targets):
            receipt = ordinary_fetch(targets)
            if not any(call[0] == 'build' for call in b.calls):
                b.held.update({smooth:115, polished:57})
                receipt.update(ready_for_build=True, provided_finished={smooth:115, polished:57}, projection_key='ship')
            return receipt
        b.fetch = fetch
        job = self.job(b, self.request(projection=True))
        job.prerequisites = {deep:128}
        result = job.run()
        self.assertEqual('completed', result['state'], result)
        self.assertEqual(('build','ship',172), b.calls[1])
        self.assertEqual({}, json.loads((job.out/'receipts'/'000002.json').read_text())['output_targets'])
        self.assertGreater(next(i for i,c in enumerate(b.calls) if c[0]=='acquire'), 1)

    def test_ready_receipt_needs_new_actual_projection_stock_not_food_or_depot_hints(self):
        deep, smooth = 'minecraft:cobbled_deepslate', 'minecraft:smooth_stone'
        for change in ('none', 'food', 'hint', 'non_projection_item', 'stock_only', 'wrong_key', 'boolean_count'):
            with self.subTest(change=change):
                b = FakeBackend(self.catalog, held={smooth:8}, projection={deep:128, smooth:200})
                b.stack_sizes[deep] = 64
                ordinary_observe, ordinary_stock = b.observe, b.stock
                def fetch(targets):
                    b.calls.append(('fetch', dict(targets)))
                    receipt = {'phase':'waiting', 'ready_for_build':True, 'provided_finished':{smooth:8}}
                    if change in ('food', 'non_projection_item'):
                        b.held['minecraft:bread'] += 8
                    if change == 'non_projection_item':
                        receipt['provided_finished'] = {'minecraft:bread':8}
                    if change == 'hint':
                        b.observe = lambda:{**ordinary_observe(), 'warehouse_stock_hint':{smooth:1000}}
                    if change == 'stock_only':
                        b.stock = lambda:{**ordinary_stock(), smooth:16}
                    if change == 'wrong_key':
                        b.held[smooth] += 8
                        receipt['projection_key'] = 'another-placement'
                    if change == 'boolean_count':
                        b.held[smooth] += 8
                        receipt['provided_finished'] = {smooth:True}
                    return receipt
                b.fetch = fetch
                job = self.job(b, self.request(projection=True), name='ready-'+change)
                job.prerequisites = {deep:128}
                job._step(job._observe())
                self.assertIsNone(job.pending_ready_build)
                job._step(job._observe())
                self.assertEqual('acquire', b.calls[-1][0])
                self.assertFalse(any(c[0] == 'build' for c in b.calls))

    def test_repeated_finished_receipt_with_unchanged_inventory_cannot_rebuild(self):
        deep, smooth = 'minecraft:cobbled_deepslate', 'minecraft:smooth_stone'
        b = FakeBackend(self.catalog, projection={deep:128, smooth:200})
        b.stack_sizes[deep] = 64
        def fetch(targets):
            b.calls.append(('fetch', dict(targets)))
            b.held[smooth] = 8  # Only the first call adds stock.
            return {'phase':'waiting', 'ready_for_build':True, 'provided_finished':{smooth:8}}
        def build(key):
            b.calls.append(('build', key, 0))
            return {'phase':'waiting', 'requirements':{deep:128}}
        b.fetch, b.build = fetch, build
        job = self.job(b, self.request(projection=True))
        job.prerequisites = {deep:128}
        for _ in range(4):
            job._step(job._observe())
        self.assertEqual(['fetch','build','fetch','acquire'], [c[0] for c in b.calls])

    def test_finished_materials_disappearing_before_next_step_do_not_override_prerequisite(self):
        deep, smooth = 'minecraft:cobbled_deepslate', 'minecraft:smooth_stone'
        b = FakeBackend(self.catalog, projection={deep:128, smooth:200})
        b.stack_sizes[deep] = 64
        def fetch(targets):
            b.calls.append(('fetch', dict(targets)))
            b.held[smooth] = 115
            return {'phase':'waiting', 'ready_for_build':True, 'provided_finished':{smooth:115}}
        b.fetch = fetch
        job = self.job(b, self.request(projection=True))
        job.prerequisites = {deep:128}
        job._step(job._observe())
        self.assertIsNotNone(job.pending_ready_build)
        b.held[smooth] = 0
        job._step(job._observe())
        self.assertEqual('acquire', b.calls[-1][0])
        self.assertIsNone(job.pending_ready_build)

    def test_build_without_placement_cannot_reset_stuck_guard_by_eating_food(self):
        smooth = 'minecraft:smooth_stone'
        b = FakeBackend(self.catalog, held={smooth:115,'minecraft:bread':8}, projection={smooth:200})
        def build(key):
            b.held['minecraft:bread'] -= 1
            return {'phase':'waiting'}
        b.build = build
        job = self.job(b, self.request(projection=True))
        job._observe()
        job._call('build', ['ship'], 'building')
        with self.assertRaisesRegex(JobBlocked, '两次没有实际进展'):
            job._call('build', ['ship'], 'building')

    def test_item_jobs_ignore_finished_projection_receipts(self):
        b = FakeBackend(self.catalog, depot={'minecraft:sand':16})
        original = b.fetch
        def fetch(targets):
            receipt = original(targets)
            receipt.update(ready_for_build=True, provided_finished={'minecraft:sand':16})
            return receipt
        b.fetch = fetch
        job = self.job(b, self.request('sand',16))
        self.assertEqual('completed', job.run()['state'])
        self.assertIsNone(job.pending_ready_build)
        self.assertEqual(['fetch'], [c[0] for c in b.calls])

    def test_item_larger_than_backpack_is_blocked_before_fetching(self):
        for count in (3000,1_000_000):
            b=FakeBackend(self.catalog)
            result=self.job(b,self.request('sand',count),name='capacity'+str(count)).run()
            self.assertEqual('blocked',result['state']);self.assertIn('背包',result['detail']);self.assertEqual([],b.calls)

    def test_real_backend_capacity_preflight_preserves_full_baseline_and_never_logs_out(self):
        import material_jobs_backend as native
        item='minecraft:cobbled_deepslate'
        observed=FakeBackend(self.catalog,held={item:302,'minecraft:stone':31*64})
        observed.stack_sizes[item]=64
        request=self.request('cobbled_deepslate',2304);request['target_stack_sizes']={item:64}
        real=native.Backend.__new__(native.Backend)
        real.root=self.root;real.out=self.root/'backend';real.request=request;real.client=None
        real.catalog=self.catalog;real.baseline=dict(observed.held);real.observe=observed.observe
        real.ensure_client=Mock();real.action=Mock();real.prepare_travel=Mock();real.stage_near_base=Mock()
        real.fetch=Mock();real.acquire=Mock()
        with patch.object(native,'read_fresh',side_effect=lambda root:observed.observe()),patch('material_depots.exchange') as exchange:
            result=self.job(real,request).run()
        self.assertEqual('blocked',result['state'],result)
        self.assertEqual((302,2304),(result['done'],result['total']))
        self.assertTrue(all(str(n) in result['detail'] for n in (302,2304,320)))
        self.assertEqual({item:2304},request['targets']);self.assertEqual(dict(observed.held),real.baseline)
        self.assertIsNone(real.client);self.assertTrue(observed.connected)
        real.ensure_client.assert_not_called();real.action.assert_not_called()
        real.prepare_travel.assert_not_called();real.stage_near_base.assert_not_called()
        real.fetch.assert_not_called();real.acquire.assert_not_called();exchange.assert_not_called()
        self.assertFalse((self.root/'backend'/'finish-fallback.json').exists())

    def test_stack_limits_of_sixteen_and_one_are_not_treated_as_sixty_four(self):
        for item,size,count in [('ender_pearl',16,577),('diamond_sword',1,37)]:
            b=FakeBackend(self.catalog);b.stack_sizes['minecraft:'+item]=size
            result=self.job(b,self.request(item,count),name=item).run()
            self.assertEqual('blocked',result['state'],result);self.assertEqual([],b.calls)

    def test_large_item_target_produces_in_batches_and_keeps_all_finished_output(self):
        b=FakeBackend(self.catalog)
        result=self.job(b,self.request(count=800)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual(800,b.held['minecraft:white_concrete'])
        self.assertTrue(all(c[2] <= 256 for c in b.calls if c[0]=='harden'))
        self.assertTrue(all(c[2] <= 128 for c in b.calls if c[0]=='acquire' and c[1] in ('minecraft:sand','minecraft:gravel')))
        self.assertEqual([], [c for c in b.calls if c[0]=='build'])

    def test_oak_trapdoor_batches_craft_on_hand_logs_after_first_depot_pass(self):
        self.add_oak_trapdoor_recipes()
        log,planks,door='minecraft:oak_log','minecraft:oak_planks','minecraft:oak_trapdoor'
        # Five free slots force the same 64-door first batch as the live job.
        held={log:241,**{'minecraft:filler_'+str(i):1 for i in range(27)}}
        b=FakeBackend(self.catalog,held=held)
        b.stack_sizes.update({log:64,planks:64,door:64})
        result=self.job(b,self.request('oak_trapdoor',247)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual([(door,64)],
                         [(item,count) for call in b.calls if call[0]=='fetch'
                          for item,count in call[1].items()])
        self.assertEqual(248,b.held[door])
        self.assertEqual(55,b.held[log])
        self.assertEqual(0,b.held[planks])

    def test_local_craft_priority_does_not_skip_larger_fetch_without_inputs(self):
        self.add_oak_trapdoor_recipes()
        door='minecraft:oak_trapdoor'
        # The first batch consumes all acquired logs; the next one must still
        # check the depot because it has no on-hand crafting inputs.
        b=FakeBackend(self.catalog,held={'minecraft:filler_'+str(i):1 for i in range(31)})
        b.stack_sizes.update({'minecraft:oak_log':64,'minecraft:oak_planks':64,door:64})
        result=self.job(b,self.request('oak_trapdoor',128)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual([64,128],[call[1][door] for call in b.calls
                                   if call[0]=='fetch' and door in call[1]])

    def test_capacity_shortfall_stores_job_byproducts_then_continues(self):
        b=FakeBackend(self.catalog,held={'minecraft:stone':34*64});room=[]
        def make_room(targets,keep):
            room.append((targets,keep));b.held['minecraft:stone']=0
            return {'phase':'done'}
        b.make_room=make_room
        result=self.job(b,self.request('sand',256)).run()
        self.assertEqual('completed',result['state'],result);self.assertEqual(1,len(room))
        self.assertIn('minecraft:sand',room[0][1]);self.assertEqual(256,b.held['minecraft:sand'])

    def test_intermediate_space_cleanup_keeps_required_recipe_materials(self):
        b=FakeBackend(self.catalog,held={'minecraft:stone':33*64,'minecraft:white_concrete':8});kept=[]
        def make_room(targets,keep):
            kept.append(keep);b.held['minecraft:stone']=0
            return {'phase':'done'}
        b.make_room=make_room
        result=self.job(b,self.request(count=128)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertTrue({'minecraft:sand','minecraft:gravel','minecraft:white_dye','minecraft:white_concrete'}<=set(kept[0]))

    def test_make_room_zero_progress_is_bounded_to_two_attempts(self):
        b=FakeBackend(self.catalog,held={'minecraft:stone':35*64});attempts=[]
        def make_room(targets,keep):
            attempts.append(1);return {'phase':'waiting'}
        b.make_room=make_room
        result=self.job(b,self.request('sand',256)).run()
        self.assertEqual('blocked',result['state']);self.assertEqual(2,len(attempts))

    def test_confirmed_quarry_reserve_stop_unloads_byproducts_before_next_batch(self):
        b=FakeBackend(self.catalog);calls=[];normal=b.acquire
        def acquire(item,count):
            if not calls:
                calls.append('reserve');b.held['minecraft:stone']=64
                return {'phase':'waiting','code':'quarry_backpack_reserve'}
            calls.append('acquire');return normal(item,count)
        b.acquire=acquire
        job=self.job(b,self.request('sand',16))
        job_root=job.out
        def checked_room(targets,keep):
            calls.append('unload');self.assertIn('minecraft:sand',keep)
            # The first acquisition transaction is settled before cleanup starts.
            self.assertEqual('make_room',json.loads((job_root/'inflight.json').read_text())['operation'])
            b.held['minecraft:stone']=0;return {'phase':'done'}
        b.make_room=checked_room
        result=job.run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual(['reserve','unload','acquire'],calls)
        self.assertEqual(16,b.held['minecraft:sand'])

    def test_unknown_quarry_failure_does_not_trigger_automatic_unload(self):
        b=FakeBackend(self.catalog);unloads=[]
        b.acquire=lambda item,count:{'phase':'blocked','code':'native_clear_stopped','detail':'Unknown stop'}
        b.make_room=lambda targets,keep:unloads.append(1)
        result=self.job(b,self.request('sand',16)).run()
        self.assertEqual('blocked',result['state']);self.assertFalse(unloads)

    def test_missing_furnace_fuel_is_locally_fetched_or_acquired_before_retry(self):
        b=FakeBackend(self.catalog,held={'minecraft:cobblestone':6},depot={'minecraft:coal':1})
        real_smelt=b.smelt
        def fueled(recipe,target):
            if b.held['minecraft:coal']<1:
                return {'phase':'waiting','requirements':{'minecraft:coal':1}}
            return real_smelt(recipe,target)
        b.smelt=fueled
        result=self.job(b,self.request('smooth_stone',6)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual(6,b.held['minecraft:smooth_stone'])
        self.assertTrue(any(c[0]=='fetch' and c[1].get('minecraft:coal')==1 for c in b.calls))

    def test_iron_is_acquired_as_raw_iron_then_actually_smelted(self):
        self.add_recipes();b=FakeBackend(self.catalog)
        result=self.job(b,self.request('iron_ingot',16)).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual([('acquire','minecraft:raw_iron',16)], [c for c in b.calls if c[0]=='acquire'])
        self.assertEqual([('smelt','minecraft:iron_ingot',16)], [c for c in b.calls if c[0]=='smelt'])

    def test_warehouse_bone_hint_selects_recipe_but_never_counts_as_inventory(self):
        self.add_recipes()
        planned=plan(self.catalog,{'minecraft:white_dye':18},{},{'minecraft:bone_block':64})
        self.assertEqual({'minecraft:bone_block':2},planned['missing_supplies'])
        self.assertEqual({},planned['input_stock'])
        self.assertTrue(any(step['item']=='minecraft:bone_meal' for step in planned['steps']))

    def test_missing_capability_is_blocked_not_reported_complete(self):
        b=FakeBackend(self.catalog);b.unsupported={'minecraft:gravel'}
        result=self.job(b).run()
        self.assertEqual('blocked',result['state']);self.assertLess(result['done'],result['total'])

    def test_lying_done_receipts_cannot_complete_without_inventory_progress(self):
        b=FakeBackend(self.catalog);b.lie=True
        result=self.job(b,self.request('sand',64)).run()
        self.assertEqual('blocked',result['state'])
        self.assertEqual(2,len([c for c in b.calls if c[0]=='acquire']))
        self.assertEqual(0,result['done'])

    def test_health_lock_manual_takeover_and_disconnect_never_start_actions(self):
        for field,value in [('hold',True),('manual',True),('connected',False),('health',12),('health',float('nan'))]:
            with self.subTest(field=field):
                b=FakeBackend(self.catalog);setattr(b,field,value)
                result=self.job(b,name=field+str(value)).run()
                self.assertEqual('paused',result['state']);self.assertEqual([],b.calls)
                self.assertEqual(1,b.finish_count)

    def test_changed_world_blocks_and_cannot_reconnect(self):
        b=FakeBackend(self.catalog);b.world='other'
        result=self.job(b).run()
        self.assertEqual('blocked',result['state']);self.assertEqual([],b.calls)

    def test_cancel_command_is_distinct_terminal_state(self):
        b=FakeBackend(self.catalog);j=self.job(b)
        (j.out/'control.json').write_text(json.dumps({'id':'test-job','action':'cancel','created_at':1001}))
        result=j.run()
        self.assertEqual('cancelled',result['state']);self.assertTrue(result['terminal']);self.assertEqual([],b.calls)

    def test_interrupted_smelting_does_not_repeat_input_without_reconciliation(self):
        b=FakeBackend(self.catalog,held={'minecraft:cobblestone':6});b.pause_smelt=True
        request=self.request('smooth_stone',6);j=self.job(b,request)
        self.assertEqual('paused',j.run()['state']);calls=len(b.calls)
        resumed=self.job(b,request)
        result=resumed.run()
        self.assertEqual('blocked',result['state']);self.assertEqual(calls,len(b.calls))
        self.assertEqual(0,b.held['minecraft:cobblestone'])

    def test_reconciled_inflight_output_resumes_remaining_pipeline(self):
        b=FakeBackend(self.catalog,held={'minecraft:cobblestone':6});b.pause_smelt=True
        request=self.request('smooth_stone',6);j=self.job(b,request)
        self.assertEqual('paused',j.run()['state'])
        def recover(pending):
            item,count=b.pending;b.held[item]+=count;b.pending=None
            return {'phase':'done','safe_to_replan':True}
        b.recover=recover
        result=self.job(b,request).run()
        self.assertEqual('completed',result['state'],result)
        self.assertEqual(1,len([c for c in b.calls if c[:2]==('smelt','minecraft:stone')]))

    def test_explicit_unresolved_work_cannot_be_overruled_by_enough_final_items(self):
        b=FakeBackend(self.catalog,held={'minecraft:cobblestone':6});b.pause_smelt=True
        request=self.request('smooth_stone',6);j=self.job(b,request);j.run()
        b.held['minecraft:smooth_stone']=6;b.held['minecraft:stone']=6;b.pending=None
        b.recover=lambda pending:{'phase':'blocked','safe_to_replan':False,'detail':'owned furnace contents unresolved'}
        result=self.job(b,request).run()
        self.assertEqual('blocked',result['state']);self.assertIn('unresolved',result['detail'])
        self.assertTrue((j.out/'inflight.json').exists())

    def test_serve_releases_paused_backend_and_recreates_only_on_resume(self):
        request=self.request('sand',16);out=self.root/'serve';contexts=[]
        first=FakeBackend(self.catalog);first.manual=True
        second=FakeBackend(self.catalog);second.revision=9
        def factory(**args):
            contexts.append(args['request'])
            if len(contexts)==1:
                first.on_finish=lambda:(out/'control.json').write_text(json.dumps({'id':'test-job','action':'resume','created_at':1001,
                    'context':{**request['context'],'expected_revision':9}}))
                return first
            return second
        result=serve(request,self.root/'empty-automation',out,factory,poll_seconds=0)
        self.assertEqual('completed',result['state'],result)
        self.assertEqual([False,True],[c['_resume'] for c in contexts])
        self.assertEqual((1,1),(first.finish_count,second.finish_count))

    def test_restarted_paused_job_does_not_reacquire_without_resume_control(self):
        request=self.request('sand',16);b=FakeBackend(self.catalog);b.manual=True
        j=self.job(b,request);self.assertEqual('paused',j.run()['state'])
        with patch('test_material_jobs.FakeBackend',side_effect=AssertionError('Must not create a controller')) as factory:
            result=serve(request,self.root/'empty-automation',j.out,factory,poll_seconds=0,max_pause_seconds=0)
        self.assertEqual('blocked',result['state']);factory.assert_not_called()

    def test_cross_world_resume_context_is_rejected_before_creating_backend(self):
        request=self.request('sand',16);b=FakeBackend(self.catalog);b.manual=True
        j=self.job(b,request);j.run()
        (j.out/'control.json').write_text(json.dumps({'id':request['id'],'action':'resume','created_at':1001,
                                                     'context':{**request['context'],'world_session':'other'}}))
        with patch('test_material_jobs.FakeBackend') as factory:
            result=serve(request,self.root/'empty-automation',j.out,factory,poll_seconds=0)
        self.assertEqual('blocked',result['state']);factory.assert_not_called()

    def test_resume_context_is_persisted_without_rewriting_initial_request(self):
        request=self.request('sand',16);b=FakeBackend(self.catalog);b.manual=True
        j=self.job(b,request);j.run()
        context={**request['context'],'expected_revision':9,'start_pos':[5,64,8]}
        (j.out/'control.json').write_text(json.dumps({'id':request['id'],'action':'resume','created_at':1001,'context':context}))
        self.assertEqual('resume',j.control());self.assertEqual(context,j.context)
        self.assertEqual(request,json.loads((j.out/'request.json').read_text()))
        recovered=MaterialJob(request,j.out,b)
        self.assertEqual(context,recovered.context)

    def test_lock_appearing_after_fetch_prevents_completed_claim(self):
        b=FakeBackend(self.catalog,depot={'minecraft:white_concrete':64})
        fetch=b.fetch
        def locked_fetch(targets):
            receipt=fetch(targets);b.hold=True;return receipt
        b.fetch=locked_fetch;j=self.job(b)
        result=j.run()
        self.assertEqual('paused',result['state']);self.assertFalse(result['terminal'])
        self.assertTrue((j.out/'inflight.json').exists())

    def test_backend_returning_with_native_work_active_cannot_schedule_again(self):
        b=FakeBackend(self.catalog)
        acquire=b.acquire
        def pending_acquire(item,target):
            receipt=acquire(item,target);b.pending=(item,target);return receipt
        b.acquire=pending_acquire;j=self.job(b,self.request('sand',16))
        result=j.run()
        self.assertEqual('blocked',result['state']);self.assertTrue((j.out/'inflight.json').exists())
        self.assertEqual(1,len([c for c in b.calls if c[0]=='acquire']))

    def test_mid_action_cancel_checkpoint_preserves_intent_and_releases_owner(self):
        b=FakeBackend(self.catalog);j=self.job(b,self.request('sand',16))
        def cancelling_acquire(item,target):
            (j.out/'control.json').write_text(json.dumps({'id':'test-job','action':'cancel','created_at':1001}))
            j.checkpoint()
            raise AssertionError('No further action after cancellation')
        b.acquire=cancelling_acquire
        result=j.run()
        self.assertEqual('cancelled',result['state']);self.assertTrue((j.out/'inflight.json').exists())
        self.assertEqual(1,b.finish_count);self.assertEqual('fake-native-owner',result['native_task_session'])

    def test_no_projection_deficits_is_not_enough_without_full_match(self):
        b=FakeBackend(self.catalog);b.total=100;b.matched=99
        result=self.job(b,self.request(projection=True)).run()
        self.assertEqual('blocked',result['state']);self.assertEqual([],b.calls)

    def test_blocked_frontier_requests_new_materials_before_retrying_build(self):
        b=FakeBackend(self.catalog,held={'minecraft:furnace':1},
                      depot={'minecraft:white_concrete_powder':128,'minecraft:smooth_stone':64},
                      projection={'minecraft:furnace':1,'minecraft:white_concrete':128,'minecraft:smooth_stone':64})
        original=b.build
        def build(key):
            for item,count in (('minecraft:white_concrete',128),('minecraft:smooth_stone',64)):
                if b.held[item]<count:
                    b.calls.append(('build_wait',item))
                    return {'phase':'waiting','requirements':{item:count}}
            return original(key)
        b.build=build
        result=self.job(b,self.request(projection=True)).run()
        self.assertEqual('completed',result['state']);self.assertEqual(193,b.matched)
        self.assertEqual(2,sum(call[0]=='build_wait' for call in b.calls))

    def test_internal_air_conflicts_are_not_reported_as_finished(self):
        b=FakeBackend(self.catalog);b.total=b.matched=100
        original=b.observe
        def observe():
            value=original();value['projection_audit']['enclosed_air_conflicts']=2;return value
        b.observe=observe
        result=self.job(b,self.request(projection=True)).run()
        self.assertEqual('blocked',result['state']);self.assertIn('占位冲突',result['detail'])
        self.assertEqual([],b.calls)

    def test_out_directory_cannot_be_reused_for_changed_targets(self):
        b=FakeBackend(self.catalog);self.job(b)
        with self.assertRaisesRegex(ValueError,'different material request'):
            self.job(b,self.request(count=128))


if __name__=='__main__':
    unittest.main()
