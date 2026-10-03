"""Registered wheat harvest: real grain/seed balances and no replay of unknown actions."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from potato_farm import WHEAT_SEEDS, plan as farm_plan, _key
from potato_harvest import BONE, plan, recover_known_loot, run
from test_potato_farm import FarmClient, SPEC, row
from test_potato_harvest import Clock

WHEAT = 'minecraft:wheat'
REQUEST = {**SPEC, 'crop':'wheat'}


class WheatHarvestClient(FarmClient):
    def __init__(self, root, *, seeds=8, age=7):
        super().__init__(potatoes=seeds, farmland=True)
        self.root=Path(root);self.last=None;self.heartbeat=SimpleNamespace(id='wheat-heartbeat')
        self.extra['supervision_lease'].update(id=self.heartbeat.id,remote_finish='guard')
        self.extra['pos'][1]=64.5
        self.inv[10].update(item=WHEAT_SEEDS if seeds else 'minecraft:air',count=seeds,max_stack=64)
        self.inv[11].update(item=BONE,count=16,max_stack=64)
        for pos in farm_plan(REQUEST)['cells']:
            crop=(pos[0],pos[1]+1,pos[2]);self.rows[crop]=row(crop,'Block{minecraft:wheat}[age='+str(age)+']',False)
        self.grains=1;self.seeds=2;self.pickup_delay=3;self.pending_pickup=None
        self.pickup_items={WHEAT,WHEAT_SEEDS};self.bad_ack=False;self.mine_phase='done'
        self.seed_delta=1;self.after_select=None;self.after_mine=None;self.on_scan=None
        self.plant_calls=0
        layout=farm_plan(REQUEST)
        scope={'server':'server','dimension':'minecraft:overworld','layout':layout}
        self.field_key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
        self.registry=self.root/'farms'/self.field_key/'registry.json';self.registry.parent.mkdir(parents=True)
        self.plant_directory=self.root/'original-plant';self.plant_directory.mkdir()
        self.registry.write_text(json.dumps({'scope':scope,'world_session':self.world,'directory':str(self.plant_directory)}))
        self.plant_journal=self.plant_directory/('wheat-farm-'+self.field_key+'.json')
        self.plant_journal.write_text(json.dumps({'scope':scope,'world_session':self.world,'pending':None,'complete':True,
            'cells':{_key(pos):{'planted':True} for pos in layout['cells']}}))

    def status(self):
        state=super().status();state['entities']=copy.deepcopy(self.entities);return state

    def credit(self,item,amount):
        if not amount:return
        slot=next((r for r in self.inv[:36] if r['item']==item and r['count']+amount<=64),None)
        if slot is None:slot=next(r for r in self.inv[:36] if not r['count'])
        slot.update(item=item,count=slot['count']+amount,max_stack=64)

    def request(self,op,**params):
        if op=='scan':
            if self.on_scan:self.on_scan(self)
            if self.pending_pickup is not None:
                self.pending_pickup-=1
                if self.pending_pickup<=0 and self.pickup_delay is not None:
                    for drop in list(self.entities):
                        if drop['stack']['item'] in self.pickup_items:
                            self.credit(drop['stack']['item'],drop['stack']['count']);self.entities.remove(drop)
                    self.pending_pickup=None
            answer=super().request(op,**params)
            for entity in answer['scan_entities']:entity.pop('stack',None)
            return answer
        if op=='select_item':
            answer=super().request(op,**params)
            if self.after_select:self.after_select(self)
            return answer
        if op=='mine_block':
            self.calls.append((op,copy.deepcopy(params)));self.last='wheat-mine-'+str(len(self.calls))
            pos=tuple(params['pos']);assert params['expected_state']=='Block{minecraft:wheat}[age=7]'
            assert self.rows[pos]['state']==params['expected_state']
            assert self.rows[(pos[0],pos[1]-1,pos[2])]['state'].startswith('Block{minecraft:farmland}')
            if self.mine_phase=='done':
                self.rows.pop(pos);self.rev+=1;self.extra['control_revision']=self.rev
                self.extra['supervision_lease']['revision']=self.rev
                for index,(item,amount) in enumerate(((WHEAT,self.grains),(WHEAT_SEEDS,self.seeds))):
                    if amount:
                        ident=len(self.calls)*10+index
                        self.entities.append({'uuid':'owned-'+str(ident),'id':ident,'type':'minecraft:item',
                            'pos':[pos[0]+.5,pos[1]+.2,pos[2]+.5],'stack':{'item':item,'count':amount}})
                self.pending_pickup=self.pickup_delay if self.pickup_delay is not None else 1000
            if self.after_mine:self.after_mine(self)
            return {**self.status(),'phase':self.mine_phase,'id':self.last,
                    'server_confirmed':not self.bad_ack,'outcome_pending':self.bad_ack,
                    'confirmation_scope':'single_target_server_block_update_and_native_sequence_ack',
                    'server_update_seen':True,'server_observed_state':'Block{minecraft:air}',
                    'native_sequence':3,'server_ack_sequence':3,'mining_target':list(pos)}
        if op=='interact':
            self.calls.append((op,copy.deepcopy(params)));self.last='wheat-use-'+str(len(self.calls))
            pos=tuple(params['pos']);assert self.rows[pos]['state']==params['expected_state']
            hand=self.inv[self.selected];assert hand['item']==params['expected_hand']
            if hand['item']==BONE:
                age=int(self.rows[pos]['state'].split('age=')[1][0])
                self.rows[pos]['state']='Block{minecraft:wheat}[age='+str(min(7,age+4))+']'
                hand['count']-=1
            else:
                assert hand['item']==WHEAT_SEEDS and self.rows[pos]['state'].startswith('Block{minecraft:farmland}')
                crop=(pos[0],pos[1]+1,pos[2]);assert crop not in self.rows
                self.rows[crop]=row(crop,'Block{minecraft:wheat}[age=0]',False)
                hand['count']-=self.seed_delta;self.plant_calls+=1
                if not hand['count']:hand['item']='minecraft:air'
            return {**self.status(),'phase':'done','id':self.last}
        raise AssertionError(op)


class WheatHarvestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.client=WheatHarvestClient(self.root)
        self.out=self.root/'harvest';self.clock=Clock()

    def execute(self,request=None,**kwargs):
        return run(self.client,request or REQUEST,self.out,sleep=self.clock.sleep,
                   monotonic=self.clock.monotonic,**kwargs)

    def actions(self):return [(op,p) for op,p in self.client.calls if op in ('mine_block','interact')]
    def book(self,result):return json.loads(Path(result['journal']).read_text())

    def test_four_registered_cells_confirm_grain_and_seeds_separately_then_replant_exact_cells(self):
        result=self.execute();book=self.book(result)
        self.assertEqual(('done',4),(result['phase'],result['harvested_replanted']),result)
        self.assertEqual((4,4,4),(result['wheat_gain'],result['grain_gain'],result['seed_gain']))
        self.assertEqual(12,book['seeds_after']);self.assertEqual(4,book['wheat_after'])
        self.assertNotIn('potato_gain',result);self.assertEqual(8,len(self.actions()))
        mined=[p['pos'] for op,p in self.actions() if op=='mine_block']
        planted=[p['pos'] for op,p in self.actions() if op=='interact']
        self.assertEqual([[p[0],p[1]+1,p[2]] for p in planted],mined)
        self.assertTrue(all(p in farm_plan(REQUEST)['cells'] for p in planted))
        self.assertTrue(all(record['harvest']['native_mining_confirmed'] for record in book['cells'].values()))
        self.assertTrue(all(record['wheat_gain']==1 and record['seed_gain']==2 for record in book['cells'].values()))
        self.assertTrue(all(len(record['plant']['observed_times'])==2 for record in book['cells'].values()))

    def test_zero_seed_drops_are_not_guessed_from_wheat_and_preserve_four_seed_reserve(self):
        self.client.seeds=0
        result=self.execute();book=self.book(result)
        self.assertEqual('done',result['phase'],result)
        self.assertEqual(4,result['wheat_gain']);self.assertEqual(-4,result['seed_gain'])
        self.assertEqual(4,book['seeds_after']);self.assertEqual(4,self.client.plant_calls)

    def test_one_seed_or_many_seeds_do_not_change_observed_grain_credit(self):
        for seeds in (1,3):
            with self.subTest(seeds=seeds),tempfile.TemporaryDirectory() as folder:
                self.client=WheatHarvestClient(folder);self.client.seeds=seeds
                result=run(self.client,{**REQUEST,'cells':[[1,63,0]]},Path(folder)/'harvest',
                           sleep=self.clock.sleep,monotonic=self.clock.monotonic)
                self.assertEqual('done',result['phase'],result)
                self.assertEqual(1,result['wheat_gain']);self.assertEqual(seeds-1,result['seed_gain'])

    def test_seed_reserve_and_each_output_type_need_capacity_before_break(self):
        self.client.inv[10]['count']=4
        result=self.execute();self.assertEqual('WAIT_RESERVE',result['code']);self.assertFalse(self.actions())
        self.client.inv[10]['count']=64
        for row in self.client.inv[:36]:
            if row['slot'] not in (10,12):row.update(item='minecraft:stone',count=64,max_stack=64)
        result=self.execute();self.assertEqual('WAIT_INVENTORY',result['code']);self.assertFalse(self.actions())

    def test_registry_and_original_planting_receipt_cannot_be_bypassed_by_request_coordinates(self):
        self.client.registry.unlink()
        result=self.execute();self.assertEqual('WAIT_REGISTERED_FARM',result['code']);self.assertFalse(self.actions())
        self.assertFalse(self.client.calls)
        with self.assertRaises(ValueError):self.execute({**REQUEST,'authorized':False})
        with self.assertRaises(ValueError):self.execute({**REQUEST,'cells':[[3,63,0]]})

    def test_original_planting_pending_blocks_all_harvest_actions(self):
        planted=json.loads(self.client.plant_journal.read_text());planted['pending']={'operation':'plant'}
        self.client.plant_journal.write_text(json.dumps(planted))
        result=self.execute();self.assertEqual('WAIT_RECONCILE',result['code']);self.assertFalse(self.client.calls)

    def test_only_mature_wheat_on_actual_farmland_is_eligible(self):
        for changed in ('grass','young','other-crop'):
            with self.subTest(changed=changed),tempfile.TemporaryDirectory() as folder:
                self.client=WheatHarvestClient(folder)
                if changed=='grass':self.client.rows[(1,63,0)]=row((1,63,0),'Block{minecraft:grass_block}[snowy=false]')
                elif changed=='young':self.client.rows[(1,64,0)]['state']='Block{minecraft:wheat}[age=6]'
                else:self.client.rows[(1,64,0)]['state']='Block{minecraft:potatoes}[age=7]'
                result=run(self.client,REQUEST,Path(folder)/'harvest',sleep=self.clock.sleep,monotonic=self.clock.monotonic)
                self.assertEqual('waiting',result['phase']);self.assertFalse(self.actions())

    def test_native_done_without_matching_server_removal_proof_is_pending_and_never_replayed(self):
        self.client.bad_ack=True
        first=self.execute();self.assertEqual('WAIT_RECONCILE',first['code']);self.assertEqual(1,len(self.actions()))
        self.assertEqual('harvest',self.book(first)['pending']['operation'])
        again=self.execute();self.assertEqual('WAIT_RECONCILE',again['code']);self.assertEqual(1,len(self.actions()))
        new_out=self.root/'another-output'
        blocked=run(self.client,{**REQUEST,'cells':[[0,63,1]]},new_out,
                    sleep=self.clock.sleep,monotonic=self.clock.monotonic)
        self.assertEqual('WAIT_RECONCILE',blocked['code']);self.assertEqual(Path(first['journal']).resolve(),Path(blocked['active_journal']).resolve())
        self.assertEqual(1,len(self.actions()))

    def test_grain_picked_but_owned_seed_drop_remaining_does_not_replant(self):
        self.client.pickup_items={WHEAT}
        result=self.execute();self.assertEqual('WAIT_LOOT',result['code'])
        self.assertEqual(1,len(self.actions()));self.assertEqual(0,self.client.plant_calls)
        self.assertEqual({WHEAT_SEEDS},{d['item'] for d in result['known_loot']})
        self.assertEqual('await_loot',self.book(result)['pending']['operation'])

    def test_previously_seen_seed_drop_disappearing_without_seed_gain_stays_unreconciled(self):
        self.client.pickup_items={WHEAT}
        def vanish(c):
            if any(row['item']==WHEAT and row['count'] for row in c.inv):
                c.entities=[entity for entity in c.entities if entity['stack']['item']!=WHEAT_SEEDS]
        self.client.on_scan=vanish
        result=self.execute();self.assertEqual('WAIT_LOOT',result['code'])
        self.assertEqual(0,result['remaining_count']);self.assertEqual(0,self.client.plant_calls)
        pending=self.book(result)['pending']
        self.assertEqual(2,pending['observed_drop_totals'][WHEAT_SEEDS])
        self.assertEqual(0,pending['actual_gains'][WHEAT_SEEDS])

    def test_default_and_explicit_potato_harvest_retain_original_scope_hash_and_receipt_reuse(self):
        from test_potato_harvest import HarvestClient
        legacy=HarvestClient();directory=self.root/'legacy-potato'
        first=run(legacy,SPEC,directory,sleep=self.clock.sleep,monotonic=self.clock.monotonic)
        scope={'server':'server','layout':plan(SPEC),'bonemeal':False}
        digest=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
        self.assertEqual('potato-harvest-'+digest+'.json',Path(first['journal']).name)
        sent=len(legacy.calls)
        again=run(legacy,{**SPEC,'crop':'potato'},directory,sleep=self.clock.sleep,monotonic=self.clock.monotonic)
        self.assertTrue(again['prior_receipt_reuse']);self.assertEqual(first['journal'],again['journal'])
        self.assertFalse(any(op in ('mine_block','interact') for op,_ in legacy.calls[sent:]))

    def test_seeds_picked_without_wheat_never_prove_harvest_yield(self):
        self.client.pickup_items={WHEAT_SEEDS}
        result=self.execute();self.assertEqual('WAIT_LOOT',result['code']);self.assertEqual(0,self.client.plant_calls)
        self.assertEqual({WHEAT},{d['item'] for d in result['known_loot']})

    def test_unknown_or_preexisting_drops_block_without_becoming_owned_pickups(self):
        self.client.entities=[{'uuid':'old-seeds','id':999,'type':'minecraft:item','pos':[1.5,64,.5],
                               'stack':{'item':WHEAT_SEEDS,'count':2}}]
        result=self.execute();self.assertEqual('WAIT_ENTITY',result['code']);self.assertFalse(self.actions())

    def test_pickup_callback_receipt_is_not_inventory_proof_and_each_uuid_is_offered_once(self):
        self.client.pickup_delay=None;offered=[]
        def no_change(c,drop,observation):offered.append(drop['uuid']);return True
        first=self.execute(pickup=no_change);self.assertEqual('WAIT_LOOT',first['code'])
        self.assertEqual(2,len(offered));self.assertEqual(2,len(set(offered)))
        second=self.execute(pickup=no_change);self.assertEqual('WAIT_LOOT',second['code'])
        self.assertEqual(2,len(offered));self.assertEqual(1,len(self.actions()))

    def test_pickup_callback_receives_only_exact_wheat_or_seed_id_and_current_stack(self):
        self.client.pickup_delay=None;items=[]
        def collect(c,drop,observation):
            current=next(entity for entity in c.entities if entity['uuid']==drop['uuid'])
            self.assertEqual(drop['stack'],current['stack']);items.append(drop['item'])
            c.credit(current['stack']['item'],current['stack']['count']);c.entities.remove(current)
            return {'movement_only':True}
        result=self.execute({**REQUEST,'cells':[[1,63,0]]},pickup=collect)
        self.assertEqual('done',result['phase'],result);self.assertEqual({WHEAT,WHEAT_SEEDS},set(items))

    def test_floor_change_before_final_action_check_and_after_harvest_never_causes_tilling(self):
        def change(c):c.rows[(1,63,0)]=row((1,63,0),'Block{minecraft:dirt}')
        self.client.after_select=change
        first=self.execute();self.assertIn(first['code'],('WAIT_SOIL','WAIT_AIR'));self.assertFalse(self.actions())
        self.client.after_select=None;self.client.rows[(1,63,0)]=row((1,63,0),'Block{minecraft:farmland}[moisture=7]',False)
        self.client.after_mine=change
        second=self.execute();self.assertEqual('WAIT_SOIL',second['code']);self.assertEqual(1,len(self.actions()))
        self.assertEqual(0,self.client.plant_calls)

    def test_crop_age_change_on_final_pre_mine_scan_sends_no_break(self):
        scans=0
        def change(c):
            nonlocal scans
            scans+=1
            if scans==4:c.rows[(1,64,0)]['state']='Block{minecraft:wheat}[age=6]'
        self.client.on_scan=change
        result=self.execute();self.assertEqual('WAIT_GROWTH',result['code']);self.assertFalse(self.actions())
        self.assertEqual('Block{minecraft:wheat}[age=6]',self.client.rows[(1,64,0)]['state'])

    def test_replant_final_scan_preserves_a_crop_that_appeared_after_loot_reconciliation(self):
        ready_scans=0
        def occupied(c):
            nonlocal ready_scans
            books=list(self.out.glob('wheat-harvest-*.json')) if self.out.exists() else []
            if books and (json.loads(books[0].read_text()).get('pending') or {}).get('operation')=='await_replant':
                ready_scans+=1
                if ready_scans==2:c.rows[(1,64,0)]=row((1,64,0),'Block{minecraft:wheat}[age=7]',False)
        self.client.on_scan=occupied
        result=self.execute({**REQUEST,'cells':[[1,63,0]]})
        self.assertEqual('WAIT_AIR',result['code']);self.assertEqual(1,len(self.actions()))
        self.assertEqual(0,self.client.plant_calls)
        self.assertEqual('Block{minecraft:wheat}[age=7]',self.client.rows[(1,64,0)]['state'])

    def test_exact_minus_one_seed_and_age_zero_are_required_after_replant(self):
        self.client.seed_delta=0
        result=self.execute({**REQUEST,'cells':[[1,63,0]]})
        self.assertEqual('WAIT_RECONCILE',result['code']);self.assertEqual('plant',self.book(result)['pending']['operation'])
        self.assertEqual(2,len(self.actions()));self.execute({**REQUEST,'cells':[[1,63,0]]});self.assertEqual(2,len(self.actions()))

    def test_four_cell_budget_and_read_only_loot_recovery_preserve_original_request(self):
        with self.assertRaises(ValueError):self.execute(max_cells=5)
        self.client.pickup_delay=None
        first=self.execute();before=len(self.actions())
        recovered=recover_known_loot(self.client,REQUEST,self.out,sleep=self.clock.sleep,monotonic=self.clock.monotonic)
        self.assertEqual('WAIT_LOOT',recovered['code']);self.assertEqual(before,len(self.actions()))
        self.assertEqual(first['journal'],recovered['journal'])


if __name__=='__main__':unittest.main()
