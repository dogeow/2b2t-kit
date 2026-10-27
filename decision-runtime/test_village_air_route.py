import unittest
from material_jobs.local_air_path import plan
from village_air_route import move


class VillageAirRouteTests(unittest.TestCase):
    def test_high_hover_above_water_starts_up_without_a_spurious_surface_descent(self):
        water=[{'pos':[x,62,z],'state':'Block{minecraft:water}[level=0]','fluid':True}
               for x in range(3)for z in range(3)]
        route=plan(water,[1.7,63.9,1.5],[.5,64.1,1.5],[-1,61,-1],[3,68,3],foot_offset=.1)
        self.assertGreaterEqual(min(p[1]for p in route),64.1)
    def test_collisionless_torch_is_not_a_solid_voxel_but_web_remains_protected(self):
        class Builder:
            def __init__(self,name):self.position=[.5,0,.5];self.book={};self.inputs=[];self.name=name
            def check(self):return {'pos':self.position}
            def save(self):pass
            def scan(self,low,high):return {'time':1},{(0,0,0):{'pos':[0,0,0],'state':'Block{minecraft:'+self.name+'}',
                                                            'passable':True,'fluid':False,'block_entity':False}}
            def n(self,op,**params):self.inputs.append(op);self.position=params['target']
        c=Builder('torch');move(c,[2.5,.1,.5]);self.assertTrue(c.book['observed_air_routes'][0]['complete'])
        self.assertEqual(set(c.inputs),{'navigate'})
        c=Builder('cobweb')
        with self.assertRaises(Exception):move(c,[2.5,.1,.5])
        self.assertEqual(c.inputs,[])
    def test_exit_low_overhang_before_rising(self):
        rows = [{'pos': [0, 3, 0], 'state': 'Block{minecraft:dark_oak_planks}'}]
        route = plan(rows, [.5, 0, .5], [.5, 4.1, .5], [-1, 0, -1], [1, 6, 1], foot_offset=.1)
        # No vertical segment through the roof voxel; a horizontal exit is necessary.
        for a, b in zip(route, route[1:]):
            if a[0] == b[0] == .5 and a[2] == b[2] == .5:
                self.assertFalse(min(a[1], b[1]) < 3 < max(a[1], b[1]) + 1.8)
        self.assertTrue(any(p[0] != .5 or p[2] != .5 for p in route))


if __name__ == '__main__':
    unittest.main()
