import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.colored_sources import acquire, _candidate
from material_jobs.protocol import JobPaused


def block(pos,name,fluid=False,solid=True):
    return {"pos":pos,"state":"Block{minecraft:"+name+"}","fluid":fluid,
            "solid":solid,"block_entity":False}


class Client:
    world="world"
    def __init__(self):
        self.actions=[]; self.rows=[block([100,64,100],"poppy",solid=False),block([100,63,100],"dirt")]
        self.count=0; self.uncertain=False
    def status(self):
        return {"world_session":self.world,"connected":True,"health":20,"food":20,
                "manual_movement":False,"guard_armed":True,"guard_pve_only":True,
                "guard_busy":False,"under_water":False,"pos":[100,66,100],"entities":[],
                "inventory":[{"slot":0,"item":"minecraft:poppy","count":self.count,"max_stack":64}]
                +[{"slot":i,"item":"minecraft:air","count":0,"max_stack":64} for i in range(1,36)]}
    def request(self,op,**params):
        self.actions.append((op,params))
        if op=="scan":
            rows=[copy.deepcopy(r) for r in self.rows if all(params["min"][i]<=r["pos"][i]<=params["max"][i] for i in range(3))]
            if not params.get("details"):
                rows=[{k:v for k,v in r.items() if k in ("pos","state")} for r in rows]
            return {"world_session":self.world,"phase":"done","blocks":rows}
        if op=="mine_block":
            if self.uncertain:return {"phase":"waiting"}
            self.rows=[r for r in self.rows if r["pos"]!=params["pos"]]; self.count+=1
            return {"phase":"done"}
        raise AssertionError(op)
    def checked(self,op,**params):
        self.actions.append((op,params)); return {"phase":"done"}


class ColoredSourcesTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name); self.c=Client()
        self.profile={"protected_regions":[{"min":[0,50,0],"max":[10,90,10]}],
                      "colored_source_regions":[{"item":"minecraft:poppy","authorized":True,
                                                 "min":[99,62,99],"max":[101,66,101]}]}
    def go(self):
        with patch("work_access.approach_faces",return_value="up"):
            return acquire(self.c,"minecraft:poppy",1,self.profile,self.out,lambda:None)
    def test_authorized_fresh_flower_mine_net_delta(self):
        self.assertEqual("done",self.go()["phase"])
        self.assertEqual(1,self.c.count)
        self.assertEqual(1,sum(op=="mine_block" for op,_ in self.c.actions))
        self.assertTrue(all(p.get("details") is True for op,p in self.c.actions if op=="scan"))
    def test_absent_authorized_source_waits_without_game_actions(self):
        self.profile["colored_source_regions"]=[]
        self.assertEqual("WAIT_SOURCE",self.go()["code"]); self.assertEqual([],self.c.actions)
    def test_legacy_cache_region_is_not_authorized_source(self):
        self.profile["colored_source_regions"][0].pop("authorized")
        self.assertEqual("WAIT_SOURCE",self.go()["code"]); self.assertEqual([],self.c.actions)
    def test_protected_region_skips_mining(self):
        self.profile["protected_regions"]=[{"min":[90,50,90],"max":[110,90,110]}]
        self.assertEqual("WAIT_SOURCE",self.go()["code"])
        self.assertFalse(any(op=="mine_block" for op,_ in self.c.actions))
    def test_nearby_water_prevents_plain_mining(self):
        self.c.rows.append(block([101,64,100],"water",True,False))
        self.assertEqual("WAIT_SOURCE",self.go()["code"])
        self.assertFalse(any(op=="mine_block" for op,_ in self.c.actions))
    def test_unknown_receipt_durable_no_replay(self):
        self.c.uncertain=True
        self.assertEqual("WAIT_RECONCILE",self.go()["code"])
        self.assertEqual("WAIT_RECONCILE",self.go()["code"])
        self.assertEqual(1,sum(op=="mine_block" for op,_ in self.c.actions))
    def test_world_transition_before_action_raises(self):
        self.go(); self.c.world="new"
        with self.assertRaises(JobPaused):self.go()
    def test_cactus_base_preserved_and_top_eligible(self):
        rows=[block([100,64,100],"cactus"),block([100,63,100],"sand")]
        self.assertFalse(_candidate(rows,[100,64,100],"minecraft:cactus"))
        rows=[block([100,65,100],"cactus"),block([100,64,100],"cactus")]
        self.assertTrue(_candidate(rows,[100,65,100],"minecraft:cactus"))
    def test_ink_absent_drop_waits_not_fake_squid_attack(self):
        self.profile["colored_source_regions"][0]["item"]="minecraft:ink_sac"
        result=acquire(self.c,"minecraft:ink_sac",1,self.profile,self.out,lambda:None)
        self.assertEqual("WAIT_SOURCE",result["code"]); self.assertEqual([],self.c.actions)
    def test_claimed_complete_inventory_requires_safety_and_world(self):
        self.c.count=1
        self.assertEqual("done",self.go()["phase"])
        self.assertEqual([],self.c.actions)
    def test_cocoa_requires_mature_attached_natural_jungle_log(self):
        rows=[block([100,64,100],"cocoa",solid=False),block([101,64,100],"jungle_log")]
        rows[0]["state"]="Block{minecraft:cocoa}[age=2,facing=east]"
        self.assertTrue(_candidate(rows,[100,64,100],"minecraft:cocoa_beans"))
        rows[0]["state"]="Block{minecraft:cocoa}[age=1,facing=east]"
        self.assertFalse(_candidate(rows,[100,64,100],"minecraft:cocoa_beans"))


if __name__ == "__main__":unittest.main()
