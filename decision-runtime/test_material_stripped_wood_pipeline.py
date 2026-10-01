"""Offline owned-cell conservation/no-replay tests; never creates a game client."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs import stripped_wood_pipeline as wood
from material_jobs.protocol import JobPaused


class Client:
    def __init__(self, directory, stock=None):
        self.world='world';self.out=Path(directory);self.held=dict(stock or {})
        self.depot={};self.cell='AIR';self.selected=0;self.clock=1000
        self.axe={'slot':3,'item':'minecraft:diamond_axe','count':1,'durability':100,
                  'damage':1461,'max_damage':1561,'enchantments':{'minecraft:silk_touch':1}}
        self.health=20;self.entities=[];self.calls=[];self.strip_unknown=False
        self.pickup_unknown=False;self.support_changed=False;self.headroom=False
        self.unloaded=False;self.raw_after_pickup=None;self.axe_after_pickup=False
    def status(self):
        self.clock+=500
        rows=[{'slot':i,'item':item,'count':self.held.get(item,0),'max_stack':64}
              for i,item in enumerate((wood.RAW,wood.STRIPPED,wood.OUTPUT))]
        rows.append(copy.deepcopy(self.axe))
        rows.extend({'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(4,36))
        return {'world_session':self.world,'connected':True,'server':'example',
                'dimension':'minecraft:overworld','health':self.health,'food':20,
                'guard_armed':True,'guard_pve_only':True,'manual_movement':False,
                'under_water':False,'time':self.clock,'inventory':rows,
                'selected_slot':self.selected,'hand':copy.deepcopy(rows[self.selected]),
                'entities':copy.deepcopy(self.entities),'menu':{'cursor':{'count':0}}}
    def checked(self, operation, **args):
        self.calls.append((operation,args))
        assert operation=='select_item'
        self.selected=args.get('slot', next(i for i,item in enumerate((wood.RAW,wood.STRIPPED,wood.OUTPUT,self.axe['item']))
                                               if item==args['item']))
        return {'phase':'done'}
    def request(self, operation, **args):
        self.calls.append((operation,args))
        if operation=='scan':
            if self.unloaded:return {'phase':'waiting','world_session':self.world,'blocks':[]}
            rows=[{'pos':[10,63,10],'state':'Block{minecraft:cobblestone}' if not self.support_changed else 'Block{minecraft:dirt}',
                   'solid':True,'fluid':False,'block_entity':False}]
            if self.cell!='AIR':rows.append({'pos':[10,64,10],'state':self.cell,'solid':True,'fluid':False,'block_entity':False})
            if self.headroom:rows.append({'pos':[10,65,10],'state':'Block{minecraft:stone}','solid':True,'fluid':False,'block_entity':False})
            return {'phase':'done','world_session':self.world,'blocks':rows}
        if operation=='interact' and args['pos']==[10,63,10]:
            assert self.cell=='AIR' and self.selected==0
            assert args['face']=='up' and args['expected_state']=='Block{minecraft:cobblestone}'
            self.cell=wood.RAW_STATE;self.held[wood.RAW]-=1
        elif operation=='interact':
            assert args['pos']==[10,64,10] and args['expected_state']==wood.RAW_STATE and self.selected==3
            self.cell=wood.STRIPPED_STATE;self.axe['damage']+=1;self.axe['durability']-=1
            if self.strip_unknown:return {'phase':'waiting'}
        elif operation=='mine_block':
            assert args['pos']==[10,64,10] and args['expected_state']==self.cell and self.selected==3
            returned=wood.RAW if self.cell==wood.RAW_STATE else wood.STRIPPED
            self.cell='AIR';self.axe['damage']+=1;self.axe['durability']-=1
            self.entities=[{'uuid':'new-owned-drop','type':'minecraft:item','pos':[10.5,64.5,10.5],
                            'stack':{'item':returned,'count':1}}]
        elif operation=='collect_item':
            assert args['expected_uuid']=='new-owned-drop' and args['expected_count']==1
            if self.pickup_unknown:return {'phase':'waiting'}
            self.held[args['expected_item']]=self.held.get(args['expected_item'],0)+1;self.entities=[]
            if self.raw_after_pickup is not None:self.held[wood.RAW]=self.raw_after_pickup
            if self.axe_after_pickup:self.axe['enchantments']={'minecraft:efficiency':5}
        else:raise AssertionError(operation)
        return {'phase':'done'}


class Catalog:
    def candidates(self, output, stock, width):
        return [{'recipe_id':'stripped_cherry_wood','output':wood.OUTPUT,'produces':3,'width':2,
                 'ingredients':{wood.STRIPPED:[1,2,3,4]}}]


class Backend:
    def __init__(self,c,profile):
        self.client=c;self.profile=profile;self.request={'mode':'item'}
        self.crafting_catalog=Catalog();self.calls=[]
    def prepare_travel(self):self.calls.append(('prepare',))
    def stage_near_base(self,positions):self.calls.append(('stage',positions))
    def fetch(self,targets):
        self.calls.append(('fetch',targets))
        for item,target in targets.items():
            take=min(max(0,target-self.client.held.get(item,0)),self.client.depot.get(item,0))
            self.client.held[item]=self.client.held.get(item,0)+take;self.client.depot[item]=self.client.depot.get(item,0)-take
        missing={i:n-self.client.held.get(i,0) for i,n in targets.items() if self.client.held.get(i,0)<n}
        return {'phase':'waiting' if missing else 'done','missing':missing}
    def craft(self,targets):
        self.calls.append(('craft',targets))
        target=targets[wood.OUTPUT];rounds=(target-self.client.held.get(wood.OUTPUT,0))//3
        self.client.held[wood.STRIPPED]-=rounds*4;self.client.held[wood.OUTPUT]=target
        return {'phase':'done'}


def audit(c,depots,items):
    return {'complete':True,'world_session':c.world,'counts':{i:c.depot.get(i,0) for i in items}}


def exchange(c,depots,deposit):
    for item,keep in deposit.items():
        moved=max(0,c.held.get(item,0)-keep)
        c.held[item]-=moved;c.depot[item]=c.depot.get(item,0)+moved
    return {'complete':True}


class StrippedWoodPipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.profile={'server':'example','dimension':'minecraft:overworld','depots':[[1,64,2]],
                      'stripped_wood_worksite':{'owned':True,'cell':[10,64,10],'support_state':'Block{minecraft:cobblestone}'}}
        for p in (patch.object(wood,'audit',side_effect=audit),patch.object(wood,'exchange',side_effect=exchange),
                  patch.object(wood,'approach_faces',return_value='up'),patch.object(wood.time,'sleep',return_value=None)):
            p.start();self.addCleanup(p.stop)
    def client(self,stock=None):
        c=Client(self.base,stock);c.stripped_wood_backend=Backend(c,self.profile);return c
    def run_pipeline(self,c,target=57):
        return wood.run(c,self.profile,wood.OUTPUT,target,self.base/'run',lambda:None)
    def journal(self):return json.loads((self.base/'run'/'stripped-wood-pipeline.json').read_text())
    def mutations(self,c):return [op for op,args in c.calls if op!='scan']

    def test_owned_worksite_requires_dry_plain_support_and_explicit_integer_coordinates(self):
        self.assertEqual([10,63,10],wood.worksite(self.profile)['support'])
        for changes in ({'owned':False},{'cell':[10,64.0,10]},{'cell':[True,64,10]},
                        {'support':[10,62,10]},{'support_state':'Block{minecraft:chest}'},
                        {'support_state':'Block{minecraft:oak_log}[axis=y]'}):
            profile=copy.deepcopy(self.profile);profile['stripped_wood_worksite'].update(changes)
            self.assertIsNone(wood.worksite(profile))

    def test_missing_worksite_and_existing_user_log_are_preserved_without_mutations(self):
        c=self.client({wood.RAW:1});self.profile.pop('stripped_wood_worksite')
        self.assertEqual('wait_worksite',self.run_pipeline(c)['code']);self.assertEqual([],self.mutations(c))
        self.profile['stripped_wood_worksite']={'owned':True,'cell':[10,64,10],'support_state':'Block{minecraft:cobblestone}'}
        c.cell=wood.RAW_STATE
        self.assertEqual('wait_worksite',self.run_pipeline(c)['code']);self.assertEqual([],self.mutations(c))

    def test_support_headroom_or_unloaded_world_refuses_before_placement(self):
        for attribute in ('support_changed','headroom','unloaded'):
            with self.subTest(attribute=attribute):
                c=self.client({wood.RAW:1});setattr(c,attribute,True)
                with self.assertRaises(JobPaused):self.run_pipeline(c)
                self.assertEqual([],self.mutations(c))

    def test_normal_supported_cycle_conserves_one_raw_log_and_restores_own_cell(self):
        c=self.client({wood.RAW:1})
        result=self.run_pipeline(c)
        self.assertEqual('stripped_log_produced',result['code']);self.assertTrue(result['work_cell_restored'])
        self.assertEqual('AIR',c.cell);self.assertEqual(0,c.held[wood.RAW]);self.assertEqual(1,c.held[wood.STRIPPED])
        self.assertNotIn(wood.OUTPUT,c.held);self.assertEqual({},getattr(c,'resource_cleanup',{}))
        self.assertEqual(2,self.mutations(c).count('interact'));self.assertEqual(1,self.mutations(c).count('mine_block'))
        self.assertEqual(1,self.mutations(c).count('collect_item'))
        job=self.journal();self.assertIsNone(job['owned_cell']);self.assertIsNone(job['pending'])
        event=next(e for e in job['events'] if e['kind']=='stripped_owned')
        self.assertIn('not a dedicated packet ACK',event['proof_scope'])
        self.assertEqual({'minecraft:silk_touch':1},event['axe']['enchantments'])

    def test_unknown_axe_use_retains_confirmed_ownership_and_never_replays_or_mines(self):
        c=self.client({wood.RAW:1});c.strip_unknown=True
        self.assertEqual('wait_receipt',self.run_pipeline(c)['code'])
        job=self.journal();self.assertEqual('strip_owned',job['pending']['kind'])
        self.assertTrue(job['owned_cell']['confirmed']);self.assertEqual(wood.RAW_STATE,job['owned_cell']['state'])
        before=list(c.calls)
        self.assertEqual('wait_receipt',self.run_pipeline(c)['code']);self.assertEqual(before,c.calls)
        callback=next(iter(c.resource_cleanup.values()))
        with self.assertRaises(JobPaused):callback()
        self.assertNotIn('mine_block',self.mutations(c))

    def pause_after_known_placement(self,c):
        original=c.request
        def request(operation,**args):
            result=original(operation,**args)
            if operation=='interact' and args['pos']==[10,63,10]:c.axe['durability']=0
            return result
        c.request=request
        self.assertEqual('wait_tool',self.run_pipeline(c)['code'])
        self.assertIsNone(self.journal()['pending']);self.assertTrue(self.journal()['owned_cell']['confirmed'])
        c.axe['durability']=100

    def test_confirmed_raw_ownership_resumes_only_cleanup_and_restores_actual_raw_drop(self):
        c=self.client({wood.RAW:1});self.pause_after_known_placement(c)
        self.assertEqual('owned_cell_restored',self.run_pipeline(c)['code'])
        self.assertEqual('AIR',c.cell);self.assertEqual(1,c.held[wood.RAW])
        self.assertEqual(0,c.held.get(wood.STRIPPED,0));self.assertEqual(1,self.mutations(c).count('interact'))
        self.assertEqual(1,self.mutations(c).count('mine_block'))

    def test_cleanup_refuses_a_changed_user_block_in_confirmed_owned_cell(self):
        c=self.client({wood.RAW:1});self.pause_after_known_placement(c)
        c.cell='Block{minecraft:oak_log}[axis=y]';before=list(c.calls)
        with self.assertRaises(JobPaused):self.run_pipeline(c)
        self.assertEqual(c.cell,'Block{minecraft:oak_log}[axis=y]')
        self.assertNotIn('mine_block',[op for op,args in c.calls[len(before):]])

    def test_unknown_single_drop_pickup_is_never_replayed_or_credited(self):
        c=self.client({wood.RAW:1});c.pickup_unknown=True
        with self.assertRaises(JobPaused):self.run_pipeline(c)
        self.assertEqual('pickup_owned',self.journal()['pending']['kind'])
        self.assertEqual(0,c.held.get(wood.STRIPPED,0));before=list(c.calls)
        self.assertEqual('wait_receipt',self.run_pipeline(c)['code']);self.assertEqual(before,c.calls)

    def test_changed_axe_metadata_after_mining_retains_uncertainty(self):
        c=self.client({wood.RAW:1});c.axe_after_pickup=True
        with self.assertRaises(JobPaused):self.run_pipeline(c)
        self.assertEqual('pickup_owned',self.journal()['pending']['kind'])
        self.assertIsNotNone(self.journal()['owned_cell'])

    def test_final_raw_delta_divergence_blocks_any_next_conversion(self):
        c=self.client({wood.RAW:2});c.raw_after_pickup=0
        self.assertEqual('wait_receipt',self.run_pipeline(c)['code'])
        self.assertEqual('verify_conversion',self.journal()['pending']['kind']);before=list(c.calls)
        self.assertEqual('wait_receipt',self.run_pipeline(c)['code']);self.assertEqual(before,c.calls)

    def test_actual_four_to_three_craft_uses_absolute_target_and_keeps_goal_rounding_surplus(self):
        c=self.client({wood.STRIPPED:4})
        result=self.run_pipeline(c,2)
        self.assertEqual('batch_crafted',result['code']);self.assertEqual(3,c.held[wood.OUTPUT])
        self.assertEqual(0,c.held[wood.STRIPPED]);self.assertEqual(0,c.depot.get(wood.OUTPUT,0))
        self.assertIn(('craft',{wood.OUTPUT:3}),c.stripped_wood_backend.calls)
        result=self.run_pipeline(c,2)
        self.assertEqual('done',result['phase']);self.assertEqual(2,c.depot[wood.OUTPUT])
        self.assertEqual(1,c.held[wood.OUTPUT]);self.assertEqual('approved_depot_total',result['target_scope'])

    def test_unknown_craft_or_wrong_recipe_never_calls_axe_or_fake_deposit(self):
        c=self.client({wood.STRIPPED:4})
        c.stripped_wood_backend.craft=lambda targets:{'phase':'waiting'}
        self.assertEqual('wait_receipt',self.run_pipeline(c)['code']);before=len(c.stripped_wood_backend.calls)
        self.assertEqual('wait_receipt',self.run_pipeline(c)['code'])
        self.assertEqual(before,len(c.stripped_wood_backend.calls));self.assertEqual([],self.mutations(c))
        c=self.client({wood.STRIPPED:4});c.stripped_wood_backend.crafting_catalog=None
        self.assertEqual('wait_recipe',self.run_pipeline(c)['code'])

    def test_wrong_craft_delta_or_unconserved_deposit_retains_pending(self):
        c=self.client({wood.STRIPPED:4})
        def wrong_craft(targets):
            c.held[wood.OUTPUT]=3;c.held[wood.STRIPPED]=1;return {'phase':'done'}
        c.stripped_wood_backend.craft=wrong_craft
        self.assertEqual('wait_receipt',self.run_pipeline(c)['code'])
        self.assertEqual('craft',self.journal()['pending']['kind']);self.assertEqual({},c.depot)
        (self.base/'run'/'stripped-wood-pipeline.json').unlink()
        c=self.client({wood.OUTPUT:3})
        def wrong_deposit(c,depots,deposit):c.held[wood.OUTPUT]=0;return {'complete':True}
        with patch.object(wood,'exchange',side_effect=wrong_deposit):
            self.assertEqual('wait_receipt',self.run_pipeline(c)['code'])
        self.assertEqual('deposit',self.journal()['pending']['kind'])

    def test_missing_raw_source_reuses_same_bound_supplier_and_preserves_unknown(self):
        c=self.client();self.assertFalse(hasattr(c,'wood_backend'))
        def source(client,profile,item,target,out,checkpoint):
            self.assertIs(c,client);self.assertIs(c.stripped_wood_backend,c.wood_backend)
            self.assertEqual((wood.RAW,4),(item,target));return {'phase':'waiting','code':'wait_receipt'}
        with patch('material_jobs.wood_pipeline.run',side_effect=source) as supplier:
            self.assertEqual('wait_receipt',self.run_pipeline(c)['code'])
            self.assertEqual('wait_receipt',self.run_pipeline(c)['code'])
        self.assertEqual(1,supplier.call_count);self.assertFalse(hasattr(c,'wood_backend'))
        self.assertEqual('produce_raw',self.journal()['pending']['kind'])

    def test_fetched_real_cherry_log_is_not_fabricated_or_overconsumed(self):
        c=self.client();c.depot[wood.RAW]=1
        self.assertEqual('stripped_log_produced',self.run_pipeline(c)['code'])
        self.assertEqual(0,c.depot[wood.RAW]);self.assertEqual(1,c.held[wood.STRIPPED])
        self.assertIn(('fetch',{wood.RAW:4}),c.stripped_wood_backend.calls)

    def test_finished_stock_changed_or_other_target_journal_requires_explicit_reconciliation(self):
        c=self.client({wood.STRIPPED:4});self.run_pipeline(c,57)
        c.depot[wood.OUTPUT]=1
        self.assertEqual('wait_depot',self.run_pipeline(c,57)['code'])
        path=self.base/'run'/'stripped-wood-pipeline.json';before=path.read_bytes()
        self.assertEqual('wait_receipt',self.run_pipeline(c,3)['code']);self.assertEqual(before,path.read_bytes())

    def test_invalid_depots_backend_mode_and_hurt_client_never_place(self):
        c=self.client({wood.RAW:1});self.profile['depots']=[None]
        self.assertEqual('wait_source',self.run_pipeline(c)['code']);self.assertEqual([],c.calls)
        self.profile['depots']=[[1,64,2]];c.stripped_wood_backend.request['mode']='projection'
        self.assertEqual('wait_source',self.run_pipeline(c)['code']);self.assertEqual([],c.calls)
        c.stripped_wood_backend.request['mode']='item';c.health=18
        with self.assertRaises(JobPaused):self.run_pipeline(c)
        self.assertEqual([],c.calls)

    def test_axe_selection_requires_normal_actual_durable_stack_and_preserves_metadata(self):
        good={'slot':3,'item':'minecraft:diamond_axe','count':1,'durability':4,
              'max_damage':1561,'damage':1557,'enchantments':{'minecraft:silk_touch':1}}
        self.assertEqual(good,wood.choose_axe({'inventory':[good]}))
        for changes in ({'count':2},{'durability':3},{'slot':36},{'item':'minecraft:diamond_pickaxe'}):
            self.assertIsNone(wood.choose_axe({'inventory':[{**good,**changes}]}))
        self.assertEqual(wood.axe_identity(good),wood.axe_identity({**good,'slot':5,'durability':3,'damage':1558}))
        self.assertNotEqual(wood.axe_identity(good),wood.axe_identity({**good,'enchantments':{}}))


if __name__=='__main__':unittest.main()
