from collections import Counter
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from material_jobs.colored_pipeline import (run, coverage, choose_recipe, COLORS,
                                           _ingredients,_craft_site_balanced)
from types import SimpleNamespace
from material_jobs.protocol import JobPaused, JobBlocked
from projection_material_plan import ProcessingCatalog
from recipe_catalog import RecipeCatalog


def fixture(path):
    recipes = {}
    def shapeless(name, output, ingredients, count=1):
        recipes[name] = {"type":"minecraft:crafting_shapeless", "ingredients":ingredients,
                         "result":{"id":output,"count":count}}
    for color in COLORS:
        shapeless(color+"_concrete_powder", "minecraft:"+color+"_concrete_powder",
                  ["minecraft:"+color+"_dye"]+["minecraft:sand"]*4+["minecraft:gravel"]*4,8)
        shapeless(color+"_terracotta", "minecraft:"+color+"_terracotta",
                  ["minecraft:terracotta"]*8+["minecraft:"+color+"_dye"],8)
    shapeless("clay", "minecraft:clay", ["minecraft:clay_ball"]*4)
    shapeless("red_dye_from_poppy", "minecraft:red_dye", ["minecraft:poppy"])
    shapeless("red_dye_from_rose_bush", "minecraft:red_dye", ["minecraft:rose_bush"],2)
    shapeless("white_dye", "minecraft:white_dye", ["minecraft:bone_meal"])
    shapeless("bone_meal", "minecraft:bone_meal", ["minecraft:bone"],3)
    shapeless("bone_meal_from_bone_block", "minecraft:bone_meal", ["minecraft:bone_block"],9)
    shapeless("blue_dye", "minecraft:blue_dye", ["minecraft:lapis_lazuli"])
    shapeless("cyan_dye", "minecraft:cyan_dye", ["minecraft:blue_dye","minecraft:green_dye"],2)
    shapeless("cyan_dye_from_pitcher_plant", "minecraft:cyan_dye", ["minecraft:pitcher_plant"],2)
    shapeless("pink_dye_from_red_white_dye", "minecraft:pink_dye", ["minecraft:red_dye","minecraft:white_dye"],2)
    shapeless("pink_dye_from_peony", "minecraft:pink_dye", ["minecraft:peony"],2)
    for name, raw, output in (("terracotta","clay","terracotta"),("green_dye","cactus","green_dye")):
        recipes[name] = {"type":"minecraft:smelting", "ingredient":"minecraft:"+raw,
                         "cookingtime":200,"result":{"id":"minecraft:"+output}}
    with zipfile.ZipFile(path,"w") as z:
        for name, data in recipes.items():
            z.writestr("data/minecraft/recipe/"+name+".json",json.dumps(data))


class Client:
    world="world"
    def __init__(self, stock):
        self.stock=Counter(stock); self.actions=[]
    def status(self):
        return {"world_session":self.world,"manual_movement":False,
                "connected":True,"health":20,"food":20,"guard_armed":True,
                "guard_pve_only":True,"guard_busy":False,"under_water":False,
                "inventory":[{"slot":i,"item":k,"count":n,"max_stack":64}
                             for i,(k,n) in enumerate(self.stock.items()) if n],
                "screen":"","menu":{"type":"InventoryMenu"}}


class Backend:
    def __init__(self,c,jar):
        self.client=c; c.colored_backend=self
        self.crafting_catalog=RecipeCatalog(jar); self.calls=[]
    def ensure_client(self):return self.client
    def fetch(self,targets):
        self.calls.append(("fetch",dict(targets)))
        return {"phase":"waiting","missing":{i:n-self.client.stock[i] for i,n in targets.items() if n>self.client.stock[i]}}
    def craft(self,targets):
        self.calls.append(("craft",dict(targets)))
        for item,target in targets.items():
            recipe=self.crafting_catalog.recipes[item][0]
            rounds=math.ceil((target-self.client.stock[item])/recipe.count)
            for raw,n in _ingredients(recipe,rounds).items():
                assert self.client.stock[raw]>=n
                self.client.stock[raw]-=n
            self.client.stock[item]+=rounds*recipe.count
        return {"phase":"done"}
    def smelt(self,recipe,target):
        self.calls.append(("smelt",recipe,target))
        n=target-self.client.stock[recipe["output"]]
        self.client.stock[recipe["source"]]-=n
        self.client.stock["minecraft:coal"]-=math.ceil(n/8)
        self.client.stock[recipe["output"]]+=n
        return {"phase":"done"}
    def harden(self,item,target):
        self.calls.append(("harden",item,target))
        n=target-self.client.stock[item]
        self.client.stock[item+"_powder"]-=n; self.client.stock[item]+=n
        return {"phase":"done"}
    def acquire(self,item,target):
        self.calls.append(("acquire",item,target))
        return {"phase":"waiting","code":"WAIT_SOURCE","requirements":{item:target}}


class ColoredPipelineTest(unittest.TestCase):
    def test_positive_ingredient_arrival_during_travel_uses_exact_craft_site_balance(self):
        c=Client({'minecraft:pink_dye':1,'minecraft:sand':4,'minecraft:gravel':4});c.task='task';c.rev=7
        class ArrivalBackend(Backend):
            def craft(self,targets):
                self.client.stock['minecraft:sand']+=1
                before=dict(self.client.stock);result=super().craft(targets)
                result.update(complete=True,inventory_observed_at=2,craft_site_observation={
                    'schema':1,'world_session':c.world,'task_session':c.task,'revision_before':7,'revision_after':7,
                    'before_time':1,'after_time':3,'before':before,'after':dict(self.client.stock)})
                return result
        b=ArrivalBackend(c,self.jar);result=self.execute(c,'minecraft:pink_concrete',8)
        self.assertEqual('done',result['phase']);self.assertEqual(8,c.stock['minecraft:pink_concrete'])
        self.assertEqual(1,c.stock['minecraft:sand']);self.assertEqual(1,sum(k=='craft'for k,*_ in b.calls))
        book=json.loads((self.root/'job/colored-pipeline.json').read_text());self.assertIsNone(book['inflight'])

    def test_craft_site_witness_rejects_stale_foreign_or_unexplained_consumption(self):
        output='minecraft:pink_concrete_powder';before=Counter({'minecraft:sand':4,'minecraft:gravel':4,'minecraft:pink_dye':1})
        after=Counter({output:8,'minecraft:sand':1});ingredients={'minecraft:sand':4,'minecraft:gravel':4,'minecraft:pink_dye':1}
        c=SimpleNamespace(world='world',task='task',rev=7)
        w={'schema':1,'world_session':'world','task_session':'task','revision_before':7,'revision_after':7,
           'before_time':1,'after_time':3,'before':{**before,'minecraft:sand':5},'after':dict(after)}
        result={'complete':True,'inventory_observed_at':2,'craft_site_observation':w}
        self.assertTrue(_craft_site_balanced(result,before,after,output,ingredients,8,c))
        for change in({'world_session':'other'},{'task_session':'other'},{'revision_after':8},
                      {'before_time':3},{'before':{**w['before'],'minecraft:sand':6}},
                      {'after':{**w['after'],'minecraft:sand':2}},
                      {'before':{**w['before'],output:1}}):
            bad=copy.deepcopy(result);bad['craft_site_observation'].update(change)
            self.assertFalse(_craft_site_balanced(bad,before,after,output,ingredients,8,c),change)
        bad=copy.deepcopy(result);bad['complete']=False
        self.assertFalse(_craft_site_balanced(bad,before,after,output,ingredients,8,c))
        depleted=Counter(after);depleted['minecraft:sand']=0
        self.assertFalse(_craft_site_balanced(result,before,depleted,output,ingredients,8,c))

    def test_pre_entry_hatch_refusal_fetches_one_known_input_on_the_same_controller(self):
        c=Client({'minecraft:black_concrete_powder':4})
        class HatchBackend(Backend):
            def harden(self,item,target):
                if not self.client.stock['minecraft:cobblestone']:
                    self.calls.append(('hatch_refused',item,target))
                    return {'phase':'waiting','code':'WAIT_WORKSPACE_INPUT','safe_to_leave':True,
                            'hardening_started':False,'requirements':{'minecraft:cobblestone':1}}
                return super().harden(item,target)
            def fetch(self,targets):
                if targets=={'minecraft:cobblestone':1}:
                    self.calls.append(('fetch',dict(targets)));self.client.stock['minecraft:cobblestone']=1
                    return {'phase':'done'}
                return super().fetch(targets)
        b=HatchBackend(c,self.jar);result=self.execute(c,'minecraft:black_concrete',4)
        self.assertEqual('done',result['phase']);self.assertEqual(4,c.stock['minecraft:black_concrete'])
        self.assertEqual(1,b.calls.count(('fetch',{'minecraft:cobblestone':1})))
        self.assertEqual(1,b.calls.count(('harden','minecraft:black_concrete',4)))
        book=json.loads((self.root/'job/colored-pipeline.json').read_text());self.assertIsNone(book['inflight'])
    def test_unknown_hardening_wait_cannot_become_a_workspace_fetch_or_replay(self):
        c=Client({'minecraft:black_concrete_powder':4});b=Backend(c,self.jar)
        def unknown(item,target):
            b.calls.append(('unknown_harden',item,target))
            return {'phase':'waiting','code':'WAIT_RECONCILE','safe_to_leave':True,
                    'hardening_started':False,'requirements':{'minecraft:cobblestone':1}}
        b.harden=unknown;first=self.execute(c,'minecraft:black_concrete',4)
        second=self.execute(c,'minecraft:black_concrete',4)
        self.assertEqual('WAIT_RECONCILE',first['code']);self.assertEqual('WAIT_RECONCILE',second['code'])
        self.assertEqual(1,b.calls.count(('unknown_harden','minecraft:black_concrete',4)))
        self.assertNotIn(('fetch',{'minecraft:cobblestone':1}),b.calls)
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); self.jar=self.root/"recipes.jar"; fixture(self.jar)
        self.profile={"recipe_jar":str(self.jar),"furnace_positions":[[0,64,0]]}
    def execute(self,c,item,target,dirname="job",**kw):
        return run(c,self.profile,item,target,self.root/dirname,lambda:None,**kw)
    def test_32_actual_output_recipe_coverage(self):
        table=coverage(self.jar)
        self.assertEqual(32,len(table)); self.assertTrue(all(r["pipeline_implemented"] for r in table))
    def test_all32_outputs_complete_using_existing_backend_without_new_controller(self):
        for color in COLORS:
            for suffix in ("_concrete","_terracotta"):
                with self.subTest(color=color,suffix=suffix):
                    c=Client({"minecraft:"+color+"_dye":1,"minecraft:sand":4,
                              "minecraft:gravel":4,"minecraft:terracotta":8})
                    backend=Backend(c,self.jar)
                    result=self.execute(c,"minecraft:"+color+suffix,3,color+suffix)
                    self.assertEqual("done",result["phase"])
                    self.assertIs(backend.client,c)
                    self.assertEqual(3 if suffix=="_concrete" else 8,c.stock["minecraft:"+color+suffix])
    def test_terracotta_clay_ball_craft_smelt_color_net_delta(self):
        c=Client({"minecraft:clay_ball":32,"minecraft:coal":1,"minecraft:red_dye":1})
        b=Backend(c,self.jar); result=self.execute(c,"minecraft:red_terracotta",7)
        self.assertEqual(("done",8),(result["phase"],result["after"]))
        self.assertEqual(0,c.stock["minecraft:clay_ball"])
        self.assertEqual(1,len([r for r in b.calls if r[0]=="smelt"]))
    def test_concrete_preserves_powder_surplus_and_counts_absolute_target(self):
        c=Client({"minecraft:red_concrete":2,"minecraft:red_dye":1,"minecraft:sand":4,"minecraft:gravel":4})
        b=Backend(c,self.jar); result=self.execute(c,"minecraft:red_concrete",7)
        self.assertEqual((7,5,3),(result["after"],result["gained"],c.stock["minecraft:red_concrete_powder"]))
        self.assertEqual(7,[r for r in b.calls if r[0]=="harden"][0][2])
    def test_actual_partial_poppy_stock_preferred_to_absent_rose(self):
        cat=ProcessingCatalog(self.jar)
        self.assertEqual("red_dye_from_poppy",choose_recipe(cat,"minecraft:red_dye",28,{"minecraft:poppy":8}).id)
    def test_lapis_green_cyan_route_preferred_to_missing_pitcher(self):
        cat=ProcessingCatalog(self.jar)
        self.assertEqual("cyan_dye",choose_recipe(cat,"minecraft:cyan_dye",34,{"minecraft:lapis_lazuli":24}).id)
    def test_pink_route_uses_existing_red_and_white_without_peony(self):
        cat=ProcessingCatalog(self.jar)
        self.assertEqual("pink_dye_from_red_white_dye",choose_recipe(cat,"minecraft:pink_dye",9,{"minecraft:red_dye":5,"minecraft:white_dye":5}).id)
    def test_missing_source_does_not_claim_done_or_send_processing(self):
        c=Client({}); b=Backend(c,self.jar)
        result=self.execute(c,"minecraft:red_terracotta",8)
        self.assertEqual("WAIT_SOURCE",result["code"])
        self.assertFalse(any(r[0] in ("craft","smelt","harden") for r in b.calls))
    def test_unknown_harden_receipt_never_replayed(self):
        c=Client({"minecraft:red_concrete_powder":8}); b=Backend(c,self.jar)
        with patch.object(b,"harden",return_value={"phase":"waiting","detail":"unknown"}) as harden:
            first=self.execute(c,"minecraft:red_concrete",7)
            second=self.execute(c,"minecraft:red_concrete",7)
        self.assertEqual("WAIT_RECONCILE",first["code"]); self.assertEqual("WAIT_RECONCILE",second["code"])
        harden.assert_called_once()
    def test_native_done_without_gain_retains_inflight_and_blocks_replay(self):
        c=Client({"minecraft:red_concrete_powder":8}); b=Backend(c,self.jar)
        with patch.object(b,"harden",return_value={"phase":"done"}) as harden:
            self.assertEqual("WAIT_RECONCILE",self.execute(c,"minecraft:red_concrete",7)["code"])
            self.assertEqual("WAIT_RECONCILE",self.execute(c,"minecraft:red_concrete",7)["code"])
        harden.assert_called_once()
    def test_craft_conservation_failure_not_completed(self):
        c=Client({"minecraft:red_dye":1,"minecraft:sand":4,"minecraft:gravel":4}); b=Backend(c,self.jar)
        def bad(targets):
            c.stock["minecraft:red_concrete_powder"]+=8; return {"phase":"done"}
        with patch.object(b,"craft",side_effect=bad):
            result=self.execute(c,"minecraft:red_concrete",7)
        self.assertEqual("WAIT_RECONCILE",result["code"])
        self.assertEqual(0,c.stock["minecraft:red_concrete"])
    def test_completed_moved_output_never_produced_again(self):
        c=Client({"minecraft:red_concrete":7}); Backend(c,self.jar)
        self.assertEqual("done",self.execute(c,"minecraft:red_concrete",7)["phase"])
        c.stock["minecraft:red_concrete"]=0
        self.assertEqual("blocked",self.execute(c,"minecraft:red_concrete",7)["phase"])
    def test_craft_catalog_restored_on_failure(self):
        c=Client({"minecraft:red_dye":1,"minecraft:sand":4,"minecraft:gravel":4}); b=Backend(c,self.jar)
        original=b.crafting_catalog
        with patch.object(b,"craft",side_effect=JobPaused("handoff")):
            with self.assertRaises(JobPaused):self.execute(c,"minecraft:red_concrete",7)
        self.assertIs(original,b.crafting_catalog)
    def test_changed_world_journal_stops_before_actions(self):
        c=Client({"minecraft:red_concrete":7}); b=Backend(c,self.jar)
        self.execute(c,"minecraft:red_concrete",7); c.world="new"
        with self.assertRaises(JobPaused):self.execute(c,"minecraft:red_concrete",7)
        self.assertEqual([],b.calls)
    def test_unowned_backend_rejected(self):
        c=Client({}); b=Backend(c,self.jar); b.client=Client({})
        with self.assertRaises(JobBlocked):self.execute(c,"minecraft:red_concrete",7)
    def test_large_order_uses128_intermediate_batches_not5280_ball_target(self):
        c=Client({"minecraft:clay_ball":1024,"minecraft:coal":32,"minecraft:red_dye":32})
        b=Backend(c,self.jar)
        result=self.execute(c,"minecraft:red_terracotta",256)
        self.assertEqual("done",result["phase"])
        smelts=[r for r in b.calls if r[0]=="smelt"]
        self.assertEqual([128,128],[r[2] for r in smelts])


if __name__ == "__main__":unittest.main()
