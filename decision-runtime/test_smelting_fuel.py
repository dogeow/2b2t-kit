from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import zipfile
import json

from smelting_fuel import FuelCatalog,select_fuels,policy,FUEL_CLASS

JAR=Path('/Applications/.minecraft/versions/26.1.2/26.1.2.jar')
COAL='minecraft:coal';CHARCOAL='minecraft:charcoal';LOG='minecraft:oak_log';PLANK='minecraft:oak_planks'


class FuelPlanTest(unittest.TestCase):
    def setUp(self):
        self.catalog=SimpleNamespace(durations={COAL:1600,CHARCOAL:1600,LOG:300,PLANK:300},evidence={'kind':'offline_fixture'})
    def test_coal_existing_path_preserves_rounding_per_furnace(self):
        p=select_fuels(self.catalog,{COAL:15,'minecraft:raw_iron':118},[20,20,20,20,19,19],200,'minecraft:raw_iron','minecraft:iron_ingot')
        self.assertFalse(p['ready']);self.assertEqual({COAL:18},p['requirements'])
        self.assertEqual({COAL:18},p['fuel_totals'])
    def test_charcoal_is_real1600_fuel_not_a_coal_alias(self):
        p=select_fuels(self.catalog,{CHARCOAL:2,LOG:12},[12],200,LOG,'minecraft:terracotta')
        self.assertTrue(p['ready']);self.assertEqual(CHARCOAL,p['entries'][0]['fuel_item'])
        self.assertEqual(2,p['entries'][0]['fuel']);self.assertEqual(3200,p['entries'][0]['planned_fuel_ticks'])
    def test_torch_charcoal_requirement_keeps_future_planks(self):
        p=select_fuels(self.catalog,{LOG:57,PLANK:2},[3,3,2,2,2],200,LOG,CHARCOAL,{PLANK:6},[PLANK])
        self.assertFalse(p['ready']);self.assertEqual({PLANK:16},p['requirements'])
        self.assertEqual({PLANK:10},p['fuel_totals'])
    def test_same_log_source_and_fuel_reserve_input_separately(self):
        p=select_fuels(self.catalog,{LOG:12},[12],200,LOG,CHARCOAL,allowed=[LOG])
        self.assertFalse(p['ready']);self.assertEqual({LOG:20},p['requirements'])
        p=select_fuels(self.catalog,{LOG:20},[12],200,LOG,CHARCOAL,allowed=[LOG])
        self.assertTrue(p['ready']);self.assertEqual(8,p['entries'][0]['fuel'])
    def test_no_output_charcoal_can_fund_its_own_production(self):
        p=select_fuels(self.catalog,{LOG:12,CHARCOAL:20},[12],200,LOG,CHARCOAL)
        self.assertFalse(p['ready']);self.assertEqual({COAL:2},p['requirements'])
        self.assertNotIn(CHARCOAL,p['fuel_totals'])
    def test_reserved_coal_and_output_are_not_spent(self):
        p=select_fuels(self.catalog,{COAL:8,CHARCOAL:2,LOG:12},[12],200,LOG,'minecraft:iron_ingot',{COAL:8})
        self.assertTrue(p['ready']);self.assertEqual({CHARCOAL:2},p['fuel_totals'])
    def test_multiple_furnaces_can_use_different_fixed_fuel_items(self):
        p=select_fuels(self.catalog,{COAL:1,CHARCOAL:1,PLANK:2,LOG:9},[3,3,3],200,LOG,'minecraft:stone',allowed=[COAL,CHARCOAL,PLANK])
        self.assertTrue(p['ready']);self.assertEqual([COAL,CHARCOAL,PLANK],[r['fuel_item'] for r in p['entries']])
    def test_wood_is_action_scoped_and_requires_verified_allowlist(self):
        keep,allowed=policy(self.catalog,{},{});self.assertEqual([COAL,CHARCOAL],allowed)
        keep,allowed=policy(self.catalog,{'fuel_keep':{PLANK:4}}, {'fuel_allow_items':[PLANK],'fuel_keep':{PLANK:6}})
        self.assertEqual({PLANK:6},keep);self.assertEqual([PLANK],allowed)
        for bad in [[{'item':PLANK}],['minecraft:warped_planks'],[PLANK,PLANK]]:
            with self.assertRaises(ValueError):policy(self.catalog,{}, {'fuel_allow_items':bad})
    def test_existing_client_owner_goal_reservations_merge_without_backend_import(self):
        c=SimpleNamespace(owner=SimpleNamespace(request={'targets':{COAL:3,PLANK:5}}))
        keep,_=policy(self.catalog,{'fuel_keep':{COAL:4}}, {'fuel_keep':{PLANK:6}},c)
        self.assertEqual({COAL:4,PLANK:6},keep)
    def test_bounded_slots_and_quantities_fail_closed(self):
        for parts in [[65],[True],[-1],[0]*17]:
            with self.assertRaises(ValueError):select_fuels(self.catalog,{LOG:100},parts,200,LOG,CHARCOAL)
        with self.assertRaises(ValueError):select_fuels(self.catalog,{COAL:True},[1],200,LOG,CHARCOAL)


@unittest.skipUnless(JAR.exists(),'Current Minecraft jar not available')
class ActualFuelFactsTest(unittest.TestCase):
    def test_blaze_rods_are_checked_native_fuel_but_never_enabled_by_default(self):
        c=FuelCatalog(JAR)
        self.assertEqual(2400,c.durations['minecraft:blaze_rod'])
        self.assertNotIn('minecraft:blaze_rod',policy(c,{}, {})[1])
        p=select_fuels(c,{'minecraft:blaze_rod':32,'minecraft:cobblestone':322},[20]*16,
                      200,'minecraft:cobblestone','minecraft:stone',
                      {'minecraft:cobblestone':2},['minecraft:blaze_rod'])
        self.assertTrue(p['ready']);self.assertEqual({'minecraft:blaze_rod':32},p['fuel_totals'])
        self.assertTrue(all(e['fuel']==2 and e['planned_fuel_ticks']==4800 for e in p['entries']))
    def test_current_compiled_fuel_class_and_tags_verify_four_requested_families(self):
        c=FuelCatalog(JAR);self.assertTrue(c.evidence['extra_fuels_verified'])
        self.assertEqual(1600,c.durations[COAL]);self.assertEqual(1600,c.durations[CHARCOAL])
        self.assertEqual(300,c.durations[LOG]);self.assertEqual(300,c.durations[PLANK])
        self.assertNotIn('minecraft:warped_planks',c.durations);self.assertNotIn('minecraft:crimson_stem',c.durations)
    def test_changed_game_fuel_class_does_not_inherit_known_wood_burn_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'wrong.jar'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr(FUEL_CLASS,b'unverified');z.writestr('version.json',json.dumps({'id':'26.1.2'}))
            with self.assertRaises(ValueError):FuelCatalog(p)


if __name__=='__main__':unittest.main()
