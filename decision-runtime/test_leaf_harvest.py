import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from material_jobs.leaf_harvest import LeafHarvester,LeafStopped,validate,natural_leaf,shears,capacity,release_or_observe

ITEM='minecraft:oak_leaves'
ROW={'pos':[0,1,0],'state':'Block{minecraft:oak_leaves}[distance=2,persistent=false,waterlogged=false]',
     'fluid':False,'block_entity':False,'solid':True,'passable':False}
CFG={'schema':1,'server':'example.org','dimension':'minecraft:overworld','target':1,'target_scope':'new_collected',
     'park_target':[0,100,0],'regions':[{'min':[-2,0,-2],'max':[2,3,2],'authorized':True}],'depots':[[4,0,0]]}

class Clock:
    def __init__(self):self.now=0;self.slept=0
    def __call__(self):return self.now
    def sleep(self,n):self.now+=n;self.slept+=n

class Fake:
    world='world';task='task';native_inflight=None;unconfirmed_native_request=None
    def __init__(self):
        self.qty=5;self.rows={tuple(ROW['pos']):copy.deepcopy(ROW)};self.actions=[];self.out=Path('.')
        self.mode='done';self.credit=True;self.drop=False;self.entities=[];self.partial=False;self.manual=False;self.approach_result=None
        self.hand_item='minecraft:netherite_sword';self.durability=100;self.last='';self.seq=0;self.corrupt=False;self.pos=[.5,2,.5]
    def status(self):
        return {'time':self.seq,'control_revision':self.seq,'world_session':self.world,'manual_movement':self.manual,'screen':'','health':20,'food':20,
                'guard_armed':True,'guard_pve_only':True,'guard_busy':False,'flight':True,'pos':self.pos[:],
                'entities':copy.deepcopy(self.entities),'hand':{'item':self.hand_item,'durability':self.durability},
                'inventory':[{'item':ITEM,'count':self.qty,'slot':0},{'item':'minecraft:shears','count':1,'slot':1,'durability':self.durability}]
                +[{'item':'minecraft:air','count':0,'slot':i}for i in range(2,36)]}
    def checked(self,op,**kw):
        self.actions.append((op,kw));self.seq+=1;self.last='r'+str(self.seq)
        if op=='select_item':self.hand_item=kw['item']
        return {'phase':'done'}
    def request(self,op,**kw):
        self.actions.append((op,kw));self.seq+=1;self.last='r'+str(self.seq)
        if op=='scan':
            n=1
            for a,b in zip(kw['min'],kw['max']):n*=b-a+1
            return {'world_session':self.world,'phase':'done','scan_cells_read':n-int(self.partial),'scan_total_cells':n,
                    'blocks':[copy.deepcopy(r)for p,r in self.rows.items()if all(a<=v<=b for a,v,b in zip(kw['min'],p,kw['max']))]}
        if op=='approach_block':
            if self.approach_result:return self.approach_result
            self.pos=[kw['pos'][0]+.5,kw['pos'][1]+1,kw['pos'][2]-.5];return {'phase':'done'}
        if op=='mine_block':
            if self.mode=='done':
                self.rows.pop(tuple(kw['pos']),None);self.durability-=1
                if self.credit:self.qty+=1
                elif self.drop:
                    if self.entities:self.entities[0]['stack']['count']+=1
                    else:self.entities=[{'type':'minecraft:item','uuid':'new-drop','pos':[0.,1.,0.],'stack':{'item':ITEM,'count':1}}]
            return {'id':self.last,'world_session':self.world,'op':'mine_block','phase':self.mode,'server_confirmed':self.mode=='done',
                    'outcome_pending':self.mode!='done','confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
                    'server_update_seen':not self.corrupt,'native_sequence':self.seq,'server_ack_sequence':self.seq,
                    'mining_target':kw['pos'],'server_observed_state':'Block{minecraft:air}'}
        raise AssertionError(op)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        self.c=Fake();self.cfg=copy.deepcopy(CFG);self.clock=Clock();self.pickups=0
    def pickup(self,c,d,s):self.pickups+=1;c.qty+=d['stack']['count'];c.entities=[];return True
    def job(self,**kw):
        return LeafHarvester(self.c,self.cfg,self.path,pickup=kw.get('pickup',self.pickup),deposit=kw.get('deposit',lambda *a:{'complete':True}),clock=self.clock,sleep=self.clock.sleep,resume_batch=kw.get('resume_batch',False))
    def many(self,n=12):
        points=[(x,1,z)for x in(-1,0,1)for z in(-1,0,1)]+[(x,2,0)for x in(-1,0,1)]
        self.c.rows={p:{**copy.deepcopy(ROW),'pos':list(p)}for p in points[:n]}
    def calls(self,op):return [kw for action,kw in self.c.actions if action==op]
    def test_continuous_batch_selects_once_and_never_sleeps_per_leaf(self):
        self.many();self.cfg['target']=12;j=self.job();r=j.run()
        self.assertEqual(r['collected'],12);self.assertEqual(self.c.qty,17);self.assertEqual(len(self.calls('select_item')),1)
        self.assertEqual(len(self.calls('mine_block')),12);self.assertEqual(len(self.calls('scan')),13)
        self.assertFalse(self.calls('approach_block'));self.assertEqual(self.clock.slept,0);self.assertEqual(r['metrics']['batches'],1)
    def test_twelve_merged_leaf_drops_use_one_pickup_and_one_short_grace(self):
        self.many();self.cfg['target']=12;self.c.credit=False;self.c.drop=True;j=self.job();j.run()
        self.assertEqual(self.pickups,1);self.assertEqual(j.book['collected'],12);self.assertLess(self.clock.slept,.6)
    def test_current_shears_are_retained(self):
        self.c.hand_item='minecraft:shears';self.c.durability=3;j=self.job();j.run();self.assertFalse(self.calls('select_item'))
    def test_exact_server_proof_required_before_next_mine(self):
        self.many(2);self.c.corrupt=True;j=self.job()
        with self.assertRaises(LeafStopped):j.harvest_batch(list(self.c.rows.values()))
        self.assertEqual(len(self.calls('mine_block')),1);self.assertEqual(j.book['collected'],0);self.assertIsNotNone(j.book['pending'])
        with self.assertRaises(LeafStopped):self.job()
    def test_unknown_mine_retains_identity_without_replay(self):
        self.c.mode='waiting';j=self.job()
        with self.assertRaises(LeafStopped):j.harvest(ROW)
        with self.assertRaises(LeafStopped):j.harvest(ROW)
        self.assertEqual(len(self.calls('mine_block')),1);self.assertEqual(j.book['pending']['kind'],'mine')
    def test_missing_drop_is_not_credited(self):
        self.c.credit=False;j=self.job();self.assertFalse(j.harvest(ROW));self.assertEqual(j.book['collected'],0)
        self.assertIsNone(j.book['pending']);self.assertIsNone(j.book['batch']);self.assertEqual(j.book['outstanding'],{ITEM:1})
    def test_late_gain_limited_to_confirmed_missing_quantity(self):
        self.c.credit=False;j=self.job();j.harvest(ROW);self.c.qty+=1;j.late_gains(self.c.status())
        self.assertEqual(j.book['collected'],1);self.assertEqual(j.book['outstanding'][ITEM],0);self.c.qty+=1
        with self.assertRaises(LeafStopped):j.late_gains(self.c.status())
    def test_old_drop_not_collected_as_new_loot(self):
        self.c.credit=False;self.c.entities=[{'type':'minecraft:item','uuid':'old','pos':[0,1,0],'stack':{'item':ITEM,'count':1}}]
        j=self.job();j.harvest(ROW);self.assertEqual(self.pickups,0);self.assertEqual(j.book['collected'],0)
    def test_pickup_failure_retains_exact_uuid(self):
        self.c.credit=False;self.c.drop=True;j=self.job(pickup=lambda *a:False)
        with self.assertRaises(LeafStopped):j.harvest(ROW)
        self.assertEqual(j.book['pending']['drop']['uuid'],'new-drop');self.assertIsNotNone(j.book['batch'])
    def test_merge_refusal_refreshes_new_uuid_without_repeating_old_pickup(self):
        self.many(2);self.cfg['target']=2;self.c.credit=False;self.c.drop=True;attempts=[]
        def pickup(c,d,s):
            attempts.append(d['uuid'])
            if len(attempts)==1:
                c.seq+=1;c.last='pickup-merge'
                c.last_terminal_evidence={'request_id':c.last,'world_session':c.world,'task_session':c.task,'revision_after':c.seq,
                    'op':'collect_item','phase':'waiting','detail':'Drop disappeared without inventory confirmation',
                    'params':{'expected_uuid':d['uuid'],'expected_item':ITEM,'expected_count':2}}
                c.entities=[{'type':'minecraft:item','uuid':'merged-replacement','pos':[0.,1.,0.],'stack':{'item':ITEM,'count':2}}];return False
            return self.pickup(c,d,s)
        j=self.job(pickup=pickup);j.harvest_batch(list(self.c.rows.values()))
        self.assertEqual(attempts,['new-drop','merged-replacement']);self.assertEqual(j.book['collected'],2)
        self.assertEqual(len(self.calls('mine_block')),2)
    def test_explicit_resume_settles_batch_without_replaying_mines(self):
        self.c.credit=False;self.c.drop=True;j=self.job(pickup=lambda *a:False)
        with self.assertRaises(LeafStopped):j.harvest(ROW)
        d=j.book['pending']['drop'];control=self.path/'control';control.mkdir()
        event={'request_id':j.book['pending']['request_id'],'world_session':self.c.world,'op':'collect_item','phase':'waiting',
               'detail':'Drop disappeared without inventory confirmation','params':{'expected_uuid':d['uuid'],'expected_item':ITEM,'expected_count':1}}
        (control/'events.jsonl').write_text(json.dumps(event)+'\n');self.c.entities[0]['uuid']='new-merged-id'
        resumed=self.job(resume_batch=True);resumed.run()
        self.assertEqual(len(self.calls('mine_block')),1);self.assertEqual(resumed.book['collected'],1)
    def test_resume_refuses_unknown_request_file(self):
        self.c.credit=False;self.c.drop=True;j=self.job(pickup=lambda *a:False)
        with self.assertRaises(LeafStopped):j.harvest(ROW)
        control=self.path/'control';control.mkdir();(control/'unconfirmed-native-request.json').write_text('{}')
        with self.assertRaises(LeafStopped):self.job(resume_batch=True)
    def test_oversized_merge_is_not_guessed(self):
        self.c.credit=False;self.c.drop=True;original=self.c.request
        def request(op,**kw):
            r=original(op,**kw)
            if op=='mine_block':self.c.entities[0]['stack']['count']=2
            return r
        self.c.request=request;j=self.job();j.harvest(ROW);self.assertEqual(self.pickups,0);self.assertEqual(j.book['collected'],0)
    def test_extra_inventory_gain_cannot_complete_goal(self):
        original=self.c.request
        def request(op,**kw):
            r=original(op,**kw)
            if op=='mine_block':self.c.qty+=1
            return r
        self.c.request=request;j=self.job()
        with self.assertRaises(LeafStopped):j.run()
        self.assertEqual(j.book['collected'],0);self.assertIsNotNone(j.book['batch'])
    def test_collecting_one_pile_can_absorb_other_confirmed_batch_piles(self):
        self.many(2);self.cfg['target']=2;self.c.credit=False;self.c.drop=True;original=self.c.request
        def request(op,**kw):
            r=original(op,**kw)
            if op=='mine_block' and len(self.c.rows)==0:
                self.c.entities=[{'type':'minecraft:item','uuid':uid,'pos':[0.,1.,0.],'stack':{'item':ITEM,'count':1}}for uid in('a','b')]
            return r
        def pickup(c,d,s):self.pickups+=1;c.qty+=2;c.entities=[];return True
        self.c.request=request;j=self.job(pickup=pickup);j.harvest_batch(list(self.c.rows.values()))
        self.assertEqual(j.book['collected'],2);self.assertEqual(self.pickups,1)
    def test_old_uncredited_leaf_can_arrive_during_next_confirmed_batch(self):
        self.c.credit=False;j=self.job();j.harvest(ROW);self.c.rows[(0,1,0)]=copy.deepcopy(ROW)
        original=self.c.request
        def request(op,**kw):
            r=original(op,**kw)
            if op=='mine_block':self.c.qty+=2
            return r
        self.c.request=request;j.harvest(ROW)
        self.assertEqual(j.book['collected'],2);self.assertEqual(j.book['outstanding'],{})
    def test_explicit_no_dispatch_refusal_is_skipped_without_retry(self):
        original=self.c.request
        def request(op,**kw):
            if op!='mine_block':return original(op,**kw)
            self.c.actions.append((op,kw));self.c.last='refused'
            return {'id':'refused','world_session':self.c.world,'op':op,'phase':'waiting','mining_target':kw['pos'],
                    'server_confirmed':False,'outcome_pending':False,'server_update_seen':False,
                    'confirmation_scope':'none','native_sequence':-1,'server_ack_sequence':-1}
        self.c.request=request;j=self.job();self.assertFalse(j.harvest(ROW))
        self.assertEqual(len(self.calls('mine_block')),1);self.assertIsNone(j.book['pending'])
    def test_scissors_switch_only_after_current_tool_reaches_reserve(self):
        self.many(3);self.cfg['target']=3;self.c.hand_item='minecraft:shears';self.c.durability=3
        original=self.c.status
        def state():
            s=original();s['inventory'][2]={'item':'minecraft:shears','count':1,'slot':2,'durability':50};return s
        original_select=self.c.checked
        def select(op,**kw):
            if op=='select_item':self.c.durability=50
            return original_select(op,**kw)
        self.c.status=state;self.c.checked=select;self.job().run()
        self.assertEqual(len(self.calls('select_item')),1);self.assertEqual(self.calls('select_item')[0]['slot'],2)
    def test_decayed_target_skipped_without_mining(self):
        j=self.job();self.c.rows.clear();self.assertFalse(j.harvest(ROW));self.assertFalse(self.calls('mine_block'))
    def test_decayed_target_skipped_before_approach(self):
        j=self.job();self.c.rows.clear();self.assertFalse(j.approach(ROW));self.assertFalse(self.calls('approach_block'))
    def test_decay_during_known_terminal_approach_is_refreshed(self):
        original=self.c.request
        def request(op,**kw):
            if op!='approach_block':return original(op,**kw)
            self.c.actions.append((op,kw));self.c.rows.clear()
            return {'phase':'waiting','detail':'Work block state changed during approach'}
        self.c.request=request;j=self.job();self.assertFalse(j.approach(ROW));self.assertEqual(len(self.calls('approach_block')),1)
    def test_known_collision_refusal_skips_this_station_for_replanning(self):
        self.c.approach_result={'phase':'error','detail':'Actual collision on depot route'}
        j=self.job();self.assertFalse(j.approach(ROW));self.assertEqual(len(self.calls('approach_block')),1)
    def test_adjacent_fluid_is_skipped_before_native_mine(self):
        self.c.rows[(1,1,0)]={**ROW,'pos':[1,1,0],'state':'Block{minecraft:water}[level=0]','fluid':True}
        j=self.job();self.assertFalse(j.harvest(ROW));self.assertFalse(self.calls('mine_block'))
    def test_leaf_distance_change_refreshed_before_mining(self):
        j=self.job();self.c.rows[(0,1,0)]['state']=ROW['state'].replace('distance=2','distance=7');j.harvest(ROW)
        self.assertIn('distance=7',self.calls('mine_block')[0]['expected_state'])
    def test_one_approach_clears_multiple_nearby_leaves(self):
        self.cfg['regions']=[{'min':[5,0,0],'max':[8,3,2],'authorized':True}];self.cfg['target']=2
        self.c.rows={(6,1,0):{**ROW,'pos':[6,1,0]},(7,1,0):{**ROW,'pos':[7,1,0]}}
        j=self.job();j.run();self.assertEqual(len(self.calls('approach_block')),1)
    def test_partial_scan_does_not_mine(self):
        j=self.job();self.c.partial=True
        with self.assertRaises(LeafStopped):j.run()
        self.assertFalse(self.calls('mine_block'))
    def test_manual_input_preempts(self):
        j=self.job();self.c.manual=True
        with self.assertRaises(LeafStopped):j.run()
        self.assertFalse(self.c.actions)
    def test_short_native_food_or_defense_pause_waits_without_new_actions(self):
        j=self.job();original=self.c.status;states=iter([True,True,False])
        def status():return {**original(),'guard_busy':next(states,False)}
        self.c.status=status;j.state();self.assertEqual(self.clock.slept,.2);self.assertFalse(self.c.actions)
    def test_protected_artificial_wet_and_container_blocks_not_mined(self):
        for change in ({'fluid':True},{'block_entity':True},{'state':ROW['state'].replace('persistent=false','persistent=true')},{'state':'Block{minecraft:oak_log}'}):self.assertFalse(natural_leaf({**ROW,**change}))
        self.cfg['protected_regions']=copy.deepcopy(self.cfg['regions']);j=self.job()
        with self.assertRaises(LeafStopped):j.harvest(ROW)
        self.assertFalse(self.calls('mine_block'))
    def test_no_capacity_preserves_equipment(self):
        self.c.qty=64;original=self.c.status
        def state():
            s=original()
            for row in s['inventory'][2:]:row.update(item='minecraft:diamond_pickaxe',count=1)
            return s
        self.c.status=state;self.cfg['depots']=[];j=self.job()
        with self.assertRaises(LeafStopped):j.run()
        self.assertFalse(self.calls('mine_block'));self.assertEqual(capacity(state(),ITEM,2),0)
    def test_deposit_keeps_baseline_leaves(self):
        seen=[]
        def deposit(c,depots,keep):seen.append(keep);c.qty=keep[ITEM];return {'complete':True}
        j=self.job(deposit=deposit);j.harvest(ROW);j.store();self.assertEqual(seen,[{ITEM:5}]);self.assertEqual(j.book['stored'],{ITEM:1})
    def test_incomplete_deposit_retains_pending(self):
        j=self.job(deposit=lambda *a:{'complete':False});j.harvest(ROW)
        with self.assertRaises(LeafStopped):j.store()
        self.assertEqual(j.book['pending']['kind'],'deposit')
    def test_resume_rejects_changed_world_inventory_or_unsettled_batch(self):
        j=self.job();self.c.world='other'
        with self.assertRaises(LeafStopped):self.job()
        self.c.world='world';self.c.qty+=1
        with self.assertRaises(LeafStopped):self.job()
        self.c.qty-=1;j.begin_batch(self.c.status())
        with self.assertRaises(LeafStopped):self.job()
    def test_existing_target_does_not_mine(self):
        self.cfg.update(target_scope='total_stock',target=5);self.job().run();self.assertFalse(self.calls('mine_block'))
    def test_stop_file_prevents_actions(self):
        j=self.job();(self.path/'STOP').touch()
        with self.assertRaises(LeafStopped):j.run()
        self.assertFalse(self.c.actions)
    def test_invalid_config(self):
        for change in ({'target':True},{'target':0},{'server':''},{'batch_size':17},{'batch_size':True},{'pickup_grace_seconds':float('nan')},{'regions':[{'min':[0,0,0],'max':[40,4,4],'authorized':True}]}):
            with self.assertRaises(ValueError):validate({**self.cfg,**change})
    def test_shears_selector_excludes_equipment(self):
        self.assertEqual(shears(self.c.status())['slot'],1)
        self.assertIsNone(shears({'inventory':[{'item':'minecraft:netherite_sword','count':1,'slot':0,'durability':2000}]}))
    def test_settled_owner_released_before_heartbeat_close(self):
        class Owner:
            world='w';task='t';unconfirmed_native_request=None;native_inflight=None
            def __init__(self):self.active=True;self.calls=[]
            def raw(self):return {'connected':True,'world_session':'w','supervision_lease':{'job_session':'t'}if self.active else {}}
            def checked(self,op,**kw):self.calls.append((op,kw));self.active=False
        c=Owner()
        with patch('native_outcome_fence.wait_exact_idle_terminal',return_value={}):release_or_observe(c)
        self.assertEqual(c.calls,[('material_job_pause',{'release':True})])

if __name__=='__main__':unittest.main()
