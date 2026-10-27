import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.colored_sources import acquire, _candidate, _ordered_rows, _stage_source
from material_jobs.protocol import JobPaused


def block(pos,name,fluid=False,solid=True):
    return {"pos":pos,"state":"Block{minecraft:"+name+"}","fluid":fluid,
            "solid":solid,"block_entity":False}


class Client:
    world="world"
    def __init__(self):
        self.actions=[]; self.rows=[block([100,64,100],"poppy",solid=False),block([100,63,100],"dirt")]
        self.count=0; self.uncertain=False;self.sword="minecraft:netherite_sword";self.hand="minecraft:air"
    def status(self):
        return {"world_session":self.world,"connected":True,"health":20,"food":20,
                "manual_movement":False,"guard_armed":True,"guard_pve_only":True,
                "guard_busy":False,"under_water":False,"pos":[100,66,100],"entities":[],
                "hand":{"item":self.hand,"count":1},
                "inventory":[{"slot":0,"item":"minecraft:poppy","count":self.count,"max_stack":64},
                    {"slot":1,"item":self.sword,"count":0 if self.sword=="minecraft:air" else 1,"max_stack":1}]
                +[{"slot":i,"item":"minecraft:air","count":0,"max_stack":64} for i in range(2,36)]}
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
        self.actions.append((op,params))
        if op=='select_item':self.hand=params['item']
        return {"phase":"done"}


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
        self.assertIn(('select_item',{'item':'minecraft:netherite_sword'}),self.c.actions)
    def test_no_carried_sword_never_guesses_a_diamond_sword_or_starts_mining(self):
        self.c.sword='minecraft:air'
        self.assertEqual('WAIT_TOOL',self.go()['code'])
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.actions))
    def test_absent_authorized_source_waits_without_game_actions(self):
        self.profile["colored_source_regions"]=[]
        self.assertEqual("WAIT_SOURCE",self.go()["code"]); self.assertEqual([],self.c.actions)
    def cactus_setup(self):
        self.c.rows=[block([100,63,100],'sand'),block([100,64,100],'cactus'),
                     block([100,65,100],'cactus'),block([100,66,100],'cactus')]
        original=self.c.status
        def status():
            s=original();s['inventory'][0]['item']='minecraft:cactus';return s
        self.c.status=status
        self.profile['colored_source_regions']=[{'item':'minecraft:cactus','authorized':True,
            'min':[100,63,100],'max':[100,66,100]}]
    def test_cactus_uses_side_kernel_and_highest_segment(self):
        self.cactus_setup()
        def side(c,pos,profile,out,checkpoint):
            self.assertEqual([100,66,100],pos)
            c.rows=[r for r in c.rows if r['pos']!=pos];c.count+=1
            return {'complete':True,'base_retained':True,'after':c.count}
        with patch('material_jobs.renewable_cactus.harvest_top',side), \
             patch('material_jobs.colored_sources._stage_source',side_effect=AssertionError('generic staging forbidden')), \
             patch('work_access.approach_faces',side_effect=AssertionError('generic cactus-top approach forbidden')):
            result=acquire(self.c,'minecraft:cactus',1,self.profile,self.out,lambda:None)
        self.assertEqual('done',result['phase'])
        self.assertTrue(any(r['pos']==[100,64,100]for r in self.c.rows))
    def test_deferred_cactus_source_never_scans_moves_or_harvests(self):
        self.cactus_setup();self.profile['cactus_harvest_paused']=True
        with patch('material_jobs.renewable_cactus.harvest_top')as harvest:
            result=acquire(self.c,'minecraft:cactus',1,self.profile,self.out,lambda:None)
        self.assertEqual('WAIT_CACTUS_DEFERRED',result['code'])
        self.assertEqual([],self.c.actions);harvest.assert_not_called()
    def test_unknown_cactus_side_receipt_never_replays_the_harvest(self):
        self.cactus_setup()
        with patch('material_jobs.renewable_cactus.harvest_top',side_effect=RuntimeError('unknown'))as kernel:
            with self.assertRaises(RuntimeError):
                acquire(self.c,'minecraft:cactus',1,self.profile,self.out,lambda:None)
            result=acquire(self.c,'minecraft:cactus',1,self.profile,self.out,lambda:None)
            self.assertEqual('WAIT_RECONCILE',result['code']);self.assertEqual(1,kernel.call_count)
    def test_known_removed_unreceived_top_allows_distinct_top_without_credit_or_replay(self):
        self.cactus_setup();seen=[]
        def side(c,pos,profile,out,checkpoint):
            seen.append(list(pos));c.rows=[r for r in c.rows if r['pos']!=pos]
            if len(seen)==1:
                return {'complete':False,'unreceived':True,'mining_confirmed':True,
                        'base_retained':True,'actual_gain':0,'pickup_confirmed':False,'drop_uuid':'missing'}
            c.count+=1;return {'complete':True,'base_retained':True}
        with patch('material_jobs.renewable_cactus.harvest_top',side):
            result=acquire(self.c,'minecraft:cactus',1,self.profile,self.out,lambda:None)
        self.assertEqual('done',result['phase']);self.assertEqual(1,self.c.count)
        self.assertEqual([[100,66,100],[100,65,100]],seen)
        book=json.loads((self.out/'colored-source-cactus.json').read_text())
        self.assertEqual(['unreceived','done'],[r['state']for r in book['receipts']])
        self.assertEqual(0,book['receipts'][0]['gained'])
        self.c.rows.append(block([100,66,100],'cactus'))
        with patch('material_jobs.renewable_cactus.harvest_top',side):
            acquire(self.c,'minecraft:cactus',2,self.profile,self.out,lambda:None)
        self.assertEqual(2,len(seen))
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

    def test_dry_clay_accepts_natural_rock_and_retained_gravel_support(self):
        rows=[block([100,64,100],'clay'),block([100,63,100],'andesite'),
              block([99,64,100],'granite'),block([101,65,100],'stone'),
              block([101,66,100],'gravel')]
        self.assertTrue(_candidate(rows,[100,64,100],'minecraft:clay_ball'))
        self.assertFalse(_candidate(rows,[100,64,100],'minecraft:poppy'))
        rows[-2]=block([101,65,100],'air',solid=False)
        self.assertFalse(_candidate(rows,[100,64,100],'minecraft:clay_ball'))

    def test_clay_never_removes_gravel_support_or_opens_liquid(self):
        rows=[block([100,64,100],'clay'),block([100,63,100],'stone'),
              block([100,65,100],'gravel')]
        self.assertFalse(_candidate(rows,[100,64,100],'minecraft:clay_ball'))
        rows[-1]=block([101,64,100],'water',fluid=True,solid=False)
        self.assertFalse(_candidate(rows,[100,64,100],'minecraft:clay_ball'))
        rows[-1]=block([101,64,100],'chest');rows[-1]['block_entity']=True
        self.assertFalse(_candidate(rows,[100,64,100],'minecraft:clay_ball'))

    def test_clay_tries_upper_nearer_faces_before_buried_lower_blocks(self):
        rows=[block([100,63,100],'clay'),block([103,64,100],'clay'),block([100,64,100],'clay')]
        ordered=_ordered_rows(rows,'minecraft:clay_ball',[100,66,100])
        self.assertEqual([[100,64,100],[103,64,100],[100,63,100]],[r['pos']for r in ordered])
        self.assertIs(rows,_ordered_rows(rows,'minecraft:poppy',[100,66,100]))

    def test_high_park_stages_through_checked_route_before_native_work_reach(self):
        state=self.c.status();state['pos']=[100.5,222,100.5];self.c.out=self.out
        self.c.status=lambda:copy.deepcopy(state)
        def move(c,target,checkpoint,trace):
            self.assertEqual([100.5,128,100.5],target)
            self.assertGreater(target[1],64+1.8)
            state['pos']=target;trace.append({'actual_reached':target})
        with patch('material_jobs.acquisition._travel',side_effect=move) as travel:
            _stage_source(self.c,[100,64,100],lambda:None)
        travel.assert_called_once();self.assertEqual(state['pos'],self.c.anchor)
        self.assertTrue(list(self.out.glob('source-stage-*.json')))

    def test_unknown_staging_or_manual_takeover_never_reaches_mining(self):
        state=self.c.status();state['pos']=[100.5,222,100.5];self.c.out=self.out
        self.c.status=lambda:copy.deepcopy(state)
        with patch('material_jobs.acquisition._travel',side_effect=RuntimeError('unconfirmed')):
            with self.assertRaisesRegex(RuntimeError,'unconfirmed'):self.go()
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.actions))
        state['manual_movement']=True
        with patch('material_jobs.acquisition._travel') as travel:
            with self.assertRaises(JobPaused):_stage_source(self.c,[100,64,100],lambda:None)
        travel.assert_not_called()


    def test_unloaded_owned_cactus_farm_is_visited_then_read_without_resource_credit(self):
        self.cactus_setup();region=self.profile['colored_source_regions'][0]
        region.update(source='owned_cactus_farm',min=[100,65,100])
        with (patch('material_jobs.colored_sources._fresh_scan',side_effect=[None,[]])as scan,
              patch('material_jobs.renewable_cactus.owned_farm_top',return_value=True),
              patch('material_jobs.colored_sources._stage_source')as stage):
            result=acquire(self.c,'minecraft:cactus',1,self.profile,self.out,lambda:None)
        self.assertEqual('WAIT_SOURCE',result['code']);self.assertEqual(2,scan.call_count)
        stage.assert_called_once();self.assertEqual(region['min'],stage.call_args.args[1])
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.actions))

    def test_unproved_cactus_farm_does_not_authorize_unloaded_source_travel(self):
        self.cactus_setup();self.profile['colored_source_regions'][0]['source']='owned_cactus_farm'
        with (patch('material_jobs.colored_sources._fresh_scan',return_value=None)as scan,
              patch('material_jobs.renewable_cactus.owned_farm_top',return_value=False),
              patch('material_jobs.colored_sources._stage_source')as stage):
            acquire(self.c,'minecraft:cactus',1,self.profile,self.out,lambda:None)
        stage.assert_not_called();self.assertEqual(1,scan.call_count)

    def test_loaded_but_empty_farm_does_not_repeat_a_travel(self):
        self.cactus_setup();self.profile['colored_source_regions'][0]['source']='owned_cactus_farm'
        with (patch('material_jobs.colored_sources._fresh_scan',return_value=[]),
              patch('material_jobs.colored_sources._stage_source')as stage):
            acquire(self.c,'minecraft:cactus',1,self.profile,self.out,lambda:None)
        stage.assert_not_called()


if __name__ == "__main__":unittest.main()
