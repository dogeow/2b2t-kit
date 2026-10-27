import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from material_jobs.loaded_squid_survey import read,read_glow


class LoadedSquidSurveyTests(unittest.TestCase):
    def test_glowing_observation_is_separate_fresh_and_requires_its_new_protocol(self):
        s={'connected':True,'world_session':'w','server':'srv','dimension':'dim','time':1000}
        e={'id':2,'uuid':'g','type':'minecraft:glow_squid','alive':True,'has_custom_name':False,'health':10,'pos':[50,27,0]}
        q={**s,'protocol':1,'glow_protocol':1,'glow_scope':'current_client_loaded_server_entities_wild_glow_squid','glow_squids':[e]}
        with TemporaryDirectory()as d:
            p=Path(d)/'loaded-squid-survey.json';p.write_text(json.dumps(q));self.assertEqual('g',read_glow(d,s)[0]['uuid']);self.assertEqual([],read(d,s))
            for changed in ({'glow_protocol':0},{'world_session':'old'},{'time':-5000},{'glow_squids':[{**e,'has_custom_name':True}]},{'glow_squids':[{**e,'pos':[50,320,0]}]}):
                p.write_text(json.dumps({**q,**changed}));self.assertEqual([],read_glow(d,s))
            p.write_text(json.dumps({**q,'glow_squids':[{**e,'pos':[50,31,0]}]}));self.assertEqual([50,31,0],read_glow(d,s)[0]['pos'])
    def test_accepts_real_side_target_beyond_old_nearby_radius(self):
        s = {'connected': True, 'world_session': 'w', 'server': 'srv', 'dimension': 'dim', 'time': 1000}
        q = {**s, 'protocol': 1,
             'scope': 'current_client_loaded_server_entities_ordinary_unnamed_squid_y50_64',
             'squids': [{'id': 1, 'uuid': 's', 'type': 'minecraft:squid', 'alive': True,
                         'has_custom_name': False, 'health': 10, 'pos': [50, 53, 0]}]}
        with TemporaryDirectory() as d:
            p = Path(d)/'loaded-squid-survey.json'; p.write_text(json.dumps(q))
            self.assertEqual([50, 53, 0], read(d, s)[0]['pos'])
            for field, value in (('world_session', 'old'), ('server', 'other'),
                                 ('time', -1), ('scope', 'cached_spawn_guess'), ('connected', False)):
                p.write_text(json.dumps({**q, field: value}))
                self.assertEqual([], read(d, s))


if __name__ == '__main__':
    unittest.main()
