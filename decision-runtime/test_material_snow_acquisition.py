"""Offline contracts for bounded natural surface-snow acquisition."""
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_jobs.acquisition import acquire
from material_jobs.discovery import choose_region
from material_jobs.equipment import prepare
from material_jobs.snow_harvest import (SNOW, SNOW_BLOCK, SNOWBALL, candidate,
                                        source_yield)
from material_jobs.bobby_snow_route import ledger_state as bobby_ledger, outbound as bobby_outbound
from material_jobs.bobby_snow_route import authorizes_natural_snowpack


def block(pos, name, *, state=None, solid=True, passable=False,
          fluid=False, block_entity=False):
    return {'pos': list(pos), 'state': state or 'Block{' + name + '}',
            'solid': solid, 'passable': passable, 'fluid': fluid,
            'block_entity': block_entity}


def patch_rows(source=SNOW, layers=1, centre=(3, 64, 3)):
    rows = [block((x, 63, z), 'minecraft:dirt') for x in range(7) for z in range(7)]
    state = ('Block{minecraft:snow}[layers=' + str(layers) + ']'
             if source == SNOW else 'Block{minecraft:snow_block}')
    rows.append(block(centre, source, state=state,
                      solid=source == SNOW_BLOCK, passable=source == SNOW))
    return rows


def profile(item, centre=(3, 64, 3)):
    return {'protected_regions': [{'min': [-100, 50, -100], 'max': [-80, 95, -80]}],
            'depots': [[-94, 64, -94]], 'search_origin': [-90, 80, -90],
            'resource_regions': [{'item': item,
                                  'min': [centre[0]-3, centre[1], centre[2]-3],
                                  'max': [centre[0]+3, centre[1], centre[2]+3]}]}


class FakeClient:
    world = 'snow-world'

    def __init__(self, item, rows, *, silk=True, protocol=1, before=0, slot=20):
        self.item, self.rows, self.actions, self.last = item, copy.deepcopy(rows), [], None
        self.rev=7;self.native_inflight=None
        inventory = [{'slot': i, 'item': 'minecraft:air', 'count': 0, 'max_stack': 64}
                     for i in range(36)]
        inventory[slot] = {'slot': slot, 'item': 'minecraft:diamond_shovel', 'count': 1,
                           'durability': 600, 'max_stack': 1,
                           'enchantments': ([{'id': 'minecraft:silk_touch', 'level': 1}]
                                            if silk else [])}
        if before:
            inventory[1] = {'slot': 1, 'item': item, 'count': before, 'max_stack': 64}
        self.state = {'world_session': self.world, 'pos': [3.5, 70.1, 3.5],
                      'connected':True,'control_revision':self.rev,'navigating':False,'native_material_busy':False,
                      'health': 20, 'food': 20, 'under_water': False,
                      'guard_armed': True, 'guard_pve_only': True,
                      'manual_movement': False, 'safety_hold': {'active': False},
                      'flight': True, 'air_only_navigation_protocol': 2,
                      'snow_harvest_protocol': protocol, 'projection_selection': {},
                      'time': 1, 'inventory': inventory}

    def status(self):
        return copy.deepcopy(self.state)

    def checked(self, op, **params):
        reply = self.request(op, **params)
        if reply.get('phase') != 'done':
            raise RuntimeError(reply.get('detail', 'failed'))
        return reply

    def request(self, op, **params):
        self.actions.append((op, copy.deepcopy(params)))
        self.last = 'offline-' + str(len(self.actions))
        if op == 'scan':
            total=math.prod(b-a+1 for a,b in zip(params['min'],params['max']))
            return {'id':self.last,'phase':'done','world_session':self.world,
                    'control_revision':self.rev,'scan_start_revision':self.rev,'scan_end_revision':self.rev,
                    'scan_cells_read':total,'scan_total_cells':total,
                    'blocks': [copy.deepcopy(row) for row in self.rows
                               if all(params['min'][i] <= row['pos'][i] <= params['max'][i]
                                      for i in range(3))]}
        if op == 'navigate':
            self.state['pos'] = list(params['target'])
            return {'phase': 'done'}
        if op == 'select_item':
            source = self.state['inventory'][params['slot']]
            self.assert_tool(source, params['item'])
            selected = params['slot'] if params['slot'] < 9 else 5
            if selected != params['slot']:
                self.state['inventory'][params['slot']], self.state['inventory'][selected] = (
                    dict(self.state['inventory'][selected], slot=params['slot']),
                    dict(source, slot=selected))
            self.state['selected_slot'] = selected
            self.state['hand'] = copy.deepcopy(self.state['inventory'][selected])
            return {'phase': 'done'}
        if op == 'mine_block':
            target = next(row for row in self.rows if row['pos'] == params['pos'])
            assert target['state'] == params['expected_state']
            hand = self.state['hand']
            silk = any(e.get('id') == 'minecraft:silk_touch' and e.get('level', 0) > 0
                       for e in hand.get('enchantments', []))
            if self.item == SNOWBALL:
                assert params['required_plain_shovel'] is True and not silk
            else:
                assert params['required_silk_shovel'] is True and silk
            gain = source_yield(target, self.item)
            self.rows.remove(target)
            output = next((row for row in self.state['inventory']
                           if row.get('item') == self.item and row.get('count')), None)
            if output is None:
                output = next(row for row in self.state['inventory'] if not row.get('count'))
                output.update(item=self.item, count=0, max_stack=64)
            output['count'] += gain
            hand['durability'] -= 1
            self.state['inventory'][self.state['selected_slot']]['durability'] -= 1
            self.state['time'] += 1
            return {'phase': 'done'}
        raise AssertionError(op)

    @staticmethod
    def assert_tool(row, item):
        assert row['item'] == item and row['count'] == 1


class SnowAcquisitionTest(unittest.TestCase):
    def setUp(self):
        settled = patch('material_jobs.navigation.settled_state',
                        side_effect=lambda c, *args, **kwargs: c.status())
        settled.start(); self.addCleanup(settled.stop)

    def test_unproved_travel_scan_cannot_navigate_or_harvest_snow(self):
        for malformed in ('missing','partial','stale_id','foreign_world','revision'):
            with self.subTest(malformed=malformed),tempfile.TemporaryDirectory() as directory:
                c=FakeClient(SNOW,patch_rows(),silk=True);original=c.request
                def request(op,**params):
                    reply=original(op,**params)
                    if op=='scan':
                        if malformed=='missing':reply.pop('scan_cells_read')
                        elif malformed=='partial':reply['scan_cells_read']-=1
                        elif malformed=='stale_id':reply['id']='previous-read'
                        elif malformed=='foreign_world':reply['world_session']='foreign-world'
                        else:reply['scan_end_revision']+=1
                    return reply
                c.request=request
                result=acquire(c,SNOW,1,profile(SNOW),directory,lambda:None)
                self.assertEqual('waiting',result['phase'])
                self.assertNotIn('navigate',[op for op,_ in c.actions])
                self.assertNotIn('mine_block',[op for op,_ in c.actions])

    def test_silk_touch_layer_yield_has_exact_inventory_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(SNOW, patch_rows(layers=3), silk=True)
            result = acquire(c, SNOW, 3, profile(SNOW), directory, lambda: None)
            self.assertEqual(('done', 0, 3, 3),
                             (result['phase'], result['before'], result['after'], result['gained']))
            mine = next(params for op, params in c.actions if op == 'mine_block')
            self.assertEqual((True, 5, 'minecraft:diamond_shovel'),
                             (mine['required_silk_shovel'], mine['expected_tool_slot'],
                              mine['expected_tool_item']))
            ledger = json.loads((Path(directory) / 'acquisition-snow.json').read_text())
            receipt = next(row for key, row in ledger['visited'].items()
                           if key.startswith('snow-block-'))
            self.assertEqual(('collected', 3, 3, 'silk_touch'),
                             (receipt['state'], receipt['expected_gain'], receipt['gained'],
                              receipt['tool_mode']))

    def test_far_discovered_snow_patch_keeps_region_and_arrives_in_two_segments(self):
        rows = patch_rows()
        rows = [dict(row, pos=[row['pos'][0] + 247, row['pos'][1], row['pos'][2]])
                for row in rows]
        far = profile(SNOW, centre=(250, 64, 3))
        far.update(search_origin=[0, 80, 0], search_radius=256)
        far['resource_regions'][0].update(source='natural_survey', surface_y=64)
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(SNOW, rows, silk=True)
            c.state['pos'] = [-250.5, 145, 3.5]
            c.out = Path(directory)
            result = acquire(c, SNOW, 1, far, directory, lambda: None)
            self.assertEqual(('done', 1, 1),
                             (result['phase'], result['after'], result['gained']))
            ledger = json.loads((Path(directory) / 'acquisition-snow.json').read_text())
            receipt = next(row for key, row in ledger['visited'].items()
                           if key.startswith('snow-block-'))
            starts = [row for row in receipt['route']
                      if row.get('event') == 'resource_route_segment_start']
            self.assertEqual(2, len(starts))
            self.assertTrue(all(row['final_target'] == [250.5, 67.1, 3.5]
                                for row in starts))
            self.assertEqual(1, sum(op == 'mine_block' for op, _ in c.actions))

    def test_completed_seed_expedition_returns_via_host_without_python_home_coordinates(self):
        class ExpeditionClient(FakeClient):
            def request(self, op, **params):
                if op == 'navigate' and params.get('snow_expedition_return'):
                    self.actions.append((op, copy.deepcopy(params)))
                    self.last = 'offline-' + str(len(self.actions))
                    self.state['pos'] = [0.5, 160.0, 0.5]
                    return {'id': self.last, 'world_session': self.world,
                            'phase': 'done'}
                return super().request(op, **params)

        with tempfile.TemporaryDirectory() as directory:
            c = ExpeditionClient(SNOW, patch_rows(), silk=True)
            c.snow_expedition_token = '11111111-1111-1111-1111-111111111111'
            c.snow_expedition_route_id = '22222222-2222-2222-2222-222222222222'
            result = acquire(c, SNOW, 1, profile(SNOW), directory, lambda: None)
            self.assertEqual(('done', 1, True),
                             (result['phase'], result['after'],
                              result['return_home']['host_target']))
            returning = [params for op, params in c.actions
                         if op == 'navigate' and params.get('snow_expedition_return')]
            self.assertEqual(1, len(returning))
            self.assertNotIn('target', returning[0])
            self.assertNotIn('snow_expedition_token', c.__dict__)
            self.assertEqual([0.5,160.0,0.5],c.anchor)

    def test_completed_bobby_harvest_returns_over_same_segments_to_host_home(self):
        class BobbyClient(FakeClient):
            task='materials-job'
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                self.rev=7
                self.state.update(server='test:25565',dimension='minecraft:overworld',
                    control_revision=self.rev,flight=True,guard_armed=True,
                    guard_pve_only=True,manual_movement=False,under_water=False,
                    health=20,food=20,safety_hold={'active':False},
                    navigating=False,native_material_busy=False,
                    supervision_lease={'kind':'materials','job_session':self.task,
                        'world_session':self.world,'revision':self.rev,
                        'search_origin':[-90.5,145.0,-90.5],
                        'return_target':{'x':-94.5,'z':-94.5,'cruise_y':160.0,
                            'dimension':'minecraft:overworld','source':'saved_home'}})
            def request(self,op,**params):
                if op in ('guard','navigate'):
                    self.actions.append((op,copy.deepcopy(params)))
                    self.last='offline-'+str(len(self.actions));self.state['time']+=1
                    if op=='navigate':self.state['pos']=list(params['target'])
                    return {'id':self.last,'world_session':self.world,'phase':'done'}
                return super().request(op,**params)

        with tempfile.TemporaryDirectory() as directory:
            c=BobbyClient(SNOW,patch_rows(),silk=True)
            resource=Path(directory)/'resource.json'
            discovery={'schema':1,'item':SNOW,'tiles':{}}
            bobby_ledger(discovery,'test:25565','minecraft:overworld')
            resource.write_text(json.dumps(discovery))
            cached={'source':'bobby_cache','cache_server':'test',
                    'dimension':'minecraft:overworld','chunk':[0,0],'tile':[0,0],
                    'target':[8.5,200.0,8.5],'region_file':'r.0.0.mca',
                    'fingerprint':'a'*64,'mtime_ns':100,'ctime_ns':101,
                    'size':8192,'file_id':7,
                    'biomes':['minecraft:snowy_plains'],'distance_sq':50.0}
            route=bobby_outbound(c,cached,'test:25565','minecraft:overworld',
                resource,discovery,lambda:None,lambda candidate:True,
                lambda candidate:True)
            p=profile(SNOW);region=p['resource_regions'][0]
            region.update(source='natural_survey',allow_natural_snowpack=True,
                bobby_snow_route={'route_id':route['route_id'],'chunk':[0,0],
                    'region_file':'r.0.0.mca','fingerprint':'a'*64,
                    'cache_server':'test','dimension':'minecraft:overworld',
                    'world_session':c.world,'live_biome_verified':True,
                    'live_biome':'minecraft:snowy_plains'})
            result=acquire(c,SNOW,1,p,directory,lambda:None)
            self.assertEqual(('done',1,'saved_home'),
                             (result['phase'],result['after'],
                              result['return_home']['return_source']))
            self.assertEqual([-94.5,160.0,-94.5],c.state['pos'])
            closed=json.loads(resource.read_text())['bobby_snow_cache']
            self.assertIsNone(closed['active_route'])
            local=json.loads((Path(directory)/'acquisition-snow.json').read_text())
            self.assertEqual('home_arrived',local['bobby_return']['state'])

    def test_relaxed_evidence_cannot_authorize_a_region_outside_active_cache_chunk(self):
        class BobbyClient(FakeClient):
            task='materials-job'
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs);self.rev=7
                self.state.update(server='test',dimension='minecraft:overworld',
                    control_revision=7,flight=True,guard_armed=True,guard_pve_only=True,
                    manual_movement=False,under_water=False,health=20,food=20,
                    safety_hold={'active':False},navigating=False,native_material_busy=False,
                    supervision_lease={'kind':'materials','job_session':self.task,
                        'world_session':self.world,'revision':7,
                        'search_origin':[0.5,145.0,0.5]})
            def request(self,op,**params):
                if op in ('guard','navigate'):
                    self.actions.append((op,copy.deepcopy(params)))
                    self.last='offline-'+str(len(self.actions))
                    if op=='navigate':self.state['pos']=list(params['target'])
                    return {'id':self.last,'world_session':self.world,'phase':'done'}
                return super().request(op,**params)
        with tempfile.TemporaryDirectory() as directory:
            c=BobbyClient(SNOW,patch_rows(),silk=True)
            resource=Path(directory)/'resource.json';ledger={'schema':1,'item':SNOW,'tiles':{}}
            bobby_ledger(ledger,'test','minecraft:overworld');resource.write_text(json.dumps(ledger))
            cached={'source':'bobby_cache','cache_server':'test','dimension':'minecraft:overworld',
                'chunk':[0,0],'tile':[0,0],'target':[8.5,200.0,8.5],
                'region_file':'r.0.0.mca','fingerprint':'a'*64,'mtime_ns':100,
                'ctime_ns':101,'size':8192,'file_id':7,
                'biomes':['minecraft:snowy_plains'],'distance_sq':1.0}
            route=bobby_outbound(c,cached,'test','minecraft:overworld',resource,ledger,
                                 lambda:None,lambda row:True,lambda row:True)
            from material_jobs.bobby_snow_route import mark_harvesting
            mark_harvesting(c,resource,json.loads(resource.read_text()))
            evidence={'route_id':route['route_id'],'chunk':[0,0],
                'region_file':'r.0.0.mca','fingerprint':'a'*64,
                'cache_server':'test','dimension':'minecraft:overworld',
                'world_session':c.world,'live_biome_verified':True,
                'live_biome':'minecraft:snowy_plains'}
            forged={'item':SNOW,'min':[160,58,160],'max':[175,73,175],
                    'source':'natural_survey','allow_natural_snowpack':True,
                    'bobby_snow_route':evidence}
            self.assertFalse(authorizes_natural_snowpack(c,forged))

    def test_safe_health_stop_returns_but_never_supplies_a_python_home_target(self):
        class ExpeditionClient(FakeClient):
            def request(self, op, **params):
                if op == 'navigate' and params.get('snow_expedition_return'):
                    self.actions.append((op, copy.deepcopy(params)))
                    self.last = 'offline-' + str(len(self.actions))
                    self.state['pos'] = [0.5, 160.0, 0.5]
                    return {'id': self.last, 'world_session': self.world,
                            'phase': 'done'}
                return super().request(op, **params)

        with tempfile.TemporaryDirectory() as directory:
            c = ExpeditionClient(SNOW, patch_rows(), silk=True)
            c.state['health'] = 18.5
            c.snow_expedition_token = '11111111-1111-1111-1111-111111111111'
            c.snow_expedition_route_id = '22222222-2222-2222-2222-222222222222'
            result = acquire(c, SNOW, 1, profile(SNOW), directory, lambda: None)
            self.assertEqual('blocked', result['phase'])
            returning = [params for op, params in c.actions
                         if op == 'navigate' and params.get('snow_expedition_return')]
            self.assertEqual(1, len(returning));self.assertNotIn('target', returning[0])
            self.assertNotIn('snow_expedition_token', c.__dict__)

    def test_uncertain_return_is_not_replayed_or_hidden_by_completed_inventory(self):
        class UncertainReturn(FakeClient):
            def request(self, op, **params):
                if op == 'navigate' and params.get('snow_expedition_return'):
                    self.actions.append((op, copy.deepcopy(params)))
                    self.last = 'offline-' + str(len(self.actions))
                    return {'id': self.last, 'world_session': self.world,
                            'phase': 'waiting', 'detail': 'server did not confirm arrival'}
                return super().request(op, **params)

        with tempfile.TemporaryDirectory() as directory:
            c = UncertainReturn(SNOW, patch_rows(), silk=True)
            c.snow_expedition_token = '11111111-1111-1111-1111-111111111111'
            c.snow_expedition_route_id = '22222222-2222-2222-2222-222222222222'
            first = acquire(c, SNOW, 1, profile(SNOW), directory, lambda: None)
            self.assertEqual(('waiting','route_uncertain'),
                             (first['phase'],first['code']))
            self.assertNotIn('snow_expedition_token',c.__dict__)
            returns=sum(bool(op=='navigate' and params.get('snow_expedition_return'))
                        for op,params in c.actions)
            ledger=json.loads((Path(directory)/'acquisition-snow.json').read_text())
            self.assertEqual('uncertain',ledger['seed_return']['state'])
            self.assertTrue(any(row.get('state')=='collected'
                                for row in ledger['visited'].values()))
            before=len(c.actions)
            second=acquire(c,SNOW,1,profile(SNOW),directory,lambda:None)
            self.assertEqual(('waiting','seed_return_pending'),
                             (second['phase'],second['code']))
            self.assertEqual(before,len(c.actions));self.assertEqual(1,returns)

    def test_process_restart_during_multi_batch_expedition_blocks_without_plaintext_token(self):
        with tempfile.TemporaryDirectory() as directory:
            p=profile(SNOW)
            p['resource_regions'][0]['seed_snow_route']={
                'route_id':'22222222-2222-2222-2222-222222222222',
                'candidate':[3,3],'radius':4096}
            first=FakeClient(SNOW,patch_rows(),silk=True)
            first.snow_expedition_token='11111111-1111-1111-1111-111111111111'
            first.snow_expedition_route_id='22222222-2222-2222-2222-222222222222'
            partial=acquire(first,SNOW,2,p,directory,lambda:None)
            self.assertEqual(('waiting',1),(partial['phase'],partial['after']))
            ledger=json.loads((Path(directory)/'acquisition-snow.json').read_text())
            self.assertEqual('active',ledger['seed_expedition']['state'])
            restarted=FakeClient(SNOW,patch_rows(),silk=True,before=1)
            held=acquire(restarted,SNOW,2,p,directory,lambda:None)
            self.assertEqual(('waiting','seed_route_recovery_required'),
                             (held['phase'],held['code']))
            self.assertEqual([],restarted.actions)

    def test_seed_region_without_acquisition_ledger_or_token_cannot_shortcut_inventory_done(self):
        with tempfile.TemporaryDirectory() as directory:
            p=profile(SNOW);p['resource_regions'][0]['seed_snow_route']={
                'route_id':'22222222-2222-2222-2222-222222222222',
                'candidate':[3,3],'radius':4096}
            c=FakeClient(SNOW,patch_rows(),silk=True,before=1)
            result=acquire(c,SNOW,1,p,directory,lambda:None)
            self.assertEqual(('waiting','seed_route_recovery_required'),
                             (result['phase'],result['code']))
            self.assertEqual([],c.actions)

    def test_snow_layer_requires_silk_touch_and_new_host_protocol(self):
        for silk, protocol in ((False, 1), (True, 0)):
            with self.subTest(silk=silk, protocol=protocol), tempfile.TemporaryDirectory() as directory:
                c = FakeClient(SNOW, patch_rows(), silk=silk, protocol=protocol)
                result = acquire(c, SNOW, 1, profile(SNOW), directory, lambda: None)
                self.assertEqual('blocked', result['phase'])
                self.assertFalse(any(op == 'mine_block' for op, _ in c.actions))

    def test_plain_shovel_snow_block_yields_four_snowballs(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(SNOWBALL, patch_rows(SNOW_BLOCK), silk=False)
            result = acquire(c, SNOWBALL, 4, profile(SNOWBALL), directory, lambda: None)
            self.assertEqual(('done', 4, 4),
                             (result['phase'], result['after'], result['gained']))
            mine = next(params for op, params in c.actions if op == 'mine_block')
            self.assertTrue(mine['required_plain_shovel'])
            self.assertNotIn('required_silk_shovel', mine)

    def test_snowball_route_refuses_silk_touch_shovel(self):
        with tempfile.TemporaryDirectory() as directory:
            c = FakeClient(SNOWBALL, patch_rows(SNOW_BLOCK), silk=True)
            result = acquire(c, SNOWBALL, 4, profile(SNOWBALL), directory, lambda: None)
            self.assertEqual('blocked', result['phase'])
            self.assertFalse(any(op == 'mine_block' for op, _ in c.actions))

    def test_plain_shovel_route_never_withdraws_unknown_packed_variant(self):
        class NoTool:
            def status(self):
                return {'inventory': [{'slot': i, 'item': 'minecraft:air', 'count': 0,
                                       'max_stack': 64} for i in range(36)]}
        with tempfile.TemporaryDirectory() as directory, \
                patch('material_jobs.equipment.open_box',
                      side_effect=AssertionError('must not open packed storage')) as opened:
            result = prepare(NoTool(), SNOWBALL, 120,
                             {'ender_chest': [1, 2, 3], 'shulker_pad': [2, 2, 3]},
                             directory, lambda: None)
        self.assertEqual('blocked', result['phase'])
        self.assertIn('不带精准采集', result['detail'])
        opened.assert_not_called()

    def test_structure_marker_or_connected_snow_blocks_are_not_candidates(self):
        rows = patch_rows()
        rows.append(block((4, 64, 3), 'minecraft:oak_planks'))
        self.assertFalse(candidate(rows, [3, 64, 3], SNOW))
        rows = patch_rows(SNOW_BLOCK)
        rows.append(block((4, 64, 3), SNOW_BLOCK))
        self.assertFalse(candidate(rows, [3, 64, 3], SNOWBALL))
        rows = patch_rows()
        rows.append(block((5, 64, 3), SNOW_BLOCK))
        self.assertFalse(candidate(rows, [3, 64, 3], SNOW))

    def test_bobby_live_snowpack_allows_layer_on_shallow_natural_snow_support(self):
        rows=patch_rows()
        rows=[row for row in rows if row['pos'] not in ([3,63,3],[3,62,3])]
        rows.extend((block((3,63,3),SNOW_BLOCK),block((3,62,3),'minecraft:stone')))
        rows.append(block((4,63,3),SNOW_BLOCK))
        self.assertFalse(candidate(rows,[3,64,3],SNOW))
        self.assertTrue(candidate(rows,[3,64,3],SNOW,
                                  allow_natural_snowpack=True))
        rows=[row for row in patch_rows() if row['pos']!=[3,63,3]]
        rows.append(block((3,63,3),'minecraft:spruce_leaves'))
        self.assertFalse(candidate(rows,[3,64,3],SNOW))
        self.assertTrue(candidate(rows,[3,64,3],SNOW,
                                  allow_natural_snowpack=True))

    def test_relaxed_snowpack_still_rejects_solid_or_pure_snow_construction(self):
        rows=patch_rows(SNOW_BLOCK)
        rows.append(block((3,62,3),'minecraft:stone'))
        self.assertFalse(candidate(rows,[3,64,3],SNOWBALL,
                                   allow_natural_snowpack=True))
        layers=patch_rows()
        layers=[row for row in layers if row['pos'][0]!=3 or row['pos'][2]!=3]
        layers.extend((block((3,64,3),SNOW,state='Block{minecraft:snow}[layers=1]',
                                  solid=False,passable=True),
                       block((3,63,3),SNOW_BLOCK),block((3,62,3),SNOW_BLOCK),
                       block((3,61,3),SNOW_BLOCK)))
        self.assertFalse(candidate(layers,[3,64,3],SNOW,
                                   allow_natural_snowpack=True))

    def test_allow_flag_without_current_cache_and_live_biome_evidence_does_not_relax(self):
        rows=[row for row in patch_rows() if row['pos'] not in ([3,63,3],[3,62,3])]
        rows.extend((block((3,63,3),SNOW_BLOCK),block((3,62,3),'minecraft:stone')))
        p=profile(SNOW);p['resource_regions'][0]['allow_natural_snowpack']=True
        with tempfile.TemporaryDirectory() as directory:
            c=FakeClient(SNOW,rows,silk=True)
            result=acquire(c,SNOW,1,p,directory,lambda:None)
        self.assertEqual('blocked',result['phase'])
        self.assertFalse(any(op=='mine_block' for op,_ in c.actions))

    def test_bounded_discovery_finds_high_surface_snow(self):
        rows = patch_rows(centre=(3, 200, 3))
        # Move natural support to the source's actual surface.
        rows = [dict(row, pos=[row['pos'][0], 199, row['pos'][2]])
                if row['pos'][1] == 63 else row for row in rows]
        diagnostics = {}
        found = choose_region(rows, SNOW, 0, 0, [0, 210, 0], diagnostics=diagnostics)
        self.assertEqual((SNOW, [0, 193, 0], [15, 208, 15], 1),
                         (found['item'], found['min'], found['max'], diagnostics['target_blocks']))


if __name__ == '__main__':
    unittest.main()
