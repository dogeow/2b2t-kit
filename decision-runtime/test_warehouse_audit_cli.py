"""Warehouse observation must not move inventory or claim unproved completion."""
import copy
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import kit_cli
import warehouse_audit_cli as module
from potato_farm import ENTITY_SCOPE_AT_SCAN_END


def state(time=100):
    return {
        'time': time, 'connected': True, 'server': 'example.test:25565',
        'dimension': 'minecraft:overworld', 'world_session': 'world', 'player_uuid': 'player-one',
        'control_revision': 4, 'manual_movement': False, 'screen': '',
        'health': 20, 'food': 20, 'pos': [20.5, 140, 20.5],
        'flight': True, 'guard_armed': True, 'guard_pve_only': True,
        'guard_busy': False, 'under_water': False, 'on_ground': False,
        'navigating': False, 'native_material_busy': False,
        'safety_hold': {'active': False},
        'hand': {'item': 'minecraft:diamond_sword', 'count': 1},
        'projection_selection': None,
        'inventory': [
            {'slot': 0, 'item': 'minecraft:diamond_sword', 'count': 1},
            {'slot': 1, 'item': 'minecraft:oak_planks', 'count': 17},
        ] + [{'slot': i, 'item': 'minecraft:air', 'count': 0} for i in range(2, 36)],
        'menu': {'id': 0, 'type': '', 'cursor': {'item': 'minecraft:air', 'count': 0}, 'slots': []},
        'supervision_lease': {},
    }


def slot(index, item='minecraft:air', count=0, **metadata):
    return {'slot': index, 'item': item, 'count': count, 'max_stack': 64, **metadata}


def chest_menu(contents, menu_id=1, size=27):
    rows = [slot(i) for i in range(size)]
    for i, item in enumerate(contents):
        rows[i] = slot(i, **item)
    # Deliberately unlike chest contents: carried wood must never be counted.
    rows += [slot(size+i, 'minecraft:oak_planks', 17) if i == 0 else slot(size+i)
             for i in range(36)]
    return {'id': menu_id, 'type': 'ChestMenu',
            'cursor': {'item': 'minecraft:air', 'count': 0}, 'slots': rows}


class FakeClient:
    """The movement/opener are mocked; native scans and finish proof stay real data."""
    PARK_RADIUS_SQR = 8 * 8
    _owned_guarded_finish_state = module.MaterialClient._owned_guarded_finish_state
    park_near = module.MaterialClient.park_near

    def __init__(self, root, out, *, server, **kwargs):
        self.root, self.out = Path(root), Path(out)
        self.root.mkdir(parents=True, exist_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)
        self.server = server
        self.kwargs = kwargs
        self.world, self.rev, self.task = 'world', 4, 'warehouse-task'
        self.park_target = list(kwargs.get('park_target', state()['pos']))
        self.heartbeat = SimpleNamespace(id='warehouse-lease', close=lambda: None)
        self.state = state()
        self.state['supervision_lease'] = {
            'id': self.heartbeat.id, 'job_session': self.task, 'world_session': self.world,
            'revision': self.rev, 'kind': 'materials', 'remote_finish': 'guard',
            'park_target': self.park_target[:],
        }
        self.calls, self.opened, self.menu_frames = [], [], []
        self.last, self.native_inflight = None, None
        self.scans, self.contents = {}, {}
        self.scan_changes = {}
        self.menu_changes = None
        self.finish_changes = None
        self.finish_calls = 0
        self.finish_proof = True
        self.sequence = 0

    def status(self, *args, **kwargs):
        self.state['time'] += 1
        result = copy.deepcopy(self.state)
        if result['menu']['type']:
            self.menu_frames.append(copy.deepcopy(result))
            if self.menu_changes:
                self.menu_changes(result, len(self.menu_frames))
        return result

    def raw(self, *args, **kwargs):
        return self.status(*args, **kwargs)

    def request(self, op, **params):
        self.calls.append((op, copy.deepcopy(params)))
        if op not in ('scan', 'snapshot', 'close_menu', 'material_job_park'):
            raise AssertionError('Warehouse audit must not dispatch ' + op)
        self.sequence += 1
        self.last = 'warehouse-request-' + str(self.sequence)
        if op == 'snapshot':
            return self.status()
        if op == 'close_menu':
            self.state['screen'] = ''
            self.state['menu'] = state()['menu']
            return self.status() | {'phase': 'done', 'id': self.last}
        if op == 'material_job_park':
            self.park_target = list(params['park_target'])
            self.state['pos'] = self.park_target[:]
            self.state['supervision_lease']['park_target'] = self.park_target[:]
            return self.status() | {'phase': 'done', 'id': self.last}
        low, high = params['min'], params['max']
        count = math.prod(b-a+1 for a, b in zip(low, high))
        rows = [copy.deepcopy(row) for pos, row in self.scans.items()
                if all(low[i] <= pos[i] <= high[i] for i in range(3))]
        answer = {'id': self.last, 'phase': 'done', 'world_session': self.world,
                  'control_revision': self.rev,
                  'scan_cells_read': count, 'scan_total_cells': count,
                  'scan_start_revision': self.rev, 'scan_end_revision': self.rev,
                  'scan_started_at': self.state['time'], 'scan_ended_at': self.state['time'] + 1,
                  'blocks': rows,'scan_entities':[],'scan_entity_scope':ENTITY_SCOPE_AT_SCAN_END}
        self.state['time'] += 1
        answer.update(self.scan_changes)
        return answer

    def checked(self, op, **params):
        answer = self.request(op, **params)
        if answer.get('phase') != 'done':
            raise RuntimeError(answer.get('detail', 'unconfirmed'))
        return answer

    def transfer(self, *args, **kwargs):
        raise AssertionError('An inventory audit cannot transfer stock')

    def finish(self):
        self.finish_calls += 1
        if not self.finish_proof:
            return
        self.rev += 1
        self.state.update(time=self.state['time'] + 10, control_revision=self.rev,
                          pos=self.park_target[:], screen='', flight=True)
        self.state['menu'] = state()['menu']
        self.state['supervision_lease'].update(kind='parking', revision=self.rev,
                                             park_target=self.park_target[:])
        parked = copy.deepcopy(self.state)
        native = {'lease': self.heartbeat.id, 'job_session': self.task,
                  'action': 'KEEP_PVE_GUARD', 'time': parked['time'] - 1,
                  'snapshot': parked}
        proof = {**copy.deepcopy(native), 'native_receipt': True,
                 'parking_confirmation': copy.deepcopy(parked)}
        if self.finish_changes:
            self.finish_changes(native, proof, self.state)
        (self.root / ('supervision-receipt-' + self.heartbeat.id + '.json')).write_text(json.dumps(native))
        (self.out / 'stock-safety.json').write_text(json.dumps(proof))

    def put_chest(self, pos, contents=(), *, kind='minecraft:chest', properties='', size=27):
        self.scans[tuple(pos)] = {'pos': list(pos), 'state': 'Block{' + kind + '}' + properties,
                                 'fluid': False, 'block_entity': True, 'replaceable': False,
                                 'solid':False,'passable':False}
        self.contents[tuple(pos)] = chest_menu(contents, menu_id=len(self.contents)+1, size=size)


class FakeSurvey:
    """This separate read-only client proves the live high column before the lease."""
    def __init__(self, root, out, *, server, **kwargs):
        self.root, self.out, self.server = Path(root), Path(out), server
        self.world, self.rev = 'world', 4
        self.calls = []
        self.changes = {}

    def status(self):
        return state(101)

    def request(self, op, **params):
        self.calls.append((op, copy.deepcopy(params)))
        if op != 'scan':
            raise AssertionError('Preflight survey must remain read-only')
        low, high = params['min'], params['max']
        ground = {'pos': [math.floor(state()['pos'][0]), 64, math.floor(state()['pos'][2])],
                  'state': 'Block{minecraft:stone}', 'fluid': False,
                  'block_entity': False, 'replaceable': False}
        result = {'id': 'preflight-column', 'phase': 'done', 'world_session': self.world,
                  'control_revision': self.rev,
                  'scan_cells_read': math.prod(b-a+1 for a, b in zip(low, high)),
                  'scan_total_cells': math.prod(b-a+1 for a, b in zip(low, high)),
                  'scan_start_revision': self.rev, 'scan_end_revision': self.rev,
                  'scan_started_at': 101, 'scan_ended_at': 102, 'blocks': [ground]}
        result.update(self.changes)
        return result


class WarehouseAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.game_dir = Path(temporary.name) / 'game'
        self.out = Path(temporary.name) / 'audit'
        self.client = None
        self.survey = None
        self.depots = [[1, 64, 1]]
        self.configure = None
        self.survey_changes = {}

    def snapshot(self, *args, **kwargs):
        return self.client.status() if self.client else state()

    def factory(self, *args, **kwargs):
        self.client = FakeClient(*args, **kwargs)
        self.client.put_chest(self.depots[0], [{'item': 'minecraft:stone', 'count': 12}])
        if self.configure:
            self.configure(self.client)
        return self.client

    def survey_factory(self, *args, **kwargs):
        self.survey = FakeSurvey(*args, **kwargs)
        self.survey.changes = copy.deepcopy(self.survey_changes)
        return self.survey

    def open_chest(self, session, pos, block_state, profile):
        client = self.client
        client.opened.append((list(pos), block_state, profile))
        client.state['screen'] = 'ContainerScreen'
        client.state['menu'] = copy.deepcopy(client.contents[tuple(pos)])
        client.owned_material_menu = client.state['menu']['id']
        return client.status()

    def travel(self, client, pos, checkpoint, trace):
        self.assertIs(self.client, client.core)
        self.client.state['pos'] = [pos[0]+.5, pos[1]+1, pos[2]+.5]
        return self.client.status()

    def execute(self, configure=None, *, depots=None, initial=None, opener=None):
        self.configure = configure
        if depots is not None:
            self.depots = depots
        reader = (lambda *args, **kwargs: copy.deepcopy(initial)) if initial else self.snapshot
        clock = [0.0]
        def sleeper(seconds):
            clock[0] += seconds
        with patch.object(module, '_travel_to', side_effect=self.travel), \
                patch.object(module, '_open_container', side_effect=opener or self.open_chest), \
                patch.object(module.time, 'monotonic', side_effect=lambda: clock[0]):
            return module.run(self.game_dir, self.out, self.depots,
                              client_factory=self.factory, survey_factory=self.survey_factory,
                              snapshot_reader=reader, sleeper=sleeper)

    def records(self):
        return [json.loads(path.read_text()) for path in self.out.glob('*.json')]

    def test_complete_stock_retains_nested_contents_excludes_player_slots_and_finishes_once(self):
        children = [{'item': 'minecraft:raw_iron_block', 'count': 8, 'max_stack': 64}]
        def configure(client):
            client.put_chest(self.depots[0], [
                {'item': 'minecraft:stone', 'count': 12},
                {'item': 'minecraft:blue_shulker_box', 'count': 1, 'contains': children},
            ])
        result = self.execute(configure)
        self.assertTrue(result['complete'])
        self.assertEqual('done', result['phase'])
        self.assertEqual({'minecraft:stone': 12, 'minecraft:blue_shulker_box': 1}, result['loose_counts'])
        self.assertEqual({'minecraft:raw_iron_block': 8}, result['packed_counts'])
        self.assertEqual(1, len(result['containers']))
        saved = json.loads((self.out/'stock-audit.json').read_text())
        self.assertEqual(result, saved)
        self.assertEqual(1, self.client.finish_calls)
        self.assertEqual(1, len(self.client.opened))
        self.assertGreaterEqual(len(self.client.menu_frames), 3)
        self.assertEqual('guard', self.client.kwargs['remote_finish'])
        self.assertEqual(state()['pos'], self.client.kwargs['park_target'])
        self.assertNotIn('minecraft:oak_planks', result['loose_counts'])
        self.assertIn(children, [row['contains'] for frame in self.client.menu_frames
                               for row in frame['menu']['slots'] if 'contains' in row])
        self.assertTrue(all(op in ('scan', 'snapshot', 'close_menu', 'material_job_park')
                            for op, _ in self.client.calls))

    def test_empty_chest_is_complete_observation_without_transfer_or_slot_click(self):
        result = self.execute(lambda client: client.put_chest(self.depots[0], []))
        self.assertTrue(result['complete'])
        self.assertEqual({}, result['loose_counts'])
        self.assertEqual({}, result['packed_counts'])
        self.assertEqual(1, len(result['containers']))
        self.assertEqual(1, self.client.finish_calls)

    def test_barrel_reads_27_slots_and_accepts_only_owned_open_animation_change(self):
        def configure(client):
            client.put_chest(self.depots[0],[{'item':'minecraft:raw_iron_block','count':64}],
                             kind='minecraft:barrel',properties='[facing=west,open=false]')
        def opened(session,pos,block_state,profile):
            frame=self.open_chest(session,pos,block_state,profile)
            self.client.scans[tuple(pos)]['state']='Block{minecraft:barrel}[facing=west,open=true]'
            return frame
        result=self.execute(configure,opener=opened)
        self.assertTrue(result['complete']);self.assertEqual({'minecraft:raw_iron_block':64},result['loose_counts'])
        row=result['containers'][0]
        self.assertTrue(row['identity'].startswith('barrel:'));self.assertEqual(27,len(row['slots']))
        self.assertIn('open=false',row['block_state']);self.assertIn('open=true',row['opened_block_state'])
        self.assertEqual(1,self.client.finish_calls)
        self.assertEqual(state()['inventory'],self.client.state['inventory'])

    def test_barrel_structural_change_after_opening_is_not_credited(self):
        def configure(client):
            client.put_chest(self.depots[0],[],kind='minecraft:barrel',properties='[facing=west,open=false]')
        def changed(session,pos,block_state,profile):
            frame=self.open_chest(session,pos,block_state,profile)
            self.client.scans[tuple(pos)]['state']='Block{minecraft:barrel}[facing=east,open=true]'
            return frame
        result=self.execute(configure,opener=changed)
        self.assertFalse(result['complete']);self.assertEqual([],result['containers'])

    def test_barrel_chest_and_personal_ender_remain_separate_inventory_kinds(self):
        positions=[[1,64,1],[4,64,1],[7,64,1]]
        def configure(client):
            for pos,kind,amount,props in zip(positions,
                    ['minecraft:barrel','minecraft:chest','minecraft:ender_chest'],[1,2,3],
                    ['[facing=up,open=false]','[facing=north,type=single,waterlogged=false]','[facing=north,waterlogged=false]']):
                client.put_chest(pos,[{'item':'minecraft:stone','count':amount}],kind=kind,properties=props)
        result=self.execute(configure,depots=positions)
        self.assertTrue(result['complete']);self.assertEqual({'minecraft:stone':6},result['loose_counts'])
        self.assertEqual({'barrel','chest','ender'},
                         {row['identity'].split(':',1)[0]for row in result['containers']})

    def test_roof_free_barrel_uses_visible_face_without_chest_landing_or_inventory_click(self):
        pos=[1,64,1];block_state='Block{minecraft:barrel}[facing=west,open=false]'
        answer={'phase':'done','world_session':'world','control_revision':4,'scan_start_revision':4,
                'scan_end_revision':4,'scan_cells_read':7,'scan_total_cells':7,
                'blocks':[{'pos':pos,'state':block_state}]}
        from unittest.mock import Mock
        session=SimpleNamespace(world='world',rev=4,in_house=False,request=Mock(return_value=answer),checked=Mock())
        frame=state()|{'menu':chest_menu([])}
        with patch.object(module,'_side_access',return_value='west')as face, \
                patch('container_access.wait_container_contents',return_value=frame)as contents, \
                patch('container_access.open_grounded_chest')as landed:
            self.assertIs(frame,module._open_container(session,pos,block_state,{}))
        landed.assert_not_called();face.assert_called_once();contents.assert_called_once_with(session,'ChestMenu',require_nonempty=False)
        self.assertEqual(['select_item','interact'],[call.args[0]for call in session.checked.call_args_list])

    def test_barrel_open_state_exception_does_not_relax_chest_state_checks(self):
        self.assertFalse(module._same_opened_state('Block{minecraft:barrel}[facing=west,open=false]',
                                                'Block{minecraft:barrel}[facing=west]'))
        self.assertFalse(module._same_opened_state('Block{minecraft:chest}[facing=west,type=single,waterlogged=false]',
                                                'Block{minecraft:chest}[facing=east,type=single,waterlogged=false]'))

    def test_reached_body_scan_blocks_attic_obstacle_or_entity_before_counting_slots(self):
        def obstacle(client):
            client.scans[(1,66,1)]={'pos':[1,66,1],'state':'Block{minecraft:oak_planks}',
                                   'fluid':False,'solid':True,'passable':False}
        def entity(client):
            client.scan_changes['scan_entities']=[{'type':'minecraft:villager','hostile':False}]
        def missing_scope(client):client.scan_changes['scan_entity_scope']='unverified'
        for configure in (obstacle,entity,missing_scope):
            with self.subTest(configure=configure.__name__):
                self.setUp();result=self.execute(configure)
                self.assertFalse(result['complete']);self.assertEqual([],result['containers'])
                self.assertIn('body',result['error'])

    def test_exact_partial_chest_lid_below_reached_feet_is_allowed(self):
        def landed(session,pos,block_state,profile):
            self.client.state['pos']=[pos[0]+.5,pos[1]+14/16,pos[2]+.5]
            return self.open_chest(session,pos,block_state,profile)
        result=self.execute(opener=landed)
        self.assertTrue(result['complete'])
        self.assertEqual([1.5,64.875,1.5],result['containers'][0]['reached_body_clearance']['pos'])

    def test_blast_furnace_lit_change_remains_waiting_without_inventory_credit(self):
        def configure(client):
            client.put_chest(self.depots[0],[],kind='minecraft:blast_furnace',
                             properties='[facing=north,lit=false]',size=3)
            client.contents[tuple(self.depots[0])]['type']='BlastFurnaceMenu'
        def changed(session,pos,block_state,profile):
            frame=self.open_chest(session,pos,block_state,profile)
            self.client.scans[tuple(pos)]['state']='Block{minecraft:blast_furnace}[facing=north,lit=true]'
            return frame
        result=self.execute(configure,opener=changed)
        self.assertFalse(result['complete']);self.assertEqual([],result['containers'])

    def test_hopper_reads_only_its_exact_five_native_slots(self):
        def configure(client):
            client.put_chest(self.depots[0],[{'item':'minecraft:raw_iron','count':9}],
                             kind='minecraft:hopper',properties='[enabled=true,facing=down]',size=5)
            client.contents[tuple(self.depots[0])]['type']='HopperMenu'
        result=self.execute(configure)
        self.assertTrue(result['complete']);self.assertEqual({'minecraft:raw_iron':9},result['loose_counts'])
        self.assertEqual('HopperMenu',result['containers'][0]['menu_type'])
        self.assertEqual(5,len(result['containers'][0]['slots']))
        self.assertEqual(state()['inventory'],self.client.state['inventory'])

    def test_blast_furnace_reports_only_current_input_fuel_and_output_slots(self):
        def configure(client):
            client.put_chest(self.depots[0],[{'item':'minecraft:raw_iron','count':7},
                {'item':'minecraft:coal','count':2},{'item':'minecraft:iron_ingot','count':4}],
                kind='minecraft:blast_furnace',properties='[facing=north,lit=false]',size=3)
            client.contents[tuple(self.depots[0])]['type']='BlastFurnaceMenu'
        result=self.execute(configure)
        self.assertTrue(result['complete'])
        self.assertEqual({'minecraft:raw_iron':7,'minecraft:coal':2,'minecraft:iron_ingot':4},result['loose_counts'])
        self.assertEqual({'0':'input','1':'fuel','2':'output'},result['containers'][0]['visible_slot_roles'])
        self.assertEqual(3,len(result['containers'][0]['slots']))
        self.assertFalse(any(op in ('slot_click','use_item','smelt')for op,_ in self.client.calls))

    def test_machine_block_cannot_accept_unrelated_menu_type_or_wrong_source_size(self):
        for menu_type,size in (('ChestMenu',5),('HopperMenu',27),('FurnaceMenu',5)):
            with self.subTest(menu_type=menu_type,size=size):
                self.setUp()
                def configure(client):
                    client.put_chest(self.depots[0],[],kind='minecraft:hopper',
                                     properties='[enabled=true,facing=down]',size=size)
                    client.contents[tuple(self.depots[0])]['type']=menu_type
                result=self.execute(configure)
                self.assertFalse(result['complete']);self.assertEqual([],result['containers'])

    def test_ordinary_furnace_reports_three_slots_without_loading_or_collecting(self):
        def configure(client):
            client.put_chest(self.depots[0],[{'item':'minecraft:cobblestone','count':7},
                {'item':'minecraft:coal','count':2},{'item':'minecraft:stone','count':4}],
                kind='minecraft:furnace',properties='[facing=north,lit=false]',size=3)
            client.contents[tuple(self.depots[0])]['type']='FurnaceMenu'
        result=self.execute(configure)
        self.assertTrue(result['complete'])
        self.assertEqual({'minecraft:cobblestone':7,'minecraft:coal':2,'minecraft:stone':4},result['loose_counts'])
        self.assertEqual('FurnaceMenu',result['containers'][0]['menu_type'])
        self.assertEqual({'0':'input','1':'fuel','2':'output'},result['containers'][0]['visible_slot_roles'])
        self.assertEqual(3,len(result['containers'][0]['slots']))
        self.assertFalse(any(op in ('slot_click','use_item','smelt')for op,_ in self.client.calls))

    def test_roofed_rocket_hopper_uses_side_face_without_wrong_house_route(self):
        pos=[1,64,1];block_state='Block{minecraft:hopper}[enabled=true,facing=down]'
        answer={'phase':'done','world_session':'world','control_revision':4,'scan_start_revision':4,
                'scan_end_revision':4,'scan_cells_read':7,'scan_total_cells':7,
                'blocks':[{'pos':pos,'state':block_state},
                          {'pos':[1,65,1],'state':'Block{minecraft:blast_furnace}[facing=west,lit=false]'}]}
        from unittest.mock import Mock
        session=SimpleNamespace(world='world',rev=4,in_house=False,request=Mock(return_value=answer),checked=Mock())
        frame=state()|{'menu':chest_menu([],size=5)|{'type':'HopperMenu'}}
        with patch.object(module,'_side_access',return_value='west')as face, \
                patch('container_access.wait_container_contents',return_value=frame)as contents, \
                patch('container_access.open_grounded_chest')as landed, \
                patch.object(module._RegisteredRoute,'route')as routed:
            self.assertIs(frame,module._open_container(session,pos,block_state,{}))
        landed.assert_not_called();routed.assert_not_called()
        self.assertEqual(False,face.call_args.kwargs['house'])
        contents.assert_called_once_with(session,'HopperMenu',require_nonempty=False)

    def test_partial_foreign_waiting_and_wrong_revision_scans_never_open_or_finish_complete(self):
        changes = ({'scan_cells_read': 0}, {'phase': 'waiting'}, {'world_session': 'foreign'},
                   {'scan_end_revision': 5})
        for changed in changes:
            with self.subTest(changed=changed):
                self.setUp()
                result = self.execute(lambda client: client.scan_changes.update(changed))
                self.assertFalse(result['complete'])
                self.assertEqual('waiting', result['phase'])
                self.assertEqual([], self.client.opened)
                self.assertEqual({}, result['loose_counts'])

    def test_ground_clearance_or_partial_preflight_blocks_before_material_lease(self):
        for change in ({'scan_cells_read': 0}, {'phase': 'waiting'}, {'world_session': 'foreign'},
                       {'scan_end_revision': 5},
                       {'blocks': [{'pos': [20, 130, 20], 'state': 'Block{minecraft:stone}',
                                    'fluid': False, 'block_entity': False, 'replaceable': False}]}):
            with self.subTest(change=change):
                self.setUp()
                self.survey_changes = change
                result = self.execute()
                self.assertFalse(result['complete'])
                self.assertIsNone(self.client)
                self.assertEqual(1, len(self.survey.calls))

    def test_manual_takeover_active_worker_block_before_any_controller(self):
        changes = ({'manual_movement': True}, {'connected': False}, {'screen': 'ContainerScreen'},
                   {'material_task': {'process_alive': True}}, {'native_material_busy': True},
                   {'build_job': {'active': True}})
        for change in changes:
            with self.subTest(change=change):
                self.setUp()
                with self.assertRaises(module.StockBlocked):
                    self.execute(initial=state() | change)
                self.assertIsNone(self.client)
                self.assertIsNone(self.survey)

    def test_live_double_chest_halves_count_once_only_with_adjacency_proof(self):
        left, right = [1, 64, 1], [2, 64, 1]
        def configure(client):
            client.put_chest(left, [{'item': 'minecraft:stone', 'count': 12}],
                             properties='[facing=north,type=left,waterlogged=false]', size=54)
            client.put_chest(right, [{'item': 'minecraft:stone', 'count': 12}],
                             properties='[facing=north,type=right,waterlogged=false]', size=54)
        result = self.execute(configure, depots=[left, right])
        self.assertTrue(result['complete'])
        self.assertEqual({'minecraft:stone': 12}, result['loose_counts'])
        self.assertEqual(1, len(result['containers']))
        self.assertEqual(1, len(self.client.opened))

    def test_inconsistent_adjacent_double_chest_state_never_reuses_other_half_count(self):
        left, right = [1, 64, 1], [2, 64, 1]
        def configure(client):
            client.put_chest(left, [{'item': 'minecraft:stone', 'count': 12}],
                             properties='[facing=north,type=left,waterlogged=false]', size=54)
            client.put_chest(right, [{'item': 'minecraft:stone', 'count': 12}],
                             properties='[facing=south,type=right,waterlogged=false]', size=54)
        result = self.execute(configure, depots=[left, right])
        self.assertFalse(result['complete'])
        self.assertEqual('waiting', result['phase'])
        self.assertLessEqual(len(self.client.opened), 1)

    def test_two_ender_chest_coordinates_are_one_personal_inventory(self):
        first, second = [1, 64, 1], [10, 64, 10]
        def configure(client):
            for pos in (first, second):
                client.put_chest(pos, [{'item': 'minecraft:oak_log', 'count': 5}],
                                 kind='minecraft:ender_chest', properties='[facing=north,waterlogged=false]')
        result = self.execute(configure, depots=[first, second])
        self.assertTrue(result['complete'])
        self.assertEqual({'minecraft:oak_log': 5}, result['loose_counts'])
        self.assertEqual(1, len(result['containers']))
        self.assertEqual(1, len(self.client.opened))

    def test_menu_or_inventory_changes_between_observation_frames_are_not_published(self):
        def menu_count_changed(snapshot, frame):
            snapshot['menu']['slots'][0]['count'] += frame
        def menu_id_changed(snapshot, frame):
            snapshot['menu']['id'] += frame
        def carried_changed(snapshot, frame):
            snapshot['inventory'][1]['count'] += frame
        def cursor_occupied(snapshot, frame):
            snapshot['menu']['cursor'] = {'item': 'minecraft:stone', 'count': 1}
        def repeated_timestamp(snapshot, frame):
            snapshot['time'] = 1000
        for mutate in (menu_count_changed, menu_id_changed, carried_changed, cursor_occupied,
                       repeated_timestamp):
            with self.subTest(mutate=mutate.__name__):
                self.setUp()
                result = self.execute(lambda client: setattr(client, 'menu_changes', mutate))
                self.assertFalse(result['complete'])
                self.assertEqual('waiting', result['phase'])
                self.assertEqual([], result['containers'])
                self.assertEqual({}, result['loose_counts'])

    def test_missing_mismatched_stale_or_unprotected_finish_proof_does_not_claim_complete(self):
        def missing(client):
            client.finish_proof = False
        def native_different_time(client):
            client.finish_changes = lambda native, proof, current: native.update(time=native['time']-1)
        def foreign_lease(client):
            client.finish_changes = lambda native, proof, current: native.update(lease='foreign-lease')
        def stale_current(client):
            client.finish_changes = lambda native, proof, current: current.update(time=proof['time']-1)
        def guard_changed(client):
            client.finish_changes = lambda native, proof, current: current.update(guard_armed=False)
        def locally_synthetic(client):
            client.finish_changes = lambda native, proof, current: proof.update(local_verified=True)
        def pending_transition(client):
            client.finish_changes = lambda native, proof, current: native.update(lease_transition_pending=True)
        def revoked_current(client):
            client.finish_changes = lambda native, proof, current: current.update(manual_movement=True)
        def foreign_native_snapshot(client):
            client.finish_changes = lambda native, proof, current: native['snapshot'].update(world_session='foreign')
        def foreign_worker_snapshot(client):
            client.finish_changes = lambda native, proof, current: proof['snapshot'].update(world_session='foreign')
        def newer_current_revision(client):
            def change(native, proof, current):
                current['control_revision'] += 1
                current['supervision_lease']['revision'] = current['control_revision']
            client.finish_changes = change
        def invalid_native_time(client):
            def change(native, proof, current):
                native['time'] = proof['time'] = 0
            client.finish_changes = change
        for configure in (missing, native_different_time, foreign_lease, stale_current, guard_changed,
                          locally_synthetic, pending_transition, revoked_current,
                          foreign_native_snapshot, foreign_worker_snapshot,
                          newer_current_revision, invalid_native_time):
            with self.subTest(configure=configure.__name__):
                self.setUp()
                result = self.execute(configure)
                self.assertFalse(result['complete'])
                self.assertEqual('waiting', result['phase'])
                self.assertEqual(1, self.client.finish_calls)
                self.assertEqual(1, len(result['containers']))
                self.assertEqual({'minecraft:stone': 12}, result['containers'][0]['loose_counts'])

    def test_unknown_open_keeps_pending_identity_and_blocks_output_replay(self):
        unknown_id = 'warehouse-open-unknown'
        def unknown(session, pos, block_state, profile):
            self.client.opened.append((list(pos), block_state, profile))
            self.client.last = unknown_id
            self.client.native_inflight = {'id': unknown_id, 'op': 'interact', 'world_session': 'world'}
            raise RuntimeError('Original container interaction result is unknown')
        result = self.execute(opener=unknown)
        self.assertFalse(result['complete'])
        self.assertEqual('waiting', result['phase'])
        self.assertEqual(1, len(self.client.opened))
        self.assertEqual(0, self.client.finish_calls)
        self.assertIn(unknown_id, json.dumps(result['pending']))
        first = self.client
        with patch.object(module, '_travel_to') as travel, patch.object(module, '_open_container') as opened, \
                patch.object(module, 'MaterialClient') as constructed, self.assertRaises(module.StockBlocked):
            module.run(self.game_dir, self.out, self.depots,
                       client_factory=constructed, survey_factory=self.survey_factory,
                       snapshot_reader=self.snapshot, sleeper=lambda seconds: None)
        self.assertEqual(unknown_id, first.last)
        constructed.assert_not_called()
        travel.assert_not_called()
        opened.assert_not_called()

    def test_audit_session_refuses_mutating_helper_before_core_dispatch(self):
        for operation in ('slot_click', 'place', 'deposit', 'transfer'):
            with self.subTest(operation=operation):
                self.setUp()
                def forbidden(session, pos, block_state, profile):
                    if operation == 'transfer':
                        return session.transfer('minecraft:stone', 1)
                    return session.checked(operation, pos=pos, slot=0, item='minecraft:stone')
                result = self.execute(opener=forbidden)
                self.assertFalse(result['complete'])
                self.assertEqual([], result['containers'])
                self.assertNotIn(operation, [op for op, _ in self.client.calls])
                self.assertEqual(state()['inventory'], self.client.state['inventory'])

    def test_central_cli_routes_stock_without_material_task_controller(self):
        with patch.object(module, 'main', return_value=0) as main, \
                patch('material_task_client.MaterialTaskClient') as tasks:
            result = kit_cli.main(['--game-dir', '/game', 'materials', 'stock',
                                   '--depot', '1', '64', '1', '--depot', '2', '65', '2',
                                   '--out', '/out', '--profile', '/profile.json'])
        self.assertEqual(0, result)
        tasks.assert_not_called()
        main.assert_called_once_with(['--game-dir', '/game', '--out', '/out',
                                      '--depot', '1', '64', '1', '--depot', '2', '65', '2',
                                      '--profile', '/profile.json'])

    def test_stock_cli_requires_explicit_depots_and_output_before_any_session(self):
        for command in (['--out', '/out'], ['--depot', '1', '64', '1']):
            with self.subTest(command=command), patch.object(module, 'run') as run, \
                    patch('sys.stderr'), self.assertRaises(SystemExit) as error:
                module.main(command)
            self.assertEqual(2, error.exception.code)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
