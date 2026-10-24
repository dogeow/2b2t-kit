import unittest
from village_adult_enclosure import audit, maximum_gap


def cube():
    return dict(state='Block{minecraft:oak_planks}', solid=True, fluid=False, block_entity=False)


def partial(kind, props):
    return dict(state='Block{minecraft:'+kind+'}['+props+']', solid=False, fluid=False, block_entity=False)


class EnclosureTests(unittest.TestCase):
    def fixture(self, depth=3):
        rows = {(x,y,z):cube() for x in (-1,0,1) for y in range(63,69) for z in range(depth+2)}
        for z in range(1,depth+1):
            for y in range(64,67):
                rows.pop((0,y,z))
        # Closed top hatch: verifies even with the lectern entirely absent.
        rows.pop((0,64,0));rows[(0,65,0)]=partial('oak_trapdoor','half=top,open=false,waterlogged=false')
        return rows, dict(front=[0,64,0],floor=64,inward=1,depth=depth)

    def test_full_perimeter_and_closed_hatch_needs_no_resident_position(self):
        r,k=self.fixture();a=audit(r,**k);self.assertTrue(a['verified']);self.assertEqual(a['boundary_columns'][0]['maximum_open_height'],1.8125)

    def test_open_hatch_or_missing_rear_is_rejected(self):
        for change in ('open','rear'):
            r,k=self.fixture()
            if change=='open':r[(0,65,0)]=partial('oak_trapdoor','half=top,open=true,waterlogged=false')
            else:
                for y in range(64,67):r.pop((0,y,4))
            self.assertFalse(audit(r,**k)['verified'])

    def test_one_block_high_wire_gap_is_safe_but_two_block_gap_is_not(self):
        r,k=self.fixture();r[(-1,66,2)]=partial('redstone_wire','power=0');self.assertTrue(audit(r,**k)['verified'])
        r.pop((-1,65,2));self.assertFalse(audit(r,**k)['verified'])

    def test_top_slab_roof_and_nonfull_lower_boundary_use_strict_clearance(self):
        r,k=self.fixture();r[(0,67,2)]=partial('dark_oak_slab','type=top,waterlogged=false')
        r.pop((-1,64,2));self.assertTrue(audit(r,**k)['verified'])
        r.pop((-1,65,2));self.assertFalse(audit(r,**k)['verified'])

    def test_extended_bed_room_requires_the_full_explicit_depth(self):
        r,k=self.fixture(4);self.assertTrue(audit(r,**k)['verified']);r.pop((0,65,5));r.pop((0,66,5));self.assertFalse(audit(r,**k)['verified'])

    def test_missing_floor_unknown_or_wet_roof_cannot_pass(self):
        for mode in ('floor','unknown','wet'):
            r,k=self.fixture()
            if mode=='floor':r.pop((0,63,2))
            elif mode=='unknown':r[(0,67,2)]=partial('odd_shape','')
            else:r[(0,67,2)]['fluid']=True
            self.assertFalse(audit(r,**k)['verified'])

    def test_highest_roof_is_used_even_at_a_different_boundary_column(self):
        r,k=self.fixture();r[(0,67,1)]=partial('oak_slab','type=top,waterlogged=false')
        # A 1.5-high gap below the normal roof becomes 2.0 at the highest roof.
        r[(-1,65,2)]=partial('oak_slab','type=bottom,waterlogged=false');r.pop((-1,66,2));r.pop((-1,67,2))
        self.assertFalse(audit(r,**k)['verified'])

    def test_unknown_boundary_shape_does_not_count_as_a_blocker(self):
        r,k=self.fixture()
        for y in range(64,68):r[(-1,y,2)]=partial('unknown','variant=x')
        self.assertFalse(audit(r,**k)['verified'])

    def test_geometry_and_exact_adult_gap_boundary(self):
        self.assertEqual(maximum_gap([(1.9,3)],0,3),1.9)
        r,k=self.fixture()
        for key,value in [('depth',True),('depth',5),('floor',63),('inward',True)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):audit(r,**{**k,key:value})


class TwoColumnEnclosureTests(unittest.TestCase):
 def fixture(self):
  rows={(x,y,z):cube()for x in range(-1,3)for y in range(63,69)for z in range(5)}
  for x in (0,1):
   for z in (1,2,3):
    for y in (64,65,66):rows.pop((x,y,z))
   rows.pop((x,64,0));rows[x,65,0]=partial('oak_trapdoor','half=top,open=false,waterlogged=false')
  return rows,dict(front=[0,64,0],floor=64,inward=1,depth=3,x_offsets=(0,1))
 def test_shared_interior_is_not_invented_as_an_internal_wall(self):
  r,k=self.fixture();self.assertTrue(audit(r,**k)['verified']);self.assertFalse(audit(r,**{**k,'x_offsets':(0,)})['verified'])
 def test_second_column_floor_roof_and_boundary_are_all_required(self):
  for cell in [(1,63,2),(1,67,2)]:
   r,k=self.fixture();r.pop(cell);self.assertFalse(audit(r,**k)['verified'])
  for side in ([(1,y,4)for y in (64,65,66)],[(2,y,2)for y in (64,65,66)]):
   r,k=self.fixture()
   for p in side:r.pop(p)
   self.assertFalse(audit(r,**k)['verified'])
 def test_nonadjacent_boolean_or_unbounded_columns_are_rejected(self):
  for offsets in ((0,2),(False,1),(0,1,2),[0,1]):
   r,k=self.fixture()
   with self.assertRaises(ValueError):audit(r,**{**k,'x_offsets':offsets})

if __name__=='__main__':unittest.main()
