import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from goal_workflow import open_workbench

class Client:
 def __init__(self,out,replies):self.out=out;self.replies=list(replies);self.calls=[];self.open=False;self.owned_material_menu=None
 def status(self):return {'menu':{'type':'CraftingMenu'if self.open else'InventoryMenu','id':9 if self.open else 0}}
 def request(self,op,**args):
  self.calls.append((op,args))
  if op=='scan':return {'blocks':[{'pos':[1,64,2],'state':'Block{minecraft:crafting_table}'}]}
  if op=='approach_block':return self.replies.pop(0)
  if op=='interact':self.open=True;return {'phase':'done'}
  raise AssertionError(op)
 def checked(self,op,**args):
  r=self.request(op,**args)
  if r.get('phase')!='done':raise RuntimeError(r.get('detail'))
  return r

class WorkbenchAlternativeFacesTest(unittest.TestCase):
 def test_known_blocked_top_uses_one_verified_side_interaction(self):
  with tempfile.TemporaryDirectory()as t:
   c=Client(Path(t),[{'phase':'waiting','detail':'Depot approach occluded or out of reach'},{'phase':'done'}])
   with patch('goal_workflow.select_container_hand',return_value='minecraft:cooked_beef'):open_workbench(c,[1,64,2])
   self.assertEqual(['up','north'],[a['face']for op,a in c.calls if op=='approach_block'])
   self.assertEqual(['north'],[a['face']for op,a in c.calls if op=='interact']);self.assertEqual(9,c.owned_material_menu)
 def test_unknown_navigation_never_tries_another_pose_or_interacts(self):
  with tempfile.TemporaryDirectory()as t:
   c=Client(Path(t),[{'phase':'waiting','detail':'unknown acknowledgement'}])
   with self.assertRaisesRegex(RuntimeError,'unknown acknowledgement'):open_workbench(c,[1,64,2])
   self.assertEqual(1,sum(op=='approach_block'for op,_ in c.calls));self.assertFalse(any(op=='interact'for op,_ in c.calls))
 def test_already_reachable_top_keeps_the_single_normal_interaction(self):
  with tempfile.TemporaryDirectory()as t:
   c=Client(Path(t),[{'phase':'done'}])
   with patch('goal_workflow.select_container_hand',return_value='minecraft:cooked_beef'):open_workbench(c,[1,64,2])
   self.assertEqual(['up'],[a['face']for op,a in c.calls if op=='interact'])
if __name__=='__main__':unittest.main()
