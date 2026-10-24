from copy import deepcopy
import unittest
from merchant_repair_hand import selected_tool,retained


class RepairHandTests(unittest.TestCase):
    def state(self):
        row={'slot':5,'item':'minecraft:diamond_pickaxe','count':1,'durability':411,'max_durability':1561,
             'enchantments':[{'id':'minecraft:mending','level':1},{'id':'minecraft:efficiency','level':5}]}
        return {'selected_slot':5,'hand':deepcopy(row),'inventory':[row]}
    def test_exact_selected_damaged_tool_and_natural_repair_can_be_preserved(self):
        state=self.state();preferred=selected_tool(state);self.assertEqual(preferred['slot'],5)
        state['hand']['durability']=1561;self.assertTrue(retained(state,preferred))
    def test_missing_mending_wrong_slot_full_or_changed_tool_never_gets_preference(self):
        for change in ('full','slot','book','different'):
            state=self.state()
            if change=='full':state['hand']['durability']=1561
            elif change=='slot':state['selected_slot']=1
            elif change=='book':state['hand']['enchantments']=[]
            elif change=='different':state['inventory'][0]['durability']=400
            with self.subTest(change=change):self.assertIsNone(selected_tool(state))


if __name__=='__main__':unittest.main()
