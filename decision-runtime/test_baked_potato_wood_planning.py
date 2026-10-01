"""Offline baked-potato planning through the real recipe/fuel catalog, no game client."""
from collections import Counter
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

POTATO, BAKED = 'minecraft:potato', 'minecraft:baked_potato'
PLANKS, LOG = 'minecraft:oak_planks', 'minecraft:oak_log'
COAL, CHARCOAL = 'minecraft:coal', 'minecraft:charcoal'
JAR = Path('/Applications/.minecraft/versions/26.1.2/26.1.2.jar')


class LegacyFuelBoundaryTest(unittest.TestCase):
    def test_recipe_only_catalog_does_not_claim_wood_fuel_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            jar=Path(folder)/'recipes.jar'
            with zipfile.ZipFile(jar,'w') as archive:
                for name,value in {
                    'baked_potato':{'type':'minecraft:smelting','ingredient':POTATO,'result':{'id':BAKED}},
                    'oak_planks':{'type':'minecraft:crafting_shapeless','ingredients':[LOG],
                                  'result':{'id':PLANKS,'count':4}}}.items():
                    archive.writestr('data/minecraft/recipe/'+name+'.json',json.dumps(value))
            result=plan(ProcessingCatalog(jar),{BAKED:7},{POTATO:8,BAKED:3,LOG:54,PLANKS:1})
            self.assertNotIn('fuel_preparation',result)
            self.assertFalse(any('fuel_allow_items' in step for step in result['steps']))


@unittest.skipUnless(JAR.is_file(),'Actual 26.1.2 JAR is unavailable')
class BakedPotatoWoodPlanningTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=ProcessingCatalog(JAR)
        from smelting_fuel import FuelCatalog
        cls.fuel=FuelCatalog(JAR)
        assert cls.fuel.evidence['extra_fuels_verified']
    def stock(self,**changes):
        return {POTATO:8,BAKED:3,LOG:54,PLANKS:1,**changes}
    def cooking(self,result):
        return next(step for step in result['steps'] if step['kind']=='smelt' and step['item']==BAKED)
    def test_prepares_one_owned_log_before_four_additional_potatoes(self):
        stock=self.stock();result=plan(self.catalog,{BAKED:7},stock)
        action=[step for step in result['steps'] if step['kind']!='reserve']
        self.assertEqual(('craft',PLANKS,4),(action[0]['kind'],action[0]['item'],action[0]['produced']))
        self.assertEqual({LOG:1},action[0]['ingredients'])
        self.assertEqual(('smelt',BAKED,4),(action[1]['kind'],action[1]['item'],action[1]['produced']))
        self.assertEqual([PLANKS],action[1]['fuel_allow_items'])
        self.assertNotIn(POTATO,action[1]['fuel_keep'])
        self.assertNotIn('source_keep',action[1])
        self.assertFalse(result['fuel_preparation']['source_reserve_supported'])
        self.assertFalse(result['missing_supplies']);self.assertEqual(stock,self.stock())
        held=Counter(stock)
        for step in action:
            for item,n in step['ingredients'].items():
                self.assertGreaterEqual(held[item],n);held[item]-=n
            held[step['item']]+=step['produced']
        self.assertEqual(+held,+(Counter(result['targets'])+Counter(result['surplus'])))
    def test_owned_planks_and_existing_coal_or_charcoal_retain_distinct_routes(self):
        result=plan(self.catalog,{BAKED:7},self.stock(**{LOG:0,PLANKS:4}))
        self.assertEqual([PLANKS],self.cooking(result)['fuel_allow_items'])
        self.assertFalse(any(step['kind']=='craft' for step in result['steps']))
        for fuel in (COAL,CHARCOAL):
            with self.subTest(fuel=fuel):
                result=plan(self.catalog,{BAKED:7},self.stock(**{fuel:1}))
                self.assertNotIn('fuel_allow_items',self.cooking(result))
                self.assertNotIn('fuel_preparation',result)
    def test_hints_nonflammable_wood_and_missing_input_cannot_create_a_ready_prefix(self):
        for stock,hint in (({POTATO:8,BAKED:3},{LOG:54}),
                           ({POTATO:8,BAKED:3,'minecraft:warped_stem':64},{}),
                           ({POTATO:2,BAKED:3,LOG:54,PLANKS:1},{})):
            with self.subTest(stock=stock):
                result=plan(self.catalog,{BAKED:7},stock,hint)
                self.assertNotIn('fuel_preparation',result)
                self.assertFalse(any('fuel_allow_items' in step for step in result['steps']))
                self.assertFalse(any(step.get('item')==PLANKS and step['kind']=='craft' for step in result['steps']))
    def test_later_sticks_and_requested_planks_are_retained_from_fuel(self):
        result=plan(self.catalog,{BAKED:7,'minecraft:stick':8},self.stock())
        self.assertEqual(4,self.cooking(result)['fuel_keep'][PLANKS])
        result=plan(self.catalog,{BAKED:7,PLANKS:1},self.stock())
        self.assertEqual(1,self.cooking(result)['fuel_keep'][PLANKS])
        result=plan(self.catalog,{BAKED:7,LOG:54},self.stock())
        self.assertNotIn('fuel_allow_items',self.cooking(result))
    def test_entire_explicit_request_is_not_silently_changed_into_a_seed_policy(self):
        result=plan(self.catalog,{BAKED:11},self.stock())
        self.assertEqual({POTATO:8},self.cooking(result)['ingredients'])
        self.assertEqual(11,result['targets'][BAKED])
        self.assertFalse(result['fuel_preparation']['source_reserve_supported'])
    def job(self,backend,out):
        request={'schema':1,'id':'baked-potato-test','mode':'item','targets':{BAKED:7},'created_at':1,
                 'context':{'server':'example.test','dimension':'minecraft:overworld','world_session':'world',
                            'expected_revision':1,'start_pos':[0,64,0]}}
        return MaterialJob(request,out,backend=backend)
    def backend(self,held):
        fuel=self.fuel
        class FuelBackend(FakeBackend):
            def smelt(self,recipe,target):
                from smelting_fuel import policy,select_fuels
                self.calls.append(('smelt',recipe['output'],target))
                amount=target-self.held[recipe['output']]
                keep,allowed=policy(fuel,{},recipe)
                choice=select_fuels(fuel,dict(+self.held),[amount],recipe['cooking_ticks_per_recipe'],
                                    recipe['source'],recipe['output'],keep,allowed)
                if not choice['ready']:
                    self.calls.append(('fuel_requirements',choice['requirements']))
                    return {'phase':'waiting','requirements':choice['requirements']}
                for item,n in choice['fuel_totals'].items():self.held[item]-=n
                self.calls.append(('fuel_consumed',choice['fuel_totals']))
                return super().smelt(recipe,target)
        return FuelBackend(self.catalog,held=held)
    def test_generic_job_uses_real_wood_fuel_and_stock_without_ore_acquisition(self):
        backend=self.backend(self.stock())
        with tempfile.TemporaryDirectory() as folder:
            result=self.job(backend,Path(folder)).run()
        self.assertEqual('completed',result['state'])
        self.assertEqual((7,4,53,2),(backend.held[BAKED],backend.held[POTATO],backend.held[LOG],backend.held[PLANKS]))
        self.assertIn(('fuel_consumed',{PLANKS:3}),backend.calls)
        self.assertFalse(any(call[0]=='acquire' for call in backend.calls))
    def test_actual_single_furnace_uses_three_carried_planks_without_assuming_sixteen_furnaces(self):
        stock=self.stock(**{LOG:0,PLANKS:3})
        planned=plan(self.catalog,{BAKED:7},stock)
        self.assertFalse(planned['fuel_preparation']['stock_prefix_ready'])
        self.assertEqual([PLANKS],self.cooking(planned)['fuel_allow_items'])
        self.assertFalse(any(step['kind']=='craft' for step in planned['steps']))
        backend=self.backend(stock)
        with tempfile.TemporaryDirectory() as folder:
            result=self.job(backend,Path(folder)).run()
        self.assertEqual('completed',result['state'])
        self.assertEqual(7,backend.held[BAKED]);self.assertEqual(4,backend.held[POTATO])
        self.assertEqual(0,backend.held[PLANKS]);self.assertEqual(0,backend.held[LOG])
        self.assertFalse(any(call[0]=='acquire' for call in backend.calls))
    def test_no_fuel_source_stays_blocked_and_unknown_smelt_is_never_repeated(self):
        backend=self.backend({POTATO:8,BAKED:3});backend.unsupported.add(COAL)
        with tempfile.TemporaryDirectory() as folder:
            result=self.job(backend,Path(folder)).run()
        self.assertEqual('blocked',result['state']);self.assertEqual(3,backend.held[BAKED])
        self.assertEqual(0,backend.held[COAL]);self.assertTrue(any(call[0]=='acquire' for call in backend.calls))
        backend=self.backend(self.stock());backend.pause_smelt=True
        with tempfile.TemporaryDirectory() as folder:
            result=self.job(backend,Path(folder)).run()
            self.assertTrue((Path(folder)/'inflight.json').is_file())
        self.assertEqual('paused',result['state'])
        self.assertEqual(1,sum(call[0]=='fuel_consumed' for call in backend.calls))
        self.assertFalse(any(call[0]=='acquire' for call in backend.calls))


if __name__=='__main__':unittest.main()
