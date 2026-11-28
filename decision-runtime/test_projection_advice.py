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






if __name__ == '__main__':
    unittest.main()
