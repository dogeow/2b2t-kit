import copy
from pathlib import Path
import tempfile
import unittest

from material_jobs.seed_snow_search import (allowed_survey_tiles, ledger_state,
                                             parse_reply, public_candidate,
                                             record_server_mismatch,
                                             shared_hints_disabled)


def reply(*, request='current', world='world', cursor=0, next_cursor=5):
    candidate={'sample_cursor':3,'x':1024,'z':-512,'sample_y':128,
               'biome':'minecraft:snowy_plains','distance':1145,
               'token':'11111111-1111-1111-1111-111111111111',
               'route_id':'22222222-2222-2222-2222-222222222222',
               'expires_at':2_000_000_000_000,
               'target':[1024.5,200.0,-511.5]}
    return {'id':request,'world_session':world,'phase':'done',
            'snow_seed_candidates':{'protocol':1,'available':True,'cursor':cursor,
                'next_cursor':next_cursor,'processed':5,'total':81,'done':False,
                'radius':4096,'stride':256,'candidates':[candidate]}}


class SeedSnowSearchTest(unittest.TestCase):
    def test_strict_reply_accepts_coordinates_progress_and_opaque_permit(self):
        parsed=parse_reply(reply(),'current','world',0)
        row=parsed['candidates'][0]
        self.assertEqual((3,1024,-512,'minecraft:snowy_plains'),
                         (row['sample_cursor'],row['x'],row['z'],row['biome']))
        stored=public_candidate(row)
        self.assertNotIn('token',stored);self.assertNotIn('route_id',stored)
        self.assertNotIn('target',stored)

    def test_seed_fields_foreign_identity_and_bad_candidate_are_rejected(self):
        cases=[]
        bad=reply();bad['snow_seed_candidates']['seed']=123;cases.append(bad)
        bad=reply();bad['id']='old';cases.append(bad)
        bad=reply();bad['snow_seed_candidates']['candidates'][0]['target'][0]=999;cases.append(bad)
        bad=reply();bad['snow_seed_candidates']['candidates'][0]['token']='raw';cases.append(bad)
        for value in cases:
            with self.subTest(value=value),self.assertRaises(ValueError):
                parse_reply(value,'current','world',0)

    def test_structured_sampler_unavailable_keeps_request_identity_and_requests_fallback(self):
        value={'id':'current','world_session':'world','phase':'done',
               'snow_seed_candidates':{'protocol':1,'available':False,
                                       'reason':'sampler_unavailable'}}
        self.assertEqual(False,parse_reply(value,'current','world',0)['available'])
        bad=copy.deepcopy(value);bad['id']='old'
        with self.assertRaises(ValueError):parse_reply(bad,'current','world',0)
        bad=copy.deepcopy(value);bad['snow_seed_candidates']['detail']='raw failure'
        with self.assertRaises(ValueError):parse_reply(bad,'current','world',0)

    def test_cursor_ledger_is_bounded_and_refuses_corruption(self):
        ledger={};state=ledger_state(ledger);row=public_candidate(reply()['snow_seed_candidates']['candidates'][0])
        state.update(next_cursor=4,total=81,radius=4096);state['candidates']['1024:-512']=row
        self.assertEqual(4,ledger_state(ledger)['next_cursor'])
        broken=copy.deepcopy(ledger);broken['seed_snow_search']['candidates']['1024:-512']['state']='done'
        with self.assertRaises(RuntimeError):ledger_state(broken)

    def test_actual_survey_tile_allowlist_is_nine_exact_tiles(self):
        found=allowed_survey_tiles((1024,-512))
        self.assertEqual(9,len(found))
        self.assertIn((1024,-512),found)
        self.assertIn((960,-576),found)

    def test_two_distinct_server_mismatches_disable_seed_hints_across_items_and_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            common=dict(world_session='world',observed_at=100,loaded_samples=9)
            self.assertFalse(record_server_mismatch(
                directory,'example.test:25565','minecraft:overworld',1024,-512,**common))
            self.assertFalse(shared_hints_disabled(
                directory,'example.test','minecraft:overworld'))
            self.assertFalse(record_server_mismatch(
                directory,'example.test','minecraft:overworld',1024,-512,**common))
            self.assertTrue(record_server_mismatch(
                directory,'example.test','minecraft:overworld',2048,-512,**common))
            self.assertTrue(shared_hints_disabled(
                directory,'example.test:25565','minecraft:overworld'))
            self.assertFalse(shared_hints_disabled(
                directory,'example.test','minecraft:the_nether'))

    def test_mismatch_gate_corruption_is_fail_closed_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            common=dict(world_session='world',observed_at=100,loaded_samples=9)
            record_server_mismatch(
                directory,'example.test','minecraft:overworld',1,2,**common)
            path=next(Path(directory).glob('snow-hint-policy-*.json'))
            path.write_text('{"schema":1,"disabled":false,"mismatches":[]}',encoding='utf-8')
            before=path.read_text()
            with self.assertRaises(RuntimeError):
                shared_hints_disabled(directory,'example.test','minecraft:overworld')
            self.assertEqual(before,path.read_text())


if __name__=='__main__':unittest.main()
