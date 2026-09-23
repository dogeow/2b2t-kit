import unittest

from surface_gravel_expedition import route_for_targets, candidates


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


if __name__=='__main__':unittest.main()
