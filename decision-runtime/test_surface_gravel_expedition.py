import unittest

from surface_gravel_expedition import route_for_targets, candidates,search_tiles,frontier_tiles,best_surface_layer,expedition


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
        self.assertEqual((61,63),best_surface_layer([[1,62,1],[2,63,2],[3,75,3]]))
        self.assertEqual(2,len(search_tiles([0,0,31,15],[58,118])))
        with self.assertRaises(ValueError):search_tiles([0,0,999,999],[58,88])

    def test_fully_visited_tile_is_skipped_before_any_game_movement(self):
        class Client:
            def status(self):
                return {'pos':[100.5,95,200.5],'health':20,'inventory':[]}
            def request(self,*args,**kwargs):
                raise AssertionError('Visited tile must not issue game movement or scan')
        class Ledger:
            def covered(self,*args):return True
        result=expedition(Client(),[([0,58,0],[15,88,15])],8,95,'/tmp/unused',
                          search=True,ledger=Ledger())
        self.assertEqual(1,len(result['skipped_visited']))
        self.assertEqual([],result['regions'])

    def test_out_of_scope_tile_is_skipped_before_native_target_rejection(self):
        class Client:
            anchor=[0,95,0]
            def status(self):return {'pos':[0,95,0],'health':20,'inventory':[]}
            def request(self,*args,**kwargs):raise AssertionError('No request outside worksite')
        result=expedition(Client(),[([500,58,500],[515,88,515])],1,95,'/tmp/unused',search=True)
        self.assertEqual(1,len(result['skipped_out_of_scope']))
        self.assertEqual([],result['regions'])

    def test_frontier_selects_new_tiles_without_revisiting_recorded_tile(self):
        class Ledger:
            def covered(self,low,high,buffer):return low[0]==-96 and low[2]==-96
        tiles=frontier_tiles([0,0],[58,88],96,128,3,Ledger())
        self.assertEqual(3,len(tiles))
        self.assertEqual([-80,58,-96],tiles[0][0])
        self.assertEqual([-64,58,-96],tiles[1][0])
        self.assertNotIn([-96,58,-96],[low for low,high in tiles])
        bounded=frontier_tiles([0,0],[58,88],96,512,32,Ledger(),[0,95,0])
        self.assertTrue(all(((low[0]+8)**2+(low[2]+8)**2)**.5<=480 for low,high in bounded))


if __name__=='__main__':unittest.main()
