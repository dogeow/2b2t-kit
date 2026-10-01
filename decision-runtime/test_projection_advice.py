"""Offline Jev boundary tests; no Minecraft or network access."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from decision_advisor import Advisor
from material_jobs import JobPaused, MaterialJob
from material_jobs.profile import load as load_profile, profile_path
from material_jobs.protocol import JobBlocked
from material_jobs.projection_advice import audit_fingerprint, material_choices
import material_jobs_backend


ITEMS = {'minecraft:grass_block': 12, 'minecraft:deepslate_tiles': 18}


def audit():
    return {'audit_schema': 2, 'observed_at': int(time.time() * 1000), 'loaded_chunks_verified': True,
            'placement_key': 'private-placement-at-761020-797854',
            'matched': 8, 'total': 10, 'replacement_items': dict(ITEMS),
            'mismatches': [
                {'pos': [761020, 65, 797854], 'expected': 'Block{minecraft:grass_block}'},
                {'pos': [761021, 65, 797854], 'expected': 'Block{minecraft:deepslate_tiles}'}]}


def offer():
    return material_choices(audit(), audit()['placement_key'], ITEMS, {}, list(ITEMS))


def state():
    return {'connected': True, 'world_session': 'private-player-world',
            'control_revision': 1, 'server': 'private.example',
            'dimension': 'minecraft:overworld', 'projection_selection': {'key': audit()['placement_key']},
            'manual_movement': False, 'screen': '', 'health': 20, 'food': 20,
            'guard_armed': True, 'guard_busy': False, 'under_water': False,
            'air_return_active': False, 'safety_hold': {'active': False},
            'pos': [761020.5, 100, 797854.5], 'inventory': []}


class Model:
    def __init__(self):
        self.calls = 0
        self.prompt = None

    def predict(self, state_value, question):
        self.calls += 1
        self.prompt = {'state': state_value, 'question': question}
        keys = question['action']['criteria']
        return {'model': 'offline-jev', 'answers': {'action': {
            'type': 'choice', 'choice': 'supply_02', 'confidence': .95,
            'probabilities': {key: (1 if key == 'supply_02' else 0) for key in keys}}}}

    def close(self):
        pass


class ProjectionAdviceTests(unittest.TestCase):
    def test_offer_is_bounded_and_redacts_projection_identity_and_coordinates(self):
        selected = offer()
        self.assertEqual('minecraft:deepslate_tiles', selected['mapping']['supply_02'])
        sent = json.dumps([selected['choices'], selected['scene']])
        for private in ('761020', '797854', 'private-placement', 'private-player-world'):
            self.assertNotIn(private, sent)
        large = {f'minecraft:material_{n}': 1 for n in range(20)}
        source = audit();source['replacement_items'] = large
        selected = material_choices(source, source['placement_key'], large, {}, list(large))
        self.assertEqual(9, len(selected['choices']))
        self.assertEqual(8, len(selected['mapping']))

    def test_incomplete_or_changed_audit_never_reaches_adviser(self):
        for change in ({'loaded_chunks_verified': False}, {'audit_schema': 1},
                       {'matched': 7}, {'placement_key': 'another-project'},
                       {'replacement_items': {'minecraft:grass_block': 13}}):
            with self.subTest(change=change):
                source = audit();source.update(change)
                self.assertIsNone(material_choices(source, audit()['placement_key'],
                                                   ITEMS, {}, list(ITEMS)))
        source = audit();original = audit_fingerprint(source, source['placement_key'], ITEMS)
        source['mismatches'][0]['pos'][0] += 1
        self.assertNotEqual(original, audit_fingerprint(source, source['placement_key'], ITEMS))

    def test_engine_only_maps_opaque_choice_to_local_bounded_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = {'schema': 1, 'id': 'projection-test', 'mode': 'projection',
                       'targets': {}, 'projection_key': audit()['placement_key'],
                       'context': {'server': 'private.example', 'dimension': 'minecraft:overworld',
                                   'world_session': 'private-player-world',
                                   'expected_revision': 1, 'start_pos': [0, 64, 0]},
                       'created_at': 1000}
            job = MaterialJob(request, Path(tmp) / 'job')
            job.snapshot = {'projection_audit': audit()}
            job.held = {}
            job._fit_batch = lambda item, count: min(count, 8)
            job.backend = SimpleNamespace(projection_jev_enabled=True,
                advise_projection_supply=lambda selected, stock: {
                'id': 'decision-a', 'source': 'jev', 'choice': 'supply_02',
                'model_call_scheduled': True})
            self.assertEqual({'minecraft:grass_block': 8}, job._projection_batch(ITEMS))
            self.assertEqual(1, job.state['ai_calls'])
            record = json.loads((job.out / 'events.jsonl').read_text().splitlines()[0])
            self.assertEqual('minecraft:grass_block', record['selected_item'])
            job.batch_item = None
            job.backend = SimpleNamespace(projection_jev_enabled=True,
                advise_projection_supply=lambda selected, stock: {
                'source': 'local', 'reason': 'provider_error', 'choice': selected['fallback']})
            self.assertEqual({'minecraft:deepslate_tiles': 8}, job._projection_batch(ITEMS))
            job.batch_item = None
            job.backend = SimpleNamespace(projection_jev_enabled=True,
                advise_projection_supply=lambda selected, stock: {
                'source': 'jev', 'choice': 'wait'})
            with self.assertRaises(JobPaused):
                job._projection_batch(ITEMS)

    def test_default_projection_path_never_offers_model_or_spends_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = {'schema': 1, 'id': 'projection-test', 'mode': 'projection',
                       'targets': {}, 'projection_key': audit()['placement_key'],
                       'context': {'server': 'private.example', 'dimension': 'minecraft:overworld',
                                   'world_session': 'private-player-world',
                                   'expected_revision': 1, 'start_pos': [0, 64, 0]},
                       'created_at': 1000}
            job = MaterialJob(request, Path(tmp) / 'job')
            job.snapshot = {'projection_audit': audit()}
            job.held = {}
            job._fit_batch = lambda item, count: min(count, 8)

            def unexpected(*args, **kwargs):
                raise AssertionError('Default projection path attempted Jev')

            job.backend = SimpleNamespace(advise_projection_supply=unexpected)
            self.assertEqual({'minecraft:deepslate_tiles': 8}, job._projection_batch(ITEMS))
            self.assertEqual(0, job.state['ai_calls'])
            self.assertFalse((job.out / 'events.jsonl').exists())
            backend = material_jobs_backend.Backend.__new__(material_jobs_backend.Backend)
            backend.profile = {}
            backend.ensure_client = unexpected
            self.assertEqual('projection_jev_disabled',
                             backend.advise_projection_supply(offer(), {})['reason'])

    def test_world_profile_requires_boolean_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            automation = Path(tmp) / 'config' / 'twob2tkit' / 'automation'
            automation.mkdir(parents=True)
            jar = Path(tmp) / 'recipes.jar'
            jar.write_bytes(b'fixture')
            context = {'server': 'private.example', 'dimension': 'minecraft:overworld'}
            path = profile_path(automation, context)
            path.parent.mkdir(parents=True, exist_ok=True)
            base = {**context, 'recipe_jar': str(jar)}
            path.write_text(json.dumps(base))
            self.assertIs(load_profile(automation, context)['projection_jev_advice'], False)
            path.write_text(json.dumps({**base, 'projection_jev_advice': True}))
            self.assertIs(load_profile(automation, context)['projection_jev_advice'], True)
            path.write_text(json.dumps({**base, 'projection_jev_advice': 'true'}))
            with self.assertRaises(JobBlocked):
                load_profile(automation, context)

    def test_world_profile_rejects_malformed_resource_and_search_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            automation=Path(tmp)/'config'/'twob2tkit'/'automation';automation.mkdir(parents=True)
            jar=Path(tmp)/'recipes.jar';jar.write_bytes(b'fixture')
            context={'server':'private.example','dimension':'minecraft:overworld'}
            path=profile_path(automation,context);path.parent.mkdir(parents=True)
            region={'item':'minecraft:cobbled_deepslate','min':[0,-18,0],'max':[1,-1,1],
                    'source':'natural_survey','future_extension':{'kept':True},
                    'access_shaft':{'min':[0,0,0],'max':[1,80,1]}}
            base={**context,'schema':1,'recipe_jar':str(jar),'resource_regions':[region],
                  'search_origin':[0,80,0],'search_radius':256}
            path.write_text(json.dumps(base))
            loaded=load_profile(automation,context)
            self.assertEqual({'kept':True},loaded['resource_regions'][0]['future_extension'])
            malformed=([],{**base,'schema':2},{**base,'resource_regions':{}},
                       {**base,'resource_regions':[None]},
                       {**base,'resource_regions':[{**region,'item':'cobbled_deepslate'}]},
                       {**base,'resource_regions':[{**region,'min':[0.5,-18,0]}]},
                       {**base,'resource_regions':[{**region,'min':[2,-18,0]}]},
                       {**base,'resource_regions':[{**region,'access_shaft':[]}]},
                       {**base,'search_origin':[0,float('nan'),0]},
                       {**base,'search_radius':True},{**base,'search_radius':0},
                       {**base,'search_radius':385})
            for value in malformed:
                with self.subTest(value=value):
                    path.write_text(json.dumps(value))
                    with self.assertRaises(JobBlocked):load_profile(automation,context)

    def test_world_profile_rejects_malformed_registered_supply_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            automation=Path(tmp)/'config'/'twob2tkit'/'automation';automation.mkdir(parents=True)
            jar=Path(tmp)/'recipes.jar';jar.write_bytes(b'fixture')
            context={'server':'private.example','dimension':'minecraft:overworld'}
            path=profile_path(automation,context);path.parent.mkdir(parents=True)
            path.write_text(json.dumps({**context,'schema':1,'recipe_jar':str(jar)}))
            config=automation.parent.parent/'twob2tkit.json'
            malformed=([],{'projectionSupplySources':{}},
                       {'projectionSupplySources':[None]},
                       {'projectionSupplySources':[{'server':'other.example','dimension':'minecraft:overworld',
                                                     'x':True,'y':64,'z':0}]},
                       {'projectionSupplySources':[{'server':'other.example','x':0,'y':64,'z':0}]})
            for value in malformed:
                with self.subTest(value=value):
                    config.write_text(json.dumps(value))
                    with self.assertRaises(JobBlocked):load_profile(automation,context)

    def test_backend_uses_shared_adviser_and_rechecks_full_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = material_jobs_backend.Backend.__new__(material_jobs_backend.Backend)
            backend.root = backend.out = Path(tmp)
            backend.profile = {'projection_jev_advice': True}
            backend.request = {'projection_key': audit()['placement_key'], 'context': {}}
            backend.ensure_client = lambda: object()
            backend.refresh_audit = lambda: copy.deepcopy(audit())
            model = Model()
            backend.projection_advisor = Advisor(tmp, Path(tmp) / 'settings', lambda: model)
            with (patch.object(material_jobs_backend, 'read_fresh', return_value=state()),
                  patch.object(material_jobs_backend, 'require_unlocked'),
                  patch.object(material_jobs_backend, 'require_scope'),
                  patch.object(material_jobs_backend, 'owns_material_state', return_value=True)):
                decision = backend.advise_projection_supply(offer(), {})
            self.assertEqual(('jev', 'supply_02'), (decision['source'], decision['choice']))
            self.assertEqual(1, model.calls)
            self.assertNotIn('761020', json.dumps(model.prompt))
            self.assertNotIn('private-placement', json.dumps(model.prompt))
            kinds = [json.loads(line)['kind'] for line in (Path(tmp) / 'jev-decisions.jsonl').read_text().splitlines()]
            self.assertEqual(['decision', 'outcome'], kinds)

    def test_missing_credential_falls_back_locally_and_changed_audit_discards_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = material_jobs_backend.Backend.__new__(material_jobs_backend.Backend)
            backend.root = backend.out = Path(tmp)
            backend.profile = {'projection_jev_advice': True}
            backend.request = {'projection_key': audit()['placement_key'], 'context': {}}
            backend.ensure_client = lambda: object()
            backend.refresh_audit = lambda: copy.deepcopy(audit())
            backend.projection_advisor = Advisor(tmp, Path(tmp) / 'settings',
                                                 lambda: (_ for _ in ()).throw(FileNotFoundError()))
            with (patch.object(material_jobs_backend, 'read_fresh', return_value=state()),
                  patch.object(material_jobs_backend, 'require_unlocked'),
                  patch.object(material_jobs_backend, 'require_scope'),
                  patch.object(material_jobs_backend, 'owns_material_state', return_value=True)):
                decision = backend.advise_projection_supply(offer(), {})
            self.assertEqual(('supply_01', 'provider_error'),
                             (decision['choice'], decision['reason']))
            self.assertTrue(decision['model_call_scheduled'])

            changed = audit();changed['mismatches'][0]['pos'][0] += 1
            observations = iter((audit(), changed))
            backend.refresh_audit = lambda: copy.deepcopy(next(observations))
            model = Model()
            backend.projection_advisor = Advisor(Path(tmp) / 'changed', Path(tmp) / 'new-settings', lambda: model)
            with (patch.object(material_jobs_backend, 'read_fresh', return_value=state()),
                  patch.object(material_jobs_backend, 'require_unlocked'),
                  patch.object(material_jobs_backend, 'require_scope'),
                  patch.object(material_jobs_backend, 'owns_material_state', return_value=True)):
                with self.assertRaisesRegex(JobPaused, '建议期间已改变'):
                    backend.advise_projection_supply(offer(), {})
            rows = [json.loads(line) for line in (Path(tmp) / 'changed' / 'jev-decisions.jsonl').read_text().splitlines()]
            self.assertEqual('discarded_changed_audit_or_stock', rows[-1]['result'])

    def test_timeout_uses_local_material_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = material_jobs_backend.Backend.__new__(material_jobs_backend.Backend)
            backend.root = backend.out = Path(tmp)
            backend.profile = {'projection_jev_advice': True}
            backend.request = {'projection_key': audit()['placement_key'], 'context': {}}
            backend.ensure_client = lambda: object()
            backend.refresh_audit = lambda: copy.deepcopy(audit())
            gate = threading.Event()

            class Slow(Model):
                def predict(self, state_value, question):
                    gate.wait(.5)
                    return super().predict(state_value, question)

            settings = Path(tmp) / 'settings'
            settings.mkdir()
            (settings / 'settings.json').write_text(json.dumps({'timeout_seconds': .1}))
            backend.projection_advisor = Advisor(tmp, settings, lambda: Slow())
            try:
                with (patch.object(material_jobs_backend, 'read_fresh', return_value=state()),
                      patch.object(material_jobs_backend, 'require_unlocked'),
                      patch.object(material_jobs_backend, 'require_scope'),
                      patch.object(material_jobs_backend, 'owns_material_state', return_value=True)):
                    decision = backend.advise_projection_supply(offer(), {})
                self.assertEqual(('supply_01', 'timeout'),
                                 (decision['choice'], decision['reason']))
                self.assertTrue(decision['model_call_scheduled'])
            finally:
                gate.set()

    def test_native_receipt_records_observed_material_change_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = {'schema': 1, 'id': 'projection-test', 'mode': 'projection',
                       'targets': {}, 'projection_key': audit()['placement_key'],
                       'context': {'server': 'private.example', 'dimension': 'minecraft:overworld',
                                   'world_session': 'private-player-world',
                                   'expected_revision': 1, 'start_pos': [0, 64, 0]},
                       'created_at': 1000}

            class Backend:
                projection_jev_enabled = True

                def __init__(self):
                    self.held = 0
                    self.single = False
                    self.outcomes = []

                def observe(self):
                    projection = audit()
                    if self.single:
                        projection['matched'] = 9
                        projection['mismatches'] = projection['mismatches'][:1]
                        projection['replacement_items'] = {'minecraft:grass_block': 12}
                    return {'connected': True, 'server': 'private.example',
                            'dimension': 'minecraft:overworld',
                            'world_session': 'private-player-world',
                            'control_revision': 1, 'manual_movement': False,
                            'health': 20, 'inventory': [
                                {'slot': 0, 'item': 'minecraft:grass_block', 'count': self.held}],
                            'projection_audit': projection}

                def stock(self):
                    return {'minecraft:grass_block': self.held} if self.held else {}

                def fetch(self, targets):
                    self.held = targets['minecraft:grass_block']
                    return {'phase': 'done'}

                def build(self, key):
                    self.held = 0
                    self.single = True
                    return {'phase': 'done'}

                def advise_projection_supply(self, offer, stock):
                    raise AssertionError('One candidate should not invoke Jev')

                def record_projection_advice_outcome(self, decision, result, **evidence):
                    self.outcomes.append((decision['id'], result, evidence))

            backend = Backend()
            job = MaterialJob(request, Path(tmp) / 'job', backend)
            job._observe()
            job.batch_item = 'minecraft:grass_block'
            job.active_advice = {'id': 'decision-a', 'choice': 'supply_01'}
            job._call('fetch', [{'minecraft:grass_block': 3}], 'fetching',
                      {'minecraft:grass_block': 3})
            self.assertEqual(3, backend.held)
            self.assertEqual(('decision-a', 'native_step_observed'), backend.outcomes[0][:2])
            self.assertEqual((0, 3),
                             (backend.outcomes[0][2]['item_before'], backend.outcomes[0][2]['item_after']))
            job._build_batch()
            self.assertIsNone(job.active_advice)
            self.assertEqual(2, len(backend.outcomes))
            job._fit_batch = lambda item, count: 4
            next_target = job._projection_batch({'minecraft:grass_block': 12})
            self.assertEqual({'minecraft:grass_block': 4}, next_target)
            job._call('fetch', [next_target], 'fetching', next_target)
            self.assertEqual(2, len(backend.outcomes),
                             'A later one-candidate batch must not inherit the old decision ID')


if __name__ == '__main__':
    unittest.main()
