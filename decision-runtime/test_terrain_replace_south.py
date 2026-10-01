import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import projection_dry_paving as paving
import terrain_replace_south as terrain


class FakeClient:
    def __init__(self, root, pos=terrain.CELLS[0]):
        self.root = Path(root)
        self.out = self.root / 'out'
        self.out.mkdir(parents=True)
        self.pos = pos
        self.world = 'world-1'
        self.task = 'materials-test'
        self.key = 'eight-regions-test'
        self.model_hash = 'same-model'
        self.protocol = 1
        self.base = terrain.STONE
        self.top = terrain.GRASS
        self.below = terrain.STONE
        self.extra = []
        self.player = terrain._station(pos)
        self.on_ground = False
        self.park_target = [761008.5, 110.0, 797865.5]
        self.time = 10000
        self.hand = 'minecraft:diamond_shovel'
        self.selected_slot = 2
        self.selection_active = False
        self.silk = True
        self.shovel_durability = 700
        self.revision = 7
        self.last_request = ''
        self.phase = None
        self.detail = None
        self.pre_send_rejection_stage = None
        self.pre_send_rejection_detail = next(
            iter(terrain.KNOWN_PRE_SEND_REJECTIONS))
        self.pre_send_revision_delta = 0
        self.request_number = 0
        self.inventory = {'minecraft:diamond_shovel': 1,
                          'minecraft:diamond_pickaxe': 1,
                          'minecraft:dirt': 12,
                          'minecraft:grass_block': 0,
                          'minecraft:cobblestone': 0}
        self.entities = []
        self.actions = []
        self.uncertain_stage = None
        self.ghost_stage = None
        self.unacknowledged_stage = None
        self.fall_on_pickup = False
        self.animal_after_grass_mine = False
        self.omit_slot = None
        self.duplicate_slot = None
        self.area = {**paving.SITE,
                     'placement_key_sha256': hashlib.sha256(self.key.encode()).hexdigest()}

    def _items(self):
        rows = [
            {'slot': 0, 'item': 'minecraft:air', 'count': 0},
            {'slot': 1, 'item': 'minecraft:air', 'count': 0},
            {'slot': 2, 'item': 'minecraft:diamond_shovel', 'count': 1,
             'durability': self.shovel_durability,
             'enchantments': [{'id': 'minecraft:silk_touch', 'level': 1}] if self.silk else []},
            {'slot': 3, 'item': 'minecraft:diamond_pickaxe', 'count': 1,
             'durability': 700},
        ]
        slot = 4
        for item in ('minecraft:dirt', 'minecraft:grass_block', 'minecraft:cobblestone'):
            if self.inventory[item]:
                rows.append({'slot': slot, 'item': item, 'count': self.inventory[item]})
                slot += 1
        for n in range(slot, 36):
            rows.append({'slot': n, 'item': 'minecraft:air', 'count': 0})
        if self.omit_slot is not None:
            rows = [row for row in rows if row['slot'] != self.omit_slot]
        if self.duplicate_slot is not None:
            rows.append({'slot': self.duplicate_slot, 'item': 'minecraft:air', 'count': 0})
        return rows

    def status(self):
        self.time += 1
        rows=self._items()
        if self.selection_active and 0 <= self.selected_slot < 9:
            selected=rows[self.selected_slot]
            if selected.get('item') != self.hand:
                source=next((row for row in rows if row.get('item')==self.hand
                             and row.get('count',0)>0),None)
                if source is not None:
                    source_slot=source['slot']
                    rows[self.selected_slot]={**source,'slot':self.selected_slot}
                    rows[source_slot]={**selected,'slot':source_slot}
        return copy.deepcopy({
            'time': self.time, 'connected': True, 'world_session': self.world,
            'terrain_replace_protocol': self.protocol, 'dry_paving_protocol': 2,
            'server': 'simpcraft.com:25565', 'dimension': 'minecraft:overworld',
            'screen': '', 'manual_movement': False, 'health': 20, 'food': 20,
            'guard_armed': True, 'guard_pve_only': True, 'guard_busy': False,
            'flight': True, 'under_water': False, 'air_return_active': False,
            'safety_hold': {'active': False}, 'on_ground': self.on_ground,
            'game_mode': 'survival',
            'supervision_lease': {'kind': 'materials', 'job_session': self.task},
            'projection_selection': {'key': self.key, **self.area['bounds']},
            'pos': self.player, 'entities': self.entities, 'inventory': rows,
            'hand': {'item': self.hand, 'count': 1,
                     'durability': (self.shovel_durability
                                    if self.hand == 'minecraft:diamond_shovel' else 700),
                     'enchantments': ([{'id':'minecraft:silk_touch','level':1}]
                                      if self.hand=='minecraft:diamond_shovel' and self.silk
                                      else [])},
            'selected_slot': self.selected_slot, 'control_revision': self.revision,
            'last_request': self.last_request, 'phase': self.phase,
            'detail': self.detail})

    def model(self):
        return {'placement_key': self.key, 'content_hash': self.model_hash,
                'observed_at': self.time, 'total': 3701, 'expected': [
                    {'pos': list(self.pos), 'state': terrain.DIRT},
                    {'pos': [self.pos[0], 63, self.pos[2]], 'state': terrain.GRASS}]}

    def audit(self):
        mismatches = []
        for pos, expected, actual in ((list(self.pos), terrain.DIRT, self.base),
                                      ([self.pos[0], 63, self.pos[2]], terrain.GRASS, self.top)):
            if actual == expected:
                continue
            mismatches.append({'pos': pos, 'expected': expected,
                               'actual': actual or 'Block{minecraft:air}',
                               'kind': 'missing' if actual is None else 'occupied',
                               'block_entity': False, 'fluid': False,
                               'adjacent_fluid': False, 'neighbors_loaded': True})
        return {'mismatches': mismatches,
                'observed_at': self.time,
                'matched': 3701-len(mismatches), 'total': 3701}

    def context(self, *_):
        return self.status(), self.model(), self.audit()

    def _blocks(self, low, high):
        x, y, z = self.pos
        rows = [{'pos': [x, y-1, z], 'state': self.below, 'solid': True,
                 'replaceable': False, 'passable': False,
                 'fluid': False, 'block_entity': False}]
        if self.base:
            rows.append({'pos': [x, y, z], 'state': self.base,
                         'solid': True, 'replaceable': False, 'passable': False,
                         'fluid': False, 'block_entity': False})
        if self.top:
            rows.append({'pos': [x, y+1, z], 'state': self.top,
                         'solid': True, 'replaceable': False, 'passable': False,
                         'fluid': False, 'block_entity': False})
        rows += self.extra
        return [r for r in rows if all(low[i] <= r['pos'][i] <= high[i] for i in range(3))]

    def request(self, op, **params):
        self.actions.append((op, params))
        if op == 'scan':
            return {'world_session': self.world,
                    'blocks': self._blocks(params['min'], params['max'])}
        if op == 'navigate':
            self.player = list(params['target'])
            self.on_ground = False
            return {'phase': 'done'}
        if op == 'select_item':
            self.hand = params['item']
            self.selected_slot = params.get('slot', self.selected_slot)
            self.selection_active = True
            return {'phase': 'done'}
        if op in ('mine_block', 'interact'):
            stage = params.get('terrain_replace_stage')
            assert params.get('terrain_replace_guard') is True
            assert params.get('replacement_pos') == list(self.pos)
            assert params.get('placement_key') == self.key
            if stage == self.pre_send_rejection_stage:
                self.request_number += 1
                request_id = 'materials-preflight%04d' % self.request_number
                request = {'id': request_id, 'op': op, 'world_session': self.world,
                           'expected_revision': self.revision,
                           'task_session': self.task, 'background_ok': True, **params}
                (self.root / 'request.json').write_text(json.dumps(request))
                self.last_request = request_id
                self.phase = 'error'
                self.detail = self.pre_send_rejection_detail
                reply = {**self.status(), 'id': request_id, 'phase': 'error',
                         'detail': self.detail, 'world_session': self.world,
                         'control_revision': self.revision + self.pre_send_revision_delta}
                reply = json.loads(json.dumps(reply))
                (self.root / ('reply-' + request_id + '.json')).write_text(json.dumps(reply))
                return reply
            if stage == self.ghost_stage:
                return {'phase': 'done', 'server_confirmed': True,
                        'confirmation_scope': 'matched_server_block_update_after_native_send'}
            if stage == 'lift_grass':
                assert params.get('required_silk_shovel') is True
                assert params.get('expected_tool_slot') == self.selected_slot
                self.top = None
                item = 'minecraft:grass_block'
            elif stage == 'mine_stone':
                self.base = None
                item = 'minecraft:cobblestone'
            elif stage == 'place_dirt':
                assert params['pos'] == [self.pos[0], self.pos[1]-1, self.pos[2]]
                self.base = terrain.DIRT
                self.inventory['minecraft:dirt'] -= 1
                item = None
            elif stage == 'restore_grass':
                self.top = terrain.GRASS
                self.inventory['minecraft:grass_block'] -= 1
                item = None
            else:
                raise AssertionError(stage)
            if item:
                self.entities = [{'type': 'minecraft:item',
                                  'uuid': stage + '-drop',
                                  'pos': [self.pos[0]+.5, self.pos[1]+.5, self.pos[2]+.5],
                                  'stack': {'item': item, 'count': 1}}]
                if stage == 'lift_grass' and self.animal_after_grass_mine:
                    self.entities.append({'type': 'minecraft:cow', 'uuid': 'arriving-animal',
                                          'pos': [self.pos[0]+1.5, self.pos[1]+.5,
                                                  self.pos[2]+.5]})
            return {'phase': 'waiting' if stage == self.uncertain_stage else 'done',
                    'server_confirmed': stage != self.unacknowledged_stage
                        and stage != self.uncertain_stage,
                    'confirmation_scope': 'matched_server_block_update_after_native_send'
                        if stage != self.unacknowledged_stage else 'unverified'}
        if op == 'collect_item':
            drop = next(e for e in self.entities if e['uuid'] == params['expected_uuid'])
            self.inventory[drop['stack']['item']] += 1
            self.entities = []
            if self.fall_on_pickup:
                self.player = [self.pos[0]+.5, 63.0, self.pos[2]+.5]
            return {'phase': 'done'}
        raise AssertionError(op)

    def checked(self, op, **params):
        result = self.request(op, **params)
        if result.get('phase') != 'done':
            raise AssertionError(op + ' not confirmed')
        return result


class SouthTwoLayerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client = FakeClient(self.temp.name)
        site_patch = patch.object(paving, 'SITE', self.client.area)
        context_patch = patch.object(paving, '_fresh_context',
                                     side_effect=lambda *_: self.client.context())
        site_patch.start();context_patch.start()
        self.addCleanup(site_patch.stop);self.addCleanup(context_patch.stop)

    def journal(self):
        files = list(self.client.root.glob('terrain-replace-south-v1/*/*.json'))
        self.assertEqual(len(files), 1)
        return json.loads(files[0].read_text())

    def run_one(self):
        return terrain.replace_batch(self.client, settle=lambda _: None)

    @staticmethod
    def file_hash(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def legacy_pre_send_evidence(self):
        path = next(self.client.root.glob('terrain-replace-south-v1/*/*.json'))
        record = json.loads(path.read_text())
        request_id = 'materials-legacy-proof'
        detail = next(iter(terrain.KNOWN_PRE_SEND_REJECTIONS))
        x, y, z = self.client.pos
        params = {
            'task_session': self.client.task, 'background_ok': True,
            'pos': [x, y + 1, z], 'face': 'up', 'expected_state': terrain.GRASS,
            'required_silk_shovel': True, 'expected_tool_slot': 2,
            'expected_tool_item': 'minecraft:diamond_shovel', 'seconds': 20,
            'terrain_replace_guard': True, 'terrain_replace_stage': 'lift_grass',
            'replacement_pos': [x, y, z], 'expected_surface_state': terrain.GRASS,
            'expected_below_state': terrain.STONE, 'placement_key': self.client.key,
        }
        event = {
            'time': record['updated_at_ns'] / 1_000_000_000 + .1,
            'request_id': request_id, 'world_session': record['world_session'],
            'op': 'mine_block', 'params': params, 'phase': 'error', 'detail': detail,
            'pos': list(self.client.player), 'health': 20, 'duration_ms': 100,
            'inventory_delta': {}, 'revision_before': self.client.revision,
            'revision_after': self.client.revision,
            'position_before': list(self.client.player),
            'position_after': list(self.client.player),
            'health_before': 20, 'health_after': 20,
        }
        events_path = self.client.root / 'legacy-events.jsonl'
        events_path.write_text(json.dumps(event) + '\n')
        started = record['updated_at_ns'] / 1_000_000_000 - 1
        progress_path = self.client.root / 'progress.json'
        progress_path.write_text(json.dumps({
            'schema': 1, 'status': 'pending_review',
            'world_session': record['world_session'], 'task_session': self.client.task,
            'started_at': started, 'ended_at': started + 2,
            'cells_requested': [list(self.client.pos)], 'done': 0,
            'reason': 'Native lift_grass lacks a matching server block update; never replay it'}))
        manifest_path = self.client.root / ('run-manifest-' + self.client.task + '.json')
        manifest_path.write_text(json.dumps({
            'schema': 1, 'task_session': self.client.task,
            'created_at': int((started - 1) * 1000),
            'world_session': record['world_session'],
            'placement_key': record['placement_key'], 'complete': False}))
        reply = {**self.client.status(), 'id': request_id, 'phase': 'error',
                 'detail': detail, 'world_session': record['world_session'],
                 'control_revision': self.client.revision, 'selected_slot': 2,
                 'hand': {'item': 'minecraft:diamond_shovel', 'count': 1,
                          'durability': self.client.shovel_durability,
                          'enchantments': [{'id': 'minecraft:silk_touch', 'level': 1}]}}
        reply_path = self.client.root / ('reply-' + request_id + '.json')
        reply_path.write_text(json.dumps(reply))
        return {
            'schema': 1, 'kind': terrain.PRE_SEND_EVIDENCE_KIND,
            'cell': list(self.client.pos), 'stage': 'lift_grass',
            'task_session': self.client.task,
            'known_error': detail,
            'expected_unchanged_state': {
                'foundation': terrain.STONE, 'surface': terrain.GRASS,
                'grass_inventory': self.client.inventory['minecraft:grass_block'],
                'tool_item': 'minecraft:diamond_shovel',
                'tool_durability': self.client.shovel_durability},
            'journal': {'path': str(path.resolve()), 'sha256': self.file_hash(path)},
            'events': {'path': str(events_path.resolve()),
                       'sha256': self.file_hash(events_path),
                       'request_id': request_id},
            'progress': {'path': str(progress_path.resolve()),
                         'sha256': self.file_hash(progress_path)},
            'run_manifest': {'path': str(manifest_path.resolve()),
                             'sha256': self.file_hash(manifest_path)},
            'native_reply': {'path': str(reply_path.resolve()),
                             'sha256': self.file_hash(reply_path),
                             'request_id': request_id},
        }

    def legacy_restore_pre_send_evidence(self):
        path = next(self.client.root.glob('terrain-replace-south-v1/*/*.json'))
        record = json.loads(path.read_text())
        request_id = 'materials-legacy-restore'
        detail = next(iter(terrain.KNOWN_PRE_SEND_REJECTIONS))
        x, y, z = self.client.pos
        params = {
            'task_session': self.client.task, 'background_ok': True,
            'pos': [x, y, z], 'face': 'up', 'expected_state': terrain.DIRT,
            'expected_hand': 'minecraft:grass_block',
            'terrain_replace_guard': True, 'terrain_replace_stage': 'restore_grass',
            'replacement_pos': [x, y, z], 'expected_surface_state': terrain.GRASS,
            'expected_below_state': terrain.STONE, 'placement_key': self.client.key,
        }
        event = {
            'time': record['updated_at_ns'] / 1_000_000_000 + .1,
            'request_id': request_id, 'world_session': record['world_session'],
            'op': 'interact', 'params': params, 'phase': 'error', 'detail': detail,
            'pos': list(self.client.player), 'health': 20, 'duration_ms': 100,
            'inventory_delta': {}, 'revision_before': self.client.revision,
            'revision_after': self.client.revision,
            'position_before': list(self.client.player),
            'position_after': list(self.client.player),
            'health_before': 20, 'health_after': 20,
        }
        events_path = self.client.root / 'restore-events.jsonl'
        events_path.write_text(json.dumps(event) + '\n')
        started = record['updated_at_ns'] / 1_000_000_000 - 1
        progress_path = self.client.root / 'restore-progress.json'
        progress_path.write_text(json.dumps({
            'schema': 1, 'status': 'pending_review',
            'world_session': record['world_session'], 'task_session': self.client.task,
            'started_at': started, 'ended_at': started + 2,
            'cells_requested': [list(self.client.pos)], 'done': 0,
            'reason': 'Native restore_grass lacks a matching server block update; never replay it'}))
        manifest_path = self.client.root / 'restore-run-manifest.json'
        manifest_path.write_text(json.dumps({
            'schema': 1, 'task_session': self.client.task,
            'created_at': int((started - 1) * 1000),
            'world_session': record['world_session'],
            'placement_key': record['placement_key'], 'complete': False}))
        reply = {**self.client.status(), 'id': request_id, 'phase': 'error',
                 'detail': detail, 'world_session': record['world_session'],
                 'control_revision': self.client.revision,
                 'selected_slot': self.client.selected_slot,
                 'hand': {'item': 'minecraft:grass_block', 'count': 1}}
        reply = json.loads(json.dumps(reply))
        reply_path = self.client.root / ('reply-' + request_id + '.json')
        reply_path.write_text(json.dumps(reply))
        observation = {
            'world_session': record['world_session'],
            'observations': [
                {'time': 20001, 'blocks': [
                    {'pos': [x, y - 1, z], 'state': terrain.STONE, 'solid': True,
                     'fluid': False, 'block_entity': False},
                    {'pos': [x, y, z], 'state': terrain.GRASS, 'solid': True,
                     'fluid': False, 'block_entity': False}],
                 'grass_inventory': record['grass_reserve']},
                {'time': 20002, 'blocks': [
                    {'pos': [x, y - 1, z], 'state': terrain.STONE, 'solid': True,
                     'fluid': False, 'block_entity': False},
                    {'pos': [x, y, z], 'state': terrain.GRASS, 'solid': True,
                     'fluid': False, 'block_entity': False}],
                 'grass_inventory': record['grass_reserve']}],
            'audit': {'loaded': True, 'target': [
                {'pos': [x, y, z], 'expected': terrain.DIRT, 'actual': terrain.GRASS,
                 'kind': 'occupied', 'block_entity': False, 'fluid': False,
                 'neighbors_loaded': True, 'adjacent_fluid': False},
                {'pos': [x, y + 1, z], 'expected': terrain.GRASS,
                 'actual': 'Block{minecraft:air}', 'kind': 'missing',
                 'block_entity': False, 'fluid': False,
                 'neighbors_loaded': True, 'adjacent_fluid': False}]}}
        observation_path = self.client.root / 'restore-observation.json'
        observation_path.write_text(json.dumps(observation))
        return {
            'schema': 1, 'kind': terrain.PRE_SEND_EVIDENCE_KIND,
            'cell': list(self.client.pos), 'stage': 'restore_grass',
            'task_session': self.client.task, 'known_error': detail,
            'expected_unchanged_state': {
                'foundation_at_request': terrain.DIRT,
                'surface_at_request': 'Block{minecraft:air}',
                'post_failure_foundation': terrain.GRASS,
                'grass_inventory': record['grass_reserve'],
                'item': 'minecraft:grass_block'},
            'journal': {'path': str(path.resolve()), 'sha256': self.file_hash(path)},
            'events': {'path': str(events_path.resolve()),
                       'sha256': self.file_hash(events_path),
                       'request_id': request_id},
            'progress': {'path': str(progress_path.resolve()),
                         'sha256': self.file_hash(progress_path)},
            'run_manifest': {'path': str(manifest_path.resolve()),
                             'sha256': self.file_hash(manifest_path)},
            'native_reply': {'path': str(reply_path.resolve()),
                             'sha256': self.file_hash(reply_path),
                             'request_id': request_id},
            'post_failure_observation': {
                'path': str(observation_path.resolve()),
                'sha256': self.file_hash(observation_path)},
        }

    def legacy_post_send_lift_evidence(self):
        path = next(self.client.root.glob('terrain-replace-south-v1/*/*.json'))
        record = json.loads(path.read_text())
        task = record['receipts'][0]['task_session']
        mine_id = 'materials-post-send-lift'
        ascent_id = 'materials-owned-safety-ascent'
        drop_uuid = 'lift_grass-drop'
        x, y, z = self.client.pos
        revision = record['receipts'][0]['expected_revision']
        detail = 'An entity or loose item approached the terrain replacement'
        params = {
            'task_session': task, 'background_ok': True,
            'pos': [x, y + 1, z], 'face': 'up',
            'expected_state': terrain.GRASS, 'required_silk_shovel': True,
            'expected_tool_slot': 2,
            'expected_tool_item': 'minecraft:diamond_shovel', 'seconds': 20,
            'terrain_replace_guard': True,
            'terrain_replace_stage': 'lift_grass',
            'replacement_pos': [x, y, z],
            'expected_surface_state': terrain.GRASS,
            'expected_below_state': terrain.STONE,
            'placement_key': self.client.key,
        }
        mine_time = record['updated_at_ns'] / 1_000_000_000 + .1
        position = list(self.client.player)
        mine = {
            'time': mine_time, 'request_id': mine_id,
            'world_session': record['world_session'], 'op': 'mine_block',
            'params': params, 'phase': 'waiting', 'detail': detail,
            'pos': position, 'health': 20, 'duration_ms': 100,
            'inventory_delta': {}, 'revision_before': revision,
            'revision_after': revision + 1,
            'position_before': position, 'position_after': position,
            'health_before': 20, 'health_after': 20,
        }
        target = [position[0], position[1] + 40, position[2]]
        ascent = {
            'time': mine_time + 1, 'request_id': ascent_id,
            'world_session': record['world_session'], 'op': 'navigate',
            'params': {'task_session': task, 'background_ok': True,
                       'target': target, 'arrival': 1, 'seconds': 35,
                       'air_only': True},
            'phase': 'done',
            'detail': 'air-only waypoint reached and stable after restoring Flight settings',
            'pos': target, 'health': 20, 'duration_ms': 1000,
            'inventory_delta': {'minecraft:grass_block': 1},
            'revision_before': revision + 1,
            'revision_after': revision + 2,
            'position_before': position, 'position_after': target,
            'health_before': 20, 'health_after': 20,
        }
        events_path = self.client.root / 'post-send-events.jsonl'
        events_path.write_text(json.dumps(mine) + '\n' + json.dumps(ascent) + '\n')
        started = record['updated_at_ns'] / 1_000_000_000 - 1
        progress_path = self.client.root / 'post-send-progress.json'
        progress_path.write_text(json.dumps({
            'schema': 1, 'status': 'pending_review',
            'world_session': record['world_session'], 'task_session': task,
            'started_at': started, 'ended_at': mine_time + 2,
            'cells_requested': [list(self.client.pos)], 'done': 0,
            'reason': 'Native lift_grass lacks a matching server block update; never replay it'}))
        manifest_path = self.client.root / 'post-send-run-manifest.json'
        manifest_path.write_text(json.dumps({
            'schema': 1, 'task_session': task,
            'created_at': int((started - 1) * 1000),
            'world_session': record['world_session'],
            'placement_key': record['placement_key'], 'complete': False}))
        reply = self.client.status()
        reply.update(id=mine_id, phase='waiting', detail=detail,
                     world_session=record['world_session'],
                     control_revision=revision + 1, selected_slot=2,
                     hand={'item': 'minecraft:diamond_shovel', 'count': 1,
                           'durability': self.client.shovel_durability - 1,
                           'enchantments': [
                               {'id': 'minecraft:silk_touch', 'level': 1}]})
        for row in reply['inventory']:
            if row.get('slot') == 2:
                row['durability'] = self.client.shovel_durability - 1
        reply_path = self.client.root / ('reply-' + mine_id + '.json')
        reply_path.write_text(json.dumps(reply))
        return {
            'schema': 1, 'kind': terrain.POST_SEND_LIFT_EVIDENCE_KIND,
            'cell': list(self.client.pos), 'stage': 'lift_grass',
            'confirmation_scope': terrain.POST_SEND_CONFIRMATION_SCOPE,
            'task_session': task, 'mine_request_id': mine_id,
            'safety_ascent_request_id': ascent_id, 'drop_uuid': drop_uuid,
            'expected_transition': {
                'mine_revision_before': revision,
                'mine_revision_after': revision + 1,
                'safety_ascent_revision_after': revision + 2,
                'grass_inventory_before': record['grass_inventory_before'],
                'grass_inventory_after': record['grass_reserve'],
                'tool_durability_before': self.client.shovel_durability,
                'tool_durability_after': self.client.shovel_durability - 1},
            'journal': {'path': str(path.resolve()),
                        'sha256': self.file_hash(path)},
            'events': {'path': str(events_path.resolve()),
                       'sha256': self.file_hash(events_path),
                       'mine_request_id': mine_id,
                       'safety_ascent_request_id': ascent_id},
            'progress': {'path': str(progress_path.resolve()),
                         'sha256': self.file_hash(progress_path)},
            'run_manifest': {'path': str(manifest_path.resolve()),
                             'sha256': self.file_hash(manifest_path)},
            'native_reply': {'path': str(reply_path.resolve()),
                             'sha256': self.file_hash(reply_path),
                             'request_id': mine_id},
        }

    def test_exact_single_cell_lifts_stone_replaces_and_restores_with_proof(self):
        result = self.run_one()
        self.assertEqual(result[0]['result'], 'placed')
        self.assertEqual((self.client.base, self.client.top), (terrain.DIRT, terrain.GRASS))
        self.assertEqual([p['terrain_replace_stage'] for op, p in self.client.actions
                          if op in ('mine_block','interact')],
                         ['lift_grass','mine_stone','place_dirt','restore_grass'])
        exact=[(p['terrain_replace_stage'],p['pos'],p['face'])
               for op,p in self.client.actions if op in ('mine_block','interact')]
        x,y,z=terrain.CELLS[0]
        self.assertEqual([('lift_grass',[x,y+1,z],'up'),
                          ('mine_stone',[x,y,z],'up'),
                          ('place_dirt',[x,y-1,z],'up'),
                          ('restore_grass',[x,y,z],'up')],exact)
        self.assertEqual(self.journal()['phase'], 'complete')
        self.assertEqual(self.client.inventory['minecraft:grass_block'], 0)
        self.assertEqual(self.client.inventory['minecraft:dirt'], 11)
        self.assertEqual(self.client.inventory['minecraft:cobblestone'], 1)

    def test_backpack_silk_shovel_swap_uses_actual_hotbar_slot_for_native_guard(self):
        original_items=self.client._items
        original_request=self.client.request
        moved={'value':False,'source':None}
        def items():
            rows=original_items()
            shovel=next(row for row in rows if row['slot']==2)
            rows[2]={'slot':2,'item':'minecraft:air','count':0}
            if moved['value']:
                for slot in range(35,5,-1):
                    rows[slot]={**rows[slot-1],'slot':slot}
                rows[5]={**shovel,'slot':5}
            else:
                rows[28]={**shovel,'slot':28}
            return rows
        def request(op,**params):
            if op=='select_item' and params.get('item')=='minecraft:diamond_shovel':
                moved['source']=params.get('slot')
                moved['value']=True
                return original_request(op,item=params['item'],slot=5)
            return original_request(op,**params)
        self.client._items=items
        self.client.request=request
        result=self.run_one()
        self.assertEqual('placed',result[0]['result'])
        self.assertEqual(28,moved['source'])
        grass_mines=[params for op,params in self.client.actions
                     if op=='mine_block' and params.get('terrain_replace_stage')=='lift_grass']
        self.assertEqual(1,len(grass_mines))
        self.assertEqual(5,grass_mines[0]['expected_tool_slot'])
        self.assertEqual('complete',self.journal()['phase'])

    def test_backpack_pickaxe_swap_selects_source_once_then_mines(self):
        original_items=self.client._items
        original_request=self.client.request
        moved={'value':False,'sources':[]}
        def items():
            rows=original_items()
            pickaxe=next(row for row in rows if row['slot']==3)
            rows[3]={'slot':3,'item':'minecraft:air','count':0}
            if moved['value']:
                for slot in range(35,6,-1):
                    rows[slot]={**rows[slot-1],'slot':slot}
                rows[6]={**pickaxe,'slot':6}
            else:
                rows[29]={**pickaxe,'slot':29}
            return rows
        def request(op,**params):
            if op=='select_item' and params.get('item')=='minecraft:diamond_pickaxe':
                moved['sources'].append(params.get('slot'))
                moved['value']=True
                return original_request(op,item=params['item'],slot=6)
            return original_request(op,**params)
        self.client._items=items
        self.client.request=request
        result=self.run_one()
        self.assertEqual('placed',result[0]['result'])
        self.assertEqual([29],moved['sources'])
        stone_mines=[params for op,params in self.client.actions
                     if op=='mine_block' and params.get('terrain_replace_stage')=='mine_stone']
        self.assertEqual(1,len(stone_mines))
        self.assertEqual('complete',self.journal()['phase'])

    def test_no_native_guard_or_silk_tool_never_writes_mine_intent(self):
        for change in ('protocol', 'silk'):
            with self.subTest(change=change):
                self.client = FakeClient(Path(self.temp.name) / change)
                if change == 'protocol':self.client.protocol = 0
                else:self.client.silk = False
                with self.assertRaises(paving.PavingBlocked):self.run_one()
                self.assertEqual(list(self.client.root.glob('terrain-replace-south-v1/*/*.json')), [])
                self.assertFalse(any(op == 'mine_block' for op,_ in self.client.actions))

    def test_missing_or_duplicate_backpack_slot_blocks_before_lift_intent(self):
        for change in ('missing', 'duplicate'):
            with self.subTest(change=change):
                self.client = FakeClient(Path(self.temp.name) / change)
                if change == 'missing':self.client.omit_slot = 35
                else:self.client.duplicate_slot = 34
                with self.assertRaisesRegex(paving.PavingBlocked, 'Backpack capacity'):
                    self.run_one()
                self.assertEqual(list(self.client.root.glob('terrain-replace-south-v1/*/*.json')), [])
                self.assertFalse(any(op == 'mine_block' for op,_ in self.client.actions))

    def test_user_flower_above_or_fluid_nearby_never_starts_mining(self):
        for name, row in (
            ('flower', {'pos':[terrain.CELLS[0][0],64,797865],
                        'state':'Block{minecraft:allium}','solid':False,
                        'fluid':False,'block_entity':False}),
            ('water', {'pos':[terrain.CELLS[0][0]+1,62,797865],
                       'state':'Block{minecraft:water}[level=0]','solid':False,
                       'fluid':True,'block_entity':False})):
            with self.subTest(name=name):
                self.client = FakeClient(Path(self.temp.name) / name)
                self.client.extra = [row]
                with self.assertRaises(paving.PavingBlocked):self.run_one()
                self.assertFalse(any(op == 'mine_block' for op,_ in self.client.actions))

    def test_grounded_pose_inside_native_height_band_never_lifts_original_grass(self):
        x, _, z = terrain.CELLS[0]
        self.client.player = [x + .5003771636, 64.13744900638982,
                              z + .4669847823]
        self.client.on_ground = True
        with self.assertRaises(paving.PavingBlocked):
            terrain._station_status(self.client, terrain.CELLS[0])
        self.assertFalse(any(op == 'mine_block' for op,_ in self.client.actions))

    def test_native_y64_137_settle_waits_for_new_stable_frame(self):
        x, _, z = terrain.CELLS[0]
        settled = [x + .5003771636, 64.13744900638982,
                   z + .4669847823]
        self.client.player = settled.copy()
        original_status = self.client.status
        calls = 0

        def delayed_new_frame():
            nonlocal calls
            calls += 1
            result = original_status()
            result['time'] = 10000 if calls <= 2 else 10001
            return result

        self.client.status = delayed_new_frame
        observed = terrain._reach_station(self.client, terrain.CELLS[0])
        self.assertEqual(settled, observed['pos'])
        self.assertEqual(10001, observed['time'])
        self.assertEqual(3, calls)
        self.assertEqual([x + .5, 64.3, z + .5],
                         terrain._station(terrain.CELLS[0]))
        self.assertFalse(any(op in ('navigate', 'mine_block', 'interact')
                             for op, _ in self.client.actions))

    def test_station_below_native_flight_floor_is_rejected_before_any_mine(self):
        x, y, z = terrain.CELLS[0]
        self.client.player = [x + .5, y + 2.079, z + .5]
        with self.assertRaisesRegex(paving.PavingBlocked, 'stable flight pose'):
            terrain._station_status(self.client, terrain.CELLS[0])
        self.assertFalse(any(op in ('mine_block', 'interact')
                             for op, _ in self.client.actions))

    def test_station_arrival_envelope_rejects_vertical_and_horizontal_misses(self):
        x, _, z = terrain.CELLS[0]
        for point in ([x + .5, 64.100001, z + .5],
                      [x + .5, 64.499999, z + .5],
                      [x + .699999, 64.3, z + .5]):
            with self.subTest(point=point):
                self.assertTrue(terrain._station_pose_ok(point, terrain.CELLS[0]))
        for point in ([x + .5, 64.099, z + .5],
                      [x + .5, 64.501, z + .5],
                      [x + .701, 64.3, z + .5]):
            with self.subTest(point=point):
                self.assertFalse(terrain._station_pose_ok(point, terrain.CELLS[0]))

    def test_same_tick_station_reads_wait_for_new_safe_frame_without_action(self):
        original_status=self.client.status
        calls=0
        def slow_frame():
            nonlocal calls
            calls+=1
            result=original_status()
            result['time']=10000 if calls<=3 else 10001
            return result
        self.client.status=slow_frame
        observed=terrain._reach_station(self.client,terrain.CELLS[0])
        self.assertEqual(10001,observed['time'])
        self.assertGreaterEqual(calls,4)
        self.assertFalse(any(op in ('navigate','mine_block','interact')
                             for op,_ in self.client.actions))

    def test_new_station_frame_uses_separate_horizontal_and_vertical_stability(self):
        x, _, z = terrain.CELLS[0]
        self.client.player = [x + .5, 64.2, z + .5]
        first = terrain._station_status(self.client, terrain.CELLS[0])
        original_status = self.client.status

        def next_frame():
            result = original_status()
            result['pos'][0] += .004
            result['pos'][1] += .004
            return result

        self.client.status = next_frame
        observed = terrain._next_station_frame(
            self.client, terrain.CELLS[0], first, seconds=.1)
        self.assertEqual([first['pos'][0] + .004, first['pos'][1] + .004,
                          first['pos'][2]], observed['pos'])

    def test_new_station_frame_rejects_vertical_drift_before_any_mine(self):
        x, _, z = terrain.CELLS[0]
        self.client.player = [x + .5, 64.2, z + .5]
        first = terrain._station_status(self.client, terrain.CELLS[0])
        original_status = self.client.status

        def drifting_frame():
            result = original_status()
            result['pos'][1] += .006
            return result

        self.client.status = drifting_frame
        with self.assertRaisesRegex(paving.PavingBlocked, 'moved'):
            terrain._next_station_frame(
                self.client, terrain.CELLS[0], first, seconds=.1)
        self.assertFalse(any(op in ('navigate', 'mine_block', 'interact')
                             for op, _ in self.client.actions))

    def test_same_tick_station_drift_is_rejected_before_any_mine(self):
        x, _, z = terrain.CELLS[0]
        settled = [x + .5003771636, 64.13744900638982,
                   z + .4669847823]
        self.client.player = settled.copy()
        original_status=self.client.status
        calls=0
        def drifting_frame():
            nonlocal calls
            calls+=1
            result=original_status()
            result['time']=10000
            if calls>=3:result['pos'][0]+=.1
            return result
        self.client.status=drifting_frame
        with self.assertRaisesRegex(paving.PavingBlocked,'moved'):
            terrain._reach_station(self.client,terrain.CELLS[0])
        self.assertFalse(any(op in ('navigate','mine_block','interact')
                             for op,_ in self.client.actions))

    def test_known_live_preflight_error_retries_in_same_world_only_under_new_task(self):
        self.client.pre_send_rejection_stage = 'lift_grass'
        with self.assertRaisesRegex(paving.PavingPending, 'rejected before send'):
            self.run_one()
        journal = self.journal()
        self.assertEqual('pre_send_rejected', journal['phase'])
        self.assertEqual(['lift_intent', 'pre_send_rejected'],
                         [receipt['phase'] for receipt in journal['receipts']])
        rejected = journal['receipts'][-1]
        self.assertIs(False, rejected['action_sent'])
        self.assertEqual(self.client.revision, rejected['expected_revision'])
        self.assertEqual(self.client.revision, rejected['observed_control_revision'])
        self.assertEqual((terrain.STONE, terrain.GRASS),
                         (self.client.base, self.client.top))
        with self.assertRaisesRegex(paving.PavingPending, 'new material task session'):
            self.run_one()
        self.assertEqual(1, sum(op == 'mine_block' for op, _ in self.client.actions))

        self.client.task = 'materials-recovery'
        self.client.pre_send_rejection_stage = None
        self.client.phase = None
        self.client.detail = None
        self.assertEqual('placed', self.run_one()[0]['result'])
        journal = self.journal()
        self.assertEqual('complete', journal['phase'])
        self.assertTrue(any(receipt.get('event') == 'pre_send_task_rebind'
                            and receipt['phase'] == 'pre_send_rejected'
                            for receipt in journal['receipts']))
        self.assertEqual(2, sum(op == 'mine_block'
                                and params.get('terrain_replace_stage') == 'lift_grass'
                                for op, params in self.client.actions))

    def test_unknown_native_error_remains_uncertain_and_never_retries(self):
        self.client.pre_send_rejection_stage = 'lift_grass'
        self.client.pre_send_rejection_detail = 'unclassified native error'
        with self.assertRaisesRegex(paving.PavingPending, 'matching server block update'):
            self.run_one()
        self.assertEqual('lift_intent', self.journal()['phase'])
        self.client.world = 'world-2'
        self.client.pre_send_rejection_stage = None
        with self.assertRaisesRegex(paving.PavingPending, 'uncertain'):
            self.run_one()
        self.assertEqual(1, sum(op == 'mine_block' for op, _ in self.client.actions))

    def test_known_error_with_control_revision_advance_remains_uncertain(self):
        self.client.pre_send_rejection_stage = 'lift_grass'
        self.client.pre_send_revision_delta = 1
        with self.assertRaisesRegex(paving.PavingPending, 'matching server block update'):
            self.run_one()
        self.assertEqual('lift_intent', self.journal()['phase'])
        self.assertFalse(any(receipt.get('phase') == 'pre_send_rejected'
                             for receipt in self.journal()['receipts']))

    def test_restore_preflight_rejection_retries_same_world_under_new_task(self):
        self.client.pre_send_rejection_stage = 'restore_grass'
        with self.assertRaisesRegex(paving.PavingPending, 'restore_grass was rejected before send'):
            self.run_one()
        journal = self.journal()
        self.assertEqual('pre_send_rejected', journal['phase'])
        rejected = journal['receipts'][-1]
        self.assertEqual('restore_grass', rejected['stage'])
        self.assertIs(False, rejected['action_sent'])
        self.assertEqual(1, self.client.inventory['minecraft:grass_block'])
        self.assertEqual((terrain.DIRT, None), (self.client.base, self.client.top))
        with self.assertRaisesRegex(paving.PavingPending, 'new material task session'):
            self.run_one()
        restore_before = sum(params.get('terrain_replace_stage') == 'restore_grass'
                             for op, params in self.client.actions if op == 'interact')
        self.assertEqual(1, restore_before)

        self.client.task = 'materials-restore-recovery'
        self.client.pre_send_rejection_stage = None
        self.client.phase = None
        self.client.detail = None
        self.assertEqual('placed', self.run_one()[0]['result'])
        self.assertEqual(0, self.client.inventory['minecraft:grass_block'])
        restores = [params for op, params in self.client.actions
                    if op == 'interact'
                    and params.get('terrain_replace_stage') == 'restore_grass']
        self.assertEqual(2, len(restores))
        self.assertEqual(terrain.DIRT, restores[-1]['expected_state'])

    def test_unknown_restore_error_remains_uncertain_and_never_replays(self):
        self.client.pre_send_rejection_stage = 'restore_grass'
        self.client.pre_send_rejection_detail = 'unclassified restore error'
        with self.assertRaisesRegex(paving.PavingPending, 'matching server block update'):
            self.run_one()
        self.assertEqual('grass_restore_intent', self.journal()['phase'])
        restores = sum(params.get('terrain_replace_stage') == 'restore_grass'
                       for op, params in self.client.actions if op == 'interact')
        self.client.world = 'world-2'
        self.client.pre_send_rejection_stage = None
        with self.assertRaisesRegex(paving.PavingPending, 'uncertain'):
            self.run_one()
        self.assertEqual(restores, sum(
            params.get('terrain_replace_stage') == 'restore_grass'
            for op, params in self.client.actions if op == 'interact'))

    def test_spread_foundation_places_upper_grass_once_then_waits_for_natural_decay(self):
        with patch.object(terrain, '_finish_grass', side_effect=paving.PavingBlocked('pause')):
            with self.assertRaises(paving.PavingBlocked):
                self.run_one()
        self.assertEqual('dirt_placed', self.journal()['phase'])
        self.assertEqual(1, self.client.inventory['minecraft:grass_block'])
        self.client.base = terrain.GRASS
        self.client.top = None
        with self.assertRaisesRegex(paving.PavingPending, 'natural dirt decay'):
            self.run_one()
        self.assertEqual('grass_decay_wait', self.journal()['phase'])
        self.assertEqual((terrain.GRASS, terrain.GRASS),
                         (self.client.base, self.client.top))
        self.assertEqual(0, self.client.inventory['minecraft:grass_block'])
        restores = [params for op, params in self.client.actions
                    if op == 'interact'
                    and params.get('terrain_replace_stage') == 'restore_grass']
        self.assertEqual(1, len(restores))
        self.assertEqual(terrain.GRASS, restores[0]['expected_state'])
        self.assertFalse(any(op == 'mine_block' and params.get('pos') == list(self.client.pos)
                             for op, params in self.client.actions
                             if params.get('terrain_replace_stage') == 'restore_grass'))

        self.client.base = terrain.DIRT
        self.assertEqual('placed', self.run_one()[0]['result'])
        self.assertEqual('complete', self.journal()['phase'])
        self.assertEqual(1, len([params for op, params in self.client.actions
                                if op == 'interact'
                                and params.get('terrain_replace_stage') == 'restore_grass']))
        decay = next(receipt for receipt in self.journal()['receipts']
                     if receipt.get('event') == 'covered_foundation_naturally_decayed')
        self.assertIs(True, decay['loaded_double_scan'])
        self.assertIs(True, decay['full_projection_confirmed'])

    def test_legacy_restore_evidence_binds_run_then_recovers_spread_foundation(self):
        self.client.pre_send_rejection_stage = 'restore_grass'
        self.client.pre_send_rejection_detail = 'unclassified restore error'
        with self.assertRaises(paving.PavingPending):
            self.run_one()
        self.assertEqual('grass_restore_intent', self.journal()['phase'])
        evidence = self.legacy_restore_pre_send_evidence()
        self.client.base = terrain.GRASS
        self.client.top = None
        self.client.task = 'materials-restore-recovery'
        self.client.pre_send_rejection_stage = None
        self.client.phase = None
        self.client.detail = None
        with self.assertRaisesRegex(paving.PavingPending, 'natural dirt decay'):
            terrain.replace_batch(
                self.client, cells=[self.client.pos], max_cells=1,
                settle=lambda _: None, pre_send_evidence=evidence)
        journal = self.journal()
        rejected = next(receipt for receipt in journal['receipts']
                        if receipt.get('stage') == 'restore_grass'
                        and receipt.get('event') == 'native_preflight_rejected_before_send')
        self.assertEqual('immutable_legacy_event_and_reply', rejected['source'])
        self.assertEqual(terrain.GRASS, rejected['post_failure_foundation_state'])
        self.assertEqual('grass_decay_wait', journal['phase'])
        self.assertEqual(0, self.client.inventory['minecraft:grass_block'])
        self.client.base = terrain.DIRT
        self.assertEqual('placed', self.run_one()[0]['result'])
        self.assertEqual('complete', self.journal()['phase'])

    def test_legacy_exact_event_and_reply_can_reconcile_without_deleting_intent(self):
        self.client.uncertain_stage = 'lift_grass'
        with self.assertRaises(paving.PavingPending):
            self.run_one()
        self.client.top = terrain.GRASS
        self.client.entities = []
        evidence = self.legacy_pre_send_evidence()
        self.client.task = 'materials-lift-recovery'
        self.client.uncertain_stage = None
        result = terrain.replace_batch(
            self.client, cells=[self.client.pos], max_cells=1,
            settle=lambda _: None, pre_send_evidence=evidence)
        self.assertEqual('placed', result[0]['result'])
        receipts = self.journal()['receipts']
        phases = [receipt['phase'] for receipt in receipts]
        self.assertEqual('lift_intent', phases[0])
        self.assertIn('pre_send_rejected', phases)
        self.assertGreater(phases.count('lift_intent'), 1)
        rejected = next(receipt for receipt in receipts
                        if receipt.get('event') == 'native_preflight_rejected_before_send')
        self.assertEqual('immutable_legacy_event_and_reply', rejected['source'])
        self.assertIs(False, rejected['action_sent'])

    def test_legacy_reconciliation_rejects_changed_hash_revision_and_same_task(self):
        for change in ('hash', 'revision', 'task', 'same_task'):
            with self.subTest(change=change):
                self.client = FakeClient(Path(self.temp.name) / change)
                self.client.uncertain_stage = 'lift_grass'
                with self.assertRaises(paving.PavingPending):
                    self.run_one()
                self.client.top = terrain.GRASS
                self.client.entities = []
                evidence = self.legacy_pre_send_evidence()
                if change == 'hash':
                    evidence['events']['sha256'] = '0' * 64
                elif change == 'revision':
                    reply_path = Path(evidence['native_reply']['path'])
                    reply = json.loads(reply_path.read_text())
                    reply['control_revision'] += 1
                    reply_path.write_text(json.dumps(reply))
                    evidence['native_reply']['sha256'] = self.file_hash(reply_path)
                elif change == 'task':
                    events_path = Path(evidence['events']['path'])
                    event = json.loads(events_path.read_text())
                    event['params']['task_session'] = 'materials-other-task'
                    events_path.write_text(json.dumps(event) + '\n')
                    evidence['events']['sha256'] = self.file_hash(events_path)
                else:
                    pass
                if change != 'same_task':
                    self.client.task = 'materials-recovery'
                self.client.uncertain_stage = None
                with self.assertRaises(paving.PavingPending):
                    terrain.replace_batch(
                        self.client, cells=[self.client.pos], max_cells=1,
                        settle=lambda _: None, pre_send_evidence=evidence)
                self.assertEqual('lift_intent', self.journal()['phase'])
                self.assertEqual(1, sum(op == 'mine_block' for op, _ in self.client.actions))

    def test_pre_send_rebind_worlds_and_request_identity_are_history_bound(self):
        self.client.pre_send_rejection_stage = 'lift_grass'
        with self.assertRaises(paving.PavingPending):
            self.run_one()
        self.client.world = 'world-2'
        self.client.task = 'materials-recovery'
        self.client.pre_send_rejection_stage = None
        self.client.phase = None
        self.client.detail = None
        self.run_one()
        original = self.journal()
        for field, value in (('previous_world_session', 'forged-old'),
                             ('current_world_session', 'forged-new'),
                             ('pre_send_request_id', 'forged-request'),
                             ('pre_send_stage', 'restore_grass')):
            with self.subTest(field=field):
                record = copy.deepcopy(original)
                rebind = next(receipt for receipt in record['receipts']
                              if receipt.get('event') == 'world_session_rebind'
                              and receipt.get('phase') == 'pre_send_rejected')
                rebind[field] = value
                with self.assertRaises(paving.PavingPending):
                    terrain._validated_history(record)

    def test_same_world_pre_send_task_rebind_identity_is_history_bound(self):
        self.client.pre_send_rejection_stage = 'restore_grass'
        with self.assertRaises(paving.PavingPending):
            self.run_one()
        self.client.task = 'materials-restore-recovery'
        self.client.pre_send_rejection_stage = None
        self.client.phase = None
        self.client.detail = None
        self.run_one()
        original = self.journal()
        terrain._validated_history(original)
        for field, value in (('world_session', 'forged-world'),
                             ('previous_task_session', 'forged-old-task'),
                             ('current_task_session', 'forged-new-task'),
                             ('pre_send_request_id', 'forged-request'),
                             ('pre_send_stage', 'lift_grass')):
            with self.subTest(field=field):
                record = copy.deepcopy(original)
                rebind = next(receipt for receipt in record['receipts']
                              if receipt.get('event') == 'pre_send_task_rebind')
                rebind[field] = value
                with self.assertRaises(paving.PavingPending):
                    terrain._validated_history(record)

    def test_crash_after_world_rebind_can_chain_a_new_task_for_lift_and_restore(self):
        for stage, retry_name in (('lift_grass', '_retry_pre_send_lift'),
                                  ('restore_grass', '_retry_pre_send_restore')):
            with self.subTest(stage=stage):
                self.client = FakeClient(Path(self.temp.name) / ('crash-' + stage))
                self.client.pre_send_rejection_stage = stage
                with self.assertRaises(paving.PavingPending):
                    self.run_one()
                self.client.world = 'world-2'
                self.client.task = 'materials-recovery-2'
                self.client.pre_send_rejection_stage = None
                self.client.phase = None
                self.client.detail = None
                with patch.object(terrain, retry_name,
                                  side_effect=paving.PavingBlocked('simulated crash window')):
                    with self.assertRaisesRegex(paving.PavingBlocked, 'crash window'):
                        self.run_one()
                journal = self.journal()
                self.assertEqual('pre_send_rejected', journal['phase'])
                self.assertEqual('world_session_rebind', journal['receipts'][-1]['event'])
                self.client.task = 'materials-recovery-3'
                self.assertEqual('placed', self.run_one()[0]['result'])
                journal = self.journal()
                self.assertEqual('complete', journal['phase'])
                rebinds = [receipt for receipt in journal['receipts']
                           if receipt.get('phase') == 'pre_send_rejected'
                           and receipt.get('event') in (
                               'world_session_rebind', 'pre_send_task_rebind')]
                self.assertEqual(['world_session_rebind', 'pre_send_task_rebind'],
                                 [receipt['event'] for receipt in rebinds])
                self.assertEqual('materials-recovery-2',
                                 rebinds[-1]['previous_task_session'])
                self.assertEqual('materials-recovery-3',
                                 rebinds[-1]['current_task_session'])

    def test_reconnect_proof_requires_original_stock_tool_column_and_clear_entity_ring(self):
        for change in ('grass', 'tool', 'column', 'drop', 'horse'):
            with self.subTest(change=change):
                self.client = FakeClient(Path(self.temp.name) / ('reconnect-' + change))
                self.client.pre_send_rejection_stage = 'lift_grass'
                with self.assertRaises(paving.PavingPending):
                    self.run_one()
                self.client.task = 'materials-recovery-' + change
                self.client.pre_send_rejection_stage = None
                self.client.phase = None
                self.client.detail = None
                if change == 'grass':
                    self.client.inventory['minecraft:grass_block'] = 1
                elif change == 'tool':
                    self.client.shovel_durability -= 1
                elif change == 'column':
                    self.client.top = None
                elif change == 'drop':
                    self.client.entities = [{
                        'type': 'minecraft:item', 'uuid': 'unexpected-drop',
                        'pos': [self.client.pos[0] + .5, 63.5, self.client.pos[2] + .5],
                        'stack': {'item': 'minecraft:grass_block', 'count': 1}}]
                else:
                    self.client.entities = [{
                        'type': 'minecraft:horse', 'uuid': 'near-ring-horse',
                        'pos': [self.client.pos[0] - 2.8, 64,
                                self.client.pos[2] - 2.0]}]
                with self.assertRaises(paving.PavingBlocked):
                    self.run_one()
                self.assertEqual(1, sum(op == 'mine_block' for op, _ in self.client.actions))

    def prepare_post_send_lift(self, *, world=None):
        self.client.uncertain_stage = 'lift_grass'
        with self.assertRaises(paving.PavingPending):
            self.run_one()
        self.assertEqual('lift_intent', self.journal()['phase'])
        evidence = self.legacy_post_send_lift_evidence()
        self.client.uncertain_stage = None
        self.client.task = 'materials-post-send-recovery'
        self.client.revision = evidence['expected_transition'][
            'safety_ascent_revision_after']
        self.client.shovel_durability = evidence['expected_transition'][
            'tool_durability_after']
        self.client.inventory['minecraft:grass_block'] = 1
        self.client.entities = []
        self.client.phase = None
        self.client.detail = None
        if world is not None:
            self.client.world = world
        return evidence

    def test_explicit_post_send_lift_recovery_never_replays_lift(self):
        evidence = self.prepare_post_send_lift()
        result = terrain.replace_batch(
            self.client, cells=[self.client.pos], max_cells=1,
            settle=lambda _: None, post_send_evidence=evidence)
        self.assertEqual('placed', result[0]['result'])
        journal = self.journal()
        self.assertEqual('complete', journal['phase'])
        self.assertEqual(1, sum(
            params.get('terrain_replace_stage') == 'lift_grass'
            for op, params in self.client.actions if op == 'mine_block'))
        self.assertEqual(1, sum(
            params.get('terrain_replace_stage') == 'mine_stone'
            for op, params in self.client.actions if op == 'mine_block'))
        reconciled = [receipt for receipt in journal['receipts']
                      if receipt.get('confirmation_scope')
                      == terrain.POST_SEND_CONFIRMATION_SCOPE]
        self.assertEqual(['grass_mined', 'grass_recovered'],
                         [receipt['phase'] for receipt in reconciled])
        self.assertTrue(all(receipt['server_confirmed'] is False
                            for receipt in reconciled))
        self.assertEqual('lift_grass-drop', reconciled[0]['drop_uuid'])

    def test_post_send_recovery_survives_crash_after_each_durable_receipt(self):
        evidence = self.prepare_post_send_lift()
        with patch.object(terrain, '_append_post_send_grass_recovered',
                          side_effect=RuntimeError('crash after grass_mined')):
            with self.assertRaisesRegex(RuntimeError, 'after grass_mined'):
                terrain.replace_batch(
                    self.client, cells=[self.client.pos], max_cells=1,
                    settle=lambda _: None, post_send_evidence=evidence)
        self.assertEqual('grass_mined', self.journal()['phase'])
        with patch.object(terrain, '_finish_stone_and_restore',
                          side_effect=paving.PavingBlocked(
                              'crash after grass_recovered')):
            with self.assertRaisesRegex(paving.PavingBlocked,
                                        'after grass_recovered'):
                terrain.replace_batch(
                    self.client, cells=[self.client.pos], max_cells=1,
                    settle=lambda _: None, post_send_evidence=evidence)
        self.assertEqual('grass_recovered', self.journal()['phase'])
        self.assertEqual('placed', terrain.replace_batch(
            self.client, cells=[self.client.pos], max_cells=1,
            settle=lambda _: None, post_send_evidence=evidence)[0]['result'])
        self.assertEqual(1, sum(
            params.get('terrain_replace_stage') == 'lift_grass'
            for op, params in self.client.actions if op == 'mine_block'))

    def test_post_send_mined_crash_rebinds_observation_before_stone(self):
        evidence = self.prepare_post_send_lift(world='world-2')
        with patch.object(terrain, '_append_post_send_grass_recovered',
                          side_effect=RuntimeError('crash after grass_mined')):
            with self.assertRaisesRegex(RuntimeError, 'after grass_mined'):
                terrain.replace_batch(
                    self.client, cells=[self.client.pos], max_cells=1,
                    settle=lambda _: None, post_send_evidence=evidence)
        mined = self.journal()['receipts'][-1]
        self.assertEqual('grass_mined', mined['phase'])
        self.assertEqual('world-2', mined['current_world_session'])
        self.client.world = 'world-3'
        self.assertEqual('placed', terrain.replace_batch(
            self.client, cells=[self.client.pos], max_cells=1,
            settle=lambda _: None, post_send_evidence=evidence)[0]['result'])
        journal = self.journal()
        terrain._validated_history(journal)
        recovered = next(receipt for receipt in journal['receipts']
                         if receipt.get('confirmation_scope')
                         == terrain.POST_SEND_CONFIRMATION_SCOPE
                         and receipt.get('phase') == 'grass_recovered')
        self.assertEqual('world-2',
                         recovered['previous_observation_world_session'])
        self.assertEqual('world-3', recovered['current_world_session'])
        rebind = next(receipt for receipt in journal['receipts']
                      if receipt.get('event') == 'world_session_rebind'
                      and receipt.get('phase') == 'grass_recovered')
        self.assertEqual('world-1', rebind['previous_world_session'])
        self.assertEqual('world-3', rebind['current_world_session'])
        self.assertEqual(1, sum(
            params.get('terrain_replace_stage') == 'lift_grass'
            for op, params in self.client.actions if op == 'mine_block'))

    def test_post_send_lift_can_rebind_new_world_only_after_recovery_receipts(self):
        evidence = self.prepare_post_send_lift(world='world-2')
        result = terrain.replace_batch(
            self.client, cells=[self.client.pos], max_cells=1,
            settle=lambda _: None, post_send_evidence=evidence)
        self.assertEqual('placed', result[0]['result'])
        journal = self.journal()
        rebind = next(receipt for receipt in journal['receipts']
                      if receipt.get('event') == 'world_session_rebind'
                      and receipt.get('phase') == 'grass_recovered')
        self.assertEqual('world-1', rebind['previous_world_session'])
        self.assertEqual('world-2', rebind['current_world_session'])
        self.assertEqual('world-2', journal['world_session'])
        self.assertEqual(1, sum(
            params.get('terrain_replace_stage') == 'lift_grass'
            for op, params in self.client.actions if op == 'mine_block'))

    def test_post_send_durable_receipt_identity_is_history_bound(self):
        evidence = self.prepare_post_send_lift()
        terrain.replace_batch(
            self.client, cells=[self.client.pos], max_cells=1,
            settle=lambda _: None, post_send_evidence=evidence)
        original = self.journal()
        terrain._validated_history(original)
        cases = (
            ('grass_mined', 'request_id', 'materials-forged'),
            ('grass_mined', 'current_tool_durability', 1),
            ('grass_recovered', 'previous_observation_world_session', 'world-forged'),
            ('grass_recovered', 'current_world_session', ''),
            ('grass_recovered', 'model_hash', 'model-forged'),
        )
        for phase, field, value in cases:
            with self.subTest(phase=phase, field=field):
                record = copy.deepcopy(original)
                receipt = next(row for row in record['receipts']
                               if row.get('phase') == phase
                               and row.get('confirmation_scope')
                               == terrain.POST_SEND_CONFIRMATION_SCOPE)
                receipt[field] = value
                with self.assertRaises(paving.PavingPending):
                    terrain._validated_history(record)

    def test_post_send_lift_rejects_tampered_owned_chain_and_current_state(self):
        for change in ('duplicate_lift', 'placement', 'gain', 'task', 'world',
                       'revision', 'request', 'hash', 'drop', 'inventory', 'tool'):
            with self.subTest(change=change):
                self.client = FakeClient(Path(self.temp.name) / ('post-' + change))
                evidence = self.prepare_post_send_lift()
                if change in ('duplicate_lift', 'placement', 'gain', 'task',
                              'world', 'revision'):
                    events_path = Path(evidence['events']['path'])
                    rows = [json.loads(line) for line in events_path.read_text().splitlines()]
                    if change == 'duplicate_lift':
                        duplicate = copy.deepcopy(rows[0])
                        duplicate['request_id'] = 'materials-second-lift'
                        rows.append(duplicate)
                    elif change == 'placement':
                        rows.append({
                            'time': rows[-1]['time'] + .1,
                            'request_id': 'materials-placement', 'op': 'interact',
                            'params': {'task_session': evidence['task_session']}})
                    else:
                        if change == 'gain':
                            rows[-1]['inventory_delta'] = {
                                'minecraft:grass_block': 2}
                        elif change == 'task':
                            rows[0]['params']['task_session'] = 'materials-other'
                        elif change == 'world':
                            rows[-1]['world_session'] = 'world-other'
                        else:
                            rows[-1]['revision_before'] += 1
                    events_path.write_text(''.join(json.dumps(row) + '\n'
                                                   for row in rows))
                    evidence['events']['sha256'] = self.file_hash(events_path)
                elif change == 'request':
                    evidence['mine_request_id'] = 'materials-other-request'
                elif change == 'hash':
                    evidence['events']['sha256'] = '0' * 64
                elif change == 'drop':
                    reply_path = Path(evidence['native_reply']['path'])
                    reply = json.loads(reply_path.read_text())
                    reply['entities'][0]['uuid'] = 'another-drop'
                    reply_path.write_text(json.dumps(reply))
                    evidence['native_reply']['sha256'] = self.file_hash(reply_path)
                elif change == 'inventory':
                    self.client.inventory['minecraft:grass_block'] = 2
                else:
                    self.client.shovel_durability -= 1
                with self.assertRaises(paving.PavingPending):
                    terrain.replace_batch(
                        self.client, cells=[self.client.pos], max_cells=1,
                        settle=lambda _: None, post_send_evidence=evidence)
                self.assertEqual('lift_intent', self.journal()['phase'])
                self.assertEqual(1, sum(
                    params.get('terrain_replace_stage') == 'lift_grass'
                    for op, params in self.client.actions if op == 'mine_block'))

    def test_uncertain_grass_lift_is_durable_and_never_replayed(self):
        self.client.uncertain_stage = 'lift_grass'
        with self.assertRaises(paving.PavingPending):self.run_one()
        self.assertEqual(self.journal()['phase'], 'lift_intent')
        self.client.uncertain_stage = None
        with self.assertRaises(paving.PavingPending):self.run_one()
        self.assertEqual(sum(op == 'mine_block' for op,_ in self.client.actions),1)

    def test_native_done_without_server_air_never_starts_next_excavation(self):
        for stage, expected_phase in (('lift_grass', 'lift_intent'),
                                      ('mine_stone', 'stone_mine_intent')):
            with self.subTest(stage=stage):
                self.client = FakeClient(Path(self.temp.name) / stage)
                self.client.ghost_stage = stage
                with self.assertRaisesRegex(paving.PavingPending, 'Server did not confirm'):
                    self.run_one()
                self.assertEqual(self.journal()['phase'], expected_phase)
                self.assertFalse(any(p.get('terrain_replace_stage') in ('place_dirt','restore_grass')
                                     for op,p in self.client.actions if op == 'interact'))
                self.assertEqual(self.client.inventory['minecraft:dirt'],12)

    def test_old_same_item_drop_and_ghost_air_cannot_be_claimed_as_this_grass(self):
        self.client.entities = [{'type': 'minecraft:item', 'uuid': 'older-grass',
                                 'pos': [self.client.pos[0]+5.5, 63.5,
                                         self.client.pos[2]+.5],
                                 'stack': {'item': 'minecraft:grass_block', 'count': 1}}]
        self.client.ghost_stage = 'lift_grass'
        with self.assertRaisesRegex(paving.PavingBlocked, 'older item drop'):
            self.run_one()
        self.assertEqual(list(self.client.root.glob('terrain-replace-south-v1/*/*.json')), [])
        self.assertFalse(any(op == 'mine_block' for op,_ in self.client.actions))

    def test_client_air_without_server_packet_ack_retains_first_intent(self):
        self.client.unacknowledged_stage = 'lift_grass'
        with self.assertRaisesRegex(paving.PavingPending, 'matching server block update'):
            self.run_one()
        self.assertEqual(self.journal()['phase'], 'lift_intent')
        self.assertEqual(sum(op == 'mine_block' for op,_ in self.client.actions),1)
        self.assertFalse(any(p.get('terrain_replace_stage') == 'mine_stone'
                             for op,p in self.client.actions if op == 'mine_block'))

    def test_uncertain_dirt_placement_never_replays_after_world_changes(self):
        self.client.uncertain_stage = 'place_dirt'
        with self.assertRaises(paving.PavingPending):self.run_one()
        self.assertEqual(self.journal()['phase'], 'dirt_place_intent')
        self.client.world = 'world-2'
        self.client.uncertain_stage = None
        with self.assertRaises(paving.PavingPending):self.run_one()
        self.assertEqual(sum(p.get('terrain_replace_stage') == 'place_dirt'
                             for op,p in self.client.actions if op == 'interact'),1)

    def test_arriving_animal_blocks_second_excavation_with_grass_intact_in_inventory(self):
        self.client.animal_after_grass_mine = True
        with self.assertRaises(paving.PavingPending):self.run_one()
        self.assertEqual(self.journal()['phase'], 'grass_mined')
        self.assertEqual(sum(p.get('terrain_replace_stage') == 'mine_stone'
                             for op,p in self.client.actions if op == 'mine_block'),0)

    def test_lost_grass_reserve_does_not_mine_foundation(self):
        with patch.object(terrain, '_finish_stone_and_restore', side_effect=paving.PavingBlocked('pause')):
            with self.assertRaises(paving.PavingBlocked):self.run_one()
        self.assertEqual(self.journal()['phase'], 'grass_recovered')
        self.client.inventory['minecraft:grass_block'] = 0
        with self.assertRaisesRegex(paving.PavingBlocked, 'Recovered grass'):
            self.run_one()
        self.assertEqual(sum(p.get('terrain_replace_stage') == 'mine_stone'
                             for op,p in self.client.actions if op == 'mine_block'),0)

    def test_forged_recovered_phase_without_ordered_lift_and_drop_receipts_never_mines_stone(self):
        with patch.object(terrain, '_finish_stone_and_restore', side_effect=paving.PavingBlocked('pause')):
            with self.assertRaises(paving.PavingBlocked):self.run_one()
        path = next(self.client.root.glob('terrain-replace-south-v1/*/*.json'))
        record = json.loads(path.read_text())
        self.assertEqual(record['phase'], 'grass_recovered')
        record['receipts'] = [r for r in record['receipts'] if r['phase'] != 'grass_mined']
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(paving.PavingPending, 'out of order'):
            self.run_one()
        self.assertEqual(sum(p.get('terrain_replace_stage') == 'mine_stone'
                             for op,p in self.client.actions if op == 'mine_block'),0)

    def test_recovered_journal_requires_unique_prior_entity_uuids_before_stone_mine(self):
        with patch.object(terrain, '_finish_stone_and_restore',
                          side_effect=paving.PavingBlocked('pause')):
            with self.assertRaises(paving.PavingBlocked):
                self.run_one()
        path = next(self.client.root.glob('terrain-replace-south-v1/*/*.json'))
        original = json.loads(path.read_text())
        self.assertEqual(original['phase'], 'grass_recovered')
        self.assertEqual(original['nearby_before'], [])
        for invalid in ('missing', ['same-id', 'same-id'], ['']):
            with self.subTest(invalid=invalid):
                record = copy.deepcopy(original)
                if invalid == 'missing':
                    record.pop('nearby_before')
                else:
                    record['nearby_before'] = invalid
                path.write_text(json.dumps(record))
                with self.assertRaisesRegex(paving.PavingPending, 'prior entity UUID'):
                    self.run_one()
                self.assertEqual(sum(p.get('terrain_replace_stage') == 'mine_stone'
                                     for op,p in self.client.actions if op == 'mine_block'), 0)

    def test_changed_y61_support_blocks_before_first_mine_intent(self):
        self.client.below = 'Block{minecraft:dirt}'
        with self.assertRaisesRegex(paving.PavingBlocked, 'Y61 stone'):
            self.run_one()
        self.assertFalse(any(op == 'mine_block' for op,_ in self.client.actions))

    def test_confirmed_grass_pickup_can_rebind_without_second_grass_mine(self):
        with patch.object(terrain, '_finish_stone_and_restore', side_effect=paving.PavingBlocked('pause')):
            with self.assertRaises(paving.PavingBlocked):self.run_one()
        self.assertEqual(self.journal()['phase'], 'grass_recovered')
        self.client.world = 'world-2'
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        self.assertEqual(sum(p.get('terrain_replace_stage') == 'lift_grass'
                             for op,p in self.client.actions if op == 'mine_block'),1)
        self.assertEqual(self.journal()['world_session'],'world-2')
        self.assertEqual(self.journal()['phase'],'complete')
        original = self.journal()
        terrain._validated_history(original)
        rebind_index = next(index for index, receipt in enumerate(original['receipts'])
                            if receipt.get('event') == 'world_session_rebind'
                            and receipt.get('phase') == 'grass_recovered')
        for field in ('previous_world_session', 'current_world_session'):
            with self.subTest(field=field):
                forged = copy.deepcopy(original)
                forged['receipts'][rebind_index][field] = 'forged-world'
                with self.assertRaises(paving.PavingPending):
                    terrain._validated_history(forged)

    def test_pickup_drop_and_refly_still_restore_same_grass(self):
        self.client.fall_on_pickup = True
        self.assertEqual(self.run_one()[0]['result'],'placed')
        self.assertGreaterEqual(sum(op == 'navigate' for op,_ in self.client.actions),1)
        self.assertEqual(self.journal()['phase'],'complete')

    def test_high_guard_park_uses_scanned_horizontal_then_vertical_air_legs(self):
        self.client.player = [761000.0, 110.0, 797839.0]
        self.assertEqual(self.run_one()[0]['result'], 'placed')
        legs = [params for op, params in self.client.actions if op == 'navigate']
        self.assertGreaterEqual(len(legs), 2)
        self.assertEqual(legs[0]['target'], [terrain.CELLS[0][0]+.5, 110.0,
                                              terrain.CELLS[0][2]+.5])
        self.assertEqual(legs[1]['target'], terrain._station(terrain.CELLS[0]))
        self.assertTrue(all(leg['air_only'] is True for leg in legs))
        first_mine = next(i for i,(op,_) in enumerate(self.client.actions) if op == 'mine_block')
        self.assertTrue(all(op == 'scan' or op == 'navigate' or op == 'select_item'
                            for op,_ in self.client.actions[:first_mine]))

    def test_live_distant_low_obstruction_uses_clear_vertical_high_and_descent(self):
        source = terrain.CELLS[-1]
        target = terrain.CELLS[1]
        self.client = FakeClient(Path(self.temp.name) / 'live-distant', pos=target)
        self.client.player = terrain._station(source)
        self.client.extra = [{
            'pos': [760999, 64, target[2]],
            'state': 'Block{minecraft:oak_fence}[east=true,north=false,south=false,west=true,waterlogged=false]',
            'solid': False, 'replaceable': False, 'passable': False,
            'fluid': False, 'block_entity': False,
        }]
        site_patch = patch.object(paving, 'SITE', self.client.area)
        context_patch = patch.object(
            paving, '_fresh_context', side_effect=lambda *_: self.client.context())
        with site_patch, context_patch:
            observed = terrain._reach_station(self.client, target)
        self.assertTrue(terrain._station_pose_ok(observed['pos'], target))
        legs = [params['target'] for op, params in self.client.actions
                if op == 'navigate']
        self.assertEqual(legs, [
            [source[0] + .5, 110.0, source[2] + .5],
            [target[0] + .5, 110.0, target[2] + .5],
            terrain._station(target),
        ])
        self.assertFalse(any(op in ('mine_block', 'interact')
                             for op, _ in self.client.actions))

    def test_adjacent_clear_low_station_uses_one_fast_direct_leg(self):
        target = terrain.CELLS[2]
        source = (target[0] + 1, target[1], target[2])
        self.client = FakeClient(Path(self.temp.name) / 'adjacent', pos=target)
        self.client.player = terrain._station(source)
        site_patch = patch.object(paving, 'SITE', self.client.area)
        context_patch = patch.object(
            paving, '_fresh_context', side_effect=lambda *_: self.client.context())
        with site_patch, context_patch:
            observed = terrain._reach_station(self.client, target)
        legs = [params for op, params in self.client.actions if op == 'navigate']
        self.assertEqual(len(legs), 1)
        self.assertEqual(legs[0]['target'], terrain._station(target))
        self.assertEqual(legs[0]['seconds'], 20)
        self.assertTrue(terrain._station_pose_ok(observed['pos'], target))

    def test_blocked_vertical_or_high_sweep_fails_before_movement(self):
        source = terrain.CELLS[-1]
        target = terrain.CELLS[1]
        cases = {
            'vertical': [source[0], 70, source[2]],
            'high': [760999, 110, source[2]],
        }
        for name, blocked in cases.items():
            with self.subTest(name=name):
                client = FakeClient(Path(self.temp.name) / name, pos=target)
                client.player = terrain._station(source)
                client.extra = [{'pos': blocked, 'state': 'Block{minecraft:stone}',
                                 'solid': True, 'replaceable': False,
                                 'passable': False, 'fluid': False,
                                 'block_entity': False}]
                site_patch = patch.object(paving, 'SITE', client.area)
                with site_patch, self.assertRaisesRegex(
                        paving.PavingBlocked, 'contains a block or fluid'):
                    terrain._reach_station(client, target)
                self.assertFalse(any(op in ('navigate', 'mine_block', 'interact')
                                     for op, _ in client.actions))

    def test_high_preflight_includes_prior_arrival_envelope_before_any_move(self):
        source = terrain.CELLS[-1]
        target = terrain.CELLS[1]
        client = FakeClient(Path(self.temp.name) / 'arrival-envelope', pos=target)
        client.player = [source[0] + .6, 64.3, source[2] + .5]
        client.extra = [{
            'pos': [source[0] + 1, 110, source[2]],
            'state': 'Block{minecraft:stone}', 'solid': True,
            'replaceable': False, 'passable': False, 'fluid': False,
            'block_entity': False,
        }]
        site_patch = patch.object(paving, 'SITE', client.area)
        with site_patch, self.assertRaisesRegex(
                paving.PavingBlocked, 'contains a block or fluid'):
            terrain._reach_station(client, target)
        self.assertFalse(any(op in ('navigate', 'mine_block', 'interact')
                             for op, _ in client.actions))

    def test_low_corridor_observation_failure_is_not_treated_as_geometry(self):
        target = terrain.CELLS[2]
        source = (target[0] + 1, target[1], target[2])
        self.client = FakeClient(Path(self.temp.name) / 'wrong-world', pos=target)
        self.client.player = terrain._station(source)
        original_request = self.client.request

        def wrong_world(op, **params):
            result = original_request(op, **params)
            if op == 'scan':
                result['world_session'] = 'different-world'
            return result

        self.client.request = wrong_world
        site_patch = patch.object(paving, 'SITE', self.client.area)
        with site_patch, self.assertRaisesRegex(
                paving.PavingBlocked, 'not fully scanned'):
            terrain._reach_station(self.client, target)
        self.assertFalse(any(op == 'navigate' for op, _ in self.client.actions))

    def test_malformed_low_scan_row_is_not_retyped_as_geometry(self):
        target = terrain.CELLS[2]
        source = (target[0] + 1, target[1], target[2])
        self.client = FakeClient(Path(self.temp.name) / 'malformed-low', pos=target)
        self.client.player = terrain._station(source)
        self.client.extra = [{
            'pos': [target[0], 64, target[2]],
            'state': 'Block{minecraft:stone}',
        }]
        site_patch = patch.object(paving, 'SITE', self.client.area)
        with site_patch, self.assertRaisesRegex(
                paving.PavingBlocked, 'invalid block') as raised:
            terrain._reach_station(self.client, target)
        self.assertNotIsInstance(raised.exception, terrain._TransitGeometryBlocked)
        self.assertFalse(any(op == 'navigate' for op, _ in self.client.actions))

    def test_complete_passable_low_scan_row_keeps_fast_direct_leg(self):
        target = terrain.CELLS[2]
        source = (target[0] + 1, target[1], target[2])
        self.client = FakeClient(Path(self.temp.name) / 'passable-low', pos=target)
        self.client.player = terrain._station(source)
        self.client.extra = [{
            'pos': [target[0], 64, target[2]],
            'state': 'Block{minecraft:short_grass}', 'solid': False,
            'replaceable': True, 'passable': True, 'fluid': False,
            'block_entity': False,
        }]
        site_patch = patch.object(paving, 'SITE', self.client.area)
        with site_patch:
            observed = terrain._reach_station(self.client, target)
        legs = [params for op, params in self.client.actions if op == 'navigate']
        self.assertEqual(1, len(legs))
        self.assertEqual(terrain._station(target), legs[0]['target'])
        self.assertTrue(terrain._station_pose_ok(observed['pos'], target))

    def test_each_leg_rechecks_guard_manual_health_flight_and_entities(self):
        source = terrain.CELLS[-1]
        target = terrain.CELLS[1]
        cases = {
            'guard': lambda state: state.update(guard_pve_only=False),
            'manual': lambda state: state.update(manual_movement=True),
            'health': lambda state: state.update(health=18),
            'flight': lambda state: state.update(flight=False),
            'entities': lambda state: state.update(entities=[{
                'type': 'minecraft:cow', 'pos': list(state['pos'])}]),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                client = FakeClient(Path(self.temp.name) / name, pos=target)
                client.player = terrain._station(source)
                original_status = client.status
                calls = 0

                def changing_status():
                    nonlocal calls
                    calls += 1
                    state = original_status()
                    if calls >= 2:
                        mutate(state)
                    return state

                client.status = changing_status
                site_patch = patch.object(paving, 'SITE', client.area)
                with site_patch, self.assertRaises(paving.PavingBlocked):
                    terrain._reach_station(client, target)
                self.assertFalse(any(op == 'navigate' for op, _ in client.actions))

    def test_changed_safety_state_after_ascent_stops_before_horizontal_leg(self):
        source = terrain.CELLS[-1]
        target = terrain.CELLS[1]
        cases = {
            'guard': lambda state: state.update(guard_armed=False),
            'manual': lambda state: state.update(manual_movement=True),
            'health': lambda state: state.update(health=18),
            'flight': lambda state: state.update(flight=False),
            'entities': lambda state: state.update(entities=[{
                'type': 'minecraft:cow', 'pos': list(state['pos'])}]),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                client = FakeClient(Path(self.temp.name) / ('after-' + name),
                                    pos=target)
                client.player = terrain._station(source)
                original_status = client.status

                def changed_after_ascent():
                    state = original_status()
                    if sum(op == 'navigate' for op, _ in client.actions) >= 1:
                        mutate(state)
                    return state

                client.status = changed_after_ascent
                site_patch = patch.object(paving, 'SITE', client.area)
                with site_patch, self.assertRaises(paving.PavingBlocked):
                    terrain._reach_station(client, target)
                self.assertEqual(1, sum(op == 'navigate'
                                        for op, _ in client.actions))

    def test_batch_cannot_widen_targets_or_repeat_a_completed_cell(self):
        with self.assertRaises(ValueError):
            terrain.replace_batch(self.client,cells=[(0,62,0)],max_cells=1)
        self.run_one()
        with self.assertRaises(paving.PavingPending):self.run_one()


if __name__ == '__main__':
    unittest.main()
