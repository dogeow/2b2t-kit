import unittest
from material_stack_consolidation import offer


class ConsolidationTest(unittest.TestCase):
    def test_fragmented_plain_target_preserves_total_and_frees_two_real_slots(self):
        rows=[{'slot':i,'item':'minecraft:stone','count':64,'max_stack':64}for i in range(36)]
        for i in (2,5,9):rows[i].update(item='minecraft:mud_bricks',count=2)
        rows[-1].update(item='minecraft:air',count=0)
        state={'inventory':rows}
        self.assertEqual(offer(state,'minecraft:mud_bricks',3),{'total':6,'before_stacks':3,'freed_slots':2})
        rows[2]['custom_name']='protected'
        self.assertIsNone(offer(state,'minecraft:mud_bricks',3))

    def test_already_sufficient_workspace_or_full_stacks_do_not_visit_depot(self):
        rows=[{'slot':i,'item':'minecraft:stone','count':64,'max_stack':64}for i in range(36)]
        rows[2].update(item='minecraft:mud_bricks',count=64);rows[5].update(item='minecraft:mud_bricks',count=64)
        rows[-1].update(item='minecraft:air',count=0)
        self.assertIsNone(offer({'inventory':rows},'minecraft:mud_bricks',3))
        for r in rows[-3:]:r.update(item='minecraft:air',count=0)
        self.assertIsNone(offer({'inventory':rows},'minecraft:mud_bricks',3))


if __name__=='__main__':unittest.main()
