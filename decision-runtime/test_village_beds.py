import unittest
from village_beds import cells,matches,founder_layout

class VillageBedPlanTests(unittest.TestCase):
    def test_six_beds_follow_actual_docking_cell_without_blocking_landing_or_each_other(self):
        origin=[100,64,200]
        for x in(103,104,105):
            beds=founder_layout(origin,[x,64,204]);self.assertEqual(len(beds),6)
            blocks=[tuple(b[k])for b in beds for k in('foot','head')];self.assertEqual(len(set(blocks)),12)
            landing={(xx,64,zz)for xx in range(x-2,x+3)for zz in range(202,207)}
            torches={(xx,64,zz)for xx in(101,107)for zz in(201,207)}
            self.assertFalse(set(blocks)&landing);self.assertFalse(set(blocks)&torches)
            self.assertTrue(all(tuple(b['stand'])not in set(blocks)|torches for b in beds))
            self.assertTrue(all(101<=p[0]<=107 and 201<=p[2]<=207 for p in blocks))
        for cell in([102,64,204],[104,65,204],[104,64,203]):
            with self.assertRaises(ValueError):founder_layout(origin,cell)
    def test_exact_stand_behind_foot_and_head_in_facing_direction(self):
        self.assertEqual(([10,64,19],[10,64,21]),cells([10,64,20],'north'))
        self.assertEqual(([10,64,21],[10,64,19]),cells([10,64,20],'south'))
        self.assertEqual(([11,64,20],[9,64,20]),cells([10,64,20],'east'))
        self.assertEqual(([9,64,20],[11,64,20]),cells([10,64,20],'west'))
        for facing in ('up','down','invalid'):
            with self.assertRaises(ValueError):cells([10,64,20],facing)
    def test_both_bed_parts_orientation_and_item_identity_matter(self):
        row={'state':'Block{minecraft:white_bed}[facing=south,occupied=false,part=foot]'}
        self.assertTrue(matches(row,'minecraft:white_bed','foot','south'))
        self.assertFalse(matches(row,'minecraft:white_bed','head','south'))
        self.assertFalse(matches(row,'minecraft:white_bed','foot','north'))
        self.assertFalse(matches(row,'minecraft:red_bed','foot','south'))

if __name__=='__main__':unittest.main()
