import copy
import unittest
from public_roof_geometry import choose_clear_roof


class PublicRoofGeometryTests(unittest.TestCase):
    def rows(self,x=10,z=20):
        return {(x,-1,z):{'solid':True,'fluid':False},
                (x,3,z):{'state':'Block{minecraft:dark_oak_planks}'}}
    def choose(self,rows,z=20,blocked=()):
        return choose_clear_roof(rows,10,0,z,blocked,low_x=8,high_x=12)
    def test_uses_explicit_aisle_instead_of_a_different_buildings_row(self):
        rows=self.rows();rows.update(self.rows(z=30))
        self.assertEqual(self.choose(rows),[10,3,20])
        self.assertEqual(self.choose(rows,z=30),[10,3,30])
        self.assertIsNone(self.choose(rows,z=40))
    def test_preserves_dry_floor_body_roof_and_lighting_requirements(self):
        for case in ('missing_floor','wet_floor','different_roof','above','solid_body','wet_body','light','unknown_body'):
            rows=copy.deepcopy(self.rows())
            if case=='missing_floor':del rows[(10,-1,20)]
            if case=='wet_floor':rows[(10,-1,20)]['fluid']=True
            if case=='different_roof':rows[(10,3,20)]['state']='Block{minecraft:chest}'
            if case=='above':rows[(10,4,20)]={'passable':True,'fluid':False}
            if case in ('solid_body','wet_body','light','unknown_body'):
                rows[(10,0,20)]={'passable':True,'fluid':False,'state':'Block{minecraft:air}'}
                if case=='solid_body':rows[(10,0,20)]['passable']=False
                if case=='wet_body':rows[(10,0,20)]['fluid']=True
                if case=='light':rows[(10,0,20)]['state']='Block{minecraft:torch}'
                if case=='unknown_body':del rows[(10,0,20)]['passable']
            with self.subTest(case=case):self.assertIsNone(self.choose(rows))
    def test_quarantine_and_radius_choose_only_a_nearby_clear_alternative(self):
        rows=self.rows();rows.update(self.rows(x=9));rows.update(self.rows(x=13))
        self.assertEqual(self.choose(rows,blocked={(10,3,20)}),[9,3,20])
        self.assertIsNone(self.choose(rows,blocked={(10,3,20),(9,3,20)}))
        self.assertIsNone(choose_clear_roof(rows,10,0,20,low_x=11,high_x=12))
    def test_requires_explicit_valid_integer_geometry(self):
        for x,floor,z,low,high in ((True,0,20,8,12),(10,.0,20,8,12),(10,0,'20',8,12),(10,0,20,12,8)):
            with self.subTest(values=(x,floor,z,low,high)),self.assertRaises(ValueError):
                choose_clear_roof({},x,floor,z,low_x=low,high_x=high)


if __name__=='__main__':unittest.main()
