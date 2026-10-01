"""Run the real stage adapter against bounded inventory/entity bridge fixtures.

These are offline observations, never server or installation evidence.
"""
from collections import Counter
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from farm_caretaker import CaretakerPaused
from farm_caretaker_stages import COOKED, create_stages
from potato_harvest import POTATO, _counts
from projection_material_plan import ProcessingCatalog
from test_potato_farm import SPEC, row
from test_potato_harvest import HarvestClient


REGION={'min':[-3,63,-3],'max':[12,67,3]}


def adult(uuid,ident,pos,kind='minecraft:cow',baby=False,named=False):
    return {'uuid':uuid,'id':ident,'pos':pos,'type':kind,'alive':True,'visible':True,
            'is_baby':baby,'has_custom_name':named,'health':10}


class StageClient(HarvestClient):
    def __init__(self,potatoes=4):
        super().__init__(potatoes=potatoes);self.extra.update(on_ground=False,material_slaughter_protocol=1,attack_strength=1)
        self.inv[1].update(item='minecraft:diamond_sword',count=1,durability=1000)
        self.attack_mode='sent';self.hits=[];self.cooldown_reads=0;self.cooldown_remaining=0
        self.bad_rejection=None;self.no_damage=False;self.partial_loot=False
        self.feed_count=0;self.after_feed=None
        self.before_attack=None;self.after_attack=None;self.before_scan=None
        for x in range(-3,13):
            for z in range(-3,4):self.rows[(x,63,z)]=row((x,63,z),'Block{minecraft:stone}')
        # Field support remains actual hydrated farmland.
        for x in range(-2,3):
            for z in range(-2,3):
                if x or z:self.rows[(x,63,z)]=row((x,63,z),'Block{minecraft:farmland}[moisture=7]',False)
        self.rows[(0,63,0)]=row((0,63,0),'Block{minecraft:water}[level=0]',False,True)

    def add(self,item,amount):
        source=next((r for r in self.inv[:36] if r['item']==item and r['count']),None)
        if source is None:source=next(r for r in self.inv[:36] if not r['count'])
        source.update(item=item,count=source['count']+amount,max_stack=64)

    def take(self,item,amount):
        for source in self.inv[:36]:
            if source['item']!=item:continue
            used=min(source['count'],amount);source['count']-=used;amount-=used
            if not source['count']:source['item']='minecraft:air'
        assert amount==0

    def status(self):
        if self.cooldown_remaining:
            self.cooldown_reads+=1;self.cooldown_remaining-=1
            self.extra['attack_strength']=0 if self.cooldown_remaining else 1
        return super().status()

    def request(self,op,**params):
        if op=='scan' and self.before_scan:self.before_scan(self)
        if op=='interact_entity':
            self.calls.append((op,copy.deepcopy(params)));self.feed_count+=1
            target=next(e for e in self.entities if e['uuid']==params['expected_uuid'])
            assert target['id']==params['entity_id'] and not target['is_baby']
            assert self.inv[self.selected]['item']=='minecraft:wheat'
            self.take('minecraft:wheat',1)
            if self.feed_count==2:self.entities.append(adult('new-baby',99,[.5,64,.5],target['type'],baby=True))
            if self.after_feed:self.after_feed(self)
            return {**self.status(),'phase':'done','id':'feed-'+str(self.feed_count)}
        if op=='material_slaughter_attack':
            self.calls.append((op,copy.deepcopy(params)))
            if self.before_attack:self.before_attack(self,params)
            target=next(e for e in self.entities if e['uuid']==params['expected_uuid'])
            assert target['id']==params['entity_id']
            assert not target['is_baby'] and not target['has_custom_name']
            assert self.extra['on_ground'] is False and self.extra['attack_strength']>=.95
            same=[e for e in self.entities if e['type']==target['type'] and e['alive'] and not e['is_baby'] and not e['has_custom_name']]
            assert len(same)>params['keep_adults']
            rid='attack-'+str(len(self.calls));self.last=rid;dispatch={'id':rid,'action_sent':True,
                'expected_uuid':target['uuid'],'world_session':self.world,'result_scope':'normal_attack_dispatch_only'}
            if self.attack_mode=='reject':
                dispatch.update(action_sent=False,pre_dispatch_rejected=True)
                if self.bad_rejection=='missing_id':dispatch.pop('id');rid=None
                elif self.bad_rejection=='old_id':dispatch['id']=rid='old-attack'
                elif self.bad_rejection=='foreign_world':dispatch['world_session']='foreign'
                elif self.bad_rejection=='foreign_uuid':dispatch['expected_uuid']='another-animal'
                return {'id':rid,'phase':'error','detail':'cooldown rejected before dispatch','slaughter_attack':dispatch}
            if self.attack_mode=='unknown':return {'id':rid,'phase':'waiting','detail':'unknown attack'}
            if self.attack_mode=='timeout':raise TimeoutError('native dispatch outcome is unknown')
            self.hits.append(target['uuid'])
            if not self.no_damage:target['health']-=5
            self.extra['attack_strength']=0;self.cooldown_remaining=12
            if target['health']<=0:
                self.entities.remove(target)
                meat='minecraft:beef' if target['type']=='minecraft:cow' else 'minecraft:mutton'
                self.entities.append({'uuid':'loot-'+target['uuid'],'id':1000+target['id'],'type':'minecraft:item',
                    'pos':target['pos'][:],'alive':True,'visible':True,'stack':{'item':meat,'count':2}})
            if self.after_attack:self.after_attack(self)
            return {'id':rid,'phase':'done','slaughter_attack':dispatch}
        if op=='collect_item':
            self.calls.append((op,copy.deepcopy(params)))
            drop=next(e for e in self.entities if e['uuid']==params['expected_uuid'])
            self.add(drop['stack']['item'],1 if self.partial_loot else drop['stack']['count']);self.entities.remove(drop)
            return {'phase':'done'}
        return super().request(op,**params)


class StageBackend:
    def __init__(self,c,root):
        self.client=c;self.root=root;self.profile={'depots':[[2,64,2]],'furnace_positions':[[3,64,2]]}
        self.depot=Counter({POTATO:20,'minecraft:coal':20,'minecraft:baked_potato':20})
        self.fetches=[];self.smelt_calls=[];self.smelt_mode='real_delta';self.prepare_calls=0
        jar=root/'recipes.jar'
        with zipfile.ZipFile(jar,'w') as archive:
            for source,output in [('beef','cooked_beef'),('mutton','cooked_mutton')]:
                archive.writestr('data/minecraft/recipe/'+output+'.json',json.dumps({
                    'type':'minecraft:smelting','ingredient':'minecraft:'+source,
                    'result':{'id':'minecraft:'+output},'cookingtime':200}))
        self.catalog=ProcessingCatalog(jar)

    def prepare_travel(self):self.prepare_calls+=1
    def stage_near_base(self,positions):pass
    def fetch(self,targets):
        self.fetches.append(copy.deepcopy(targets));held=_counts(self.client.status())
        for item,target in targets.items():
            amount=max(0,target-held[item])
            if self.depot[item]<amount:return {'phase':'waiting','detail':'actual depot stock is short'}
            self.depot[item]-=amount;self.client.add(item,amount)
        return {'phase':'done','targets':targets}
    def smelt(self,spec,target):
        self.smelt_calls.append((spec.copy(),target));held=_counts(self.client.status())
        path=self.root/('smelt-'+str(len(self.smelt_calls))+'.json')
        manifest={'world_session':self.client.world,'kind':'smelt',**spec,'target':target,'batches':[]}
        if self.smelt_mode=='unknown':manifest['batches']=[{'complete':False}]
        path.write_text(json.dumps(manifest))
        if held['minecraft:coal']<1 or self.smelt_mode=='unknown':
            return {'phase':'waiting','requirements':{'minecraft:coal':1},'journal':str(path)}
        if self.smelt_mode!='false_done':
            amount=target-held[spec['output']];self.client.take(spec['source'],amount)
            self.client.take('minecraft:coal',1);self.client.add(spec['output'],amount)
        return {'phase':'done','journal':str(path)}


def native_travel(c,target,checkpoint,trace):
    checkpoint();c.calls.append(('navigate',{'target':target[:] }));c.extra['pos']=target[:]
    c.extra['on_ground']=False;trace.append({'actual_arrival':target[:]})


def depot_exchange(c,positions,deposit):
    c.calls.append(('depot_exchange',copy.deepcopy(deposit)))
    for item,keep in deposit.items():
        surplus=max(0,_counts(c.status())[item]-keep)
        if surplus:c.take(item,surplus)
    return {'complete':True,'remaining_deposit':{},'remaining_withdraw':{}}


class StageTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.c=StageClient();self.b=StageBackend(self.c,self.root)
        self.profile={'adult_keep':2,'potato_reserve':4,'cooked_food_reserve':8,
            'potato_fields':[SPEC],'livestock_region':copy.deepcopy(REGION),
            'livestock_types':['minecraft:cow'],'depots':self.b.profile['depots']}
        self.stages=create_stages(self.c,self.b);self.cycle={'id':1,'world_session':self.c.world}
        self.addCleanup(patch.stopall)
        patch('farm_caretaker_stages.travel',side_effect=native_travel).start()
        patch('farm_caretaker_stages.exchange',side_effect=depot_exchange).start()
        patch('farm_caretaker_stages.time.sleep',return_value=None).start()
    def run_stage(self,name,checkpoint=lambda:None):
        result=self.stages[name](self.profile,self.cycle,self.root/name,checkpoint)
        return result,json.loads((self.root/name/'stage.json').read_text())
    def herd(self,kind='minecraft:cow'):
        self.c.entities=[adult('target',1,[3.5,64,.5],kind),adult('keep-a',2,[7.5,64,.5],kind),
                         adult('keep-b',3,[11.5,64,.5],kind)]
        self.profile['livestock_types']=[kind]
    def attacks(self):return [p for op,p in self.c.calls if op=='material_slaughter_attack']

    def test_four_seeds_fetch_one_then_real_harvest_replant_and_keep_four(self):
        result,book=self.run_stage('harvest_store')
        self.assertEqual('done',result['phase'],result);self.assertEqual([{POTATO:5}],self.b.fetches)
        self.assertEqual(19,self.b.depot[POTATO]);self.assertEqual(4,_counts(self.c.status())[POTATO])
        self.assertEqual(4,len([p for op,p in self.c.calls if op=='mine_block']))
        self.assertTrue(all(r['result']['harvested_replanted']==4 for r in book['receipts'] if r['kind']=='harvest'))
        self.assertIsNone(book['pending'])
    def test_no_actual_seed_supply_sends_no_crop_break(self):
        self.b.depot[POTATO]=0;result,book=self.run_stage('harvest_store')
        self.assertEqual('WAIT_SUPPLY',result['code']);self.assertFalse(any(op=='mine_block' for op,p in self.c.calls))
        self.assertEqual(4,_counts(self.c.status())[POTATO]);self.assertEqual('fetch',book['pending']['operation'])
    def test_typed_stop_propagates_before_action_without_cleanup(self):
        def stopped():raise CaretakerPaused('EMERGENCY_HOLD')
        with self.assertRaisesRegex(CaretakerPaused,'EMERGENCY_HOLD'):self.run_stage('harvest_store',stopped)
        self.assertEqual([],self.c.calls);self.assertEqual(0,self.b.prepare_calls)
    def test_typed_stop_inside_real_harvest_primitive_preserves_unresolved_break(self):
        stopped=False
        def after(c):
            nonlocal stopped;stopped=True
        def checkpoint():
            if stopped:raise CaretakerPaused('HOLD_AFTER_BREAK')
        self.c.change_on_mine=after
        with self.assertRaisesRegex(CaretakerPaused,'HOLD_AFTER_BREAK'):self.run_stage('harvest_store',checkpoint)
        outer=json.loads((self.root/'harvest_store/stage.json').read_text())
        inner=json.loads(next((self.root/'harvest_store/field-0').glob('potato-harvest-*.json')).read_text())
        self.assertEqual('harvest',outer['pending']['operation']);self.assertIsNotNone(inner['pending'])
        self.assertEqual(1,len([p for op,p in self.c.calls if op=='mine_block']))
        self.assertFalse(any(op=='interact' for op,p in self.c.calls))
    def test_typed_stop_inside_real_breed_primitive_preserves_single_feed(self):
        self.c.entities=[adult('adult-a',1,[.2,64,.5]),adult('adult-b',2,[1.8,64,.5])]
        self.b.depot['minecraft:wheat']=2;stopped=False
        def after(c):
            nonlocal stopped;stopped=True
        def checkpoint():
            if stopped:raise CaretakerPaused('MANUAL_AFTER_FEED')
        self.c.after_feed=after
        with self.assertRaisesRegex(CaretakerPaused,'MANUAL_AFTER_FEED'):self.run_stage('breed',checkpoint)
        outer=json.loads((self.root/'breed/stage.json').read_text())
        inner=json.loads(next((self.root/'breed/cow').glob('animal-breed-*.json')).read_text())
        self.assertEqual('breed',outer['pending']['operation']);self.assertEqual('feed',inner['pending']['operation'])
        self.assertEqual(1,self.c.feed_count);self.assertEqual('interact_entity',self.c.calls[-1][0])
    def test_stage_uses_real_sheep_breeding_food_and_new_baby_observations(self):
        self.c.entities=[adult('adult-a',1,[.2,64,.5],'minecraft:sheep'),adult('adult-b',2,[1.8,64,.5],'minecraft:sheep')]
        self.profile['livestock_types']=['minecraft:sheep'];self.b.depot['minecraft:wheat']=2
        result,book=self.run_stage('breed');self.assertEqual('done',result['phase'],result)
        self.assertEqual(2,self.c.feed_count);self.assertEqual(0,_counts(self.c.status())['minecraft:wheat'])
        self.assertTrue(any(e['type']=='minecraft:sheep' and e['is_baby'] for e in self.c.entities))
        self.assertIsNone(book['pending'])
    def test_typed_stop_during_sent_attack_preserves_pending_and_no_pickup_or_move(self):
        self.herd();stopped=False
        def after(c):
            nonlocal stopped;stopped=True
        def checkpoint():
            if stopped:raise CaretakerPaused('MANUAL_INPUT')
        self.c.after_attack=after
        with self.assertRaisesRegex(CaretakerPaused,'MANUAL_INPUT'):self.run_stage('surplus',checkpoint)
        book=json.loads((self.root/'surplus/stage.json').read_text())
        self.assertEqual('slaughter_attack',book['pending']['operation']);self.assertEqual(1,len(self.attacks()))
        self.assertFalse(any(op=='collect_item' for op,p in self.c.calls))
        self.assertEqual('material_slaughter_attack',self.c.calls[-1][0])
    def test_safe_approach_cooldown_two_real_hits_pickup_then_keep_adults(self):
        self.herd();self.c.extra['pos']=[.5,64,.5];self.c.extra['on_ground']=True
        result,book=self.run_stage('surplus')
        self.assertEqual('done',result['phase'],result);self.assertEqual(['target','target'],self.c.hits)
        self.assertTrue(any(op=='navigate' for op,p in self.c.calls));self.assertGreater(self.c.cooldown_reads,0)
        self.assertEqual(2,len([e for e in self.c.entities if e['type']=='minecraft:cow']))
        self.assertEqual(2,_counts(self.c.status())['minecraft:beef']);self.assertIsNone(book['pending'])
        self.assertTrue(all(not r.get('server_verified') for r in book['receipts'] if r['kind']=='attack_observation'))
    def test_grounded_reach_still_moves_to_real_airborne_height(self):
        self.herd();self.c.extra.update(pos=[4.5,64,.5],on_ground=True)
        result,_=self.run_stage('surplus');self.assertEqual('done',result['phase'],result)
        moves=[p['target'] for op,p in self.c.calls if op=='navigate']
        self.assertEqual([4.5,64.5,.5],moves[0]);self.assertEqual(['target','target'],self.c.hits)
    def test_named_and_baby_never_attack_missing_metadata_waits(self):
        self.herd();self.c.entities[0]['has_custom_name']=True
        self.c.entities.append(adult('baby',4,[3.5,64,.5],baby=True))
        result,_=self.run_stage('surplus');self.assertEqual('idle',result['phase']);self.assertEqual([],self.attacks())
        self.cycle['id']=2;self.root=self.root/'second';self.root.mkdir()
        self.c.entities[0].pop('has_custom_name')
        result,_=self.run_stage('surplus');self.assertEqual('WAIT_METADATA',result['code']);self.assertEqual([],self.attacks())
    def test_default_twenty_keeps_a_small_loaded_herd(self):
        self.herd();self.profile.pop('adult_keep');result,_=self.run_stage('surplus')
        self.assertEqual('idle',result['phase']);self.assertEqual([],self.attacks())
    def test_field_only_profile_skips_unregistered_livestock(self):
        self.profile.pop('livestock_region');self.profile['livestock_types']=[]
        for stage in ('breed','surplus'):
            result,_=self.run_stage(stage);self.assertEqual('idle',result['phase'])
        self.assertEqual([],self.c.calls)
    def test_false_deposit_receipt_cannot_lose_retained_seed_or_food(self):
        self.c.add('minecraft:baked_potato',10)
        def bad_exchange(c,positions,deposit):
            c.take(POTATO,4);return {'complete':True}
        with patch('farm_caretaker_stages.exchange',side_effect=bad_exchange):
            result,book=self.run_stage('cook_store')
        self.assertEqual('WAIT_RECONCILE',result['code']);self.assertEqual('depot_exchange',book['pending']['operation'])
    def test_protocol_or_cooldown_metadata_absence_cannot_dispatch(self):
        for key in ('material_slaughter_protocol','attack_strength'):
            with self.subTest(key=key):
                self.herd();saved=self.c.extra.pop(key);self.root=self.root/key;self.root.mkdir()
                result,_=self.run_stage('surplus');self.assertEqual('WAIT_CAPABILITY',result['code']);self.assertEqual([],self.attacks())
                self.c.extra[key]=saved
    def test_known_not_sent_rejection_is_resolved_but_unknown_never_replays(self):
        self.herd();self.c.attack_mode='reject';result,book=self.run_stage('surplus')
        self.assertEqual('WAIT_ATTACK_REJECTED',result['code']);self.assertIsNone(book['pending']);self.assertEqual([],self.c.hits)
        self.root=self.root/'unknown';self.root.mkdir();self.c.attack_mode='unknown'
        result,book=self.run_stage('surplus');self.assertEqual('WAIT_RECONCILE',result['code'])
        self.assertEqual('slaughter_attack',book['pending']['operation']);sent=len(self.attacks())
        result,_=self.run_stage('surplus');self.assertEqual('WAIT_RECONCILE',result['code']);self.assertEqual(sent,len(self.attacks()))
    def test_missing_or_foreign_rejection_identity_cannot_clear_saved_intent(self):
        self.herd();self.c.attack_mode='reject'
        for wrong in ('missing_id','old_id','foreign_world','foreign_uuid'):
            with self.subTest(wrong=wrong):
                self.root=self.root/wrong;self.root.mkdir();self.c.bad_rejection=wrong
                result,book=self.run_stage('surplus');self.assertEqual('WAIT_RECONCILE',result['code'])
                self.assertEqual('slaughter_attack',book['pending']['operation'])
    def test_timeout_or_dispatch_receipt_without_real_damage_never_replays(self):
        self.herd()
        for mode in ('timeout','sent'):
            with self.subTest(mode=mode):
                self.root=self.root/mode;self.root.mkdir();self.c.attack_mode=mode;self.c.no_damage=True
                result,book=self.run_stage('surplus');self.assertTrue(book['pending']);sent=len(self.attacks())
                self.run_stage('surplus');self.assertEqual(sent,len(self.attacks()))
    def test_partial_loot_gain_cannot_complete_collection(self):
        self.herd();self.c.partial_loot=True;result,book=self.run_stage('surplus')
        self.assertEqual('WAIT_RECONCILE',result['code']);self.assertEqual('slaughter_loot_proof',book['pending']['operation'])
        self.assertEqual(1,_counts(self.c.status())['minecraft:beef'])
    def test_four_animal_batch_keeps_remaining_surplus_explicit(self):
        self.profile['livestock_region']['max'][0]=28
        self.c.entities=[adult('adult-'+str(i),i,[x,64,.5]) for i,x in enumerate((-1.5,3.5,7.5,11.5,15.5,19.5,23.5),1)]
        result,_=self.run_stage('surplus');self.assertEqual('done',result['phase'],result)
        self.assertEqual(1,result['remaining_surplus']);self.assertEqual(8,len(self.attacks()))
        self.assertEqual(3,len([e for e in self.c.entities if e['type']=='minecraft:cow']))
    def test_reserve_rechecked_during_cooldown_before_second_attack(self):
        self.herd()
        def after(c):c.entities=[e for e in c.entities if e['uuid']!='keep-a']
        self.c.after_attack=after;result,book=self.run_stage('surplus')
        self.assertEqual('WAIT_TARGET',result['code']);self.assertEqual(1,len(self.attacks()));self.assertIsNone(book['pending'])
    def test_sheep_normal_attack_and_real_mutton_cooking_reserve(self):
        self.herd('minecraft:sheep');result,_=self.run_stage('surplus');self.assertEqual('done',result['phase'],result)
        result,book=self.run_stage('cook_store');self.assertEqual('done',result['phase'],result)
        self.assertEqual('minecraft:mutton',self.b.smelt_calls[0][0]['source'])
        self.assertEqual(8,sum(_counts(self.c.status())[i] for i in COOKED));self.assertEqual(4,_counts(self.c.status())[POTATO])
        self.assertIsNone(book['pending'])
    def test_real_empty_smelting_manifest_fetches_fuel_then_actual_delta_and_deposit(self):
        self.c.add('minecraft:beef',10);self.c.add('minecraft:baked_potato',3)
        result,book=self.run_stage('cook_store');self.assertEqual('done',result['phase'],result)
        self.assertEqual([{'minecraft:coal':1}],self.b.fetches);self.assertEqual(2,len(self.b.smelt_calls))
        self.assertEqual(0,_counts(self.c.status())['minecraft:beef'])
        self.assertEqual(8,sum(_counts(self.c.status())[i] for i in COOKED));self.assertEqual(4,_counts(self.c.status())[POTATO])
        self.assertIsNone(book['pending'])
    def test_pending_furnace_manifest_is_not_fuel_retry_authorization(self):
        self.c.add('minecraft:beef',2);self.b.smelt_mode='unknown'
        result,book=self.run_stage('cook_store');self.assertEqual('WAIT_SMELT',result['code']);self.assertEqual([],self.b.fetches)
        self.assertEqual('smelt',book['pending']['operation']);self.run_stage('cook_store');self.assertEqual(1,len(self.b.smelt_calls))
    def test_done_cooking_receipt_without_consumption_and_gain_remains_pending(self):
        self.c.add('minecraft:beef',2);self.c.add('minecraft:coal',1);self.b.smelt_mode='false_done'
        result,book=self.run_stage('cook_store');self.assertEqual('WAIT_RECONCILE',result['code'])
        self.assertEqual('smelt',book['pending']['operation']);self.assertFalse(any(op=='depot_exchange' for op,p in self.c.calls))


if __name__=='__main__':unittest.main()
