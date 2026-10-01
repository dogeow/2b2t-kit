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

from material_jobs.mud_pipeline import run,DIRT,MUD,AIR,CAULDRON
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
    def test_fetch_missing_wheat_waits_without_world_mutation(self):
        self.c.add('minecraft:wheat',-4)
        result=self.go()
        self.assertEqual('WAIT_SOURCE',result['code'])
        self.assertFalse(any(op in ('mine_block','interact') for op,_ in self.c.calls))
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
