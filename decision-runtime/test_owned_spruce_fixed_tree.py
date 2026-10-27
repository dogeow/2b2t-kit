import unittest
from material_jobs.acquisition import fixed_tree_params


class OwnedSpruceTargetTest(unittest.TestCase):
    def test_owned_spruce_uses_its_registered_root_and_bounds_instead_of_nearest_tree_mode(self):
        root=[760963,64,797812]
        region={'item':'minecraft:spruce_log','min':[760960,64,797809],
                'max':[760966,80,797815],'root':root,'source':'owned_seeded_spruce_tree_farm'}
        params=fixed_tree_params({'fixed_tree_chop_protocol':1},region,root)
        self.assertEqual(root,params['tree_root']);self.assertEqual(region['min'],params['tree_min'])
        self.assertEqual(region['max'],params['tree_max'])
        self.assertEqual({},fixed_tree_params({'fixed_tree_chop_protocol':0},region,root))
