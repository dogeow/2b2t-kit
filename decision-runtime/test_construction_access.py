"""Construction access action proofs with a native-like fake, never Minecraft."""
from copy import deepcopy
from itertools import count
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from material_client import Client, Handoff
from material_jobs import construction_access as access
from material_jobs.construction_access_journal import AccessJournal, AccessJournalError, journal_path
from material_jobs.protocol import JobBlocked


CONCRETE = 'minecraft:white_concrete'
ORIGINAL = 'Block{minecraft:white_concrete}'
LOWER, UPPER = [10, 64, 20], [10, 65, 20]


def block(pos, state=ORIGINAL):
    return {'pos': list(pos), 'state': state, 'solid': True, 'fluid': False,
            'block_entity': False, 'passable': False, 'replaceable': False}


class FakeClient(Client):
    """Use the real Client.status lease checks; fake only IO and game effects."""
    def __init__(self, root):
        self.root = root / 'bridge'
        self.out = root / 'receipts'
        self.root.mkdir(); self.out.mkdir()
        self.world, self.rev, self.last = 'world-1', 1, None
        self.calls = []
        self.mine_delta, self.restore_delta = 1, -1
        self.mine_changes_block, self.restore_state = True, ORIGINAL
        self.mine_drop_mode, self.pickup_delta = None, None
        self.batch_overrides = {}
        self.clear_overrides = {}
        self.after_action = None
        self.fail_op = None
        self.reject_before_dispatch = None
        self.rows = {tuple(pos): block(pos) for pos in (LOWER, UPPER)}
        self.rows[(10, 63, 20)] = block([10, 63, 20], 'Block{minecraft:smooth_stone}')
        self.state = {
            'time': 1000, 'server': 'example.test:25565', 'dimension': 'minecraft:overworld',
            'world_session': self.world, 'control_revision': self.rev,
            'connected': True, 'manual_movement': False, 'screen': '',
            'health': 20, 'food': 20, 'under_water': False,
            'guard_armed': True, 'guard_pve_only': True, 'safety_hold': {'active': False},
            'projection_model_protocol': 1, 'projection_batch_protocol': 1,
            'projection_selection': {'key': 'ship', 'min': [9, 63, 19], 'max': [12, 66, 21]},
            'build_job': {'active': False, 'queue_settled': True},
            'professional_printer': {'waiting_for_server': False},
            'pos': [9.5, 64, 20.5], 'entities': [],
            'inventory': [{'slot': 0, 'item': CONCRETE, 'count': 4},
                          {'slot': 1, 'item': 'minecraft:diamond_pickaxe', 'count': 1, 'durability': 128}],
        }
        self.model = {'placement_key': 'ship', 'content_hash': 'fixture-model', 'loaded_chunks_verified': True,
                      'bounds': {'min': [9, 63, 19], 'max': [12, 66, 21]},
                      'expected': [{'pos': p, 'expected': ORIGINAL} for p in (LOWER, UPPER)]}

    def raw(self):
        return deepcopy(self.state)

    def request(self, op, **params):
        self.status()
        if op == self.reject_before_dispatch:
            raise Handoff('Control changed before dispatch')
        self.calls.append((op, deepcopy(params)))
        self.last = 'fake-request-' + str(len(self.calls))
        if op == self.fail_op:
            raise Handoff('Disconnected after dispatch')
        reply = {'phase': 'done', 'world_session': self.world, 'id': self.last}
        if op == 'scan':
            low, high = params['min'], params['max']
            reply['blocks'] = [deepcopy(row) for pos, row in self.rows.items()
                               if all(low[i] <= pos[i] <= high[i] for i in range(3))]
        elif op == 'projection_model':
            reply['projection_model'] = deepcopy(self.model)
        elif op == 'projection_batch_set':
            reply['projection_batch'] = {
                'active': True, 'count': len(params['positions']),
                'placement_key': params['placement_key'],
                'min_feet_y': params.get('min_feet_y'), **self.batch_overrides,
            }
        elif op == 'projection_batch_clear':
            reply['projection_batch'] = {'active': False, 'count': 0, **self.clear_overrides}
        elif op == 'mine_block':
            if self.mine_changes_block:
                self.rows.pop(tuple(params['pos']), None)
            self.state['inventory'][0]['count'] += self.mine_delta
            if self.mine_drop_mode:
                pos=params['pos']
                if self.mine_drop_mode=='merged' and len(self.actions('mine_block'))>=2:
                    self.state['entities']=[{'type':'minecraft:item','uuid':'00000000-0000-4000-8000-000000000003',
                        'pos':[LOWER[0]+.5,LOWER[1]+.5,LOWER[2]+.5],'stack':{'item':CONCRETE,'count':2}}]
                else:
                    suffix='1' if pos==UPPER else '2'
                    self.state['entities'].append({'type':'minecraft:item','uuid':'00000000-0000-4000-8000-00000000000'+suffix,
                        'pos':[pos[0]+.5,pos[1]+.5,pos[2]+.5],'stack':{'item':CONCRETE,'count':1}})
        elif op == 'collect_item':
            # A player-sized pickup route does not exist after mining only the
            # upper block. Keep this assertion in the fake interaction itself.
            if any(tuple(pos) in self.rows for pos in (LOWER,UPPER)):
                raise AssertionError('Cannot pick up through the one-block notch')
            drop=next(e for e in self.state['entities'] if e['uuid']==params['expected_uuid'])
            if drop['stack']['item']!=params['expected_item'] or drop['stack']['count']!=params['expected_count']:
                raise AssertionError('Pickup must use the currently observed drop identity and count')
            self.state['inventory'][0]['count'] += drop['stack']['count'] if self.pickup_delta is None else self.pickup_delta
            self.state['entities'].remove(drop)
        elif op == 'interact':
            pos = list(params['pos']); pos[1] += 1
            if self.restore_state is not None:
                self.rows[tuple(pos)] = block(pos, self.restore_state)
            self.state['inventory'][0]['count'] += self.restore_delta
        if self.after_action:
            self.after_action(op, self)
        return reply

    def actions(self, *ops):
        return [(op, params) for op, params in self.calls if op in ops]


class FakeOwner:
    def __init__(self, root, client):
        self.root = root / 'job'
        self.out = root / 'job-output'
        self.root.mkdir(); self.out.mkdir()
        self.client = client
        self.audit, self.audit_dirty = None, False

    def ensure_client(self):
        return self.client

    def checkpoint(self):
        self.client.status()

    def refresh_audit(self):
        return {'matched': 0}


class ConstructionAccessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.client = FakeClient(self.root)
        self.owner = FakeOwner(self.root, self.client)
        self.plan = {
            'restore_reserve': {CONCRETE: 2}, 'approach_anchor': [9.5, 64, 20.5],
            'approach_path': [], 'outside_station': [9.5, 64, 20.5],
            'inside_station': [11.5, 64, 20.5], 'mine_order': [UPPER, LOWER],
            'restore_order': [LOWER, UPPER], 'outside_face': 'west', 'entry_path': [], 'stages': [],
        }
        self.journal_plan = {
            'blocks': [{'pos': p, 'expected': ORIGINAL, 'item': CONCRETE} for p in (LOWER, UPPER)],
            'outside': self.plan['outside_station'], 'inside': self.plan['inside_station'],
            'access_plan': self.plan,
        }
        self.scope = {'server': 'example.test', 'dimension': 'minecraft:overworld',
                      'placement_key': 'ship', 'model_hash': 'fixture-model', 'world_session': 'world-1'}
        self.journal = AccessJournal(journal_path(access._index(self.owner), self.scope), self.scope, self.journal_plan)
        self.work = access.AccessWork(self.owner, deepcopy(self.client.model), self.journal)
        # These tests isolate action proof from separately tested route geometry.
        self.addCleanup(patch.stopall)
        patch.object(self.work, 'move').start()
        patch.object(self.work, 'cross').start()
        patch.object(self.work, 'path_to', return_value=[]).start()
        patch('material_jobs.acquisition._travel').start()
        patch('material_jobs.construction_access.time.sleep').start()
        patch('material_jobs.construction_access.time.monotonic', side_effect=count(0, 10)).start()

    def make_open(self):
        for pos in (LOWER, UPPER):
            self.client.rows.pop(tuple(pos), None)

    def test_missing_native_capability_does_not_dispatch_or_create_work(self):
        audit = {'placement_key': 'ship', 'loaded_chunks_verified': True, 'mismatches': [], 'matched': 0}
        for key in ('projection_model_protocol', 'projection_batch_protocol'):
            with self.subTest(key=key):
                self.client.state[key] = 0
                self.assertIsNone(access.attempt(self.owner, audit))
                self.assertEqual([], self.client.calls)
                self.client.state[key] = 1

    def test_model_hash_change_before_open_prevents_mask_and_mining(self):
        self.client.model['content_hash'] = 'changed-model'
        with self.assertRaises(JobBlocked):
            self.work.open()
        self.assertEqual(['projection_model'], [op for op, _ in self.client.calls])
        self.assertIsNone(self.journal.pending)
        self.assertEqual([], self.journal.data['operations'])

    def test_model_hash_change_before_restore_keeps_open_portal_untouched(self):
        self.make_open()
        self.client.model['content_hash'] = 'changed-model'
        with self.assertRaises(JobBlocked):
            self.work.restore()
        self.assertEqual(['projection_model'], [op for op, _ in self.client.calls])
        self.assertFalse(self.journal.restored)
        self.assertIn(self.work.cleanup_key, self.client.resource_cleanup)
        self.work.path_to.assert_not_called()
        self.work.move.assert_not_called()

    def test_model_hash_change_between_layers_blocks_the_next_target_mask(self):
        stages = [
            {'layer_y': 63, 'station': [11.5, 64, 20.5],
             'targets': [{'pos': [11, 63, 20], 'expected': ORIGINAL}]},
            {'layer_y': 64, 'station': [11.5, 65, 20.5],
             'targets': [{'pos': [11, 64, 20], 'expected': ORIGINAL}]},
        ]
        self.work.plan['stages'] = stages
        self.work.path_to.side_effect = lambda target: [target]
        self.work.move.side_effect = lambda path: self.client.state.update(pos=list(path[-1]))
        def finish_first_layer(*args, **kwargs):
            for row in kwargs['complete_cells']:
                self.client.rows[tuple(row['pos'])] = block(row['pos'], row['expected'])
            self.client.model['content_hash'] = 'changed-after-first-layer'
            return {'matched': 1}
        with patch('goal_workflow.build_phase', side_effect=finish_first_layer) as build:
            with self.assertRaises(JobBlocked):
                self.work.construct()
        self.assertEqual(1, build.call_count)
        masks = [params['positions'] for _, params in self.client.actions('projection_batch_set')]
        self.assertEqual([[[11, 63, 20]], []], masks)
        self.assertEqual('layer_completed', self.journal.data['stage'])
        self.assertFalse(self.journal.restored)

    def test_exact_portal_validation_rejects_foreign_block_before_mining(self):
        for state in ('Block{minecraft:stone}', 'Block{minecraft:chest}', 'Block{minecraft:water}', 'unknown'):
            with self.subTest(state=state):
                self.client.rows[tuple(LOWER)] = block(LOWER, state)
                with self.assertRaises(AccessJournalError):
                    self.work.dispatch('open_block', 'mine_block', pos=UPPER, expected_state=ORIGINAL)
                self.assertEqual([], self.client.actions('mine_block', 'interact'))
                self.assertIsNone(self.journal.pending)

    def test_mine_done_without_air_proof_keeps_pending_and_does_not_continue(self):
        self.client.mine_changes_block = False
        with self.assertRaises(JobBlocked):
            self.work.open()
        self.assertEqual(1, len(self.client.actions('mine_block')))
        self.assertEqual('open_block', self.journal.pending['kind'])
        self.assertEqual([], self.journal.data['operations'])

    def test_two_air_confirmed_removals_without_inventory_gain_do_not_confirm_entry(self):
        self.client.mine_delta=0
        with self.assertRaises(JobBlocked):self.work.open()
        self.assertEqual(2,len(self.client.actions('mine_block')))
        self.assertIsNone(self.journal.pending)
        self.assertEqual(2,len(self.journal.data['operations']))
        self.assertTrue(all(op['evidence']['removed'] and op['evidence']['recovered'] is False for op in self.journal.data['operations']))
        self.assertNotEqual('entered',self.journal.data['stage']);self.assertFalse(self.journal.restored)
        self.assertFalse(any(row['stage']=='drops_recovered' for row in self.journal.data['checkpoints']))

    def test_extra_inventory_gain_does_not_confirm_recovery_or_entry(self):
        self.client.mine_delta=2
        with self.assertRaisesRegex(JobBlocked,'超出预期'):self.work.open()
        self.assertEqual(2,len(self.client.actions('mine_block')))
        self.assertIsNone(self.journal.pending);self.assertEqual(2,len(self.journal.data['operations']))
        self.assertNotEqual('entered',self.journal.data['stage']);self.assertFalse(self.journal.restored)

    def test_entry_requires_both_exact_air_states_and_total_two_recovered_items(self):
        self.work.open()
        self.assertEqual(2, len(self.client.actions('mine_block')))
        self.assertEqual(6, self.client.state['inventory'][0]['count'])
        self.assertEqual(['open_block', 'open_block'], [op['kind'] for op in self.journal.data['operations']])
        self.assertIsNone(self.journal.pending)
        self.assertEqual('entered', self.journal.data['stage'])
        for _, params in self.client.actions('mine_block'):
            self.assertEqual(ORIGINAL, params['expected_state'])
        recovery=next(row for row in self.journal.data['checkpoints'] if row['stage']=='drops_recovered')
        self.assertEqual({CONCRETE:6},recovery['data']['wanted'])

    def test_separate_drops_are_collected_only_after_both_portal_blocks_are_air(self):
        self.client.mine_delta=0;self.client.mine_drop_mode='separate'
        with patch('material_jobs.construction_access.time.monotonic',side_effect=count(0,.25)):
            self.work.open()
        actions=self.client.actions('mine_block','collect_item')
        self.assertEqual(['mine_block','mine_block','collect_item','collect_item'],[op for op,_ in actions])
        self.assertEqual([1,1],[params['expected_count'] for op,params in actions if op=='collect_item'])
        self.assertEqual(6,self.client.state['inventory'][0]['count'])
        self.assertEqual([],self.client.state['entities']);self.assertEqual('entered',self.journal.data['stage'])

    def test_merged_drop_is_collected_after_full_opening_and_credited_exactly_once(self):
        self.client.mine_delta=0;self.client.mine_drop_mode='merged'
        with patch('material_jobs.construction_access.time.monotonic',side_effect=count(0,.25)):
            self.work.open()
        actions=self.client.actions('mine_block','collect_item')
        self.assertEqual(['mine_block','mine_block','collect_item'],[op for op,_ in actions])
        self.assertEqual(2,actions[-1][1]['expected_count'])
        self.assertEqual(6,self.client.state['inventory'][0]['count'])
        self.assertEqual('entered',self.journal.data['stage']);self.assertFalse(self.journal.restored)

    def test_native_pickup_done_with_only_one_item_cannot_confirm_two_item_recovery(self):
        self.client.mine_delta=0;self.client.mine_drop_mode='merged';self.client.pickup_delta=1
        with patch('material_jobs.construction_access.time.monotonic',side_effect=count(0,1)):
            with self.assertRaises(JobBlocked):self.work.open()
        self.assertEqual(2,len(self.client.actions('mine_block')))
        self.assertEqual(1,len(self.client.actions('collect_item')))
        self.assertEqual(5,self.client.state['inventory'][0]['count'])
        self.assertNotEqual('entered',self.journal.data['stage']);self.assertFalse(self.journal.restored)
        self.assertFalse(any(row['stage']=='drops_recovered' for row in self.journal.data['checkpoints']))

    def test_inventory_plus_two_with_an_owned_drop_still_present_waits_without_collecting_extra(self):
        self.client.mine_delta=0;self.client.mine_drop_mode='separate';self.client.pickup_delta=2
        with patch('material_jobs.construction_access.time.monotonic',side_effect=count(0,1)):
            with self.assertRaisesRegex(JobBlocked,'掉落仍在世界'):self.work.open()
        self.assertEqual(6,self.client.state['inventory'][0]['count'])
        self.assertEqual(1,len(self.client.state['entities']))
        self.assertEqual(1,len(self.client.actions('collect_item')))
        self.assertNotEqual('entered',self.journal.data['stage']);self.assertFalse(self.journal.restored)
        self.assertFalse(any(row['stage']=='drops_recovered' for row in self.journal.data['checkpoints']))

    def test_confirmed_prior_upper_removal_is_not_remined_before_opening_lower(self):
        self.client.mine_delta=0;self.client.mine_drop_mode='separate'
        self.work.dispatch('open_block','mine_block',{'pos':UPPER,'before_count':4,'item':CONCRETE},
                           pos=UPPER,expected_state=ORIGINAL)
        pending=self.journal.pending
        prior={'request_id':self.client.last,'op':'mine_block','phase':'done','world_session':self.client.world,
               'time':pending['created_at_ns']/1_000_000_000+1,
               'params':{'pos':UPPER,'expected_state':ORIGINAL,'task_session':'owned-native-materials'},
               'inventory_delta':{}}
        receipt={'native_event':prior,'owned_drop_ids':[self.client.state['entities'][0]['uuid']]}
        before_calls=len(self.client.calls)
        with patch('material_jobs.construction_access_receipts.find_removal_receipt',return_value=receipt) as find, \
                patch('material_jobs.construction_access.time.monotonic',side_effect=count(0,.25)):
            self.work.open()
        find.assert_called_once()
        self.assertEqual([LOWER],[params['pos'] for op,params in self.client.calls[before_calls:] if op=='mine_block'])
        self.assertEqual(2,len(self.client.actions('collect_item')))
        self.assertEqual(6,self.client.state['inventory'][0]['count'])
        self.assertEqual(2,len(self.journal.data['operations']))
        self.assertEqual(prior,self.journal.data['operations'][0]['evidence']['prior_native_event'])
        self.assertEqual('entered',self.journal.data['stage']);self.assertIsNone(self.journal.pending)

    def test_restore_done_with_wrong_state_keeps_pending(self):
        self.make_open()
        self.client.restore_state = 'Block{minecraft:glass}'
        with self.assertRaises(JobBlocked):
            self.work.restore()
        self.assertEqual(1, len(self.client.actions('interact')))
        self.assertEqual('restore_block', self.journal.pending['kind'])
        self.assertFalse(self.journal.restored)

    def test_restore_done_without_inventory_decrement_keeps_pending(self):
        self.make_open()
        self.client.restore_delta = 0
        with self.assertRaises(JobBlocked):
            self.work.restore()
        self.assertEqual(1, len(self.client.actions('interact')))
        self.assertEqual('restore_block', self.journal.pending['kind'])
        self.assertFalse(self.journal.restored)

    def test_restore_confirms_original_states_and_one_consumed_item_per_block(self):
        self.make_open()
        self.work.restore()
        self.assertEqual(2, len(self.client.actions('interact')))
        self.assertEqual(2, self.client.state['inventory'][0]['count'])
        self.assertEqual([ORIGINAL, ORIGINAL], [self.client.rows[tuple(p)]['state'] for p in (LOWER, UPPER)])
        self.assertTrue(self.journal.restored)
        self.assertIsNone(self.journal.pending)
        self.assertNotIn(self.work.cleanup_key, self.client.resource_cleanup)
        self.assertEqual('ship', self.client.actions('projection_batch_clear')[0][1].get('placement_key'))

    def test_batch_set_requires_active_count_placement_and_navigation_floor_receipt(self):
        targets = [{'pos': [11, 63, 20], 'expected': ORIGINAL}]
        for override in ({'active': False}, {'count': 2}, {'placement_key': 'other'}, {'min_feet_y': None}, {'min_feet_y': 63}):
            with self.subTest(override=override):
                self.client.batch_overrides = override
                with self.assertRaises(JobBlocked):
                    self.work.mask(targets, 64)
        self.client.batch_overrides = {}
        self.work.mask(targets, 64)
        self.assertEqual(6, len(self.client.actions('projection_batch_set')))

    def test_batch_clear_done_requires_inactive_empty_mask_without_floor(self):
        for override in ({'active': True}, {'count': 1}, {'min_feet_y': 64}):
            with self.subTest(override=override):
                self.client.clear_overrides = override
                with self.assertRaises(JobBlocked):
                    self.work.mask(None)
        self.client.clear_overrides = {}
        self.work.mask(None)

    def test_unopened_doorway_outside_model_finishes_without_path_or_mining(self):
        self.client.state['pos'] = [8, 64, 20.5]
        self.work.restore()
        self.assertTrue(self.journal.restored)
        self.work.path_to.assert_not_called()
        self.work.move.assert_not_called()
        self.assertEqual([], self.client.actions('mine_block', 'interact', 'select_item'))
        self.assertEqual(1, len(self.client.actions('projection_batch_clear')))

    def test_restore_rejects_extra_inventory_consumption(self):
        self.make_open()
        self.client.restore_delta = -2
        with self.assertRaises(JobBlocked):
            self.work.restore()
        self.assertEqual(1, len(self.client.actions('interact')))
        self.assertEqual('restore_block', self.journal.pending['kind'])
        self.assertFalse(self.journal.restored)

    def test_pending_action_is_never_automatically_replayed_or_cleaned_up(self):
        self.work.dispatch('open_block', 'mine_block', {'pos': UPPER}, pos=UPPER, expected_state=ORIGINAL)
        pending = self.journal.pending
        with self.assertRaises(AccessJournalError):
            self.work.dispatch('open_block', 'mine_block', {'pos': UPPER}, pos=UPPER, expected_state=ORIGINAL)
        with self.assertRaises(JobBlocked):
            self.work.restore()
        self.assertEqual(1, len(self.client.actions('mine_block')))
        self.assertEqual([], self.client.actions('interact'))
        self.assertEqual(pending, self.journal.pending)

    def test_dispatch_exception_records_actual_request_id_without_replay(self):
        self.client.fail_op = 'mine_block'
        with self.assertRaises(Handoff):
            self.work.dispatch('open_block', 'mine_block', {'pos': UPPER}, pos=UPPER, expected_state=ORIGINAL)
        self.assertEqual(1, len(self.client.actions('mine_block')))
        self.assertEqual(self.client.last, self.journal.pending['request_records'][-1]['request_id'])
        self.assertEqual([], self.journal.data['operations'])

    def test_pre_dispatch_rejection_never_attributes_validation_scan_id_to_mining(self):
        self.client.reject_before_dispatch = 'mine_block'
        with self.assertRaises(Handoff):
            self.work.dispatch('open_block', 'mine_block', {'pos': UPPER}, pos=UPPER, expected_state=ORIGINAL)
        self.assertEqual([], self.client.actions('mine_block'))
        self.assertEqual('open_block', self.journal.pending['kind'])
        self.assertEqual([], self.journal.pending['request_records'],
                         'A previous scan ID is not the undispatched mining request ID')

    def test_manual_world_revision_or_disconnect_handoff_never_forces_cleanup(self):
        for field, value in (('manual_movement', True), ('world_session', 'world-2'),
                             ('control_revision', 2), ('connected', False)):
            with self.subTest(field=field):
                old = self.client.state[field]
                self.client.state[field] = value
                with self.assertRaises(Handoff):
                    self.work.restore()
                self.client.state[field] = old
                self.assertEqual([], self.client.calls)
                self.assertFalse(self.journal.restored)
                self.assertIn(self.work.cleanup_key, self.client.resource_cleanup)

    def test_handoff_immediately_after_mining_stops_before_more_actions(self):
        def handoff(op, client):
            if op == 'mine_block':
                client.state['manual_movement'] = True
        self.client.after_action = handoff
        with self.assertRaises(Handoff):
            self.work.open()
        calls = deepcopy(self.client.calls)
        with self.assertRaises(Handoff):
            self.work.restore()
        self.assertEqual(calls, self.client.calls)
        self.assertEqual(1, len(self.client.actions('mine_block')))
        self.assertEqual('open_block', self.journal.pending['kind'])

    def test_recovery_discovers_explicit_transaction_directory(self):
        self.work.validate()
        self.journal.checkpoint('restored', **self.work.proof())
        nested = AccessJournal(journal_path(access._index(self.owner), self.scope, 'transaction-2'), self.scope, self.journal_plan)
        self.assertFalse(nested.restored)
        with patch.object(access.AccessWork, 'validate'), patch.object(access.AccessWork, 'restore') as restore:
            access.recover_pending(self.owner)
        self.assertEqual(1, restore.call_count, 'An unfinished second transaction must not be skipped on restart')

    def test_same_projection_owner_resumes_entered_work_before_restoring_portal(self):
        self.work.validate();self.journal.checkpoint('restored',**self.work.proof())
        plan=deepcopy(self.journal_plan)
        plan['access_plan']['stages']=[{'layer_y':63,'station':[11.5,64,20.5],
            'targets':[{'pos':[11,63,20],'expected':ORIGINAL}]}]
        journal=AccessJournal(journal_path(access._index(self.owner),self.scope,'resume-work'),self.scope,plan)
        work=access.AccessWork(self.owner,deepcopy(self.client.model),journal)
        with patch.object(work,'move'),patch.object(work,'path_to',return_value=[]),patch.object(work,'cross'):work.open()
        self.owner.request={'mode':'projection','projection_key':'ship'}
        order=[]
        with patch.object(access.AccessWork,'open') as open_again, \
                patch.object(access.AccessWork,'construct',side_effect=lambda:order.append('construct')) as construct, \
                patch.object(access.AccessWork,'restore',side_effect=lambda:order.append('restore')) as restore:
            access.recover_pending(self.owner)
        open_again.assert_not_called();construct.assert_called_once();restore.assert_called_once()
        self.assertEqual(['construct','restore'],order)

    def test_completed_layer_is_skipped_only_after_fresh_exact_block_scan(self):
        first={'layer_y':63,'station':[11.5,64,20.5],'targets':[{'pos':[11,63,20],'expected':ORIGINAL}]}
        second={'layer_y':64,'station':[11.5,65,20.5],'targets':[{'pos':[11,64,20],'expected':ORIGINAL}]}
        self.work.plan['stages']=[first,second]
        self.client.rows[(11,63,20)]=block([11,63,20])
        self.work.path_to.side_effect=lambda target:[target]
        self.work.move.side_effect=lambda path:self.client.state.update(pos=list(path[-1]))
        def build(*args,**kwargs):
            for row in kwargs['complete_cells']:self.client.rows[tuple(row['pos'])]=block(row['pos'],row['expected'])
            return {'matched':2}
        with patch('goal_workflow.build_phase',side_effect=build) as construct:
            self.assertEqual(2,self.work.construct())
        construct.assert_called_once()
        self.assertEqual(second['targets'],construct.call_args.kwargs['complete_cells'])
        self.assertTrue(any(op=='scan' and p['min']==[11,63,20] and p['max']==[11,63,20] for op,p in self.client.calls))
        self.assertTrue(any(row['stage']=='layer_revalidated' and row['data']['layer_y']==63 for row in self.journal.data['checkpoints']))

    def test_old_completed_layer_checkpoint_cannot_replace_current_block_proof(self):
        stage={'layer_y':63,'station':[11.5,64,20.5],'targets':[{'pos':[11,63,20],'expected':ORIGINAL}]}
        self.work.plan['stages']=[stage]
        self.journal.checkpoint('layer_completed',world_session=self.client.world,layer_y=63,count=1)
        self.work.path_to.side_effect=lambda target:[target]
        self.work.move.side_effect=lambda path:self.client.state.update(pos=list(path[-1]))
        def build(*args,**kwargs):
            self.client.rows[(11,63,20)]=block([11,63,20]);return {'matched':1}
        with patch('goal_workflow.build_phase',side_effect=build) as construct:
            self.assertEqual(1,self.work.construct())
        construct.assert_called_once()

    def cross_work(self):
        """Keep the old wall at Y109 and lintel at Y112; only Y110/111 is air."""
        lower,upper=[10,110,20],[10,111,20]
        self.client.rows={(10,109,20):block([10,109,20]),(10,112,20):block([10,112,20])}
        self.client.state['pos']=[9.5,109.929,20.5]
        self.client.state['projection_selection'].update(min=[9,109,19],max=[12,113,21])
        self.client.model['bounds']={'min':[9,109,19],'max':[12,113,21]}
        self.client.model['expected']=[{'pos':p,'expected':ORIGINAL} for p in (lower,upper)]
        plan=deepcopy(self.plan)
        plan.update(outside_station=[9.5,110.02,20.5],inside_station=[11.5,110.02,20.5],
                    mine_order=[upper,lower],restore_order=[lower,upper])
        journal_plan={'blocks':[{'pos':p,'expected':ORIGINAL,'item':CONCRETE} for p in (lower,upper)],
                      'outside':plan['outside_station'],'inside':plan['inside_station'],'access_plan':plan}
        journal=AccessJournal(journal_path(access._index(self.owner),self.scope,'cross-fixture'),self.scope,journal_plan)
        return access.AccessWork(self.owner,deepcopy(self.client.model),journal)

    def test_horizontal_move_keeps_measured_height_under_low_ceiling_and_still_blocks_collisions(self):
        # The descent shaft at X11 has an opening in the Y86 roof. The
        # horizontal passage at X9/X10 remains capped by real solid blocks.
        path = [[11.5, 84.02, 20.5], [9.5, 84.02, 20.5]]
        scenarios = (
            ('recorded-height', 84.17 - 84.022988, 83, None),
            ('flight-settles-point-one-nine', .19, 82, None),
            ('real-head-obstruction', .19, 82, [10, 85, 20]),
            ('real-floor-overlap', .19, 83, None),
        )
        for name, settling, floor_y, obstruction in scenarios:
            with self.subTest(name=name):
                work = access.AccessWork(self.owner, deepcopy(self.client.model), self.journal)
                self.client.calls.clear()
                self.client.state['pos'] = [11.5, 88, 20.5]
                self.client.rows = {(x, floor_y, 20): block([x, floor_y, 20]) for x in (9, 10, 11)}
                self.client.rows.update({(x, 86, 20): block([x, 86, 20]) for x in (9, 10)})
                if obstruction is not None:
                    self.client.rows[tuple(obstruction)] = block(obstruction)
                moves = []
                def settle_after_flight(client, target, seconds):
                    if moves:
                        # Asking for the nominal 84.17 again would command a
                        # climb under the roof and reproduce the live overshoot.
                        self.assertAlmostEqual(client.state['pos'][1], target[1])
                    moves.append(list(target))
                    client.state['pos'] = [target[0], target[1] - settling, target[2]]
                blocked = obstruction is not None or name == 'real-floor-overlap'
                with patch('material_jobs.navigation._air_move', side_effect=settle_after_flight):
                    if blocked:
                        with self.assertRaises(JobBlocked):
                            work.move(path)
                    else:
                        work.move(path)
                self.assertAlmostEqual(84.17, moves[0][1])
                self.assertEqual(1 if blocked else 2, len(moves))
                if not blocked:
                    self.assertAlmostEqual(84.17 - settling, moves[1][1])
                    if name == 'recorded-height':
                        self.assertAlmostEqual(84.022988, moves[1][1])
                horizontal_scans = [params for _, params in self.client.actions('scan')
                                    if params['min'][0] <= 10 <= params['max'][0]]
                self.assertEqual(1, len(horizontal_scans))
                self.assertLess(horizontal_scans[0]['max'][1], 86)
                self.assertIn((9, 86, 20), self.client.rows)
                self.assertIn((10, 86, 20), self.client.rows)
                self.assertIn((10, floor_y, 20), self.client.rows)

    def test_cross_calibrates_observed_height_then_scans_only_the_two_open_cells(self):
        work=self.cross_work();moves=[]
        def lower_after_flight(client,target,seconds):
            moves.append(list(target));client.state['pos']=[target[0],target[1]-.19,target[2]]
        with patch('material_jobs.navigation._air_move',side_effect=lower_after_flight):
            work.cross(True)
            self.assertEqual('inside',work.journal.data['stage'])
            work.cross(False)
        self.assertEqual('outside',work.journal.data['stage'])
        self.assertEqual(4,len(moves))
        self.assertAlmostEqual(110.35,moves[0][1]);self.assertAlmostEqual(110.16,moves[1][1])
        crossing_scans=[p for op,p in self.client.actions('scan') if p['min'][0]<=10<=p['max'][0]]
        self.assertEqual(2,len(crossing_scans))
        for scan in crossing_scans:
            self.assertEqual(110,scan['min'][1]);self.assertEqual(111,scan['max'][1])
        self.assertIn((10,109,20),self.client.rows);self.assertIn((10,112,20),self.client.rows)
        self.assertGreater(work.side_distance(),.82)

    def test_cross_refuses_when_actual_feet_never_enter_safe_height_band(self):
        work=self.cross_work()
        def stays_low(client,target,seconds):client.state['pos']=[target[0],109.97,target[2]]
        with patch('material_jobs.navigation._air_move',side_effect=stays_low) as move:
            with self.assertRaisesRegex(JobBlocked,'脚部高度'):work.cross(True)
        self.assertEqual(3,move.call_count)
        self.assertTrue(all(call.args[1][0]==9.5 for call in move.call_args_list))
        self.assertFalse(any(row['stage']=='inside' for row in work.journal.data['checkpoints']))

    def test_cross_refuses_real_lintel_obstruction_without_widening_clearance(self):
        work=self.cross_work();self.client.rows[(10,111,20)]=block([10,111,20])
        def lower_after_flight(client,target,seconds):client.state['pos']=[target[0],target[1]-.19,target[2]]
        with patch('material_jobs.navigation._air_move',side_effect=lower_after_flight) as move:
            with self.assertRaisesRegex(JobBlocked,'实时身体通道'):work.cross(True)
        self.assertEqual(1,move.call_count)
        self.assertFalse(any(row['stage']=='inside' for row in work.journal.data['checkpoints']))

    def test_cross_requires_the_entire_body_to_clear_the_wall_not_just_a_done_reply(self):
        work=self.cross_work()
        def incomplete_cross(client,target,seconds):
            x=11.25 if target[0]==11.5 else target[0]
            client.state['pos']=[x,target[1]-.19,target[2]]
        with patch('material_jobs.navigation._air_move',side_effect=incomplete_cross) as move:
            with self.assertRaisesRegex(JobBlocked,'完全越过'):work.cross(True)
        self.assertEqual(2,move.call_count);self.assertAlmostEqual(-.75,work.side_distance())
        self.assertFalse(any(row['stage']=='inside' for row in work.journal.data['checkpoints']))

    def test_construction_station_uses_extra_height_when_clear_and_falls_back_when_blocked(self):
        stage={'layer_y':63,'station':[11.5,64,20.5],'targets':[{'pos':[11,63,20],'expected':ORIGINAL}]}
        self.work.plan['stages']=[stage]
        self.work.move.side_effect=lambda path:self.client.state.update(pos=list(path[-1]))
        def build(*args,**kwargs):
            self.client.rows[(11,63,20)]=block([11,63,20]);return {'matched':1}
        self.work.path_to.side_effect=lambda target:[target]
        with patch('goal_workflow.build_phase',side_effect=build):self.work.construct()
        self.work.path_to.assert_called_once_with([11.5,65,20.5])
        self.client.rows.pop((11,63,20));self.work.path_to.reset_mock()
        def fallback(target):
            if target[1]==65:raise access.AccessPlanBlocked('roof at raised stance')
            return [target]
        self.work.path_to.side_effect=fallback
        with patch('goal_workflow.build_phase',side_effect=build):self.work.construct()
        self.assertEqual([[11.5,65,20.5],[11.5,64,20.5]],[call.args[0] for call in self.work.path_to.call_args_list])


if __name__ == '__main__':
    unittest.main()
