"""Offline compatibility for both bounded client-loaded entity scan envelopes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from animal_breed import entity_rows, run as breed
from animal_pen import place
from farm_caretaker_stages import create_stages
from potato_farm import ENTITY_SCOPE, FarmWait, plan, run as plant, survey_rows, valid_entity_scope
from potato_harvest import POTATO, _owned_drops, run as harvest
from test_animal_breed import BreedClient, SPEC as BREED_SPEC
from test_animal_pen import PenClient
from test_farm_caretaker_stages import StageBackend, StageClient, REGION, adult, depot_exchange, native_travel
from test_potato_farm import FarmClient, SPEC
from test_potato_harvest import Clock, HarvestClient


LEGACY = 'current_client_loaded_rendering_entities_intersecting_scan_AABB_not_whole_herd'
SAMPLED_AT_END = 'current_client_loaded_entities_intersecting_scan_AABB_sampled_at_scan_end_not_whole_herd'
MISSING = object()


def scan_envelope(client, scope=SAMPLED_AT_END, *, stale=False, lose_after_action=False):
    """Wrap offline native clients with the host's incremental scan reply shape.

    Multi-tick blocks are sampled, and scan_entities is sampled at scan end.
    The reply explicitly carries scan_coherent=False; it is no server ACK.
    Existing legacy fixtures remain unchanged.
    """
    client.scope = scope
    original = client.request

    def request(op, **params):
        before = client.time
        reply = original(op, **params)
        if op == 'scan':
            total = 1
            for low, high in zip(params['min'], params['max']): total *= high-low+1
            reply.update(id='offline-scan-'+str(len(client.calls)), phase='done',
                         detail='bounded loaded client cells sampled', scan_coherent=False,
                         scan_started_at=before, scan_ended_at=reply['time'],
                         scan_start_tick=100, scan_end_tick=102, scan_elapsed_ticks=2,
                         scan_start_revision=client.rev, scan_end_revision=client.rev,
                         scan_cells_read=total, scan_total_cells=total,
                         scan_scope='loaded_client_cells_sampled_on_client_ticks_not_atomic_server_snapshot',
                         light_survey_scope='client_light_layers_and_ordinary_zombie_geometry_block_light_only_not_complete_spawn_rules')
            if client.scope is MISSING: reply.pop('scan_entity_scope')
            if stale: reply['time'] = before
        elif lose_after_action and op in ('interact', 'mine_block', 'interact_entity'):
            client.scope = None
        return reply

    client.request = request
    return client


class EntityScanScopeTests(unittest.TestCase):
    def execute(self, kind, client, out):
        clock = Clock()
        options = {'sleep': clock.sleep, 'monotonic': clock.monotonic}
        if kind == 'farm': result = plant(client, SPEC, out, max_cells=1)
        elif kind == 'harvest':
            result = harvest(client, {**SPEC, 'cells': [[1,63,0]]}, out, bonemeal_budget=0, **options)
        elif kind == 'breed': result = breed(client, BREED_SPEC, out, **options)
        else:
            try: result = place(client, 'minecraft:oak_fence', [0,63,0], out)
            except FarmWait as error: result = {'phase':'waiting', 'code':error.code}
        paths = list(Path(out).glob('*.json'))
        book = json.loads(paths[0].read_text()) if paths else {'pending':None}
        return result, book

    def clients(self):
        return (('farm', FarmClient), ('harvest', HarvestClient), ('breed', BreedClient), ('pen', PenClient))

    def test_helper_retains_legacy_and_accepts_only_two_exact_known_values(self):
        self.assertEqual(LEGACY, ENTITY_SCOPE)
        for scope in (LEGACY, SAMPLED_AT_END): self.assertTrue(valid_entity_scope(scope))
        for scope in (None, '', 'whole_herd_server_ack', SAMPLED_AT_END+'?', [], {}, 1, True):
            with self.subTest(scope=scope): self.assertFalse(valid_entity_scope(scope))

    def test_both_known_envelopes_complete_normal_primitive_observations(self):
        for scope in (LEGACY, SAMPLED_AT_END):
            for kind, factory in self.clients():
                with self.subTest(scope=scope, kind=kind), tempfile.TemporaryDirectory() as out:
                    client = scan_envelope(factory(), scope)
                    result, book = self.execute(kind, client, out)
                    self.assertIsNone(book['pending'])
                    if kind == 'farm': self.assertEqual(1, result['planted_cells'])
                    elif kind == 'harvest': self.assertEqual(1, result['harvested_replanted'])
                    elif kind == 'breed': self.assertEqual(1, result['observed_births'])
                    else: self.assertTrue(result['complete'])
                    if kind != 'pen': self.assertFalse(result['server_verified'])

    def test_unknown_null_or_missing_scope_waits_before_any_action(self):
        for scope in ('unknown-client-entity-scope', None, MISSING):
            for kind, factory in self.clients():
                with self.subTest(scope=scope, kind=kind), tempfile.TemporaryDirectory() as out:
                    client = scan_envelope(factory(), scope)
                    result, book = self.execute(kind, client, out)
                    self.assertEqual('WAIT_SCAN', result['code'])
                    self.assertIsNone(book['pending'])
                    self.assertTrue(client.calls)
                    self.assertTrue(all(op == 'scan' for op, _ in client.calls))

    def test_new_scope_does_not_bypass_later_timestamp_requirement(self):
        for kind, factory in self.clients():
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as out:
                client = scan_envelope(factory(), stale=True)
                result, book = self.execute(kind, client, out)
                self.assertEqual('WAIT_SCAN', result['code'])
                self.assertIsNone(book['pending'])
                self.assertTrue(all(op == 'scan' for op, _ in client.calls))

    def test_new_scope_preserves_health_world_and_revision_checks(self):
        for field, value, code in (('health',19,'WAIT_SAFETY'), ('world_session','foreign','WAIT_CONTROL'),
                                   ('control_revision',999,'WAIT_CONTROL')):
            for kind, factory in self.clients():
                with self.subTest(field=field, kind=kind), tempfile.TemporaryDirectory() as out:
                    client = scan_envelope(factory()); client.extra[field] = value
                    result, book = self.execute(kind, client, out)
                    self.assertEqual(code, result['code'])
                    self.assertIsNone(book['pending']); self.assertEqual([], client.calls)

    def test_new_scope_preserves_block_metadata_and_entity_uuid_identity(self):
        client = scan_envelope(FarmClient()); layout = plan(SPEC)
        reply = client.request('scan', min=layout['scan_min'], max=layout['scan_max'], details=True)
        self.assertFalse(reply['scan_coherent']); reply['blocks'][0].pop('block_entity')
        with self.assertRaises(FarmWait) as error: survey_rows(reply, layout, {})
        self.assertEqual('WAIT_SCAN', error.exception.code)
        for change in (lambda rows:rows[0].pop('is_baby'), lambda rows:rows[0].update(uuid=''),
                       lambda rows:rows[1].update(uuid=rows[0]['uuid']), lambda rows:rows[1].update(id=rows[0]['id'])):
            client = scan_envelope(BreedClient()); change(client.entities)
            reply = client.request('scan', min=[-4,63,-4], max=[4,67,4], details=True)
            with self.assertRaises(FarmWait) as error: entity_rows(reply, {'species':'minecraft:cow'})
            self.assertEqual('WAIT_SCAN', error.exception.code)
        scoped = {'uuid':'drop','id':7,'type':'minecraft:item','pos':[1.5,64.5,.5]}
        nearby = {**scoped,'id':8,'stack':{'item':POTATO,'count':1}}
        with self.assertRaises(FarmWait) as error:
            _owned_drops({'scan_entity_scope':SAMPLED_AT_END,'scan_entities':[scoped],'entities':[nearby]},
                         [1,63,0], frozenset(), {})
        self.assertEqual('WAIT_ENTITY', error.exception.code)

    def test_scope_loss_after_one_action_keeps_pending_and_never_replays(self):
        for kind, factory in self.clients():
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as out:
                client = scan_envelope(factory(), lose_after_action=True)
                result, book = self.execute(kind, client, out)
                self.assertEqual('WAIT_SCAN', result['code']); self.assertIsNotNone(book['pending'])
                calls = copy.deepcopy(client.calls)
                result, again = self.execute(kind, client, out)
                self.assertEqual('WAIT_RECONCILE', result['code'])
                self.assertEqual(calls, client.calls); self.assertEqual(book['pending'], again['pending'])

    def test_caretaker_native_stages_accept_new_scope_and_reject_unknown_without_pending(self):
        for scope in (SAMPLED_AT_END, None, 'unknown-client-entity-scope', MISSING):
            for stage in ('harvest_store', 'breed'):
                with self.subTest(scope=scope, stage=stage), tempfile.TemporaryDirectory() as out:
                    root = Path(out); client = scan_envelope(StageClient(potatoes=8), scope)
                    backend = StageBackend(client, root)
                    config = {'adult_keep':2,'potato_reserve':4,'cooked_food_reserve':8,
                              'potato_fields':[SPEC],'livestock_region':copy.deepcopy(REGION),
                              'livestock_types':['minecraft:cow'],'depots':backend.profile['depots']}
                    if stage == 'breed':
                        client.entities = [adult('adult-a',1,[.2,64,.5]), adult('adult-b',2,[1.8,64,.5])]
                        client.add('minecraft:wheat',2)
                    with patch('farm_caretaker_stages.travel',side_effect=native_travel), \
                         patch('farm_caretaker_stages.exchange',side_effect=depot_exchange), \
                         patch('farm_caretaker_stages.time.sleep',return_value=None):
                        result = create_stages(client, backend)[stage](config, {'id':1,'world_session':client.world},
                                                                     root/stage, lambda:None)
                    book = json.loads((root/stage/'stage.json').read_text())
                    self.assertIsNone(book['pending']); self.assertFalse(result['pending'])
                    if scope == SAMPLED_AT_END:
                        self.assertEqual('done', result['phase'], result)
                        if stage == 'breed': self.assertEqual(2, client.feed_count)
                    else:
                        self.assertEqual('WAIT_SCAN', result['code'])
                        self.assertTrue(all(op == 'scan' for op, _ in client.calls))


if __name__ == '__main__': unittest.main()
