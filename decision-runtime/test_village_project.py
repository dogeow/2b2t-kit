import unittest,tempfile
from unittest.mock import Mock,patch
from pathlib import Path
from village_project import execute,owned_menu_result
from sheep_tending import eligible

class VillageProjectTests(unittest.TestCase):
    def test_queue_can_observe_only_the_existing_typed_storage_action(self):
        import json
        from village_queue import VillageQueue
        with tempfile.TemporaryDirectory()as d:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(d)
            command={'id':'exact','action':'take_packed_equipment'}
            directory=q.out/'exact';directory.mkdir()
            (q.out/'command.json').write_text(json.dumps(command));(directory/'intent.json').write_text(json.dumps(command))
            state={'screen':'ShulkerBoxScreen','interface_paused':False,'inventory_interface_paused':False,'menu':{'type':'ShulkerBoxMenu'}}
            self.assertTrue(q._expected_storage_observation(state))
            (directory/'error.json').write_text('{}');self.assertFalse(q._expected_storage_observation(state))
            (directory/'error.json').unlink();state['screen']='InventoryScreen'
            self.assertFalse(q._expected_storage_observation(state))

    def test_pending_opening_is_observable_without_adopting_a_foreign_or_filled_window(self):
        import json
        from copy import deepcopy
        from test_anvil_enchant_preview import book,empty
        from village_queue import VillageQueue
        import json
        with tempfile.TemporaryDirectory()as d:
            q=VillageQueue.__new__(VillageQueue);q.out=Path(d);q.world='w';q.lease={'job_session':'task'}
            command={'id':'merge','action':'anvil_enchant_combine','pos':[1,2,3]}
            folder=q.out/'merge';(folder/'actual-one-planned-anvil-output').mkdir(parents=True)
            for p,v in [(q.out/'command.json',command),(folder/'intent.json',command),
                        (folder/'actual-one-planned-anvil-output/combine.json',{'world_session':'w','task_session':'task','anvil':[1,2,3],'output_clicks':0,'pending':'open_owned_anvil'})]:p.write_text(json.dumps(v))
            state={'screen':'AnvilScreen','interface_paused':False,'inventory_interface_paused':False,
                   'menu':{'id':62,'type':'AnvilMenu','cursor':empty(),'slots':[empty(i)for i in range(39)]}}
            self.assertTrue(q._opening_planned_anvil(state))
            filled=deepcopy(state);filled['menu']['slots'][0]=book()
            self.assertFalse(q._opening_planned_anvil(filled))
            (folder/'error.json').write_text('{}');self.assertFalse(q._opening_planned_anvil(state))

    def test_exact_packed_equipment_stays_on_the_existing_owner(self):
        c=Mock();c.status.return_value={};expected={'item':'minecraft:enchanted_book','count':1}
        command={'action':'take_packed_equipment','profile':'profile.json','box_slot':14,'expected_stack':expected}
        with patch('village_project._safe'),patch('packed_equipment.take',return_value={'complete':True})as take:
            self.assertTrue(execute(c,command,Path('/tmp/project-dispatch-test'),lambda:{})['complete'])
        take.assert_called_once_with(c,'profile.json',14,expected);c.request.assert_not_called()

    def test_one_anvil_output_uses_exact_plan_cost_and_inputs(self):
        c=Mock();c.status.return_value={}
        command={'action':'anvil_enchant_combine','pos':[1,65,2],'left_slot':3,'right_slot':4,
                 'expected_left':{},'expected_right':{},'expected_enchantments':{'minecraft:mending':1},'expected_cost':2}
        with patch('village_project._safe'),patch('anvil_enchant_combine.run',return_value={'complete':True})as combine:
            self.assertTrue(execute(c,command,Path('/tmp/project-dispatch-test'),lambda:{})['complete'])
        combine.assert_called_once_with(c,[1,65,2],3,4,{}, {},{'minecraft:mending':1},2,
                                       Path('/tmp/project-dispatch-test/actual-one-planned-anvil-output'),face='up')
        c.request.assert_not_called()

    def test_zero_xp_anvil_preview_uses_the_same_owner_and_exact_bound_inputs(self):
        c=Mock();c.status.return_value={}
        command={'action':'anvil_enchant_preview','pos':[1,65,2], 'left_slot':3,'right_slot':4,
                 'expected_left':{'item':'minecraft:wooden_shovel','count':1},
                 'expected_right':{'item':'minecraft:enchanted_book','count':1},
                 'expected_enchantments':{'minecraft:mending':1}}
        with patch('village_project._safe'),patch('anvil_enchant_preview.run',return_value={'complete':True,'output_clicks':0})as preview:
            result=execute(c,command,Path('/tmp/bounded-anvil-preview-test'),lambda:{})
        self.assertEqual(0,result['output_clicks'])
        preview.assert_called_once_with(c,[1,65,2],3,4,command['expected_left'],command['expected_right'],
                                        command['expected_enchantments'],Path('/tmp/bounded-anvil-preview-test/actual-zero-xp-anvil-preview'),face='south')
        c.request.assert_not_called()

    def test_unknown_anvil_preview_does_not_run_registered_exit(self):
        c=Mock(server='simpcraft.com');c.status.return_value={'dimension':'minecraft:overworld'}
        profile={'server':'simpcraft.com','dimension':'minecraft:overworld','workbench':[1,65,3],
                 'workbench_entry':[{'kind':'walk','target':[1.5,65,4.5]}],
                 'workbench_exit':[{'kind':'walk','target':[1.5,65,5.5]}]}
        command={'action':'anvil_enchant_preview','profile':'/tmp/anvil-profile','pos':[1,65,2],
                 'left_slot':3,'right_slot':4,'expected_left':{},'expected_right':{},'expected_enchantments':{}}
        with patch('village_project._safe'),patch('pathlib.Path.read_text',return_value=__import__('json').dumps(profile)),patch('warehouse_audit_cli._RegisteredRoute')as route,patch('anvil_enchant_preview.run',side_effect=RuntimeError('original input unknown')):
            with self.assertRaisesRegex(RuntimeError,'original input unknown'):execute(c,command,Path('/tmp/test-preview'),lambda:{})
        route.return_value.route.assert_called_once_with('workbench_entry')
    def test_only_sdk_owned_current_window_is_published_for_storage_and_workbench(self):
        with tempfile.TemporaryDirectory()as temporary:
            c=Mock(world='w',task='j',out=Path(temporary)/'control',owned_material_menu=3)
            c.status.return_value={'menu':{'id':3,'type':'ChestMenu'},'supervision_lease':{'id':'l'},'control_revision':9}
            result=owned_menu_result(c,{'actual_held':4});p=Path(temporary)/'owned-material-menu.json'
            self.assertEqual(3,result['owned_menu']['id']);self.assertTrue(p.exists())
            c.owned_material_menu=None;self.assertNotIn('owned_menu',owned_menu_result(c,{}));self.assertFalse(p.exists())
    def test_nursery_uses_the_existing_owner_and_cannot_dispatch_an_unrelated_operation(self):
        c=Mock();c.world='world';q={'health':20};command={'action':'grow_village_supply_tree','root':[1,63,2],'min':[0,62,0],'max':[8,88,8]}
        def run(owner,*args):
            self.assertEqual('world',owner.world);self.assertIs(q,owner.status())
            with self.assertRaises(ValueError):owner.native('portal_build')
            owner.native('select_item',item='minecraft:dark_oak_sapling');return {'complete':True}
        with patch('village_project._safe'),patch('village_nursery.grow',side_effect=run):
            self.assertTrue(execute(c,command,'.',lambda:q)['complete'])
        c.checked.assert_called_once_with('select_item',item='minecraft:dark_oak_sapling')
    def test_verified_under_roof_stand_reuses_existing_chest_kernel_and_same_client(self):
        c=Mock();command={'action':'open_chest_from_pose','pos':[10,64,20],'pose':[8.5,64,20.5],'face':'west'}
        with patch('village_project._safe'),patch('container_access.open_chest_from_pose',return_value={'menu':{'type':'ChestMenu'}})as opened:
            result=execute(c,command,'.',lambda:{})
        opened.assert_called_once_with(c,[10,64,20],[8.5,64,20.5],'west',allow_empty=False)
        self.assertEqual('ChestMenu',result['menu']['type']);c.request.assert_not_called()
    def test_explicit_barrel_kind_reaches_grounded_opener_without_extra_controller(self):
        c=Mock();command={'action':'open_chest_from_pose','pos':[10,71,20],'pose':[10.5,71,18.5],'face':'north','block_id':'minecraft:barrel','allow_empty':True}
        with patch('village_project._safe'),patch('container_access.open_chest_from_pose',return_value={'menu':{'type':'ChestMenu'}})as opened:
            execute(c,command,'.',lambda:{})
        opened.assert_called_once_with(c,[10,71,20],[10.5,71,18.5],'north',allow_empty=True,block_id='minecraft:barrel')
        c.request.assert_not_called()

    def test_opt_in_hover_feeding_reuses_same_owner_and_exact_pose_scope(self):
        c=Mock(world='w');bounds={'min':[0,64,0],'max':[8,67,8]}
        command={'action':'feed_village_founders','quotas':{'p':3},'min':[0,64,0],'max':[8,67,8],'pose_bounds':bounds,'hover_approach':True}
        with patch('village_project._safe'),patch('village_feeding.feed',return_value={'complete':True})as fed:
            result=execute(c,command,Path('.'),lambda:{})
        self.assertTrue(result['complete']);self.assertEqual({'pose_bounds':bounds,'hover_approach':True},fed.call_args.kwargs)
        self.assertEqual('w',fed.call_args.args[0].world);c.request.assert_not_called()

    def test_storage_audit_uses_current_owner_without_requesting_any_item_transfers(self):
        c=Mock();positions=[[10,64,20]];items=['minecraft:hopper','minecraft:iron_block']
        observation={'complete':True,'counts':{'minecraft:hopper':5,'minecraft:iron_block':0}}
        with patch('village_project._safe'),patch('material_depots.audit',return_value=observation)as audited,patch('material_depots.exchange')as exchanged:
            result=execute(c,{'action':'audit_depots','positions':positions,'items':items},'.',lambda:{})
        self.assertIs(observation,result);audited.assert_called_once_with(c,positions,items)
        exchanged.assert_not_called();c.transfer.assert_not_called();c.request.assert_not_called()
    def test_a_full_backpack_cannot_start_breaking_a_tree(self):
        c=Mock();q={'inventory':[{'slot':i,'item':'minecraft:stick','count':1}for i in range(36)]}
        with patch('village_project._safe'),self.assertRaises(RuntimeError):
            execute(c,{'action':'native','op':'chop','params':{'tree_root':[1,64,1]}},'.',lambda:q)
        c.request.assert_not_called()
    def test_actual_wool_pickup_is_dispatched_by_the_same_owner(self):
        c=Mock();c.request.return_value={'phase':'done'}
        q={'health':20,'food':20,'guard_armed':True,'guard_pve_only':True,'manual_movement':False}
        with tempfile.TemporaryDirectory()as out,patch('village_project._safe'):
            execute(c,{'action':'native','op':'collect_item','params':{'expected_uuid':'drop','expected_item':'minecraft:white_wool','expected_count':2}},Path(out),lambda:q)
        c.request.assert_called_once_with('collect_item',expected_uuid='drop',expected_item='minecraft:white_wool',expected_count=2)
    def test_elevated_projection_seed_keeps_the_same_owner_and_native_exact_target_guards(self):
        params={'target':[10,89,20],'placement_key':'current-projection',
                'expected_item':'minecraft:cobblestone','expected_state':'Block{minecraft:cobblestone}'}
        c=Mock();checkpoint=Mock(return_value={'health':20})
        with patch('village_project._safe')as safe:
            execute(c,{'action':'native','op':'projection_air_seed','params':params},'.',checkpoint)
        safe.assert_called_once_with(checkpoint.return_value)
        c.request.assert_called_once_with('projection_air_seed',**params)
        c.reset_mock()
        with patch('village_project._safe',side_effect=RuntimeError('Manual takeover')):
            with self.assertRaisesRegex(RuntimeError,'Manual takeover'):
                execute(c,{'action':'native','op':'projection_air_seed','params':params},'.',checkpoint)
        c.request.assert_not_called()
    def test_unrelated_portal_or_chat_operations_cannot_enter_the_village_owner(self):
        # Strict projection import requires the material owner to release its
        # lease first; never route it through MaterialClient's task envelope.
        for op in ('portal_build','connect_server','say','projection_load','projection_load_rollback'):
            c=Mock()
            with patch('village_project._safe'),self.assertRaises(ValueError):execute(c,{'action':'native','op':op},'.',lambda:{})
            c.request.assert_not_called()
    def test_one_coat_requires_current_adult_unnamed_visible_ready_sheep(self):
        row={'type':'minecraft:sheep','alive':True,'is_baby':False,'has_custom_name':False,'visible':True,'pos':[.5,64,1.5],
             'sheep':{'ready_for_shearing':True,'sheared':False}}
        self.assertTrue(eligible(row,[.5,64,.5]))
        for change in ({'is_baby':True},{'has_custom_name':True},{'visible':False},{'type':'minecraft:cow'},
                       {'sheep':{'ready_for_shearing':False,'sheared':True}},{'pos':[20,64,1.5]}):
            self.assertFalse(eligible({**row,**change},[.5,64,.5]))

if __name__=='__main__':unittest.main()
