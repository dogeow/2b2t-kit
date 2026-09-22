import copy
import unittest
from unittest.mock import patch
from craft_recovery import clear_owned_workbench

class Client:
 owned_material_menu=5
 def __init__(self):
  self.calls=[];self.pending=None
  slots=[{'slot':i,'item':'minecraft:air','count':0} for i in range(46)]
  slots[1].update(item='minecraft:iron_ingot',count=5)
  self.s={'menu':{'id':5,'type':'CraftingMenu','cursor':{'item':'minecraft:iron_nugget','count':16},'slots':slots}}
 def status(self):
  if self.pending:
   p=self.pending;self.pending=None;m=self.s['menu']
   if p['kind']=='pickup':m['slots'][p['slot']].update(m['cursor']);m['cursor']={'item':'minecraft:air','count':0}
   else:m['slots'][p['slot']].update(item='minecraft:air',count=0)
  return copy.deepcopy(self.s)
 def checked(self,op,**args):self.calls.append(args);self.pending=args;return copy.deepcopy(self.s)

class Tests(unittest.TestCase):
 def test_failed_crafting_returns_cursor_and_grid_before_release(self):
  c=Client()
  with patch('craft_recovery.time.sleep'):self.assertTrue(clear_owned_workbench(c))
  self.assertEqual([a['kind'] for a in c.calls],['pickup','quick_move'])
  self.assertEqual(c.s['menu']['slots'][10]['count'],16)
  self.assertEqual(c.s['menu']['cursor']['count'],0)
 def test_different_menu_is_never_changed(self):
  c=Client();c.s['menu']['id']=6
  self.assertFalse(clear_owned_workbench(c));self.assertEqual(c.calls,[])
 def test_full_inventory_never_drops_cursor(self):
  c=Client()
  for slot in c.s['menu']['slots'][-36:]:slot.update(item='minecraft:stone',count=64)
  with self.assertRaises(RuntimeError):clear_owned_workbench(c)
  self.assertEqual(c.calls,[])
if __name__=='__main__':unittest.main()
