from copy import deepcopy
import unittest
from projection_patch_plan import connected_mask


class ConnectedPatchTests(unittest.TestCase):
    def test_one_actual_anchor_covers_dense_patch_in_one_mask(self):
        missing={(x,64,z) for x in range(4) for z in range(4)}
        correct={(-1,64,0)}
        result=connected_mask(missing,correct,[0,64,0],[3,64,3],16)
        self.assertEqual(missing,set(result))
        observed=set(correct)
        for x,y,z in result:
            self.assertTrue(any(p in observed for p in ((x-1,y,z),(x+1,y,z),(x,y,z-1),(x,y,z+1))))
            observed.add((x,y,z))

    def test_every_stock_prefix_keeps_a_supported_root_and_dependency_chain(self):
        missing={(x,64,0) for x in range(4)}
        for budget in range(1,5):
            result=connected_mask(missing,{(-1,64,0)},[0,64,0],[3,64,3],budget)
            self.assertEqual([(x,64,0) for x in range(budget)],result)

    def test_isolated_targets_and_paths_outside_patch_are_not_proposals(self):
        missing={(0,64,0),(2,64,0),(3,64,0),(4,64,0)}
        self.assertEqual([(0,64,0)],connected_mask(missing,{(-1,64,0),(5,64,0)},[0,64,0],[3,64,3],16))

    def test_pending_target_cannot_be_a_future_bridge(self):
        missing={(x,64,0) for x in range(4)}
        self.assertEqual([(0,64,0)],connected_mask(missing,{(-1,64,0)},[0,64,0],[3,64,3],16,excluded=[(1,64,0)]))

    def test_actual_matching_pending_target_may_support_without_replay(self):
        p=(0,64,0)
        self.assertEqual([(1,64,0)],connected_mask({(1,64,0)}, {p},[0,64,0],[3,64,3],16,excluded=[p]))

    def test_no_actual_support_means_no_mask(self):
        self.assertEqual([],connected_mask({(0,64,0)},set(),[0,64,0],[3,64,3],16))

    def test_planning_preserves_inputs(self):
        missing=[[0,64,0],[1,64,0]];correct=[[-1,64,0]];old=deepcopy((missing,correct))
        connected_mask(missing,correct,[0,64,0],[3,64,3],16)
        self.assertEqual(old,(missing,correct))

    def test_unknown_coordinates_and_unbounded_patch_are_rejected(self):
        cases=[([(0,True,0)],[0,64,0],[3,64,3],16),([(0,64,0)],[0,64,0],[4,64,3],16),
               ([(0,64,0)],[0,64,0],[3,64,3],True),([(0,64,0)],[0,64,0],[3,65,3],16)]
        for missing,low,high,budget in cases:
            with self.assertRaises(ValueError):connected_mask(missing,set(),low,high,budget)
        with self.assertRaises(ValueError):connected_mask({(0,64,0)},{(0,64,0)},[0,64,0],[3,64,3],16)


if __name__=='__main__':unittest.main()
