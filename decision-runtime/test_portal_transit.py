import unittest
from material_jobs.portal_transit import shape


class RealPortalShapeTest(unittest.TestCase):
    def rows(self,axis):
        dx,dz=(1,0)if axis=='x'else(0,1)
        return [{'pos':[u*dx,y,u*dz],'state':'Block{minecraft:nether_portal}[axis='+axis+']','fluid':False}for u in(0,1)for y in(1,2,3)]+[{'pos':[u*dx,0,u*dz],'state':'Block{minecraft:obsidian}'}for u in(0,1)]
    def test_observed_axis_and_all_six_cells_are_required(self):
        for axis in('x','z'):
            rows=self.rows(axis);self.assertEqual(6,len(shape(rows,[0,1,0],axis)['core']))
            with self.assertRaises(RuntimeError):shape(rows[1:],[0,1,0],axis)
            with self.assertRaises(RuntimeError):shape(rows,[0,1,0],'z'if axis=='x'else'x')
    def test_crying_obsidian_is_not_portal_footing(self):
        rows=self.rows('x');rows[-1]['state']='Block{minecraft:crying_obsidian}'
        with self.assertRaises(RuntimeError):shape(rows,[0,1,0],'x')
