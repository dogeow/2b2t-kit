import unittest
from goal_workflow import open_workbench,subset_matches,build_phase,station_target


class Client:
    def __init__(self, approach_fails=False):
        self.calls=[];self.opened=False;self.approach_fails=approach_fails
    def status(self):
        return {'inventory':[{'item':'minecraft:diamond_sword','count':1}],
                'menu':{'type':'CraftingMenu' if self.opened else 'InventoryMenu'}}
    def fetch(self,*args):self.calls.append('near_depot');return {'phase':'done'}
    def request(self,op,**args):
        self.calls.append(op);return {'blocks':[{'state':'Block{minecraft:crafting_table}'}]}
    def checked(self,op,**args):
        self.calls.append(op)
        if op=='approach_block' and self.approach_fails:raise RuntimeError('No clear path')
        if op=='interact':self.opened=True


class WorkbenchTests(unittest.TestCase):
    def test_station_reposition_uses_only_three_verified_integer_coordinates(self):
        self.assertEqual([760816.5,87.02,797764.5],station_target('760816, 87, 797764'))
        self.assertIsNone(station_target('760816, 87'))
        self.assertIsNone(station_target('untrusted station'))
    def test_background_construction_refuses_to_wait_on_ignored_movement_keys(self):
        class Background:
            def status(self):return {'projection_selection':{'key':'selected'},'window_active':False}
        with self.assertRaisesRegex(RuntimeError,'foreground'):
            build_phase(Background(),'selected')
    def test_subset_needs_every_exact_block_state_and_is_not_whole_goal_success(self):
        targets=[{'pos':[1,2,3],'expected':'Block{minecraft:stone_bricks}'},
                 {'pos':[2,2,3],'expected':'Block{minecraft:ladder}[facing=east]'}]
        self.assertFalse(subset_matches([{'pos':[1,2,3],'state':'Block{minecraft:stone_bricks}'}],targets))
        observed=[{'pos':r['pos'],'state':r['expected']} for r in targets]
        self.assertTrue(subset_matches(observed,targets))
        observed[-1]['state']='Block{minecraft:ladder}[facing=west]'
        self.assertFalse(subset_matches(observed,targets));self.assertFalse(subset_matches([],[]))
    def test_nearby_depot_does_not_substitute_for_actual_workbench_reach(self):
        c=Client();open_workbench(c,[10,65,20],[7,65,17])
        self.assertEqual(c.calls,['near_depot','scan','approach_block','select_item','interact'])
        self.assertTrue(c.opened)
    def test_failed_approach_never_attempts_interaction(self):
        c=Client(approach_fails=True)
        with self.assertRaises(RuntimeError):open_workbench(c,[10,65,20])
        self.assertNotIn('interact',c.calls)
        self.assertFalse(c.opened)

if __name__=='__main__':unittest.main()
