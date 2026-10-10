import unittest
import json
from pathlib import Path
import tempfile
from registered_wheat_growth import accept_growth,reconcile_pre_use_rejection
from material_jobs.protocol import JobBlocked


class GrowthProofTest(unittest.TestCase):
    def test_one_normal_use_requires_real_age_increase_and_exact_consumption(self):
        accept_growth(4,7,62,61,{'phase':'done','world_session':'world'},'world')
        for after_age,after_count,reply in [(4,61,{'phase':'done','world_session':'world'}),
            (7,62,{'phase':'done','world_session':'world'}),(7,60,{'phase':'done','world_session':'world'}),
            (7,61,{'phase':'waiting','world_session':'world'}),(7,61,{'phase':'done','world_session':'old'})]:
            with self.assertRaises(JobBlocked):accept_growth(4,after_age,62,after_count,reply,'world')

    def test_exact_pinned_pre_use_error_requires_unchanged_real_inventory(self):
        with tempfile.TemporaryDirectory()as tmp:
            p=Path(tmp)/'growth.json';row={'slot':0,'item':'minecraft:bone_meal','count':49,'max_stack':64}
            reply={'id':'once','phase':'error','world_session':'world','kit_version':'2026.10.10.3',
                   'detail':'Target interaction face is occluded or out of reach','inventory':[row]}
            book={'world_session':'world','uses':[],'pending':{'pos':[1,65,1],'before_bone_meal':49,'receipt':reply}}
            p.write_text(json.dumps(book));state={'world_session':'world','inventory':[row]}
            with self.assertRaises(JobBlocked):reconcile_pre_use_rejection(p,state,'wrong-host')
            changed={**state,'inventory':[{**row,'count':48}]}
            host='ef5f1bbccaa2746e9aaff2782c4c58ec8ef15c9cb6a0cf5cf1088a2819c09688'
            with self.assertRaises(JobBlocked):reconcile_pre_use_rejection(p,changed,host)
            proof=reconcile_pre_use_rejection(p,state,host)
            self.assertFalse(proof['new_bone_meal_use_sent']);self.assertIsNone(json.loads(p.read_text())['pending'])


if __name__=='__main__':unittest.main()
