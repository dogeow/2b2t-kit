from collections import Counter
import copy
import itertools
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from material_jobs.mud_pipeline import run,DIRT,GRASS,MUD,AIR,CAULDRON
from material_jobs.protocol import JobPaused,JobBlocked
from recipe_catalog import RecipeCatalog


def fixture(path):
    recipes={
        'packed_mud':{'type':'minecraft:crafting_shapeless','ingredients':['minecraft:mud','minecraft:wheat'],'result':{'id':'minecraft:packed_mud'}},
        'mud_bricks':{'type':'minecraft:crafting_shaped','key':{'#':'minecraft:packed_mud'},'pattern':['##','##'],'result':{'count':4,'id':'minecraft:mud_bricks'}},
        'glass_bottle':{'type':'minecraft:crafting_shaped','key':{'#':'minecraft:glass'},'pattern':['# #',' # '],'result':{'count':3,'id':'minecraft:glass_bottle'}}}
    with zipfile.ZipFile(path,'w') as z:
        for n,d in recipes.items():z.writestr('data/minecraft/recipe/'+n+'.json',json.dumps(d))


class Client:
    world='world'
    def __init__(self,counts):
        self.rows=[{'slot':i,'item':'minecraft:air','count':0,'max_stack':64} for i in range(36)]
        self.selected=0;self.calls=[];self.bad_mine=False;self.uncertain_mine=False
        self.pos=[102.5,64,100.5]
        self.blocks={(100,63,100):'Block{minecraft:stone}',(103,64,100):'Block{minecraft:water_cauldron}[level=3]'}
        slots={'minecraft:diamond_sword':0,'minecraft:diamond_shovel':1,'minecraft:dirt':12,
               'minecraft:glass_bottle':13,'minecraft:wheat':14,'minecraft:water_bucket':15}
        for item,count in {'minecraft:diamond_sword':1,'minecraft:diamond_shovel':1,**counts}.items():
            slot=slots.get(item,next(i for i,r in enumerate(self.rows) if r['count']==0))
            self.rows[slot]={'slot':slot,'item':item,'count':count,'max_stack':1 if item.endswith(('shovel','sword','potion','water_bucket')) else 64}
            if item.endswith(('shovel','sword')):self.rows[slot]['durability']=1000
            if item=='minecraft:potion':self.rows[slot]['water_breathing']=False
    def count(self,item):return sum(r['count'] for r in self.rows if r['item']==item)
    def add(self,item,amount):
        if amount<0:
            left=-amount
            for r in self.rows:
                if r['item']==item:
                    n=min(left,r['count']);r['count']-=n;left-=n
            assert left==0
        else:
            size=1 if item in ('minecraft:potion','minecraft:water_bucket') else 64
            for r in self.rows:
                if r['item']==item and r['count']<size:
                    n=min(amount,size-r['count']);r['count']+=n;amount-=n
            while amount:
                r=next(r for r in self.rows if r['count']==0);slot=r['slot'];n=min(amount,size)
                r.clear();r.update(slot=slot,item=item,count=n,max_stack=size)
                if item=='minecraft:potion':r['water_breathing']=False
                amount-=n
    def status(self):
        return {'world_session':self.world,'server':'simpcraft.com','dimension':'minecraft:overworld',
                'connected':True,'health':20,'food':20,'guard_armed':True,'guard_pve_only':True,
                'guard_busy':False,'under_water':False,'manual_movement':False,'flight':True,
                'pos':list(self.pos),
                'inventory':copy.deepcopy(self.rows),'entities':[],'hand':copy.deepcopy(self.rows[self.selected])}
    def checked(self,op,**kw):
        if op!='select_item':return self.request(op,**kw)
        self.calls.append((op,kw));slot=kw.get('slot')
        if slot is None:slot=next(r['slot'] for r in self.rows if r['item']==kw['item'] and r['count'])
        assert self.rows[slot]['item']==kw['item'] and self.rows[slot]['count']
        if slot>=9:
            a,b=self.rows[self.selected],self.rows[slot]
            self.rows[self.selected],self.rows[slot]=b,a
            self.rows[self.selected]['slot']=self.selected;self.rows[slot]['slot']=slot
        else:self.selected=slot
        return {'phase':'done'}
    def request(self,op,**kw):
        self.calls.append((op,kw))
        if op=='navigate':
            self.pos=list(kw['target']);return {'phase':'done'}
        if op=='scan':
            result=[]
            for p,s in self.blocks.items():
                if s==AIR or not all(kw['min'][i]<=p[i]<=kw['max'][i] for i in range(3)):continue
                row={'pos':list(p),'state':s}
                if kw.get('details'):row.update(solid=s not in (MUD,) and not s.startswith('Block{minecraft:wheat}'),fluid=False,block_entity=False)
                result.append(row)
            return {'phase':'done','world_session':self.world,'blocks':result}
        pos=tuple(kw['pos'])
        if op=='interact':
            assert self.blocks[pos]==kw['expected_state'];hand=self.rows[self.selected]
            assert hand['item']==kw['expected_hand'] and hand['count']
            if hand['item']=='minecraft:glass_bottle':
                level=int(self.blocks[pos][-2]);self.add('minecraft:glass_bottle',-1);self.add('minecraft:potion',1)
                self.blocks[pos]=CAULDRON if level==1 else 'Block{minecraft:water_cauldron}[level='+str(level-1)+']'
            elif hand['item']=='minecraft:water_bucket':
                self.add('minecraft:water_bucket',-1);self.add('minecraft:bucket',1);self.blocks[pos]='Block{minecraft:water_cauldron}[level=3]'
            elif hand['item']=='minecraft:dirt':
                assert self.blocks.get((pos[0],pos[1]+1,pos[2]),AIR)==AIR
                self.add('minecraft:dirt',-1);self.blocks[(pos[0],pos[1]+1,pos[2])]=DIRT
            elif hand['item']=='minecraft:potion':
                assert self.blocks[pos]==DIRT
                self.add('minecraft:potion',-1);self.add('minecraft:glass_bottle',1);self.blocks[pos]=MUD
            elif hand['item']=='minecraft:wheat_seeds':
                self.add('minecraft:wheat_seeds',-1);self.blocks[(pos[0],pos[1]+1,pos[2])]='Block{minecraft:wheat}[age=0]'
            else:raise AssertionError(hand['item'])
            return {'phase':'done'}
        if op=='mine_block':
            if self.uncertain_mine:return {'phase':'waiting','detail':'unknown'}
            assert self.blocks[pos]==kw['expected_state']
            original=self.blocks[pos];self.blocks[pos]=AIR
            if not self.bad_mine:
                if original==MUD:self.add('minecraft:mud',1)
                elif original==GRASS:self.add('minecraft:dirt',1)
                elif original.startswith('Block{minecraft:wheat}'):
                    self.add('minecraft:wheat',1);self.add('minecraft:wheat_seeds',2)
            return {'phase':'done'}
        raise AssertionError(op)


class Backend:
    def __init__(self,c,profile):
        self.client=c;self.profile=profile;self.request={'mode':'item'};self.calls=[]
        self.crafting_catalog=RecipeCatalog(profile['recipe_jar']);c.mud_backend=self
    def ensure_client(self):return self.client
    def fetch(self,target):
        self.calls.append(('fetch',target));return {'phase':'waiting','missing':{i:n-self.client.count(i) for i,n in target.items() if self.client.count(i)<n}}
    def acquire(self,item,target):
        self.calls.append(('acquire',item,target));return {'phase':'waiting','code':'WAIT_SOURCE','requirements':{item:target}}
    def craft(self,targets):
        self.calls.append(('craft',targets))
        for item,target in targets.items():
            recipe=self.crafting_catalog.recipes[item][0];rounds=math.ceil((target-self.client.count(item))/recipe.count)
            ingredients=Counter(opts[0] for _,opts in recipe.cells)
            for raw,n in ingredients.items():self.client.add(raw,-n*rounds)
            self.client.add(item,rounds*recipe.count)
        return {'phase':'done'}


class MudPipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);jar=self.root/'recipes.jar';fixture(jar)
        self.profile={'recipe_jar':str(jar),'protected_regions':[{'min':[0,50,0],'max':[10,80,10]}],
            'mud_station':{'authorized':True,'pos':[100,64,100],'support':[100,63,100],'support_state':'Block{minecraft:stone}'},
            'mud_water_source':{'authorized':True,'pos':[103,64,100]}}
        self.c=Client({'minecraft:dirt':4,'minecraft:glass_bottle':1,'minecraft:wheat':4,'minecraft:water_bucket':1})
        self.b=Backend(self.c,self.profile)
    def go(self,item='minecraft:mud_bricks',target=4):
        with patch('work_access.approach_faces',return_value='up'):
            return run(self.c,self.profile,item,target,self.root/'job',lambda:None)
    def test_owned_dirt_bottle_mud_packed_bricks_real_net_deltas(self):
        result=self.go()
        self.assertEqual(('done',4,'absolute_backpack_total'),(result['phase'],result['after'],result['target_scope']))
        self.assertEqual(0,self.c.count('minecraft:dirt'));self.assertEqual(0,self.c.count('minecraft:wheat'))
        self.assertEqual(1,self.c.count('minecraft:glass_bottle'));self.assertEqual(AIR,self.c.blocks[(100,64,100)])
        self.assertEqual(1,len([x for x in self.c.calls if x[0]=='interact' and x[1]['expected_hand']=='minecraft:water_bucket']))
        self.assertFalse(any(op=='use_item' for op,_ in self.c.calls))
        self.assertTrue(all(p.get('details') is True for op,p in self.c.calls if op=='scan'))
    def test_current_finished_stock_is_absolute_not_added_target(self):
        self.c.add('minecraft:mud_bricks',4)
        self.assertEqual(4,self.go()['after']);self.assertEqual([],self.b.calls)
    def test_one_dirt_source_trip_supplies_the_existing_four_cell_batch(self):
        self.c.add('minecraft:dirt',-4)
        def acquire(item,target):
            self.b.calls.append(('acquire',item,target));self.c.add(item,target-self.c.count(item))
            return {'phase':'done'}
        self.b.acquire=acquire
        self.assertEqual('done',self.go()['phase'])
        self.assertEqual([('acquire','minecraft:dirt',4)],[c for c in self.b.calls if c[0]=='acquire'])
        self.assertEqual(4,self.c.count('minecraft:mud_bricks'));self.assertEqual(0,self.c.count('minecraft:dirt'))
    def test_remote_owned_station_is_loaded_before_station_scanning(self):
        self.c.pos=[200,100,200];self.b.prepare_travel=lambda:None
        original=self.c.request
        def request(op,**params):
            if op=='scan':self.assertLessEqual(abs(self.c.pos[0]-100),3)
            return original(op,**params)
        self.c.request=request
        def travel(c,target,*args,**kwargs):c.pos=list(target)
        with patch('material_jobs.navigation.lift_for_travel'),patch('material_jobs.acquisition._travel',side_effect=travel):
            self.assertEqual('done',self.go()['phase'])
        self.assertTrue((self.root/'job/registered-mud-station-loading-travel.json').exists())
    def test_dirt_batch_demand_excludes_already_carried_mud(self):
        self.c.add('minecraft:dirt',-4);self.c.add('minecraft:mud',2)
        def acquire(item,target):
            self.b.calls.append(('acquire',item,target));self.c.add(item,target-self.c.count(item))
            return {'phase':'done'}
        self.b.acquire=acquire
        self.assertEqual('done',self.go()['phase'])
        self.assertEqual([('acquire','minecraft:dirt',2)],[c for c in self.b.calls if c[0]=='acquire'])
    def test_one_empty_slot_preserves_single_dirt_conversion_without_speculative_bulk_loading(self):
        self.c.add('minecraft:dirt',-4)
        for row in self.c.rows:
            if not row['count']and row['slot']!=12:row.update(item='minecraft:stone',count=64,max_stack=64)
        self.assertEqual('WAIT_SOURCE',self.go()['code'])
        self.assertIn(('acquire','minecraft:dirt',1),self.b.calls)
        self.assertFalse(any(op=='interact'for op,_ in self.c.calls))
    def test_known_source_search_wait_keeps_the_large_target_without_an_unknown_action(self):
        self.c.add('minecraft:dirt',-4)
        self.b.acquire=lambda item,target:{'phase':'waiting','code':'WAIT_SOURCE_SEARCH',
            'search_progress':{'new_tiles':8,'has_more':True}}
        result=self.go(target=64);self.assertEqual('WAIT_SOURCE_SEARCH',result['code'])
        book=json.loads((self.root/'job/mud-pipeline.json').read_text())
        self.assertIsNone(book['pending']);self.assertTrue(result['safe_to_leave']);self.assertEqual(64,book['target'])
        self.assertFalse(any(op in ('interact','mine_block')for op,_ in self.c.calls))
    def sea_source(self,uncertain=False,wrong_potion=False):
        from material_jobs.mud_water_supply import BOTTLE_SCOPE
        self.profile['mud_bucket_source']={'authorized':True,'pos':[104,63,100],
            'approach':[103.5,64,100.5],'expected_state':'Block{minecraft:water}[level=0]'}
        self.c.blocks[(104,63,100)]='Block{minecraft:water}[level=0]'
        self.b.checkpoint=lambda:None
        original_status=self.c.status;original_request=self.c.request
        def status():
            s=original_status();s['bottle_water_protocol']=1;return s
        def request(op,**kw):
            if op!='bottle_fill':return original_request(op,**kw)
            self.c.calls.append((op,kw))
            if uncertain:return {'phase':'waiting','detail':'unknown original use'}
            self.c.add('minecraft:glass_bottle',-1);self.c.add('minecraft:potion',1)
            slot=next(r['slot']for r in self.c.rows if r['item']=='minecraft:potion' and r['count'])
            return {'phase':'done','id':'sea-bottle', 'bottle_water':{
                'world_session':'world','request_id':'sea-bottle','operation':'bottle_fill','pos':kw['pos'],
                'use_count':1,'water_slot':slot,'potion':'minecraft:healing'if wrong_potion else'minecraft:water',
                'confirmed':True,'unknown_outcome':False,'server_hand_confirmed':True,'server_water_slot_confirmed':True,
                'source_not_consumed_by_bottle_use':True,'confirmation_scope':BOTTLE_SCOPE}}
        self.c.status=status;self.c.request=request
    def test_registered_sea_fills_four_bottles_without_cauldron_or_bucket(self):
        self.sea_source();self.assertEqual('done',self.go()['phase'])
        self.assertEqual(4,sum(op=='bottle_fill'for op,_ in self.c.calls))
        self.assertFalse(any(op=='interact'and p.get('expected_hand')in ('minecraft:glass_bottle','minecraft:water_bucket')for op,p in self.c.calls))
        self.assertEqual('Block{minecraft:water}[level=0]',self.c.blocks[(104,63,100)])
        self.assertEqual('Block{minecraft:water_cauldron}[level=3]',self.c.blocks[(103,64,100)])
        self.assertEqual(1,self.c.count('minecraft:glass_bottle'))
    def test_direct_water_unknown_use_keeps_pending_and_never_retries(self):
        self.sea_source(uncertain=True)
        with self.assertRaises(JobBlocked):self.go('minecraft:mud',1)
        self.assertEqual('WAIT_RECONCILE',self.go('minecraft:mud',1)['code'])
        self.assertEqual(1,sum(op=='bottle_fill'for op,_ in self.c.calls))
        self.assertFalse(any(op=='interact'and p.get('expected_hand')=='minecraft:dirt'for op,p in self.c.calls))
    def test_direct_water_requires_real_water_potion_receipt(self):
        self.sea_source(wrong_potion=True)
        with self.assertRaisesRegex(JobBlocked,'unproved'):self.go('minecraft:mud',1)
        self.assertEqual('WAIT_RECONCILE',self.go('minecraft:mud',1)['code'])
        self.assertEqual(1,sum(op=='bottle_fill'for op,_ in self.c.calls))
    def test_changed_sea_source_never_uses_bottle_or_falls_back_to_cauldron(self):
        self.sea_source();self.c.blocks[(104,63,100)]='Block{minecraft:water}[level=1]'
        with self.assertRaisesRegex(JobBlocked,'source changed'):self.go('minecraft:mud',1)
        self.assertFalse(any(op=='bottle_fill'for op,_ in self.c.calls))
    def test_old_host_requires_update_without_cauldron_fallback(self):
        self.sea_source();status=self.c.status
        def old_status():
            s=status();s.pop('bottle_water_protocol');return s
        self.c.status=old_status
        self.assertEqual('WAIT_WATER_SOURCE',self.go('minecraft:mud',1)['code'])
        self.assertFalse(any(op in ('bottle_fill','interact')for op,_ in self.c.calls))
    def test_bottle_is_filled_before_owned_dirt_placement_to_reduce_grass_growth_window(self):
        original=self.c.request
        def grow(op,**params):
            result=original(op,**params)
            if op=='interact' and params.get('expected_hand')=='minecraft:glass_bottle' and self.c.blocks.get((100,64,100))==DIRT:
                self.c.blocks[(100,64,100)]=GRASS
            return result
        self.c.request=grow
        self.assertEqual('done',self.go('minecraft:mud',1)['phase'])
        conversions=[p for op,p in self.c.calls if op=='interact' and p.get('expected_hand')=='minecraft:potion']
        self.assertEqual([DIRT],[p['expected_state'] for p in conversions])
        self.assertEqual(1,self.c.count('minecraft:mud'))
    def test_only_journal_owned_grass_is_normally_recovered_and_replaced_with_retained_water(self):
        def access(c,pos,expected,faces,**kw):
            if expected==DIRT:raise RuntimeError('known pre-use access failure')
            return 'up'
        with patch('work_access.approach_faces',side_effect=access):
            with self.assertRaises(RuntimeError):run(self.c,self.profile,'minecraft:mud',1,self.root/'job',lambda:None)
        self.c.blocks[(100,64,100)]=GRASS
        self.assertEqual('done',self.go('minecraft:mud',1)['phase'])
        digs=[p['expected_state'] for op,p in self.c.calls if op=='mine_block']
        self.assertEqual([GRASS,MUD],digs)
        self.assertEqual(1,len([p for op,p in self.c.calls if op=='interact'and p.get('expected_hand')=='minecraft:glass_bottle']))
    def test_current_derived_water_slot_is_retained_across_access_failure(self):
        def access(c,pos,expected,faces,**kw):
            if expected==DIRT:raise RuntimeError('known pre-use access failure')
            return 'up'
        with patch('work_access.approach_faces',side_effect=access):
            with self.assertRaises(RuntimeError):
                run(self.c,self.profile,'minecraft:mud',1,self.root/'job',lambda:None)
        before=len([p for op,p in self.c.calls if op=='interact'and p.get('expected_hand')=='minecraft:glass_bottle'])
        self.assertEqual('done',self.go('minecraft:mud',1)['phase'])
        after=len([p for op,p in self.c.calls if op=='interact'and p.get('expected_hand')=='minecraft:glass_bottle'])
        self.assertEqual(before,after)
    def test_unowned_grass_work_cell_remains_protected(self):
        self.c.blocks[(100,64,100)]=GRASS
        self.assertEqual('WAIT_SOURCE',self.go('minecraft:mud',1)['code'])
        self.assertFalse(any(op in ('interact','mine_block')for op,_ in self.c.calls))
    def test_pickup_pose_inside_work_cell_moves_to_registered_stand_before_placement(self):
        self.c.pos=[100.5,64,100.5]
        self.profile['mud_station']['approach']=[102.5,64,100.5]
        self.assertEqual('done',self.go('minecraft:mud',1)['phase'])
        moves=[p for op,p in self.c.calls if op=='navigate']
        self.assertEqual([102.5,64,100.5],moves[0]['target'])
    def test_inside_cell_without_registered_adjacent_stand_never_places(self):
        self.c.pos=[100.5,64,100.5]
        self.assertEqual('WAIT_SOURCE',self.go('minecraft:mud',1)['code'])
        self.assertFalse(any(op=='interact'and p.get('expected_hand')=='minecraft:dirt'for op,p in self.c.calls))
    def test_owned_grass_recovery_uses_ordinary_shovel_even_if_silk_touch_is_more_durable(self):
        def access(c,pos,expected,faces,**kw):
            if expected==DIRT:raise RuntimeError('known pre-use access failure')
            return 'up'
        with patch('work_access.approach_faces',side_effect=access):
            with self.assertRaises(RuntimeError):run(self.c,self.profile,'minecraft:mud',1,self.root/'job',lambda:None)
        self.c.blocks[(100,64,100)]=GRASS
        empty=next(r for r in self.c.rows if not r['count']);empty.update(item='minecraft:diamond_shovel',count=1,max_stack=1)
        tools=[r for r in self.c.rows if r['item']=='minecraft:diamond_shovel'and r['count']]
        tools[0]['durability']=1000;tools[0]['enchantments']=[{'id':'minecraft:silk_touch','level':1}]
        tools[1]['durability']=500
        self.assertEqual('done',self.go('minecraft:mud',1)['phase'])
        first=next(p for op,p in self.c.calls if op=='select_item'and p.get('item')=='minecraft:diamond_shovel')
        self.assertEqual(tools[1]['slot'],first['slot'])
    def test_consumed_water_bucket_can_be_fetched_again_in_one_four_cell_call(self):
        self.c.blocks[(103,64,100)]=CAULDRON
        self.c.add('minecraft:water_bucket',-1)
        old_fetch=self.b.fetch
        def refill(targets):
            if targets=={'minecraft:water_bucket':1}:
                self.b.calls.append(('fetch',targets));self.c.add('minecraft:water_bucket',1)
                return {'phase':'done'}
            return old_fetch(targets)
        self.b.fetch=refill
        result=self.go(item='minecraft:mud',target=4)
        self.assertEqual('done',result['phase']);self.assertEqual(4,self.c.count('minecraft:mud'))
        fills=[params for op,params in self.c.calls if op=='interact'and params['expected_hand']=='minecraft:water_bucket']
        self.assertEqual(2,len(fills))
        self.assertEqual(2,len([v for v in self.b.calls if v==('fetch',{'minecraft:water_bucket':1})]))
    def test_existing_packed_mud_uses_exact_four_output_recipe_no_source(self):
        self.c.add('minecraft:packed_mud',4)
        self.assertEqual('done',self.go()['phase'])
        self.assertFalse(any(op=='interact' for op,_ in self.c.calls))
    def test_old_unidentified_potion_not_assumed_water(self):
        self.c.add('minecraft:potion',1);before=self.c.count('minecraft:potion')
        self.assertEqual('done',self.go()['phase'])
        self.assertEqual(before,self.c.count('minecraft:potion'))
        conversions=[p for op,p in self.c.calls if op=='interact' and p['expected_hand']=='minecraft:potion']
        self.assertEqual(4,len(conversions))
    def test_water_cube_is_not_reinterpreted_as_cauldron_api(self):
        self.c.blocks[(103,64,100)]='Block{minecraft:water}[level=0]'
        self.assertEqual('WAIT_WATER_SOURCE',self.go()['code'])
        self.assertFalse(any(op=='interact' for op,_ in self.c.calls))
    def test_unowned_station_preserves_existing_dirt(self):
        self.c.blocks[(100,64,100)]=DIRT
        self.assertEqual('WAIT_SOURCE',self.go()['code'])
        self.assertFalse(any(op in ('interact','mine_block') for op,_ in self.c.calls))
    def test_empty_cauldron_needs_real_bucket_before_dirt_placement(self):
        self.c.blocks[(103,64,100)]=CAULDRON;self.c.add('minecraft:water_bucket',-1)
        self.assertEqual('WAIT_WATER_SOURCE',self.go()['code'])
        self.assertFalse(any(op=='interact' for op,_ in self.c.calls))
    def test_native_done_without_mud_gain_never_replayed(self):
        self.c.bad_mine=True
        with patch('material_jobs.mud_pipeline.time.monotonic',side_effect=itertools.count()),patch('material_jobs.mud_pipeline.time.sleep'):
            first=self.go('minecraft:mud',1);second=self.go('minecraft:mud',1)
        self.assertEqual('WAIT_RECONCILE',first['code']);self.assertEqual('WAIT_RECONCILE',second['code'])
        self.assertEqual(1,len([r for r in self.c.calls if r[0]=='mine_block']))
    def test_unknown_native_mine_remains_inflight(self):
        self.c.uncertain_mine=True
        self.assertEqual('WAIT_RECONCILE',self.go('minecraft:mud',1)['code'])
        self.assertEqual('WAIT_RECONCILE',self.go('minecraft:mud',1)['code'])
        self.assertEqual(1,len([r for r in self.c.calls if r[0]=='mine_block']))
    def test_projection_backend_not_used_for_unrelated_depot_fetch(self):
        self.b.request['mode']='projection'
        self.assertEqual('WAIT_BACKEND',self.go()['code']);self.assertEqual([],self.b.calls)
    def test_wrong_backend_client_rejected(self):
        self.b.client=Client({})
        with self.assertRaises(JobBlocked):self.go()
    def test_completed_output_moved_requires_new_job_not_reproduction(self):
        self.go();self.c.add('minecraft:mud_bricks',-4)
        self.assertEqual('blocked',self.go()['phase'])
    def test_known_four_cell_budget_not_false_completion(self):
        result=self.go('minecraft:mud',8)
        self.assertEqual('WAIT_MUD_BATCH',result['code']);self.assertEqual(4,self.c.count('minecraft:mud'))
    def test_projection_stock_visit_makes_sixteen_verified_bricks_without_completing_the_larger_goal(self):
        self.b.request.update(mode='projection',projection_key='map',context={'world_session':'world'})
        self.b.resource_pipeline_context={'target_scope':'absolute_backpack_total','projection_key':'map','world_session':'world'}
        self.c.add('minecraft:dirt',12);self.c.add('minecraft:wheat',16)
        original=self.b.fetch
        def refill(target):
            if target=={'minecraft:water_bucket':1}:
                self.c.add('minecraft:water_bucket',1);return {'phase':'done'}
            return original(target)
        self.b.fetch=refill
        result=self.go(target=64)
        self.assertEqual('WAIT_MUD_BATCH',result['code']);self.assertTrue(result['safe_to_leave'])
        self.assertEqual(16,self.c.count('minecraft:mud_bricks'))
        book=json.loads((self.root/'job/mud-pipeline.json').read_text())
        self.assertEqual(64,book['target']);self.assertIsNone(book['pending']);self.assertFalse(book['owned_cell'])
        self.assertIsNone(book['derived_water_slot']);self.assertFalse(book.get('complete',False))

    def test_large_brick_goal_uses_four_carried_wheat_before_waiting_for_more(self):
        result=self.go('minecraft:mud_bricks',120)
        self.assertEqual('waiting',result['phase'])
        self.assertEqual(4,self.c.count('minecraft:mud_bricks'))
        self.assertFalse(result.get('complete',False))
        self.assertFalse(any(call[0]=='fetch' and call[1].get('minecraft:wheat',0)>4 for call in self.b.calls))

    def fill_inventory(self):
        for r in self.c.rows:
            if not r['count']:r.update(item='minecraft:cobblestone',count=64,max_stack=64)

    def test_singleton_bottle_replaces_its_hand_slot_with_a_full_inventory(self):
        self.c.add('minecraft:mud',1);self.fill_inventory()
        result=self.go('minecraft:mud',2)
        self.assertEqual('done',result['phase'],result);self.assertEqual(2,self.c.count('minecraft:mud'))
        self.assertEqual(1,self.c.count('minecraft:glass_bottle'))
        self.assertEqual(0,self.c.count('minecraft:potion'))

    def test_stacked_bottle_still_needs_an_actual_empty_output_slot(self):
        self.c.add('minecraft:glass_bottle',1);self.c.add('minecraft:mud',1);self.fill_inventory()
        result=self.go('minecraft:mud',2)
        self.assertEqual('WAIT_CAPACITY',result['code'])
        self.assertFalse(any(op=='interact'and p.get('expected_hand')=='minecraft:glass_bottle'for op,p in self.c.calls))
    def test_fetch_missing_wheat_waits_without_world_mutation(self):
        self.c.add('minecraft:wheat',-4)
        result=self.go()
        self.assertEqual('WAIT_SOURCE',result['code'])
        self.assertFalse(any(op in ('mine_block','interact') for op,_ in self.c.calls))
    def test_missing_grain_uses_existing_backend_registered_field_handler(self):
        self.c.add('minecraft:wheat',-4);calls=[]
        def registered(target,out,checkpoint):
            calls.append(target);return {'phase':'waiting','code':'WAIT_GROWTH','detail':'registered field immature'}
        self.b.acquire_registered_wheat=registered
        with patch('material_jobs.colored_sources.acquire') as generic:
            result=self.go()
        self.assertEqual('WAIT_GROWTH',result['code']);self.assertEqual([4],calls)
        generic.assert_not_called();self.assertTrue(result['safe_to_leave'])
        self.assertFalse(any(op in ('mine_block','interact')for op,_ in self.c.calls))
    def test_craft_catalog_restored_after_actual_backend_exception(self):
        self.c.add('minecraft:packed_mud',4);original=self.b.crafting_catalog
        with patch.object(self.b,'craft',side_effect=JobPaused('handoff')):
            with self.assertRaises(JobPaused):self.go()
        self.assertIs(original,self.b.crafting_catalog)
    def test_authorized_natural_dry_mud_needs_no_water_or_station(self):
        self.profile['colored_source_regions']=[{'item':'minecraft:mud','authorized':True,'min':[199,63,199],'max':[201,65,201]}]
        self.c.blocks[(200,64,200)]=MUD;self.c.blocks[(200,63,200)]=DIRT
        self.profile.pop('mud_station');self.profile.pop('mud_water_source')
        result=self.go('minecraft:mud',1)
        self.assertEqual('done',result['phase']);self.assertEqual(1,self.c.count('minecraft:mud'))
        self.assertFalse(any(op=='interact' for op,_ in self.c.calls))
    def crop(self,age=7):
        self.c.add('minecraft:wheat',-4);self.c.add('minecraft:wheat_seeds',1)
        self.profile['colored_source_regions']=[{'item':'minecraft:wheat','authorized':True,'min':[199,63,199],'max':[201,65,201]}]
        self.c.blocks[(200,64,200)]='Block{minecraft:wheat}[age='+str(age)+']'
        self.c.blocks[(200,63,200)]='Block{minecraft:farmland}[moisture=7]'
        self.c.add('minecraft:mud',1)
    def test_mature_wheat_harvest_reseed_and_packed_mud_recipe(self):
        self.crop()
        self.assertEqual('done',self.go('minecraft:packed_mud',1)['phase'])
        self.assertEqual('Block{minecraft:wheat}[age=0]',self.c.blocks[(200,64,200)])
        self.assertEqual(2,self.c.count('minecraft:wheat_seeds'))
    def test_immature_wheat_not_harvested_or_faked(self):
        self.crop(age=6)
        self.assertEqual('WAIT_SOURCE',self.go('minecraft:packed_mud',1)['code'])
        self.assertFalse(any(op in ('interact','mine_block') for op,_ in self.c.calls))
    def test_no_seed_preserves_mature_crop(self):
        self.crop();self.c.add('minecraft:wheat_seeds',-1)
        self.assertEqual('WAIT_SEED',self.go('minecraft:packed_mud',1)['code'])
        self.assertFalse(any(op=='mine_block' for op,_ in self.c.calls))
    def test_bottle_recipe_from_three_real_glass(self):
        self.c.add('minecraft:glass_bottle',-1);self.c.add('minecraft:glass',3)
        self.assertEqual('done',self.go('minecraft:mud',1)['phase'])
        self.assertEqual(3,self.c.count('minecraft:glass_bottle'))


if __name__=='__main__':unittest.main()
