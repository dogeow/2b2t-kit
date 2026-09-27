from contextlib import contextmanager, nullcontext
import copy
import json
import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import material_jobs_backend as backend
from material_jobs.protocol import JobBlocked, JobPaused


def state():
    return {'connected':True,'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'w',
            'control_revision':3,'manual_movement':False,'screen':'','health':20,'pos':[0,100,0],'flight':True,
            'phase':'done','id':'request-a','last_request':'request-a',
            'supervision_lease':{'id':'lease-a','kind':'materials','job_session':'task-a','world_session':'w','revision':3}}


def inventory_rows(counts):
    rows=[]
    for item,total in counts.items():
        while total:
            size=1 if item.endswith('_pickaxe') else 64
            count=min(total,size)
            rows.append({'slot':len(rows),'item':item,'count':count,'max_stack':size});total-=count
    return rows+[{'slot':i,'item':'minecraft:air','count':0,'max_stack':1} for i in range(len(rows),36)]


class BackendTest(unittest.TestCase):
    def stopped_build(self,*,outcome='needs_review',budget=True,held=None,alter=None,native=None):
        audit={'placement_key':'ship','observed_at':2000,'loaded_chunks_verified':True,
               'matched':2762,'total':3407,'kinds':{'missing':645},
               'replacement_items':{'minecraft:deepslate_tiles':557,'minecraft:blast_furnace':17,
                   'minecraft:polished_andesite':57,'minecraft:hopper':6,'minecraft:white_concrete':8}}
        before={**audit,'observed_at':1000}
        if alter:alter(audit)
        self.current['projection_selection']={'key':'ship','min':[0,64,0],'max':[10,186,10]}
        self.current['build_job']={'outcome':outcome,'reason':'路线搜索达到预算上限',
                                   'navigation':{'budget_exhausted':budget,'expanded':50000,'targets':31}}
        if native:self.current['build_job'].update(native)
        self.job.request.update(mode='projection',projection_key='ship')
        self.job.action=Mock(return_value=nullcontext((self.client,self.root)))
        self.job.prepare_travel=Mock();self.job.refresh_audit=Mock(return_value=before)
        self.job.stock=Mock(return_value=held if held is not None else {'minecraft:polished_andesite':57,'minecraft:hopper':6,'minecraft:white_concrete':32})
        with patch('material_jobs.acquisition._travel'),patch.object(backend,'outside_station'),patch('goal_workflow.build_phase',return_value=audit),patch.object(backend,'leave_projection'):
            return self.job.build('ship')

    def test_budget_limited_build_requests_new_missing_batch_without_claiming_placement(self):
        receipt=self.stopped_build()
        self.assertEqual('waiting',receipt['phase'])
        self.assertEqual({'minecraft:deepslate_tiles':128},receipt['requirements'])
        self.assertEqual(0,receipt['placed']);self.assertTrue(receipt['route_budget_exhausted'])
        self.assertEqual(50000,receipt['navigation']['expanded'])

    def test_budget_limited_build_with_all_required_materials_stays_blocked(self):
        receipt=self.stopped_build(held={'minecraft:deepslate_tiles':557,'minecraft:blast_furnace':17,
            'minecraft:polished_andesite':57,'minecraft:hopper':6,'minecraft:white_concrete':32})
        self.assertEqual('blocked',receipt['phase']);self.assertFalse(receipt['requirements'])
        self.assertEqual(0,receipt['placed'])

    def test_confirmed_unreachable_current_stock_can_fetch_a_different_material(self):
        native={'outcome':'blocked','reason':'找不到可通行路线；请检查门口、支撑或剩余材料。',
                'navigation':{'path_length':0,'search_pending':False,'goals':366,'expanded':2786}}
        receipt=self.stopped_build(native=native)
        self.assertEqual('waiting',receipt['phase']);self.assertTrue(receipt['route_unreachable'])
        self.assertFalse(receipt['route_budget_exhausted']);self.assertEqual(0,receipt['placed'])
        self.assertEqual({'minecraft:deepslate_tiles':128},receipt['requirements'])
        held={'minecraft:deepslate_tiles':557,'minecraft:blast_furnace':17,
              'minecraft:polished_andesite':57,'minecraft:hopper':6,'minecraft:white_concrete':8}
        self.assertEqual('blocked',self.stopped_build(native=native,held=held)['phase'])

    def test_no_route_text_without_completed_search_does_not_start_mining(self):
        for navigation in ({'path_length':0,'search_pending':True,'goals':366,'expanded':2786},
                           {'path_length':0,'search_pending':False,'goals':0,'expanded':0}):
            with self.subTest(navigation=navigation):
                receipt=self.stopped_build(native={'outcome':'blocked','reason':'找不到可通行路线；',
                                                  'navigation':navigation})
                self.assertEqual('blocked',receipt['phase']);self.assertNotIn('requirements',receipt)

    def test_other_stopped_builds_do_not_turn_into_resource_errands(self):
        for outcome,budget in [('blocked',True),('manual_stop',True),('needs_review',False),('world_changed',True)]:
            with self.subTest(outcome=outcome,budget=budget):
                receipt=self.stopped_build(outcome=outcome,budget=budget)
                self.assertEqual('blocked',receipt['phase']);self.assertNotIn('requirements',receipt)

    def test_route_budget_fallback_requires_current_complete_missing_audit(self):
        for values in [{'placement_key':'other'},{'loaded_chunks_verified':False},{'observed_at':999},
                       {'kinds':{'missing':645,'unloaded':1}},{'kinds':{'missing':0}},{'kinds':{}}]:
            with self.subTest(values=values):
                receipt=self.stopped_build(alter=lambda a:a.update(values))
                self.assertEqual('blocked',receipt['phase']);self.assertNotIn('requirements',receipt)

    def test_missing_build_materials_request_one_new_useful_batch(self):
        audit={'replacement_items':{'minecraft:white_concrete':8,'minecraft:deepslate_tiles':625,'minecraft:hopper':6}}
        self.assertEqual({'minecraft:deepslate_tiles':128},backend.next_build_supply(audit,{'minecraft:white_concrete':32,'minecraft:hopper':6}))
        self.assertEqual({'minecraft:deepslate_tiles':256},backend.next_build_supply(audit,{'minecraft:white_concrete':32,'minecraft:hopper':6,'minecraft:deepslate_tiles':128}))
        self.assertFalse(backend.next_build_supply(audit,{'minecraft:white_concrete':32,'minecraft:hopper':6,'minecraft:deepslate_tiles':625}))

    def test_projection_preparation_checkpoint_cannot_reenter_audit_travel(self):
        self.job.request.update(mode='projection',projection_key='ship')
        self.current['pos']=[200,100,200]
        self.current['projection_selection']={'key':'ship','min':[0,64,0],'max':[10,100,10]}
        self.job.audit=None;self.job.audit_dirty=True;self.job.checking=False
        self.job.initial_revision=3;self.job.warehouse_hint={}
        self.job.ensure_client=Mock(return_value=self.client);self.job.prepare_travel=Mock()
        self.job.checkpoint=Mock(side_effect=lambda:self.job.observe())
        def audit():
            self.job.audit={'placement_key':'ship','matched':5,'total':10};self.job.audit_dirty=False
        self.job.refresh_audit=Mock(side_effect=audit)
        def travel(c,target,checkpoint,trace):
            self.assertTrue(self.job.busy)
            checkpoint();checkpoint()
        with patch.object(backend,'read_fresh',side_effect=lambda root:copy.deepcopy(self.current)), \
                patch('material_jobs.acquisition._travel',side_effect=travel) as movement:
            result=self.job.observe()
        self.assertEqual(1,movement.call_count);self.assertEqual(1,self.job.refresh_audit.call_count)
        self.assertEqual(5,result['projection_audit']['matched']);self.assertFalse(self.job.busy)

    def test_remote_quarry_return_stages_before_local_workbench_walk(self):
        self.current['pos']=[100,90,100]
        entry=[0,65,0];staging=[0,85,5]
        self.job.profile={'workbench':[0,65,-4],'workbench_staging':staging,
                          'workbench_entry':[{'kind':'walk','target':entry}]}
        self.job.action=Mock(return_value=nullcontext((self.client,self.root)))
        self.job.prepare_travel=Mock();self.job.crafting_catalog=object();self.current['inventory']=[]
        self.job.route=Mock(side_effect=lambda name:self.assertLessEqual(math.dist(self.current['pos'],entry),32))
        def travel(client,target,checkpoint,trace):self.current['pos']=list(target)
        with patch('material_jobs.acquisition._travel',side_effect=travel) as cruise, \
                patch('goal_workflow.open_workbench'), \
                patch('material_manufacture.manufacture',return_value={'complete':True}), \
                patch('material_manufacture.inventory_plan',return_value=None):
            result=self.job.craft({'minecraft:white_dye':1})
        self.assertEqual('done',result['phase'])
        self.assertEqual(staging,cruise.call_args.args[1])

    def test_two_by_two_craft_uses_live_inventory_without_navigation_or_registered_workbench(self):
        import zipfile
        from recipe_catalog import RecipeCatalog
        from test_material_manufacture import InventoryCraftClient
        jar=self.root/'inventory-recipes.jar'
        with zipfile.ZipFile(jar,'w') as archive:
            archive.writestr('data/minecraft/recipe/stone_bricks.json',json.dumps({
                'type':'minecraft:crafting_shaped','pattern':['##','##'],'key':{'#':'minecraft:stone'},
                'result':{'id':'minecraft:stone_bricks','count':4}}))
        self.client=InventoryCraftClient(self.root);self.job.client=self.client
        self.job.profile={};self.job.crafting_catalog=RecipeCatalog(jar)
        self.job.action=Mock(return_value=nullcontext((self.client,self.root)))
        self.job.prepare_travel=Mock();self.job.route=Mock()
        with patch('kit_runtime.inventory.time.sleep'),patch('material_manufacture.time.sleep'), \
                patch('goal_workflow.open_workbench') as workbench:
            result=self.job.craft({'minecraft:stone_bricks':48})
        self.assertEqual(('done','inventory'),(result['phase'],result['crafting_location']))
        self.job.prepare_travel.assert_not_called();self.job.route.assert_not_called()
        self.job.close_owned_menu.assert_not_called();workbench.assert_not_called()
        self.assertTrue(all(op=='slot_click' for op,_ in self.client.calls))

    def test_two_by_two_branch_pauses_for_player_ui_without_closing_or_navigating(self):
        self.current.update(screen='InventoryScreen',menu={'type':'InventoryMenu'},
                            inventory=inventory_rows({'minecraft:stone':48}))
        self.job.crafting_catalog=object();self.job.profile={}
        self.job.action=Mock(return_value=nullcontext((self.client,self.root)))
        self.job.prepare_travel=Mock();self.job.route=Mock()
        with patch('material_manufacture.inventory_plan',return_value={'steps':[]}), \
                patch('material_manufacture.manufacture') as make:
            with self.assertRaises(JobPaused):self.job.craft({'minecraft:stone_bricks':48})
        make.assert_not_called();self.job.prepare_travel.assert_not_called();self.job.route.assert_not_called()
        self.job.close_owned_menu.assert_not_called();self.client.checked.assert_not_called()

    def entry_route_scene(self, *, roofed=True, all_covered=False):
        self.current['pos']=[17.49,65.82,4.5]
        self.job.profile={'workbench_entry':[{'kind':'walk','target':[.5,65,.5]}]}
        blocks={}
        def solid(x,y,z):
            return {'pos':[x,y,z],'state':'Block{minecraft:stone}','solid':True,
                    'passable':False,'fluid':False,'block_entity':False}
        for x in range(-4,5):
            for z in range(-4,5):
                blocks[(x,63,z)]=solid(x,63,z)
                if roofed and (all_covered or z<=2):blocks[(x,74,z)]=solid(x,74,z)
        for x in (-1,0,1):
            for z in (0,1):blocks[(x,64,z)]=solid(x,64,z)
        for x in (-1,1):
            for y in (65,66):blocks[(x,y,0)]=solid(x,y,0)
        trace=[]
        def request(op,**params):
            assert op=='scan',op
            return {'world_session':'w','blocks':[copy.deepcopy(row) for pos,row in blocks.items()
                if all(params['min'][i]<=pos[i]<=params['max'][i] for i in range(3))]}
        def checked(op,**params):
            assert op=='walk',op
            trace.append(('walk',list(params['target']),list(self.current['pos'])))
            self.current['pos']=list(params['target'])
            return {'phase':'done'}
        def fly(client,target,checkpoint,route):
            trace.append(('fly',list(target),list(self.current['pos'])))
            self.current['pos']=list(target)
        self.client.request=Mock(side_effect=request);self.client.checked=Mock(side_effect=checked)
        return blocks,trace,fly

    def test_entry_below_old_28_block_limit_flies_to_verified_open_sky_before_short_ground_steps(self):
        blocks,trace,fly=self.entry_route_scene()
        with patch('material_jobs.acquisition._travel',side_effect=fly):
            self.job.route('workbench_entry')
        self.assertEqual(('fly',[.5,64,3.5]),trace[0][:2])
        self.assertEqual([.5,65,.5],self.current['pos'])
        walks=[(target,start) for kind,target,start in trace if kind=='walk']
        self.assertEqual(3,len(walks))
        self.assertTrue(all(math.hypot(target[0]-start[0],target[2]-start[2])<=1.8 for target,start in walks))
        self.assertTrue(all(abs(target[1]-start[1])<=1 for target,start in walks))
        self.assertIn((0,74,0),blocks)  # Never descend through the registered porch roof.
        self.assertEqual(319,self.client.request.call_args_list[0].kwargs['max'][1])

    def test_entry_itself_can_be_air_approach_only_after_full_open_sky_and_floor_proof(self):
        _,trace,fly=self.entry_route_scene(roofed=False)
        with patch('material_jobs.acquisition._travel',side_effect=fly):
            self.job.route('workbench_entry')
        self.assertEqual([('fly',[.5,65,.5],[17.49,65.82,4.5])],trace)
        self.client.checked.assert_not_called()

    def test_fully_roofed_entry_does_not_start_blind_flight_or_long_walk(self):
        _,trace,fly=self.entry_route_scene(all_covered=True)
        with patch('material_jobs.acquisition._travel',side_effect=fly) as movement:
            with self.assertRaisesRegex(JobBlocked,'露天接近点'):
                self.job.route('workbench_entry')
        movement.assert_not_called();self.client.checked.assert_not_called();self.assertEqual([],trace)

    def test_entry_incomplete_or_wrong_world_scan_cannot_authorize_approach(self):
        for reply in ({'phase':'error','world_session':'w','blocks':[]},
                      {'world_session':'other','blocks':[]},{'world_session':'w'}):
            with self.subTest(reply=reply):
                _,_,fly=self.entry_route_scene()
                self.client.request=Mock(return_value=reply)
                with patch('material_jobs.acquisition._travel',side_effect=fly) as movement:
                    with self.assertRaises(JobBlocked):self.job.route('workbench_entry')
                movement.assert_not_called();self.client.checked.assert_not_called()

    def test_entry_ground_revalidated_after_flight_before_any_walk(self):
        blocks,trace,fly=self.entry_route_scene()
        def changed(*args):
            fly(*args)
            blocks[(0,65,2)]={'pos':[0,65,2],'state':'Block{minecraft:water}',
                             'fluid':True,'passable':True,'block_entity':False,'solid':False}
        with patch('material_jobs.acquisition._travel',side_effect=changed):
            with self.assertRaises(JobBlocked):self.job.route('workbench_entry')
        self.assertEqual(['fly'],[row[0] for row in trace]);self.client.checked.assert_not_called()

    def test_indoor_exit_route_never_uses_an_aerial_entry_prefix(self):
        self.current['pos']=[.5,65,.5]
        self.job.profile={'workbench_exit':[{'kind':'walk','target':[1.5,65,.5]}]}
        with patch('material_jobs.acquisition._travel') as movement:
            self.job.route('workbench_exit')
        movement.assert_not_called()
        self.client.checked.assert_called_once_with('walk',target=[1.5,65,.5],arrival=.4,restore_flight=False,seconds=45)

    def test_ui_start_waits_for_post_click_snapshot_instead_of_old_menu(self):
        old={'time':99,'screen':'KitFormScreen'};fresh={'time':101,'screen':''}
        with patch.object(backend,'read_fresh',side_effect=[old,fresh]),patch.object(backend.time,'sleep'):
            self.assertEqual(fresh,backend.launch_snapshot(Path('/unused'),{'created_at':100}))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.current=state()
        self.client=SimpleNamespace(world='w',task='task-a',rev=3,last='request-a',root=self.root,out=self.root,
                                    heartbeat=SimpleNamespace(id='lease-a',close=Mock()),
                                    checked=Mock(return_value={'phase':'done'}),request=Mock(return_value={'phase':'done'}),
                                    finish=Mock(),status=Mock(side_effect=lambda:self.current))
        self.job=backend.Backend.__new__(backend.Backend)
        self.job.client=self.client;self.job.root=self.root;self.job.out=self.root
        self.job.cleaning=False;self.job.busy=False;self.job.ready=True;self.job.native_gravel_session=None
        self.job.request={'mode':'item','context':{'server':'simpcraft.com','dimension':'minecraft:overworld','world_session':'w','expected_revision':3}}
        self.job.checkpoint=Mock();self.job.close_owned_menu=Mock();self.job.stage_near_base=Mock()

    def test_cleanup_scope_requires_exact_lease_and_current_or_proved_own_revision(self):
        self.assertTrue(backend.owns_material_state(self.client,self.current))
        for field,value in [('connected',False),('manual_movement',True),('world_session','other')]:
            s=copy.deepcopy(self.current);s[field]=value;self.assertFalse(backend.owns_material_state(self.client,s))
        for field,value in [('id','other'),('job_session','other'),('world_session','other'),('revision',4),('kind','parking')]:
            s=copy.deepcopy(self.current);s['supervision_lease'][field]=value;self.assertFalse(backend.owns_material_state(self.client,s))
        s=copy.deepcopy(self.current);s['control_revision']=4;s['supervision_lease']['revision']=4
        self.assertTrue(backend.owns_material_state(self.client,s))
        s['last_request']='someone-else';self.assertFalse(backend.owns_material_state(self.client,s))
        s['last_request']='request-a';s['phase']='running';self.assertFalse(backend.owns_material_state(self.client,s))

    def test_kit_page_cleanup_only_releases_own_job_and_never_closes_page_or_moves(self):
        self.current['screen']='KitFormScreen'
        with patch.object(backend,'read_fresh',return_value=self.current),patch.object(backend,'local_park') as park:
            self.job.finish()
        self.client.checked.assert_called_once_with('material_job_pause',release=True)
        self.client.request.assert_not_called();self.job.close_owned_menu.assert_not_called();park.assert_not_called()
        self.assertIsNone(self.job.client);self.assertFalse(self.job.cleaning)

    def test_foreign_revision_never_gets_adopted_for_cleanup(self):
        self.current['control_revision']=4;self.current['supervision_lease']['revision']=4
        self.current['last_request']='other';self.current['id']='other'
        with patch.object(backend,'read_fresh',return_value=self.current):self.job.finish()
        self.assertEqual(3,self.client.rev);self.client.checked.assert_not_called();self.client.request.assert_not_called()

    def test_registered_shelter_cleanup_precedes_park_update_and_finish(self):
        calls=[]
        self.job.close_owned_menu=Mock(side_effect=lambda:calls.append('close'))
        self.client.checked=Mock(side_effect=lambda op,**kw:calls.append(op) or {'phase':'done'})
        def finish():
            calls.append('finish')
            (self.root/'stock-safety.json').write_text(json.dumps({'lease':'lease-a','action':'KEEP_PVE_GUARD'}))
        self.client.finish=Mock(side_effect=finish)
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_cleanup.run',side_effect=lambda c:calls.append('cleanup') or []),patch.object(backend,'local_park',side_effect=lambda c:calls.append('park') or [0,110,0]),patch.object(backend,'leave_quarry',side_effect=lambda c,d:calls.append('exit')):
            self.job.finish()
        self.assertEqual(['close','exit','cleanup','close','park','material_job_park','finish'],calls)
        self.assertEqual([0,110,0],self.client.park_target)

    def test_missing_native_safety_receipt_cannot_report_successful_finish(self):
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_cleanup.run',return_value=[]),patch.object(backend,'local_park',return_value=[0,110,0]):
            with self.assertRaisesRegex(JobBlocked,'尚未得到原生确认'):self.job.finish()

    def test_nonhealth_park_failure_is_reported_and_logout_is_not_replayed(self):
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_cleanup.run',return_value=[]),patch.object(backend,'local_park',side_effect=JobBlocked('屋顶遮挡')):
            with self.assertRaisesRegex(JobBlocked,'屋顶遮挡'):self.job.finish()
        self.client.request.assert_called_once_with('safe_logout')
        self.assertEqual('safe_logout',json.loads((self.root/'finish-fallback.json').read_text())['action'])

    def test_control_handoff_during_park_cannot_become_logout(self):
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_cleanup.run',return_value=[]),patch.object(backend,'local_park',side_effect=JobPaused('用户接管')):
            with self.assertRaises(JobPaused):self.job.finish()
        self.client.request.assert_not_called()

    def test_low_health_records_lock_and_does_not_start_cleanup(self):
        self.current['health']=10
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_cleanup.run') as clean,patch('safety_interlock.record_material_health_exit') as hold:
            self.job.finish()
        clean.assert_not_called();self.client.request.assert_called_once_with('safe_logout');hold.assert_called_once()

    def test_job_client_cleaning_can_observe_kit_page_but_forbids_other_actions(self):
        self.current['screen']='KitFormScreen'
        client=backend.JobClient.__new__(backend.JobClient)
        client.owner=SimpleNamespace(cleaning=True,latest=self.current)
        for field in ('world','task','rev','last','heartbeat'):setattr(client,field,getattr(self.client,field))
        client.raw=Mock(return_value=self.current)
        self.assertIs(client.status(),self.current)
        with self.assertRaises(JobPaused):client.request('navigate',target=[0,120,0])
        with patch('material_client.MaterialClient.request',return_value={'phase':'done'}) as request:
            self.assertEqual('done',client.request('material_job_pause',release=True)['phase'])
        request.assert_called_once()

    def test_warehouse_hint_recounts_loose_and_packed_contents_once(self):
        rows=[{'item':'minecraft:bone_block','count':10},{'item':'minecraft:blue_shulker_box','count':1,'contains':[{'item':'minecraft:bone_block','count':64}]},
              {'item':'minecraft:air','count':0}]
        hint=backend.observed_warehouse_stock(rows)
        self.assertEqual(74,hint['minecraft:bone_block'])
        rows[1]['contains'][0]['count']=32
        self.assertEqual(42,backend.observed_warehouse_stock(rows)['minecraft:bone_block'])

    def test_food_consumption_without_byproduct_deposit_cannot_report_make_room_done(self):
        self.job.baseline={'minecraft:stone':16}
        self.job.profile={'depots':[[1,2,3]]};self.job.prepare_travel=Mock()
        @contextmanager
        def action(name):yield self.client,self.root
        self.job.action=action
        self.current['inventory']=inventory_rows({'minecraft:stone':64,'minecraft:bread':2})
        self.job.stock=Mock(return_value={'minecraft:stone':64,'minecraft:bread':1})
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_depots.exchange',return_value={'complete':False,'remaining_deposit':{'minecraft:stone':48}}) as exchange:
            receipt=self.job.make_room({'minecraft:iron_ingot':2},['minecraft:iron_ingot'])
        self.assertEqual('blocked',receipt['phase']);self.assertEqual({},receipt['stored'])
        exchange.assert_called_once_with(self.client,[[1,2,3]],deposit={'minecraft:stone':16})

    def test_partial_make_room_counts_only_authorized_deposit_delta(self):
        self.job.baseline={'minecraft:stone':16,'minecraft:dirt':32}
        self.job.profile={'depots':[[1,2,3]]};self.job.prepare_travel=Mock()
        @contextmanager
        def action(name):yield self.client,self.root
        self.job.action=action
        before={'minecraft:stone':64,'minecraft:dirt':32,'minecraft:bread':2,'minecraft:diamond_pickaxe':1,'minecraft:raw_iron':8}
        self.current['inventory']=inventory_rows(before)
        self.job.stock=Mock(return_value={**before,'minecraft:stone':48,'minecraft:bread':1})
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_depots.exchange',return_value={'complete':False,'remaining_deposit':{'minecraft:stone':32}}) as exchange:
            receipt=self.job.make_room({'minecraft:iron_ingot':2},['minecraft:raw_iron'])
        self.assertEqual('done',receipt['phase']);self.assertEqual({'minecraft:stone':16},receipt['stored'])
        exchange.assert_called_once_with(self.client,[[1,2,3]],deposit={'minecraft:stone':16})

    def test_full_initial_backpack_blocks_before_any_controller_travel_or_logout(self):
        item='minecraft:cobbled_deepslate';held={item:302,'minecraft:stone':31*64}
        self.current['inventory']=inventory_rows(held)
        self.job.baseline=dict(held);self.job.client=None
        self.job.request['target_stack_sizes']={item:64}
        self.job.ensure_client=Mock();self.job.action=Mock();self.job.prepare_travel=Mock()
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_depots.exchange') as exchange:
            receipt=self.job.make_room({item:2304},[item]);self.job.finish()
        self.assertEqual('blocked',receipt['phase']);self.assertEqual('no_owned_byproducts',receipt['code'])
        self.assertEqual({item:302},receipt['held']);self.assertEqual({item:320},receipt['capacity'])
        self.assertEqual(0,receipt['free_slots']);self.assertEqual({item:2304},receipt['targets'])
        self.assertTrue(all(str(n) in receipt['detail'] for n in (2304,302,320)))
        self.assertIn('原有物品',receipt['detail'])
        self.assertEqual(held,self.job.baseline);self.assertIsNone(self.job.client)
        self.job.ensure_client.assert_not_called();self.job.action.assert_not_called()
        self.job.prepare_travel.assert_not_called();self.job.stage_near_base.assert_not_called()
        exchange.assert_not_called();self.client.request.assert_not_called()

    def test_unloading_one_owned_stack_cannot_start_travel_for_impossible_large_item_target(self):
        item='minecraft:cobbled_deepslate'
        self.current['inventory']=inventory_rows({item:302,'minecraft:stone':64,'minecraft:dirt':30*64})
        self.job.baseline={item:302,'minecraft:dirt':30*64};self.job.request['target_stack_sizes']={item:64}
        self.job.action=Mock();self.job.prepare_travel=Mock()
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_depots.exchange') as exchange:
            receipt=self.job.make_room({item:2304},[item])
        self.assertEqual('target_exceeds_safe_capacity',receipt['code'])
        self.assertEqual({item:384},receipt['capacity_after_owned_deposit'])
        self.job.action.assert_not_called();self.job.prepare_travel.assert_not_called();exchange.assert_not_called()

    def test_unknown_capacity_observation_never_creates_a_controller(self):
        self.current['inventory']=inventory_rows({'minecraft:stone':64})[:-1]
        self.job.baseline={};self.job.action=Mock()
        with patch.object(backend,'read_fresh',return_value=self.current):
            receipt=self.job.make_room({'minecraft:iron_ingot':2},[])
        self.assertEqual('capacity_observation_incomplete',receipt['code']);self.job.action.assert_not_called()

    def test_required_new_recipe_inputs_are_not_reclassified_as_unloadable_byproducts(self):
        self.current['inventory']=inventory_rows({'minecraft:raw_iron':64})
        self.job.baseline={};self.job.action=Mock()
        with patch.object(backend,'read_fresh',return_value=self.current):
            receipt=self.job.make_room({'minecraft:iron_ingot':64},['minecraft:raw_iron'])
        self.assertEqual('no_owned_byproducts',receipt['code']);self.job.action.assert_not_called()

    def test_native_gravel_cleanup_does_not_stop_other_task(self):
        self.job.native_gravel_session='gravel-owned';self.current['gravel']={'active':True}
        self.current['supervision_lease']['job_session']='somebody-else'
        with patch.object(backend,'read_fresh',return_value=self.current),patch('kit_cli.send') as send:
            self.job.stop_owned_gravel()
        send.assert_not_called()

    def test_native_gravel_health_lock_prevents_any_resume_or_stop_request(self):
        self.job.native_gravel_session='gravel-owned';self.current['gravel']={'active':True};self.current['safety_hold']={'active':True}
        with patch.object(backend,'read_fresh',return_value=self.current),patch('kit_cli.send') as send:
            with self.assertRaisesRegex(RuntimeError,'safety lock'):self.job.stop_owned_gravel()
        send.assert_not_called();self.assertEqual('gravel-owned',self.job.native_gravel_session)

    def test_native_gravel_unknown_start_acknowledgement_never_replays(self):
        self.job.client=None;self.job.stock=Mock(return_value={});self.job.finish=Mock()
        self.current['supervision_lease']={}
        reply={**self.current,'phase':'waiting','gravel':{'active':False}}
        with patch.object(backend,'read_fresh',return_value=self.current),patch('kit_cli.send',return_value=reply) as send:
            with self.assertRaisesRegex(JobBlocked,'不重复启动'):self.job.acquire_gravel(64)
        self.assertEqual(1,send.call_count);self.assertFalse(self.job.busy)

    def test_gravel_busy_scope_stays_set_while_checkpoint_observes(self):
        self.job.client=None;self.job.stock=Mock(side_effect=[{}, {'minecraft:gravel':64}]);self.job.finish=Mock()
        initial=copy.deepcopy(self.current);initial['supervision_lease']={}
        active=copy.deepcopy(self.current);active['gravel']={'active':True};active['supervision_lease']['job_session']='gravel-owned'
        ended=copy.deepcopy(active);ended['gravel']['active']=False
        seen=[]
        self.job.checkpoint=Mock(side_effect=lambda:seen.append(self.job.busy))
        with patch.object(backend,'read_fresh',side_effect=[initial,ended,ended]),patch('kit_cli.send',return_value=active):
            self.assertEqual('done',self.job.acquire_gravel(64)['phase'])
        self.assertEqual([False,False,True],seen);self.assertFalse(self.job.busy)

    def test_resume_directory_sequence_continues_without_overwriting_previous_actions(self):
        for name in ('0007-craft','control-008','0009-smelt'):(self.root/name).mkdir()
        (self.root/'1000-result.json').write_text('{}')
        self.assertEqual(9,backend.next_sequence(self.root))

    def test_only_confirmed_clean_matching_operation_can_replan(self):
        inflight={'job_id':'j','sequence':3,'operation':'craft','args':[{'minecraft:stone':64}]}
        (self.root/'inflight.json').write_text(json.dumps(inflight))
        self.current['menu']={'type':'InventoryMenu','cursor':{'count':0},'slots':[{'count':0} for _ in range(46)]}
        with patch.object(backend,'read_fresh',return_value=self.current):
            self.job.record_recovery(self.client)
            self.assertTrue(self.job.recover(inflight)['safe_to_replan'])
            self.assertFalse(self.job.recover({**inflight,'sequence':4})['safe_to_replan'])
            self.current['menu']['cursor']['count']=1
            self.assertFalse(self.job.recover(inflight)['safe_to_replan'])

    def test_unknown_cursor_or_registered_resources_cannot_be_declared_clean(self):
        self.assertFalse(backend.clean_for_replan(self.current,self.client))
        self.current['menu']={'type':'InventoryMenu','cursor':{'count':0},'slots':[{'count':0} for _ in range(46)]}
        self.client.resource_cleanup={'box-1':lambda:None}
        self.assertFalse(backend.clean_for_replan(self.current,self.client))
        self.client.resource_cleanup={};self.current['phase']='running'
        self.assertFalse(backend.clean_for_replan(self.current,self.client))

    def test_incomplete_cleanup_does_not_get_retried_by_base_finish(self):
        with patch.object(backend,'read_fresh',return_value=self.current),patch('material_cleanup.run',return_value=[{'resource':'box','completed':False}]) as clean,patch.object(backend,'local_park') as park:
            with self.assertRaisesRegex(JobBlocked,'不重复清理'):self.job.finish()
        clean.assert_called_once();park.assert_not_called();self.client.finish.assert_not_called()
        self.client.request.assert_called_once_with('safe_logout')

    def stored_tools(self,state='stored',world='w',pos=None):
        path=self.root/'equipment'/'silk-tools.json';path.parent.mkdir()
        path.write_text(json.dumps({'world_session':world,'tools':[{'state':state,'pos':pos or [5,65,5]}]}))
        self.job.profile={'depots':[[5,65,5]]}

    def test_pit_exit_precedes_base_staging_and_tool_restore(self):
        self.stored_tools();calls=[]
        self.job.close_owned_menu=Mock(side_effect=lambda:calls.append('menu'))
        self.job.stage_near_base=Mock(side_effect=lambda depots:calls.append('base'))
        def finish():
            calls.append('finish')
            (self.root/'stock-safety.json').write_text(json.dumps({'lease':'lease-a','action':'KEEP_PVE_GUARD'}))
        self.client.finish=Mock(side_effect=finish)
        with patch.object(backend,'read_fresh',return_value=self.current),patch.object(backend,'leave_quarry',side_effect=lambda c,p:calls.append('shaft')),patch('material_cleanup.run',side_effect=lambda c:calls.append('restore') or []),patch.object(backend,'local_park',side_effect=lambda c:calls.append('park') or [0,110,0]):
            self.job.finish()
        self.assertEqual(['menu','shaft','base','restore','menu','park','finish'],calls)
        self.job.stage_near_base.assert_called_once_with([[5,65,5]])

    def test_returned_tools_need_no_base_round_trip(self):
        self.stored_tools(state='returned')
        self.client.finish=Mock(side_effect=lambda:(self.root/'stock-safety.json').write_text(json.dumps({'lease':'lease-a','action':'KEEP_PVE_GUARD'})))
        with patch.object(backend,'read_fresh',return_value=self.current),patch.object(backend,'leave_quarry'),patch('material_cleanup.run',return_value=[]),patch.object(backend,'local_park',return_value=[0,110,0]):self.job.finish()
        self.job.stage_near_base.assert_not_called()

    def test_unknown_tool_transfer_never_replays_cleanup_and_logs_out_once(self):
        self.stored_tools(state='storing')
        with patch.object(backend,'read_fresh',return_value=self.current),patch.object(backend,'leave_quarry') as exit,patch('material_cleanup.run') as clean:
            with self.assertRaisesRegex(JobBlocked,'不重复取放'):self.job.finish()
        exit.assert_called_once();clean.assert_not_called();self.job.stage_near_base.assert_not_called()
        self.client.request.assert_called_once_with('safe_logout')

    def test_unapproved_tool_depot_does_not_get_visited(self):
        self.stored_tools(pos=[999,65,999])
        with patch.object(backend,'read_fresh',return_value=self.current),patch.object(backend,'leave_quarry'),patch('material_cleanup.run') as clean:
            with self.assertRaisesRegex(JobBlocked,'批准范围'):self.job.finish()
        clean.assert_not_called();self.job.stage_near_base.assert_not_called();self.client.request.assert_called_once_with('safe_logout')

    def test_failed_shaft_exit_logs_out_without_visiting_remote_chest_or_rising(self):
        self.stored_tools()
        with patch.object(backend,'read_fresh',return_value=self.current),patch.object(backend,'leave_quarry',side_effect=JobBlocked('竖井被堵')),patch('material_cleanup.run') as clean,patch.object(backend,'local_park') as park:
            with self.assertRaisesRegex(JobBlocked,'竖井被堵'):self.job.finish()
        self.job.stage_near_base.assert_not_called();clean.assert_not_called();park.assert_not_called()
        self.client.request.assert_called_once_with('safe_logout')

    def test_lost_owner_after_exit_failure_is_not_logged_out(self):
        changed=copy.deepcopy(self.current);changed['control_revision']=4;changed['supervision_lease']['revision']=4;changed['last_request']='other';changed['id']='other'
        with patch.object(backend,'read_fresh',side_effect=[self.current,changed]),patch.object(backend,'leave_quarry',side_effect=JobBlocked('入口不通')):
            with self.assertRaises(JobPaused):self.job.finish()
        self.client.request.assert_not_called();self.assertEqual(3,self.client.rev)

    def test_low_health_during_failed_exit_also_writes_existing_lock(self):
        hurt=copy.deepcopy(self.current);hurt['health']=10
        with patch.object(backend,'read_fresh',side_effect=[self.current,hurt]),patch.object(backend,'leave_quarry',side_effect=JobBlocked('入口不通')),patch('safety_interlock.record_material_health_exit') as hold:
            with self.assertRaises(JobBlocked):self.job.finish()
        self.client.request.assert_called_once_with('safe_logout');hold.assert_called_once()
        self.assertEqual(10,hold.call_args.args[1]['health'])

    def test_fallback_logging_failure_does_not_prevent_owned_safety_logout(self):
        with patch.object(backend,'read_fresh',return_value=self.current),patch.object(backend,'leave_quarry',side_effect=JobBlocked('入口不通')),patch.object(backend,'write_json',side_effect=OSError('disk full')):
            with self.assertRaises(JobBlocked):self.job.finish()
        self.client.request.assert_called_once_with('safe_logout')


if __name__=='__main__':unittest.main()
