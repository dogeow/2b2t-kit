import copy
import json
from pathlib import Path
import tempfile
import unittest

from potato_farm import (ENTITY_SCOPE, FarmWait, POTATO, PROOF_SCOPE, action_proved,
                         plan, run, survey_rows, hydration_covers, _counts)

SPEC = {'authorized': True, 'center': [0, 63, 0]}


def row(pos, state, solid=True, fluid=False):
    return {'pos': list(pos), 'state': state, 'solid': solid, 'fluid': fluid,
            'block_entity': False, 'spawn_block_light': 9, 'passable': not solid,
            'replaceable': False, 'block_light': 9, 'sky_light': 15}


class FarmClient:
    world = 'world-1'; rev = 3; task = 'farm-task'; server = 'server:25565'
    def __init__(self, potatoes=24, farmland=False):
        self.calls = []; self.time = 1000; self.fail_op = None; self.no_change = None
        self.after_interact = None; self.correct_plant = False; self.plant_scans = 0
        self.rows = {}; layout = plan(SPEC)
        for x in range(-3, 4):
            for z in range(-3, 4):
                self.rows[(x, 62, z)] = row((x, 62, z), 'Block{minecraft:dirt}')
                self.rows[(x, 63, z)] = row((x, 63, z), 'Block{minecraft:grass_block}[snowy=false]')
        self.rows[(0, 63, 0)] = row((0, 63, 0), 'Block{minecraft:water}[level=0]', False, True)
        if farmland:
            for p in layout['cells']:
                self.rows[tuple(p)] = row(p, 'Block{minecraft:farmland}[moisture=7]', False)
        self.inv = [{'slot': i, 'item': 'minecraft:air', 'count': 0, 'max_stack': 1} for i in range(43)]
        self.inv[0].update(item='minecraft:iron_hoe', count=1, max_stack=1, durability=250, max_durability=250)
        self.inv[10].update(item=POTATO if potatoes else 'minecraft:air', count=potatoes, max_stack=64)
        self.selected = 0; self.entities = []; self.scope = ENTITY_SCOPE
        self.extra = {'connected': True, 'world_session': self.world, 'control_revision': self.rev,
                      'manual_movement': False, 'screen': '', 'health': 20, 'food': 20,
                      'recent_hurt_at': 0, 'guard_armed': True, 'guard_pve_only': True,
                      'guard_busy': False, 'under_water': False, 'safety_hold': {'active': False},
                      'dimension': 'minecraft:overworld', 'game_mode': 'survival',
                      'pos': [.5, 64, .5], 'entities': [], 'flight': True,
                      'supervision_lease': {'kind': 'materials', 'job_session': self.task,
                                            'world_session': self.world, 'revision': self.rev}}

    def status(self):
        self.time += 10
        inv = copy.deepcopy(self.inv); hand = copy.deepcopy(inv[self.selected]); hand.pop('slot')
        slots = [{'slot': i, 'item': 'minecraft:air', 'count': 0, 'max_stack': 1} for i in range(46)]
        for i in range(36):
            n = i+36 if i < 9 else i
            slots[n] = {**inv[i], 'slot': n}
        return {**copy.deepcopy(self.extra), 'time': self.time, 'inventory': inv,
                'hand': hand, 'selected_slot': self.selected,
                'menu': {'id': 0, 'type': 'InventoryMenu', 'cursor': {'item': 'minecraft:air', 'count': 0}, 'slots': slots}}

    def request(self, op, **params):
        self.calls.append((op, copy.deepcopy(params))); self.time += 50
        if op == 'scan':
            if self.correct_plant and self.after_interact == 'plant':
                self.plant_scans += 1
                if self.plant_scans == 2:
                    self.rows.pop(self.last_crop, None)
                    self.inv[self.selected].update(item=POTATO, count=self.inv[self.selected]['count']+1)
            state = self.status(); lo, hi = params['min'], params['max']
            assert params.get('details') is True
            state.update(blocks=[copy.deepcopy(r) for p, r in self.rows.items()
                                 if all(a <= b <= d for a, b, d in zip(lo, p, hi))],
                         scan_entities=copy.deepcopy(self.entities), scan_entity_scope=self.scope)
            return state
        if op == 'select_item':
            source = params['slot']; assert self.inv[source]['item'] == params['item']
            if source >= 9:
                self.inv[source], self.inv[5] = self.inv[5], self.inv[source]
                self.inv[source]['slot'] = source; self.inv[5]['slot'] = 5; source = 5
            self.selected = source
            return {**self.status(), 'phase': 'done'}
        assert op == 'interact', op
        pos = tuple(params['pos']); floor = self.rows[pos]
        assert params['expected_state'] == floor['state']
        hand = self.inv[self.selected]; assert hand['item'] == params['expected_hand']
        operation = 'till' if hand['item'].endswith('_hoe') else 'plant'
        if self.fail_op == operation:
            return {**self.status(), 'phase': 'waiting', 'id': 'unknown', 'detail': 'unconfirmed'}
        if self.no_change != operation:
            if operation == 'till':
                self.rows[pos] = row(pos, 'Block{minecraft:farmland}[moisture=0]', False)
                hand['durability'] -= 1
            else:
                assert 'minecraft:farmland' in floor['state']
                self.last_crop = (pos[0], pos[1]+1, pos[2]); self.plant_scans = 0
                self.rows[self.last_crop] = row(self.last_crop, 'Block{minecraft:potatoes}[age=0]', False)
                hand['count'] -= 1
                if not hand['count']: hand.update(item='minecraft:air')
        self.after_interact = operation
        return {**self.status(), 'phase': 'done', 'id': 'native-'+str(len(self.calls))}

    def interact_calls(self): return [p for op, p in self.calls if op == 'interact']


class FarmPlanningTest(unittest.TestCase):
    def test_generic_large_coordinates_have_24_cells_and_center_excluded(self):
        layout = plan({'authorized': True, 'center': [761021, 63, 797869]})
        self.assertEqual(24, len(layout['cells'])); self.assertEqual(48, layout['maximum_interactions'])
        self.assertEqual([761019, 63, 797867], layout['cells'][0])
        self.assertEqual([761023, 63, 797871], layout['cells'][-1])
        self.assertNotIn(layout['center'], layout['cells'])
    def test_actual43_slot_native_snapshot_counts_only_carried0to35(self):
        fixture=json.loads((Path(__file__).parent/'testdata/potato_inventory_26_1_2.json').read_text())
        self.assertEqual(43,len(fixture['inventory']))
        carried=_counts(fixture)
        expected={}
        for r in fixture['inventory']:
            if r['slot']<36 and r['count']: expected[r['item']]=expected.get(r['item'],0)+r['count']
        self.assertEqual(expected,dict(carried))
        # Extra equipment slots are observed and validated but never counted as carried.
        fixture['inventory'][41].update(item=POTATO,count=64)
        fixture['inventory'][42].update(item=POTATO,count=64)
        self.assertEqual(expected,dict(_counts(fixture)))
    def test_vanilla_water_search_covers_every_samefloor_cell_and_rejects_vertical_mismatch(self):
        layout=plan(SPEC)
        self.assertTrue(all(hydration_covers(p,layout['center']) for p in layout['cells']))
        self.assertTrue(hydration_covers([0,63,0],[4,64,4]))
        self.assertFalse(hydration_covers([0,63,0],[5,63,0]))
        self.assertFalse(hydration_covers([0,63,0],[0,62,0]))
        self.assertFalse(hydration_covers([0,63,0],[0,65,0]))
    def test_radius_one_is_bounded_to_eight_cells(self):
        self.assertEqual(8, plan({**SPEC, 'radius': 1})['potatoes'])
    def test_authorization_coordinates_radius_and_budget_types(self):
        for request in ({}, {**SPEC, 'authorized': False}, {**SPEC, 'radius': 3},
                        {**SPEC, 'radius': True}, {**SPEC, 'center': [0.5, 63, 0]},
                        {**SPEC, 'center': [0, 318, 0]}):
            with self.subTest(request=request), self.assertRaises(ValueError): plan(request)
    def test_sparse_air_requires_native_typed_rows(self):
        c = FarmClient(); data = c.request('scan', min=plan(SPEC)['scan_min'], max=plan(SPEC)['scan_max'], details=True)
        self.assertEqual(98, len(survey_rows(data, plan(SPEC), {})))
        data['blocks'][0].pop('block_entity')
        with self.assertRaises(FarmWait) as error: survey_rows(data, plan(SPEC), {})
        self.assertEqual('WAIT_SCAN', error.exception.code)
    def test_duplicate_and_outside_scan_rows_are_rejected(self):
        for bad in ('duplicate', 'outside'):
            c=FarmClient(); data=c.request('scan', min=plan(SPEC)['scan_min'], max=plan(SPEC)['scan_max'], details=True)
            data['blocks'].append(copy.deepcopy(data['blocks'][0]) if bad == 'duplicate' else row([99, 63, 99], 'Block{minecraft:dirt}'))
            with self.assertRaises(FarmWait): survey_rows(data, plan(SPEC), {})
    def test_crop_light_uses_real_block_light_rather_than_day_sky(self):
        c=FarmClient(); c.rows[(-2,63,-2)]['spawn_block_light']=0
        data=c.request('scan', min=plan(SPEC)['scan_min'], max=plan(SPEC)['scan_max'], details=True)
        with self.assertRaises(FarmWait) as error: survey_rows(data, plan(SPEC), {})
        self.assertEqual('WAIT_LIGHT', error.exception.code)


class FarmRunTest(unittest.TestCase):
    def run_farm(self, c, **kwargs):
        with tempfile.TemporaryDirectory() as out:
            result=run(c, SPEC, out, **kwargs)
            book=json.loads(next(Path(out).glob('potato-farm-*.json')).read_text())
            return result, book
    def test_all24_till_then_plant_stack_once(self):
        c=FarmClient(); result, book=self.run_farm(c)
        self.assertEqual('done', result['phase']); self.assertEqual(24, result['planted_cells'])
        self.assertFalse(result['server_verified']); self.assertEqual(PROOF_SCOPE, result['verification_scope'])
        self.assertEqual(48, len(c.interact_calls()))
        self.assertEqual(2, sum(op=='select_item' for op,_ in c.calls)); self.assertFalse(any(op=='slot_click' for op,_ in c.calls))
        self.assertTrue(all(p['expected_hand']=='minecraft:iron_hoe' for p in c.interact_calls()[:24]))
        self.assertTrue(all(p['expected_hand']==POTATO for p in c.interact_calls()[24:]))
        self.assertEqual(226, c.inv[0]['durability']); self.assertEqual(0, sum(r['count'] for r in c.inv if r['item']==POTATO))
        self.assertIsNone(book['pending']); self.assertTrue(book['complete'])
    def test_existing_farmland_needs_only24_plant_calls(self):
        c=FarmClient(farmland=True); result, _=self.run_farm(c)
        self.assertEqual('done', result['phase']); self.assertEqual(24, len(c.interact_calls()))
        self.assertEqual(1, sum(op=='select_item' for op,_ in c.calls)); self.assertEqual(250,c.inv[0]['durability'])
    def test_larger_potato_stack_loses_exact24(self):
        c=FarmClient(potatoes=48); result,_=self.run_farm(c)
        self.assertEqual('done',result['phase']); self.assertEqual(24, sum(r['count'] for r in c.inv if r['item']==POTATO))
    def test_known_four_cell_batches_continue_without_repeating_completed_cells(self):
        c=FarmClient()
        with tempfile.TemporaryDirectory() as out:
            for i in range(6):
                result=run(c,SPEC,out,max_cells=4)
                self.assertEqual(4*(i+1),result['planted_cells'])
                self.assertEqual('done' if i==5 else 'FARM_BATCH',result.get('code') or result['phase'])
            self.assertEqual(48,len(c.interact_calls()))
            again=run(c,SPEC,out,max_cells=4)
            self.assertEqual('done',again['phase']); self.assertEqual(48,len(c.interact_calls()))
    def test_unconfirmed_interact_is_durable_and_not_replayed(self):
        c=FarmClient(); c.fail_op='till'
        with tempfile.TemporaryDirectory() as out:
            result=run(c,SPEC,out); self.assertEqual('WAIT_RECONCILE',result['code'])
            self.assertEqual(1,len(c.interact_calls()))
            c.fail_op=None; repeat=run(c,SPEC,out)
            self.assertEqual('WAIT_RECONCILE',repeat['code']); self.assertEqual(1,len(c.interact_calls()))
    def test_done_without_real_crop_count_delta_stops(self):
        c=FarmClient(farmland=True); c.no_change='plant'; result,book=self.run_farm(c)
        self.assertEqual('WAIT_RECONCILE',result['code']); self.assertEqual(0,result['planted_cells'])
        self.assertEqual('plant',book['pending']['operation']); self.assertEqual(1,len(c.interact_calls()))
    def test_late_prediction_rollback_is_not_claimed_as_success(self):
        c=FarmClient(farmland=True); c.correct_plant=True; result,book=self.run_farm(c)
        self.assertEqual('WAIT_RECONCILE',result['code']); self.assertEqual(0,result['planted_cells'])
        self.assertIsNotNone(book['pending']); self.assertEqual(1,len(c.interact_calls()))
    def test_missing_water_light_entities_containers_or_air_prevents_any_write(self):
        for change,code in (('water','WAIT_WATER'),('light','WAIT_LIGHT'),('entity','WAIT_ENTITY'),
                            ('container','WAIT_CONTAINER'),('air','WAIT_AIR'),('flow','WAIT_WATER')):
            c=FarmClient()
            if change=='water': c.rows[(0,63,0)]=row((0,63,0),'Block{minecraft:water}[level=1]',False,True)
            if change=='light': c.rows[(-2,63,-2)]['spawn_block_light']=8
            if change=='entity': c.entities=[{'id':1,'uuid':'cow','type':'minecraft:cow','pos':[-2,64,-2]}]
            if change=='container': c.rows[(-3,63,-3)]['block_entity']=True
            if change=='air': c.rows[(-2,64,-2)]=row((-2,64,-2),'Block{minecraft:short_grass}',False)
            if change=='flow': c.rows[(-3,63,-3)]=row((-3,63,-3),'Block{minecraft:water}[level=1]',False,True)
            with self.subTest(change=change):
                result,_=self.run_farm(c); self.assertEqual(code,result['code']); self.assertTrue(all(op=='scan' for op,_ in c.calls))
    def test_manual_safety_world_and_guard_stop_without_write(self):
        for field,value in (('manual_movement',True),('health',19),('guard_busy',True),('connected',False),
                            ('world_session','other'),('safety_hold',{'active':True}),('planter_active',True)):
            c=FarmClient(); c.extra[field]=value
            with self.subTest(field=field):
                result,_=self.run_farm(c); self.assertEqual('waiting',result['phase']); self.assertEqual([],c.calls)
    def test_injury_during_run_prevents_all_following_actions(self):
        c=FarmClient(); first=[True]
        original=c.request
        def hurt(op,**params):
            answer=original(op,**params)
            if op=='interact' and first[0]: c.extra.update(health=19,recent_hurt_at=777); first[0]=False
            return answer
        c.request=hurt; result,book=self.run_farm(c)
        self.assertEqual('WAIT_SAFETY',result['code']); self.assertEqual(1,len(c.interact_calls())); self.assertIsNotNone(book['pending'])
    def test_saved_injury_marker_does_not_auto_resume_after_healing(self):
        c=FarmClient()
        with tempfile.TemporaryDirectory() as out:
            result=run(c,SPEC,out,max_cells=4); self.assertEqual('FARM_BATCH',result['code'])
            count=len(c.interact_calls()); c.extra['recent_hurt_at']=12
            resumed=run(c,SPEC,out,max_cells=4)
            self.assertEqual('WAIT_SAFETY',resumed['code']); self.assertEqual(count,len(c.interact_calls()))
    def test_missing_supplies_and_hoe_reserve_are_real(self):
        for missing,code in (('potato','WAIT_POTATO'),('hoe','WAIT_HOE'),('enchanted','WAIT_HOE')):
            c=FarmClient(potatoes=23 if missing=='potato' else 24)
            if missing=='hoe': c.inv[0]['durability']=24
            if missing=='enchanted': c.inv[0]['enchantments']=[{'id':'minecraft:unbreaking','level':1}]
            with self.subTest(missing=missing):
                result,_=self.run_farm(c); self.assertEqual(code,result['code']); self.assertFalse(c.interact_calls())
    def test_out_of_reach_does_not_dispatch_world_interaction(self):
        c=FarmClient(); c.extra['pos']=[10.5,64,.5]; result,_=self.run_farm(c)
        self.assertEqual('WAIT_REACH',result['code']); self.assertFalse(c.interact_calls())
    def test_native_timeout_is_retained_without_second_interaction(self):
        c=FarmClient(); original=c.request
        def timeout(op,**params):
            if op=='interact': c.calls.append((op,params)); raise RuntimeError('native operation timed out')
            return original(op,**params)
        c.request=timeout
        with tempfile.TemporaryDirectory() as out:
            result=run(c,SPEC,out); self.assertEqual('WAIT_CONTROL',result['code'])
            result=run(c,SPEC,out); self.assertEqual('WAIT_RECONCILE',result['code']); self.assertEqual(1,len(c.interact_calls()))
    def test_native_scan_inventory_is_used_even_if_periodic_status_remains_old(self):
        c=FarmClient(farmland=True); real_status=c.status; real_request=c.request; stale=[None]
        def periodic(): return copy.deepcopy(stale[0]) if stale[0] is not None else real_status()
        def native(op,**params):
            before=real_status(); c.status=real_status
            try: answer=real_request(op,**params)
            finally: c.status=periodic
            if op=='interact' and stale[0] is None: stale[0]=before
            return answer
        c.status=periodic; c.request=native
        result,book=self.run_farm(c,max_cells=1)
        self.assertEqual('FARM_BATCH',result['code']); self.assertEqual(1,result['planted_cells'])
        self.assertEqual(24,periodic()['hand']['count']); self.assertEqual(23,c.inv[c.selected]['count'])
        record=next(iter(book['cells'].values()))['plant']
        self.assertEqual(24,record['hand_before']['count']); self.assertEqual(23,record['hand_after']['count'])
    def test_delayed_server_hoe_durability_uses_read_only_observation_without_repeating_till(self):
        c=FarmClient(); native=c.request; delayed=[False]; scans=[0]
        def call(op,**params):
            if op=='scan' and delayed[0]:
                scans[0]+=1
                if scans[0]==3: c.inv[0]['durability']-=1
            answer=native(op,**params)
            if op=='interact' and params['expected_hand'].endswith('_hoe') and not delayed[0]:
                c.inv[0]['durability']+=1; delayed[0]=True
            return answer
        c.request=call; result,_=self.run_farm(c,max_cells=1)
        self.assertEqual('FARM_BATCH',result['code']); self.assertEqual(1,result['planted_cells'])
        self.assertEqual(2,len(c.interact_calls())); self.assertGreaterEqual(scans[0],4)
    def test_no_harvest_move_reconnect_logout_or_generic_item_use(self):
        c=FarmClient(); self.run_farm(c)
        self.assertLessEqual({op for op,_ in c.calls},{'scan','select_item','interact'})
    def test_budget_must_be_strict_integer_bounded(self):
        c=FarmClient()
        with tempfile.TemporaryDirectory() as out:
            for n in (True,0,25):
                with self.assertRaises(ValueError): run(c,SPEC,out,max_cells=n)
            self.assertEqual([],c.calls)


if __name__=='__main__': unittest.main()

class CompletedInventoryAuditTest(unittest.TestCase):
    def test_verified_complete_field_can_be_audited_after_independent_harvest_gain(self):
        with tempfile.TemporaryDirectory() as d:
            c=FarmClient();first=run(c,SPEC,d)
            self.assertEqual(first['phase'],'done')
            before=sum(op=='interact' for op,_ in c.calls)
            c.inv[10].update(item=POTATO,count=15,max_stack=64)
            second=run(c,SPEC,d)
            self.assertEqual(second['phase'],'done')
            self.assertEqual(second['planted_cells'],24)
            self.assertEqual(sum(op=='interact' for op,_ in c.calls),before)
    def test_partial_planting_still_rejects_unrelated_inventory_change(self):
        with tempfile.TemporaryDirectory() as d:
            c=FarmClient();first=run(c,SPEC,d,max_cells=4)
            self.assertEqual(first['code'],'FARM_BATCH')
            next(row for row in c.inv if row['item']==POTATO and row['count'])['count']+=1
            result=run(c,SPEC,d)
            self.assertEqual(result['code'],'WAIT_RECONCILE')
