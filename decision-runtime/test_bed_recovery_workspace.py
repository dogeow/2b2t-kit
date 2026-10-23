import unittest
from bed_recovery_workspace import recovery_space_ready
class Tests(unittest.TestCase):
    def state(self,free=0):
        return {'inventory':[{'slot':i,'count':0 if i<free else 1}for i in range(36)]}
    def test_one_slot_cannot_cover_bed_then_roof(self):self.assertFalse(recovery_space_ready(self.state(1)))
    def test_two_slots_are_enough(self):self.assertTrue(recovery_space_ready(self.state(2)))
    def test_empty_armor_slots_do_not_cover_carry_space(self):
        s=self.state(1);s['inventory'] += [{'slot':36,'count':0},{'slot':37,'count':0}];self.assertFalse(recovery_space_ready(s))
    def test_missing_or_duplicate_slots_fail_closed(self):
        self.assertFalse(recovery_space_ready({'inventory':[{'slot':0,'count':0}]*36}));s=self.state(2);s['inventory'].pop();self.assertFalse(recovery_space_ready(s))
    def test_malformed_counts_do_not_grant_capacity(self):
        for value in [None,-1,False,'0']:
            s=self.state(2);s['inventory'][0]['count']=value
            with self.subTest(value=value):self.assertFalse(recovery_space_ready(s))
    def test_inspection_does_not_change_inventory(self):
        import copy
        s=self.state(2);before=copy.deepcopy(s);recovery_space_ready(s);self.assertEqual(before,s)

class RoofCapacityTests(unittest.TestCase):
    def state(self):
        return {'inventory':[{'slot':i,'item':'minecraft:stone','count':64,'max_stack':64}for i in range(36)]}
    def test_full_bag_cannot_receive_original_roof(self):
        from bed_recovery_workspace import plain_recovery_space_ready
        self.assertFalse(plain_recovery_space_ready(self.state(),'minecraft:dark_oak_planks'))
    def test_one_empty_slot_receives_one_roof_block(self):
        from bed_recovery_workspace import plain_recovery_space_ready
        s=self.state();s['inventory'][0]['count']=0;self.assertTrue(plain_recovery_space_ready(s,'minecraft:dark_oak_planks'))
    def test_only_plain_matching_nonfull_stack_counts(self):
        from bed_recovery_workspace import plain_recovery_space_ready
        s=self.state();s['inventory'][0].update(item='minecraft:dark_oak_planks',count=63)
        self.assertTrue(plain_recovery_space_ready(s,'minecraft:dark_oak_planks'))
        s['inventory'][0]['count']=64;self.assertFalse(plain_recovery_space_ready(s,'minecraft:dark_oak_planks'))
        s['inventory'][0].update(count=63,custom_name='named');self.assertFalse(plain_recovery_space_ready(s,'minecraft:dark_oak_planks'))
    def test_unknown_capacity_and_incomplete_rows_fail_closed(self):
        from bed_recovery_workspace import plain_recovery_space_ready
        s=self.state();s['inventory'][0].update(item='minecraft:dark_oak_planks',count=1);s['inventory'][0].pop('max_stack');self.assertFalse(plain_recovery_space_ready(s,'minecraft:dark_oak_planks'))
        s['inventory'].pop();self.assertFalse(plain_recovery_space_ready(s,'minecraft:dark_oak_planks'))
