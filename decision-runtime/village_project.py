"""Shared bounded actions for the village project; one caller retains the Kit lease."""
from pathlib import Path
import json
from material_jobs.acquisition import _safe

NATIVE_OPS=frozenset(('scan','snapshot','approach_block','navigate','walk','select_item','interact','interact_entity',
    'close_menu','recover_shulker','projection_model','decision_screenshot','material_slaughter_attack','collect_item','slot_click',
    'merchant_select_trade','mine_block','use_item','look','bucket_fill','bucket_place','chop','scan_trees','scan_snow_biomes',
    'projection_audit','projection_start','professional_print','projection_batch_set','projection_batch_clear',
    'recover_boat','villager_bread_drop','projection_air_seed'))

from owned_material_menu import owned_menu_result


def execute(c,command,directory,checkpoint):
    _safe(checkpoint());kind=command['action'];out=Path(directory)
    if kind in ('harness_iron_next','harness_iron_stage','harness_prepare_space'):
        from harness_runtime import iron_plan,run_iron_stage,prepare_space
        if kind=='harness_iron_next':return iron_plan(c,out)
        if kind=='harness_prepare_space':return prepare_space(c,command['reserve_slots'],out)
        return run_iron_stage(c,command['plan'],out,checkpoint)
    if kind=='native':
        op=command['op']
        if op not in NATIVE_OPS:raise ValueError('Native operation is outside this village project')
        if op=='chop':
            from material_plan import inventory_counts
            from village_supply_preflight import prepare_chop_inventory
            prepare_chop_inventory(c,checkpoint)
            q=checkpoint();main=[r for r in q.get('inventory',[])if 0<=r.get('slot',99)<36]
            if len(main)!=36 or sum(not r.get('count')for r in main)<3:
                raise RuntimeError('Store spare supplies first: native tree harvest reserves three empty main slots')
            if inventory_counts(q)['minecraft:dirt']<1:
                raise RuntimeError('One recoverable dirt work platform is required before native tree harvest')
            if command.get('params',{}).get('tree_root')is not None:
                from material_jobs.fixed_tree_ground import prepare
                prepare(c,checkpoint)
        return c.request(op,**command.get('params',{}))
    if kind=='repair_tool_material':
        from tool_material_repair import repair
        result=repair(c,command['pos'],out/'tool-material-repair',minimum_durability=command.get('minimum_durability',1000),max_cost=command.get('max_cost',4))
        return owned_menu_result(c,result)
    if kind=='anvil_enchant_preview':
        from anvil_enchant_preview import run
        profile=json.loads(Path(command['profile']).read_text())if command.get('profile')else None
        route=None
        if profile is not None:
            from material_jobs.profile import point
            from material_jobs.protocol import server_key
            import math
            state=c.status()
            if (server_key(profile.get('server'))!=server_key(c.server)
                    or profile.get('dimension')!=state.get('dimension')
                    or not point(profile.get('workbench'))or not point(command.get('pos'))
                    or math.dist(profile['workbench'],command['pos'])>4
                    or not profile.get('workbench_entry')or not profile.get('workbench_exit')):
                raise ValueError('Preview anvil must use its current registered local workshop route')
            from warehouse_audit_cli import _RegisteredRoute
            route=_RegisteredRoute(c,profile);route.route('workbench_entry')
        result=run(c,command['pos'],command['left_slot'],command['right_slot'],
                   command['expected_left'],command['expected_right'],command['expected_enchantments'],
                   out/'actual-zero-xp-anvil-preview',face=command.get('face','south'))
        # A failed/unknown preview keeps its original window and inputs. It
        # never enters this return path or dispatches a cleanup from finally.
        if route is not None:route.route('workbench_exit')
        return owned_menu_result(c,result)
    if kind=='anvil_enchant_combine':
        from anvil_enchant_combine import run
        result=run(c,command['pos'],command['left_slot'],command['right_slot'],
                   command['expected_left'],command['expected_right'],command['expected_enchantments'],
                   command['expected_cost'],out/'actual-one-planned-anvil-output',face=command.get('face','up'))
        return owned_menu_result(c,result)
    if kind=='hot_runtime_update':
        from hot_update import inspect_engine,install_and_reload
        artifact=inspect_engine(command['jar'])
        if artifact['sha256']!=command['sha256']or artifact['version']!=command['version']:
            raise ValueError('Exact verified engine artifact required before hot loading')
        return install_and_reload(c,command['jar'])
    if kind=='build_village_stage':
        from village_projection import build
        return build(c,command['table'],out,checkpoint,command['label'])
    if kind=='print_reachable_village_stations':
        from reach_printing import CurrentOwner,print_stations
        table=json.loads(Path(command['table']).read_text())
        return print_stations(CurrentOwner(c,out),table,command['stations'],
                              out/'reachable-print.json',checkpoint,limit=command.get('limit',32))
    if kind in('grow_village_supply_tree','feed_village_founders'):
        class Owner:
            world=c.world
            def status(self):return checkpoint()
            def native(self,op,**params):
                _safe(checkpoint())
                if op not in NATIVE_OPS:raise ValueError('Nursery/feeding cannot use an unrelated operation')
                return c.checked(op,**params)
        owner=Owner()
        if kind=='grow_village_supply_tree':
            from village_nursery import grow
            return grow(owner,command['root'],command['min'],command['max'],out/'nursery.json')
        from village_feeding import feed
        options={'pose_bounds':command['pose_bounds']}if 'pose_bounds'in command else{}
        if 'hover_approach'in command:options['hover_approach']=command['hover_approach']
        if 'ground_standoff'in command:options['ground_standoff']=command['ground_standoff']
        return feed(owner,c.root,command['quotas'],out/'feeding.json',command['min'],command['max'],**options)
    if kind in ('exchange','audit_depots'):
        from material_depots import exchange,audit
        if command.get('profile'):
            profile=json.loads(Path(command['profile']).read_text())
            saved=getattr(c,'village_storage_access',None)
            if saved is None:
                from material_jobs.recorded_storage_access import bind
                c.village_storage_access=bind(c,profile,Path(c.out)/'village-recorded-storage',checkpoint)
            elif saved.profile!=profile:
                raise RuntimeError('Original registered storage profile changed during its live route')
        if kind=='audit_depots':return audit(c,command['positions'],command['items'])
        return exchange(c,command['positions'],deposit=command.get('deposit'),withdraw=command.get('withdraw'))
    if kind=='open_shulker':
        from packed_supplies import open_box
        return owned_menu_result(c,open_box(c,command['pos'],'ShulkerBoxMenu',allow_empty=command.get('allow_empty',False)))
    if kind=='take_packed_materials':
        from packed_supplies import open_box,choose_box,take_box
        from material_plan import inventory_counts
        profile=json.loads(Path(command['profile']).read_text());ender=profile['ender_chest'];pad=profile['shulker_pad']
        q=open_box(c,ender,'ChestMenu');chosen=choose_box(q['menu']['slots'][:27],command['targets'],inventory_counts(q))
        c.checked('close_menu')
        if chosen is None:return {'complete':False,'reason':'No currently observed ender shulker contains requested stock'}
        result=take_box(c,ender,pad,chosen[1],command['targets'])
        return {'complete':result is None or result.get('stage')=='returned','packed_transfer':result}
    if kind=='take_packed_equipment':
        from packed_equipment import take
        return owned_menu_result(c,take(c,command['profile'],command['box_slot'],command['expected_stack']))
    if kind=='transfer':
        result={'actual_held':c.transfer(command['item'],command['target'],deposit=bool(command.get('deposit')))}
        return owned_menu_result(c,result)
    if kind=='open_chest_from_pose':
        from container_access import open_chest_from_pose
        options={'block_id':command['block_id']}if 'block_id'in command else{}
        if 'allow_hover'in command:options['allow_hover']=command['allow_hover']
        if 'allow_top_face'in command:options['allow_top_face']=command['allow_top_face']
        result=open_chest_from_pose(c,command['pos'],command['pose'],command['face'],allow_empty=command.get('allow_empty',False),**options)
        return owned_menu_result(c,result)
    if kind=='open_brewing_stand':
        from brewing_access import open_registered
        return owned_menu_result(c,open_registered(c,command['pos'],command['pose'],command['face']))
    if kind=='open_workbench':
        from goal_workflow import open_workbench
        open_workbench(c,command['pos']);return owned_menu_result(c,c.status())
    if kind=='breed_sheep':
        from animal_breed import run
        request=command['request']
        if request['species']!='minecraft:sheep':raise ValueError('This stage breeds sheep only')
        return run(c,request,out/'actual-sheep-breeding',checkpoint)
    if kind=='shear_sheep':
        from sheep_tending import shear_one
        return shear_one(c,command['uuid'],out/'actual-shearing-and-immediate-pickup',checkpoint)
    if kind=='place_bed':
        from village_beds import place
        return place(c,command['foot'],command['facing'],out/'actual-directional-bed',checkpoint)
    if kind=='boat_place':
        from boat_transport import place
        return place(c,command['support'],command['stand'],command['item'],out/'actual-one-boat',checkpoint,
                     allowed_passengers=command.get('allowed_passengers',()))
    if kind=='boat_attach':
        from boat_transport import attach
        return attach(c,command['uuid'],out/'actual-one-lead',checkpoint,
                      expected_passengers=command.get('expected_passengers',()))
    if kind=='tow_villager_boat':
        from boat_towing import run
        return run(c,command['uuid'],command['passengers'],command['route'],command['home'],out/'actual-villager-towing',checkpoint,
                   max_radius=command.get('max_radius',4096),resume=command.get('resume'))
    if kind=='lure_sheep':
        from animal_lure import run
        return run(c,command['uuid'],command['target'],command['scene'],out/'actual-sheep-lure',checkpoint,species='minecraft:sheep')
    if kind=='lift':
        from material_jobs.navigation import lift_for_travel
        return lift_for_travel(c)
    if kind=='travel_to':
        from material_jobs.resource_trip import travel
        target=command['target']
        if any(abs(target[i])>=799968 for i in (0,2)):raise ValueError('Village trip target is outside the known server border margin')
        return travel(c,target,out/'actual-bounded-village-trip',checkpoint,
            home=[761019.5,110.2,797850.5],max_radius=command.get('max_radius',4096),
            destination_name=command.get('name','村民来源实测'),long_transit=True)
    if kind=='harvest_registered_wheat':
        from material_jobs.native_wheat import run
        registry=Path(command['registry']).resolve()
        if not registry.is_relative_to((Path(c.root)/'farms').resolve()):raise ValueError('Original Kit farm registration required')
        saved=json.loads(registry.read_text());layout=saved['scope']['layout']
        if saved['scope']['server']!=c.server.removesuffix(':25565')or layout['crop']!='wheat':raise ValueError('Wrong registered field')
        return run(c,registry,layout,command['cells'],out/'actual-native-wheat-harvest-and-reseed',checkpoint)
    if kind=='merchant_open':
        from villager_trading import open
        return open(c,command['actor'],out/'actual-normal-merchant-open')
    if kind=='merchant_buy_one':
        from villager_trading import buy_one
        return buy_one(c,command['index'],out/'actual-one-trade')
    if kind=='merchant_lock_wanted':
        from villager_trading import lock_wanted
        return lock_wanted(c,command['targets'],out/'actual-one-wanted-lock',
                           keep=command.get('keep'),max_emeralds=command.get('max_emeralds',64),
                           max_paper=command.get('max_paper',64))
    if kind=='smelt_material':
        from material_jobs.processing import smelt
        profile=json.loads(Path(command['profile']).read_text())
        return smelt(c,command['recipe'],command['target'],profile,out,checkpoint)
    if kind=='manufacture':
        from material_manufacture import manufacture,inventory_plan
        from material_plan import inventory_counts
        from recipe_catalog import RecipeCatalog
        profile=json.loads(Path(command['profile']).read_text())
        catalog=RecipeCatalog(profile['recipe_jar']);q=c.status()
        if(q['menu']['type']=='InventoryMenu'and inventory_plan(catalog,command['targets'],inventory_counts(q))is None):
            from goal_workflow import open_workbench
            bench=(profile.get('outdoor_workbench')or{}).get('pos')or profile['workbench']
            open_workbench(c,bench)
        return owned_menu_result(c,manufacture(c,catalog,command['targets']))
    raise ValueError('Unsupported bounded village stage')
