import unittest
from sheep_tending import known_pickup_preflight,drop_fingerprint,PICKUP_HOST_SHA

class SheepDropMergeTests(unittest.TestCase):
    def test_only_pinned_exact_preflight_identity_errors_allow_a_fresh_observation(self):
        r={'id':'r','world_session':'w','phase':'error','detail':'Drop is no longer loaded; observe again'}
        self.assertTrue(known_pickup_preflight(r,'r','w',PICKUP_HOST_SHA))
        for change in ({'id':'other'},{'world_session':'old'},{'phase':'waiting'},
                       {'detail':'Drop disappeared without inventory confirmation'},{'detail':'Actual collision on depot route'}):
            self.assertFalse(known_pickup_preflight({**r,**change},'r','w',PICKUP_HOST_SHA))
        self.assertFalse(known_pickup_preflight(r,'r','w','unknown-host'))
    def test_merge_changes_uuid_or_stack_and_resets_stability(self):
        a=[{'uuid':'a','stack':{'count':1}},{'uuid':'b','stack':{'count':1}}]
        merged=[{'uuid':'b','stack':{'count':2}}]
        self.assertNotEqual(drop_fingerprint(a),drop_fingerprint(merged))
        self.assertEqual(drop_fingerprint(a),drop_fingerprint(list(reversed(a))))
        self.assertNotEqual(drop_fingerprint(merged),drop_fingerprint([{'uuid':'c','stack':{'count':2}}]))

if __name__=='__main__':unittest.main()
