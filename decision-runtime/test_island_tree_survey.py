import unittest
from island_tree_survey import centers,current_survey

class IslandTreeCoverageTests(unittest.TestCase):
    def test_declared_base_area_has_no_gap_between_survey_squares(self):
        low=[760850,797600];high=[761200,798020];points=centers(low,high)
        self.assertEqual(6,len(points))
        for x in range(low[0],high[0]+1):
            for z in range(low[1],high[1]+1):
                self.assertTrue(any(abs(x-a)<=96 and abs(z-b)<=96 for a,b in points))

    def test_small_area_uses_its_actual_center(self):
        self.assertEqual([[10,10]],centers([0,0],[20,20]))

    def test_oversized_or_invalid_bounds_are_rejected_before_any_client(self):
        for low,high in (([0,0],[513,10]),([0.,0],[10,10]),([10,0],[0,10])):
            with self.assertRaises(ValueError):centers(low,high)

    def test_current_native_read_omits_phase_but_has_exact_complete_observation(self):
        reply={'id':'read','world_session':'world','pos':[10.5,100,20.5],
               'tree_survey':{'loaded_columns':37249,'unloaded_columns':0,'trees':[]}}
        self.assertEqual([],current_survey(reply,'world','read',[10,20])['trees'])
        for changes in ({'id':'other'},{'world_session':'old'},{'phase':'error'},
                        {'pos':[11.5,100,20.5]},
                        {'tree_survey':{'loaded_columns':37248,'unloaded_columns':1,'trees':[]}}):
            with self.subTest(changes=changes),self.assertRaises(RuntimeError):
                current_survey({**reply,**changes},'world','read',[10,20])

if __name__=='__main__':unittest.main()
