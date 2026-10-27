import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import goal_workflow
from goal_workflow import open_workbench,subset_matches,build_phase,station_target,protected_background,verified_build_navigation,available_build_material,prepare_build_material


class Client:
    def __init__(self, approach_fails=False):
        self.calls=[];self.opened=False;self.approach_fails=approach_fails;self.hand='minecraft:bow'
        self.directory=tempfile.TemporaryDirectory();self.out=Path(self.directory.name)
    def status(self):
        return {'hand':{'item':self.hand},'inventory':[{'slot':0,'item':'minecraft:diamond_sword','count':1}],
                'menu':{'type':'CraftingMenu' if self.opened else 'InventoryMenu'}}
    def fetch(self,*args):self.calls.append('near_depot');return {'phase':'done'}
    def request(self,op,**args):
        self.calls.append(op)
        if op=='approach_block':
            if self.approach_fails:raise RuntimeError('No clear path')
            return {'phase':'done'}
        return {'blocks':[{'state':'Block{minecraft:crafting_table}'}]}
    def checked(self,op,**args):
        self.calls.append(op)
        if op=='select_item':self.hand=args['item']
        if op=='approach_block' and self.approach_fails:raise RuntimeError('No clear path')
        if op=='interact':self.opened=True


class WorkbenchTests(unittest.TestCase):
    def test_background_requires_current_native_guard_lease_and_live_heartbeat(self):
        from types import SimpleNamespace
        c=SimpleNamespace(task='task',heartbeat=SimpleNamespace(attached=True,id='lease'))
        s={'material_protocol':2,'guard_armed':True,'world_session':'world',
           'supervision_lease':{'kind':'materials','job_session':'task','id':'lease','world_session':'world'}}
        self.assertTrue(protected_background(c,s))
        for delta in ({'guard_armed':False},{'manual_movement':True},{'world_session':'other'},{'material_protocol':1},{'supervision_lease':None}):
            self.assertFalse(protected_background(c,{**s,**delta}))
        c.heartbeat.attached=False;self.assertFalse(protected_background(c,s))
    def test_station_reposition_uses_only_three_verified_integer_coordinates(self):
        self.assertEqual([760816.5,87.02,797764.5],station_target('760816, 87, 797764'))
        self.assertIsNone(station_target('760816, 87'))
        self.assertIsNone(station_target('untrusted station'))
    def test_background_construction_refuses_to_wait_on_ignored_movement_keys(self):
        class Background:
            def status(self):return {'projection_selection':{'key':'selected'},'window_active':False}
        with self.assertRaisesRegex(RuntimeError,'foreground'):
            build_phase(Background(),'selected')
    def test_subset_needs_every_exact_block_state_and_is_not_whole_goal_success(self):
        targets=[{'pos':[1,2,3],'expected':'Block{minecraft:stone_bricks}'},
                 {'pos':[2,2,3],'expected':'Block{minecraft:ladder}[facing=east]'}]
        self.assertFalse(subset_matches([{'pos':[1,2,3],'state':'Block{minecraft:stone_bricks}'}],targets))
        observed=[{'pos':r['pos'],'state':r['expected']} for r in targets]
        self.assertTrue(subset_matches(observed,targets))
        observed[-1]['state']='Block{minecraft:ladder}[facing=west]'
        self.assertFalse(subset_matches(observed,targets));self.assertFalse(subset_matches([],[]))
    def test_nearby_depot_does_not_substitute_for_actual_workbench_reach(self):
        c=Client();open_workbench(c,[10,65,20],[7,65,17])
        self.assertEqual(c.calls,['near_depot','scan','scan','approach_block','select_item','interact'])
        self.assertTrue(c.opened)
    def test_failed_approach_never_attempts_interaction(self):
        c=Client(approach_fails=True)
        with self.assertRaises(RuntimeError):open_workbench(c,[10,65,20])
        self.assertNotIn('interact',c.calls)
        self.assertFalse(c.opened)
    def test_workbench_opens_with_the_carried_netherite_sword(self):
        class Netherite(Client):
            def status(self):
                state=super().status();state['inventory'][0]['item']='minecraft:netherite_sword';return state
        c=Netherite();open_workbench(c,[10,65,20]);self.assertTrue(c.opened)
        self.assertEqual('minecraft:netherite_sword',c.hand)


class BuildProgressTests(unittest.TestCase):
    def test_only_current_needed_material_is_prepared_and_real_hand_is_checked(self):
        class Supply(Client):
            def status(self):
                s=super().status();s['inventory']+=[{'slot':12,'item':'minecraft:dripstone_block','count':64},
                    {'slot':13,'item':'minecraft:black_terracotta','count':4}]
                s['hand']['count']=64 if self.hand=='minecraft:dripstone_block'else 1
                s['build_job']={'material_needs':{'minecraft:dripstone_block':769,'minecraft:green_terracotta':182}}
                return s
        c=Supply();self.assertEqual('minecraft:dripstone_block',available_build_material(c.status()))
        self.assertEqual('minecraft:dripstone_block',prepare_build_material(c,c.status()))
        self.assertEqual(['select_item'],c.calls);self.assertIsNone(prepare_build_material(c,c.status()))
        c.hand='minecraft:diamond_pickaxe';c.checked=lambda *a,**k:None
        with self.assertRaisesRegex(RuntimeError,'held hand'):prepare_build_material(c,c.status())

    def test_empty_printer_hand_pauses_before_refill_and_restarts_original_projection(self):
        class Supply:
            def __init__(self,out):self.out=out;self.calls=[];self.hand='minecraft:dripstone_block';self.count=64;self.starts=0
            def status(self):
                return {'time':1,'world_session':'w','pos':[.5,65,.5],'health':20,'guard_busy':False,'screen':'','window_active':True,
                    'projection_selection':{'key':'selected'},'hand':{'item':self.hand,'count':self.count},
                    'inventory':[{'slot':12,'item':'minecraft:dripstone_block','count':128}],
                    'professional_printer':{'waiting_for_server':False,'last_hand_mismatch':'expected=minecraft:dripstone_block actual=minecraft:air'},
                    'build_job':{'active':self.starts==1,'session':'job','placement_key':'selected','matched':64 if self.starts>1 else 0,
                        'total':64,'phase':'打印中','material_needs':{'minecraft:dripstone_block':64}}}
            def checked(self,op,**kw):
                self.calls.append((op,kw))
                if op=='projection_start':self.starts+=1;self.hand='minecraft:air'if self.starts==1 else'minecraft:dripstone_block';self.count=0 if self.starts==1 else 64
                if op=='select_item':self.hand=kw['item'];self.count=64
            def request(self,*a,**k):return {'projection_audit':{'matched':64,'total':64,'kinds':{}}}
        with tempfile.TemporaryDirectory()as d:
            c=Supply(Path(d));result=build_phase(c,'selected',seconds=5)
            self.assertEqual(['projection_start','build_control','select_item','projection_start'],[op for op,kw in c.calls])
            self.assertEqual('pause_and_report',c.calls[1][1]['action']);self.assertEqual('selected',c.calls[-1][1]['placement_key'])
            self.assertEqual(64,result['matched'])
    def test_native_station_progress_requires_real_movement(self):
        old={'pos':[0,64,0],'build_job':{'path_step':1,'navigation':{'start':'0,64,0','path_length':10}}}
        moving={'pos':[1,64,0],'build_job':{'active':True,'auto_move':True,'phase':'自动走位',
                'station':'10, 64, 0','path_step':2,'navigation':{'start':'0,64,0','path_length':10}}}
        self.assertTrue(verified_build_navigation(old,moving))
        self.assertFalse(verified_build_navigation(old,{**moving,'pos':[0,64,0]}))
        self.assertFalse(verified_build_navigation(old,{**moving,'build_job':{**moving['build_job'],'auto_move':False}}))
        self.assertFalse(verified_build_navigation(old,{**moving,'pos':[-1,64,0],
            'build_job':{**moving['build_job'],'path_step':1}}))
        # A real path step may briefly detour away from the destination.
        self.assertTrue(verified_build_navigation(old,{**moving,'pos':[-1,64,0]}))

    def test_unproductive_navigation_has_only_bounded_stall_grace(self):
        class Clock:
            value=0.0
            def monotonic(self):return self.value
            def sleep(self,seconds):self.value+=seconds
        class BuildClient:
            def __init__(self,out,clock,moving):
                self.out=out;self.clock=clock;self.moving=moving;self.active=False;self.paused_at=None
            def status(self):
                x=min(self.clock.value,10) if self.moving else 0
                return {'time':int(self.clock.value*1000),'pos':[x,64,0],
                        'velocity':[0,0,0],'movement_keys':{},'flight':False,'health':20,
                        'window_active':True,'screen':None,'guard_busy':False,
                        'projection_selection':{'key':'selected'},
                        'professional_printer':{'waiting_for_server':False},
                        'build_job':{'active':self.active,'placement_key':'selected','session':'job',
                            'matched':0,'total':10,'phase':'自动走位' if self.moving else '打印中',
                            'auto_move':True,'station':'10, 64, 0','path_step':int(x),
                            'navigation':{'start':'0,64,0','path_length':10},'queue_settled':False}}
            def checked(self,op,**kwargs):
                if op=='projection_start':self.active=True
                if op=='build_control':self.active=False;self.paused_at=self.clock.value
                return {'phase':'done'}
            def request(self,op,**kwargs):
                self.assertion=op
                if op=='build_control':return self.checked(op,**kwargs)
                return {'projection_audit':{'matched':0,'total':10,'kinds':{}}}
        with tempfile.TemporaryDirectory() as directory:
            for moving in (False,True):
                clock=Clock();client=BuildClient(Path(directory),clock,moving)
                with patch.object(goal_workflow.time,'monotonic',clock.monotonic),\
                     patch.object(goal_workflow.time,'sleep',clock.sleep):
                    build_phase(client,'selected',seconds=8,stall_seconds=3,
                                navigation_grace_seconds=1)
                self.assertIsNotNone(client.paused_at)
                if moving:self.assertGreater(client.paused_at,3.0)
                else:self.assertLess(client.paused_at,3.5)
                self.assertLess(client.paused_at,4.5)
            # Even continuous verified travel cannot bypass the overall build budget.
            clock=Clock();client=BuildClient(Path(directory),clock,True)
            with patch.object(goal_workflow.time,'monotonic',clock.monotonic),\
                 patch.object(goal_workflow.time,'sleep',clock.sleep):
                build_phase(client,'selected',seconds=3.5,stall_seconds=2,
                            navigation_grace_seconds=100)
            self.assertGreaterEqual(client.paused_at,3.5)
            self.assertLess(client.paused_at,3.9)

if __name__=='__main__':unittest.main()
