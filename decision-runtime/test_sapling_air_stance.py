import unittest
from types import SimpleNamespace
from material_jobs.navigation import _air_scan


class SaplingStanceTest(unittest.TestCase):
    def test_sapling_routing_keeps_hazards_and_fluids_as_real_obstacles(self):
        rows=[{'pos':[i,64,0],'state':'Block{minecraft:'+name+'}',
               'passable':True,'fluid':wet,'block_entity':False}
              for i,(name,wet)in enumerate([('spruce_sapling',False),('bush',False),
                                           ('fire',False),('sweet_berry_bush',False),('spruce_sapling',True)])]
        client=SimpleNamespace(world='w',request=lambda *a,**k:{'phase':'done','world_session':'w','blocks':rows})
        obstacles=_air_scan(client,[0,64,0],[4,65,0])
        self.assertEqual([2,3,4],[r['pos'][0]for r in obstacles])
