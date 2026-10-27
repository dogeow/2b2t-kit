import copy,json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from material_jobs import dry_clay_columns as m
from material_jobs.protocol import JobBlocked


def block(p,name='stone',**kw):
    return {'pos':p,'state':'Block{minecraft:'+name+'}','solid':True,'fluid':False,'block_entity':False,'passable':False,**kw}


class Fake:
    world='world';task='task';rev=1
    def __init__(self,out):
        self.root=self.out=out;self.pos=[101.5,70.,100.5];self.calls=[];self.native_inflight=None
        self.counts={'minecraft:clay_ball':0,'minecraft:clay':0,'minecraft:cobblestone':0};self.last=None
        self.blocks={(100,18,100):block([100,18,100]),(101,18,100):block([101,18,100]),
                     (100,21,100):block([100,21,100],'clay')}
        self.fault=None;self.manual=False;self.flight=True;self.hand={};self.drops=[]
    def status(self):
        tools=[{'slot':0,'item':'minecraft:diamond_pickaxe','count':1,'durability':500,'max_stack':1},
               {'slot':1,'item':'minecraft:diamond_shovel','count':1,'durability':500,'max_stack':1}]
        rows=tools+[{'slot':i+2,'item':item if n else'minecraft:air','count':n,'max_stack':64}for i,(item,n)in enumerate(self.counts.items())]
        rows += [{'slot':i,'item':'minecraft:air','count':0,'max_stack':64}for i in range(len(rows),36)]
        return {'connected':True,'world_session':self.world,'server':'server','dimension':'minecraft:overworld',
                'health':20,'food':20,'guard_armed':True,'guard_pve_only':True,'guard_busy':False,
                'under_water':False,'manual_movement':self.manual,'flight':self.flight,'control_revision':1,
                'pos':list(self.pos),'velocity':[0,0,0],'inventory':rows,'hand':copy.deepcopy(self.hand),'entities':copy.deepcopy(self.drops),
                'supervision_lease':{'kind':'materials','world_session':self.world,'job_session':self.task,'revision':1}}
    def request(self,op,**kw):
        self.calls.append((op,kw));self.last='req-'+str(len(self.calls));r={'id':self.last,'phase':'done','world_session':self.world}
        if op=='scan':
            r.update(blocks=[copy.deepcopy(b)for p,b in self.blocks.items()if all(kw['min'][i]<=p[i]<=kw['max'][i]for i in range(3))],
                     control_revision=1,scan_start_revision=1,scan_end_revision=1,
                     scan_cells_read=math.prod(b-a+1 for a,b in zip(kw['min'],kw['max'])),
                     scan_total_cells=math.prod(b-a+1 for a,b in zip(kw['min'],kw['max'])))
        elif op=='select_item':
            self.hand=next(x for x in self.status()['inventory']if x['slot']==kw['slot'])
            if self.fault=='tool':self.hand={**self.hand,'durability':499}
        elif op=='navigate':self.pos=list(kw['target'])
        elif op=='guard':pass
        elif op=='mine_block':
            r.update(server_confirmed=True,confirmation_scope='single_target_server_block_update_and_native_sequence_ack',
                     native_sequence=2,server_ack_sequence=2)
            if self.fault=='unknown':r['phase']='waiting'
            else:
                b=self.blocks.pop(tuple(kw['pos']));output='minecraft:clay_ball'if 'minecraft:clay}'in b['state']else'minecraft:cobblestone'
                if self.fault=='visible':
                    self.drops=[{'type':'minecraft:item','uuid':'new-source-drop','pos':[100.5,19.125,100.5],
                                 'stack':{'item':output,'count':4,'max_stack':64}}];r['entities']=copy.deepcopy(self.drops)
                else:self.counts[output]+=5 if self.fault=='delta'else(4 if output=='minecraft:clay_ball'else 1)
                if self.fault=='world':r['world_session']='foreign'
        else:raise AssertionError(op)
        return r
    def checked(self,op,**kw):return self.request(op,**kw)


class DryClayTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.c=Fake(self.root);self.profile={'server':'server','dimension':'minecraft:overworld','recipe_jar':'unused.jar',
                                            'protected_regions':[{'min':[0,0,0],'max':[10,90,10]}]}
        self.region={'authorized':True,'source':'natural_survey','item':'minecraft:clay_ball',
                     'min':[100,19,100],'max':[101,21,100],'dry_columns':{'authorized':True,'floor_y':18,
                     'entry':[101,19,100],'cruise_y':70.,'columns':[[100,21,100]]}}
        def move(c,point,*a,**kw):c.pos=list(point)
        for name,value in [('_travel',lambda c,target,*a,**kw:move(c,target)),('move',move),
                           ('settled_state',lambda c,*a,**kw:c.status())]:
            p=patch.object(m,name,side_effect=value);p.start();self.addCleanup(p.stop)
        p=patch.object(m.time,'sleep');p.start();self.addCleanup(p.stop)
    def run_source(self,item='minecraft:clay_ball',target=4):
        return m.run(self.c,self.profile,self.region,item,target,self.root/'job',lambda:None)
    def test_explicit_bounds_and_column_identity_are_required(self):
        m.validate(self.region)
        for change in ({'authorized':False},{'source':'seed_hint'},{'min':[100,18,100]},{'max':[116,21,100]}):
            with self.subTest(change=change),self.assertRaises(JobBlocked):m.validate({**self.region,**change})
        for change in ({'columns':[[100,21,100],[100,20,100]]},{'floor_y':True},{'cruise_y':23},{'entry':[101,20,100]}):
            with self.subTest(change=change),self.assertRaises(JobBlocked):m.validate({**self.region,'dry_columns':{**self.region['dry_columns'],**change}})
    def test_real_four_ball_delta_and_preserved_floor_then_shaft_exit(self):
        result=self.run_source()
        self.assertEqual(('done',4,1),(result['phase'],result['after'],result['mined_blocks']))
        mines=[kw for op,kw in self.c.calls if op=='mine_block'];self.assertEqual(1,len(mines));self.assertEqual('down',mines[0]['face'])
        self.assertIn((100,18,100),self.c.blocks);self.assertEqual([101.5,70.,100.5],self.c.pos)
        self.assertIsNone(json.loads((self.root/'job/dry-clay-columns.json').read_text())['pending'])
    def test_unknown_or_foreign_receipt_stays_pending_and_cannot_replay(self):
        for fault in ('unknown','world'):
            with self.subTest(fault=fault):
                self.setUp();self.c.fault=fault
                with self.assertRaisesRegex(JobBlocked,'unresolved'):self.run_source()
                n=len(self.c.calls)
                with self.assertRaisesRegex(JobBlocked,'no replay'):self.run_source()
                self.assertEqual(n,len(self.c.calls))
    def test_wrong_drop_delta_is_not_source_credit(self):
        self.c.fault='delta'
        with patch.object(m.time,'monotonic',side_effect=range(20)),self.assertRaisesRegex(JobBlocked,'drop delta'):
            self.run_source()
        book=json.loads((self.root/'job/dry-clay-columns.json').read_text());self.assertIsNotNone(book['pending']);self.assertFalse(book['complete'])

    def test_native_done_without_server_sequence_confirmation_is_not_completion(self):
        original=self.c.request
        def unconfirmed(op,**kw):
            r=original(op,**kw)
            if op=='mine_block':r['server_ack_sequence']=1
            return r
        self.c.request=unconfirmed
        with self.assertRaisesRegex(JobBlocked,'receipt/removal'):self.run_source()
        self.assertIsNotNone(json.loads((self.root/'job/dry-clay-columns.json').read_text())['pending'])

    def test_visible_uncollected_drop_uses_one_scoped_pickup_and_no_remine(self):
        self.c.fault='visible'
        def pickup(c,drop,**kw):
            self.assertEqual('new-source-drop',drop['uuid']);c.counts['minecraft:clay_ball']+=4;c.drops=[];return True
        with patch.object(m,'collect_drop',side_effect=pickup)as collected:
            self.assertEqual('done',self.run_source()['phase'])
        collected.assert_called_once();self.assertEqual(1,sum(op=='mine_block'for op,_ in self.c.calls))
    def test_tool_metadata_change_stops_before_mining(self):
        self.c.fault='tool'
        with self.assertRaisesRegex(JobBlocked,'tool selection'):self.run_source()
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.calls))
    def test_water_falling_or_container_in_local_context_is_preserved(self):
        for name,extra in (('water',{'fluid':True}),('gravel',{}),('chest',{'block_entity':True})):
            with self.subTest(name=name):
                self.setUp();self.c.blocks[(100,22,101)]=block([100,22,101],name,**extra)
                with self.assertRaisesRegex(JobBlocked,'hazards'):self.run_source()
                self.assertFalse(any(op=='mine_block'for op,_ in self.c.calls))
    def test_manual_or_external_flight_change_sends_no_action(self):
        for flag in ('manual','flight'):
            with self.subTest(flag=flag):
                self.setUp();setattr(self.c,flag,flag=='manual')
                with self.assertRaises(RuntimeError):self.run_source()
                self.assertEqual([],self.c.calls)
    def test_completed_stock_consumption_cannot_replay_previous_columns(self):
        self.run_source();self.c.counts['minecraft:clay_ball']=0;n=len(self.c.calls)
        self.assertEqual('COMPLETED_RECEIPT',self.run_source()['code']);self.assertEqual(n,len(self.c.calls))
    def test_clay_compaction_requires_exact_vanilla_recipe_balance(self):
        def compact(c,catalog,targets):
            c.counts['minecraft:clay_ball']-=4;c.counts['minecraft:clay']+=1;return {'complete':True}
        with patch.object(m,'RecipeCatalog'),patch.object(m,'manufacture',side_effect=compact):result=self.run_source('minecraft:clay',1)
        self.assertEqual(('done',1,0),(result['phase'],result['after'],self.c.counts['minecraft:clay_ball']))

    def test_unknown_source_travel_is_retained_before_any_mining(self):
        def unknown(*a,**kw):
            self.c.last='unknown-travel';self.c.native_inflight={'request_id':self.c.last}
            raise RuntimeError('unknown route')
        with patch.object(m,'_travel',side_effect=unknown),self.assertRaisesRegex(RuntimeError,'unknown route'):
            self.run_source()
        n=len(self.c.calls)
        with self.assertRaisesRegex(JobBlocked,'no replay'):self.run_source()
        self.assertEqual(n,len(self.c.calls));self.assertFalse(any(op=='mine_block'for op,_ in self.c.calls))

    def test_registered_colored_source_calls_the_existing_owner_primitive(self):
        from material_jobs.colored_sources import acquire
        self.profile['colored_source_regions']=[self.region]
        result=acquire(self.c,'minecraft:clay_ball',4,self.profile,self.root/'hook',lambda:None)
        self.assertEqual(('done',4),(result['phase'],result['after']))
        self.assertEqual(1,sum(op=='mine_block'for op,_ in self.c.calls))

    def test_unknown_source_operation_blocks_a_new_job_and_changed_overlapping_box(self):
        self.c.fault='unknown'
        with self.assertRaises(JobBlocked):self.run_source()
        n=len(self.c.calls);self.region['max']=[102,21,100]
        with self.assertRaisesRegex(JobBlocked,'across jobs'):
            m.run(self.c,self.profile,self.region,'minecraft:clay',1,self.root/'new-job',lambda:None)
        self.assertEqual(n,len(self.c.calls))

    def test_depleted_column_is_skipped_without_repeating_stone_excavation(self):
        self.c.blocks.pop((100,21,100));self.c.blocks[(100,20,100)]=block([100,20,100])
        result=self.run_source()
        self.assertEqual('WAIT_SOURCE',result['code'])
        self.assertFalse(any(op=='mine_block'for op,_ in self.c.calls))

    def test_pre_dispatch_route_refusal_has_no_unknown_intent(self):
        with patch.object(m,'_travel',side_effect=JobBlocked('preflight refused')),self.assertRaises(JobBlocked):self.run_source()
        book=json.loads((self.root/'job/dry-clay-columns.json').read_text())
        self.assertIsNone(book['pending']);self.assertEqual([],self.c.calls)

    def test_remote_route_uses_only_registered_bounded_points(self):
        self.c.pos=[500.5,70.,100.5]
        self.region['dry_columns']['route']={'authorized':True,'source':'verified_native_flight','world_session':'world',
            'points':[[250.5,70.,100.5],[101.5,70.,100.5]]}
        self.assertEqual('done',self.run_source()['phase'])
        targets=[kw['target']for op,kw in self.c.calls if op=='navigate'and kw.get('arrival')==2]
        self.assertEqual(self.region['dry_columns']['route']['points'],targets)


if __name__=='__main__':unittest.main()
