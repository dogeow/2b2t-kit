import unittest
from hull_escape import horizontal_exit


class HullEscapeTests(unittest.TestCase):
    def test_does_not_climb_into_ceiling_and_finds_open_side(self):
        rows=[{'pos':[x,12,z],'passable':False} for x in range(-3,4) for z in range(-3,4)]
        rows += [{'pos':[2,y,z],'passable':False} for z in range(-4,5) for y in (10,11)]
        route=horizontal_exit(rows,[0.5,10.2,0.5],[-2,0,-2],[2,20,2],[-6,10,-6],[6,12,6])
        self.assertTrue(all(p[1]==10.2 for p in route['waypoints']))
        self.assertTrue(all(p[0]!=2 for p in route['cells']))
        self.assertEqual([-5,0],route['cells'][-1])
    def test_refuses_closed_hull_or_wet_openings(self):
        walls=[{'pos':[x,y,z],'passable':False} for x,z in ((1,0),(-1,0),(0,1),(0,-1)) for y in (10,11)]
        with self.assertRaises(RuntimeError):horizontal_exit(walls,[.5,10,.5],[-2,0,-2],[2,20,2],[-6,10,-6],[6,12,6])
        walls[-1]={'pos':[0,11,-1],'passable':True,'fluid':True}
        with self.assertRaises(RuntimeError):horizontal_exit(walls,[.5,10,.5],[-2,0,-2],[2,20,2],[-6,10,-6],[6,12,6])

if __name__=='__main__':unittest.main()
