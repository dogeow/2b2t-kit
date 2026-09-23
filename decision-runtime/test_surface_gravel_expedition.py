import unittest

from surface_gravel_expedition import route_for_targets, candidates,search_tiles,best_surface_layer


class SurfaceGravelExpeditionTest(unittest.TestCase):
    def test_only_gravel_uses_surface_route(self):
        self.assertEqual('surface',route_for_targets('GRAVEL'))
        self.assertEqual('underground',route_for_targets('GRAVEL,IRON'))
        self.assertEqual('underground',route_for_targets('ANY'))
        self.assertEqual('underground',route_for_targets(''))

    def test_surface_survey_rejects_waterlogged_gravel_neighbors(self):
        block={'pos':[10,63,20],'state':'Block{minecraft:gravel}'}
        waterlogged={'pos':[11,63,20],'state':'Block{minecraft:seagrass}','fluid':True}
        self.assertEqual([[10,63,20]],candidates([block],[10,63,20],[10,63,20]))
        self.assertEqual([],candidates([block,waterlogged],[10,63,20],[10,63,20]))
        waterlogged['pos']=[13,63,20]
        self.assertEqual([],candidates([block,waterlogged],[10,63,20],[10,63,20]))

    def test_search_tiles_are_bounded_and_choose_the_densest_surface_layer(self):
        tiles=search_tiles([0,0,31,15],[58,88])
        self.assertEqual(2,len(tiles))
        self.assertEqual(([0,58,0],[15,88,15]),tiles[0])
        self.assertEqual((62,64),best_surface_layer([[1,62,1],[2,63,2],[3,75,3]]))
        with self.assertRaises(ValueError):search_tiles([0,0,999,999],[58,88])


if __name__=='__main__':unittest.main()
