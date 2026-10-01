"""Pure planning + generic MaterialJob regressions; no Minecraft client/RPC."""
from collections import Counter
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from material_jobs import MaterialJob
from material_jobs.planning import plan
from material_jobs.protocol import JobPaused
from projection_material_plan import ProcessingCatalog
from test_material_jobs import FakeBackend

TORCH, COAL, CHARCOAL, STICK = ('minecraft:'+s for s in ('torch', 'coal', 'charcoal', 'stick'))
OAK, PLANKS = 'minecraft:oak_log', 'minecraft:oak_planks'


def jar_fixture(path):
    with zipfile.ZipFile(path, 'w') as z:
        def write(name, data): z.writestr('data/minecraft/'+name+'.json', json.dumps(data))
        write('tags/item/logs_that_burn', {'values': [OAK, 'minecraft:cherry_log']})
        write('tags/item/planks', {'values': [PLANKS, 'minecraft:cherry_planks', 'minecraft:warped_planks']})
        write('recipe/torch', {'type': 'minecraft:crafting_shaped', 'pattern': ['X','#'],
                              'key': {'X': [COAL, CHARCOAL], '#': STICK},
                              'result': {'id': TORCH, 'count': 4}})
        write('recipe/charcoal', {'type': 'minecraft:smelting', 'ingredient': '#minecraft:logs_that_burn',
                                 'result': {'id': CHARCOAL}, 'cookingtime': 200})
        write('recipe/stick', {'type': 'minecraft:crafting_shaped', 'pattern': ['#','#'],
                              'key': {'#': '#minecraft:planks'}, 'result': {'id': STICK, 'count': 4}})
        for raw, out in [(OAK, PLANKS), ('minecraft:cherry_log', 'minecraft:cherry_planks'),
                         ('minecraft:warped_stem', 'minecraft:warped_planks')]:
            write('recipe/'+out.split(':')[1], {'type': 'minecraft:crafting_shapeless',
                  'ingredients': [raw], 'result': {'id': out, 'count': 4}})


class TorchPlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); jar = self.root/'client.jar'; jar_fixture(jar)
        self.catalog = ProcessingCatalog(jar)
    def balance(self, result):
        held = Counter(result['input_stock'])
        for step in result['steps']:
            if step['kind'] == 'reserve': continue
            if step['kind'] == 'acquire': held[step['item']] += step['count']; continue
            for item, amount in step['ingredients'].items():
                self.assertGreaterEqual(held[item], amount)
                held[item] -= amount
            held[step['item']] += step['produced']
        self.assertEqual(+held, +(Counter(result['targets']) + Counter(result['surplus'])))
    def test_twenty_coal_crafts_eighty_before_requesting_remaining_twelve(self):
        result = plan(self.catalog, {TORCH: 128}, {COAL: 20, STICK: 32})
        actionable = [s for s in result['steps'] if s['kind'] != 'reserve']
        self.assertEqual(('craft', TORCH, 80),
                         (actionable[0]['kind'], actionable[0]['item'], actionable[0]['produced']))
        self.assertEqual({'minecraft:coal': 12}, result['missing_supplies'])
        self.assertEqual(128, result['targets'][TORCH]); self.balance(result)
    def test_logs_make_sticks_for_ready_coal_before_charcoal_remainder(self):
        result = plan(self.catalog, {TORCH: 128}, {COAL: 20, OAK: 57})
        ready = next(i for i,s in enumerate(result['steps']) if s.get('item') == TORCH and s['kind'] == 'craft')
        charcoal = next(i for i,s in enumerate(result['steps']) if s.get('item') == CHARCOAL and s['kind'] == 'smelt')
        self.assertLess(ready, charcoal); self.assertEqual(80, result['steps'][ready]['produced'])
        self.assertEqual(12, result['steps'][charcoal]['produced'])
        self.assertEqual(OAK, result['steps'][charcoal]['source'])
        self.assertEqual([PLANKS],result['steps'][charcoal]['fuel_allow_items'])
        self.assertEqual(6,result['steps'][charcoal]['fuel_keep'].get(PLANKS))
        self.assertFalse(result['missing_supplies']); self.balance(result)
    def test_existing_coal_and_charcoal_are_both_used_without_new_supply(self):
        result = plan(self.catalog, {TORCH: 128}, {COAL: 20, CHARCOAL: 12, STICK: 32})
        torches = [s for s in result['steps'] if s['kind'] == 'craft' and s['item'] == TORCH]
        self.assertEqual([80,48], [s['produced'] for s in torches])
        self.assertEqual({COAL:20, STICK:20}, torches[0]['ingredients'])
        self.assertEqual({CHARCOAL:12, STICK:12}, torches[1]['ingredients'])
        self.assertFalse(result['missing_supplies']); self.balance(result)
    def test_partial_sticks_still_produce_twenty_immediately(self):
        result = plan(self.catalog, {TORCH: 128}, {COAL:20, STICK:5})
        first = next(s for s in result['steps'] if s['kind'] != 'reserve')
        self.assertEqual(20, first['produced']); self.balance(result)
        torch_steps=[s for s in result['steps'] if s['kind']=='craft' and s['item']==TORCH]
        self.assertEqual([20,60,48],[s['produced'] for s in torch_steps])
        first_new_coal=next(i for i,s in enumerate(result['steps']) if s['kind']=='acquire' and s['item']==COAL)
        owned_coal_portion=next(i for i,s in enumerate(result['steps']) if s['kind']=='craft' and s['item']==TORCH and s['produced']==60)
        self.assertLess(owned_coal_portion,first_new_coal)
    def test_small_owned_wood_produces_available_prefix_without_all_goal_inputs(self):
        result = plan(self.catalog, {TORCH:128}, {COAL:20, OAK:1})
        first = next(s for s in result['steps'] if s['kind']=='craft' and s['item']==TORCH)
        self.assertEqual(32, first['produced']); self.balance(result)
    def test_finished_coal_goal_is_reserved_not_burned_as_torch_prefix(self):
        result = plan(self.catalog, {TORCH:128, COAL:20}, {COAL:20, STICK:32})
        first = next(s for s in result['steps'] if s['kind'] != 'reserve')
        self.assertEqual(('acquire', COAL), (first['kind'],first['item']))
        self.assertEqual(20, result['reserved_finished_items'][COAL]); self.balance(result)
    def test_cherry_warehouse_hint_selects_real_input_but_never_becomes_stock(self):
        result = plan(self.catalog, {TORCH:48}, {STICK:12}, {'minecraft:cherry_log':32})
        self.assertEqual({'minecraft:cherry_log':12}, result['missing_supplies'])
        self.assertNotIn('minecraft:cherry_log', result['input_stock'])
        smelt = next(s for s in result['steps'] if s['kind']=='smelt')
        self.assertEqual('minecraft:cherry_log', smelt['source']); self.balance(result)
    def test_nonflammable_stems_never_make_imaginary_charcoal(self):
        result = plan(self.catalog, {TORCH:128}, {'minecraft:warped_stem':64})
        self.assertEqual(32, result['missing_supplies'].get(COAL))
        self.assertFalse(any(s.get('item')==CHARCOAL for s in result['steps'])); self.balance(result)
    def test_rounded_target_preserves_surplus_and_original_absolute_goal(self):
        result = plan(self.catalog, {TORCH:1}, {COAL:1,STICK:1})
        self.assertEqual({TORCH:1}, result['targets']); self.assertEqual(3, result['surplus'][TORCH])
        self.balance(result)
    def test_plan_is_deterministic_and_does_not_mutate_stock_or_catalog(self):
        stock = {COAL:20,OAK:57}; hint={'minecraft:cherry_log':64}
        before = copy.deepcopy(self.catalog.recipes)
        first=plan(self.catalog,{TORCH:128},stock,hint)
        self.assertEqual(first,plan(self.catalog,{TORCH:128},stock,hint))
        self.assertEqual({COAL:20,OAK:57},stock);self.assertEqual(before,self.catalog.recipes)
    def job(self, backend, target=128):
        backend.stack_sizes.update({item:64 for item in (TORCH,CHARCOAL,COAL,STICK,OAK,PLANKS)})
        request={'schema':1,'id':'torch-test','mode':'item','targets':{TORCH:target},'created_at':1,
                 'context':{'server':'example.test','dimension':'minecraft:overworld','world_session':'world',
                            'expected_revision':1,'start_pos':[0,64,0]}}
        return MaterialJob(request,self.root/'job',backend=backend)
    def test_generic_item_job_crafts_eighty_before_acquiring_missing_coal(self):
        backend=FakeBackend(self.catalog,held={COAL:20,STICK:32})
        result=self.job(backend).run()
        self.assertEqual('completed',result['state']);self.assertEqual(128,backend.held[TORCH])
        first_craft=next(i for i,c in enumerate(backend.calls) if c[0]=='craft')
        first_acquire=next(i for i,c in enumerate(backend.calls) if c[0]=='acquire')
        self.assertLess(first_craft,first_acquire)
        self.assertEqual(('craft',{TORCH:80}),backend.calls[first_craft])
        self.assertEqual(('acquire',COAL,12),backend.calls[first_acquire])
    def test_unprepared_coal_does_not_erase_completed_eighty(self):
        backend=FakeBackend(self.catalog,held={COAL:20,STICK:32});backend.unsupported.add(COAL)
        result=self.job(backend).run()
        self.assertEqual('blocked',result['state']);self.assertEqual(80,backend.held[TORCH])
        self.assertEqual(80,result['done'])
    def test_known_wood_job_uses_charcoal_without_ore_acquisition(self):
        backend=FakeBackend(self.catalog,held={COAL:20,OAK:57})
        result=self.job(backend).run()
        self.assertEqual('completed',result['state']);self.assertEqual(128,backend.held[TORCH])
        self.assertFalse(any(c[0]=='acquire' for c in backend.calls))
        self.assertTrue(any(c[:2]==('smelt',CHARCOAL) for c in backend.calls))
    def test_unknown_craft_receipt_is_preserved_without_new_acquisition(self):
        class Interrupted(FakeBackend):
            def craft(self,targets):
                super().craft(targets)
                raise JobPaused('Result acknowledgement unknown')
        backend=Interrupted(self.catalog,held={COAL:20,STICK:32})
        job=self.job(backend);result=job.run()
        self.assertEqual('paused',result['state']);self.assertEqual(80,backend.held[TORCH])
        self.assertTrue((self.root/'job/inflight.json').is_file())
        self.assertFalse(any(c[0]=='acquire' for c in backend.calls))

    @unittest.skipUnless(Path('/Applications/.minecraft/versions/26.1.2/26.1.2.jar').is_file(),
                         'Actual26.1.2 fuel JAR is not installed')
    def test_generic_job_uses_real_fuel_selector_and_automatically_makes_reserved_planks(self):
        from furnace_batches import distribution
        from smelting_fuel import FuelCatalog, policy, select_fuels
        fuel = FuelCatalog('/Applications/.minecraft/versions/26.1.2/26.1.2.jar')
        self.assertTrue(fuel.evidence['extra_fuels_verified'])
        class FuelBackend(FakeBackend):
            def smelt(self,recipe,target):
                self.calls.append(('smelt',recipe['output'],target))
                amount=target-self.held[recipe['output']]
                keep,allowed=policy(fuel,{},recipe)
                selected=select_fuels(fuel,dict(+self.held),distribution(amount,5),
                    recipe['cooking_ticks_per_recipe'],recipe['source'],recipe['output'],keep,allowed)
                if not selected['ready']:
                    self.calls.append(('fuel_requirements',selected['requirements']))
                    return {'phase':'waiting','requirements':selected['requirements']}
                for item,n in selected['fuel_totals'].items():self.held[item]-=n
                self.calls.append(('fuel_consumed',selected['fuel_totals']))
                self.held[recipe['source']]-=amount;self.held[recipe['output']]+=amount
                return {'phase':'done'}
        backend=FuelBackend(self.catalog,held={COAL:20,OAK:57})
        result=self.job(backend).run()
        self.assertEqual('completed',result['state']);self.assertEqual(128,backend.held[TORCH])
        self.assertEqual(38,backend.held[OAK]);self.assertEqual(2,backend.held[PLANKS])
        self.assertIn(('craft',{TORCH:80}),backend.calls)
        self.assertIn(('fuel_requirements',{PLANKS:16}),backend.calls)
        self.assertIn(('fuel_consumed',{PLANKS:10}),backend.calls)
        self.assertFalse(any(c[0]=='acquire' for c in backend.calls))


if __name__=='__main__':unittest.main()
