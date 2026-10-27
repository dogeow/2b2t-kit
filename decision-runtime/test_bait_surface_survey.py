import math,unittest
from bait_surface_survey import BOAT_POSITION,WATCH_POSITION,scan_tiles,eligible,inland_tiles,deep_inland_tiles
from native_scan_bounds import validate
class BaitSurfaceSurveyTests(unittest.TestCase):
 def test_air_watch_is_outside_spawn_exclusion_and_within_observed_boat_tracking_distance(self):
  distance=math.dist(BOAT_POSITION,WATCH_POSITION);self.assertGreater(distance,24);self.assertLess(distance,32);self.assertGreater(WATCH_POSITION[1],BOAT_POSITION[1]+10)
 def test_tiles_fit_native_limit_and_cover_disjoint_shore_water_volume(self):
  tiles=scan_tiles();self.assertEqual(len(tiles),4);total=0
  for low,high in tiles:
   validate(low,high);volume=math.prod(b-a+1 for a,b in zip(low,high));self.assertLessEqual(volume,32768);total+=volume
  self.assertEqual(total,49*29*53)
  for i,(lo,hi)in enumerate(tiles):
   for lo2,hi2 in tiles[i+1:]:self.assertTrue(any(hi[d]<lo2[d]or hi2[d]<lo[d]for d in range(3)))
 def test_inland_bank_and_cave_tiles_are_disjoint_and_native_bounded(self):
  tiles=inland_tiles();self.assertEqual(8,len(tiles));self.assertEqual(42*42*61,sum(math.prod(b-a+1 for a,b in zip(lo,hi))for lo,hi in tiles))
  for i,(lo,hi)in enumerate(tiles):
   validate(lo,hi)
   for lo2,hi2 in tiles[i+1:]:self.assertTrue(any(hi[d]<lo2[d]or hi2[d]<lo[d]for d in range(3)))
 def test_deep_tiles_reach_below_shallow_survey_without_exceeding_native_limit(self):
  tiles=deep_inland_tiles();self.assertEqual(8,len(tiles));self.assertEqual(42*42*80,sum(math.prod(b-a+1 for a,b in zip(lo,hi))for lo,hi in tiles))
  for lo,hi in tiles:validate(lo,hi);self.assertLessEqual(hi[1],19);self.assertGreaterEqual(lo[1],-60)
 def test_both_supported_adult_bait_types_qualify_but_nobody_else_does(self):
  row=dict(uuid='v',type='minecraft:zombie',alive=True,health=20,is_baby=False,has_custom_name=False);self.assertTrue(eligible(row));self.assertTrue(eligible({**row,'type':'minecraft:drowned'}))
  for changed in [{'type':'minecraft:zombified_piglin'},{'type':'minecraft:creeper'},{'is_baby':True},{'health':19},{'has_custom_name':True},{'alive':False},{'uuid':''}]:self.assertFalse(eligible({**row,**changed}))
if __name__=='__main__':unittest.main()
