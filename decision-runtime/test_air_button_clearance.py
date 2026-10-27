import unittest
from types import SimpleNamespace
from material_jobs.navigation import _air_scan
from material_jobs.local_air_path import plan
from material_jobs.protocol import JobBlocked
class ButtonClearanceTests(unittest.TestCase):
 def route(self,name,**changes):
  row=dict(pos=[0,65,0],state='Block{minecraft:'+name+'}',passable=True,fluid=False,block_entity=False);row.update(changes)
  c=SimpleNamespace(world='w',request=lambda *args,**kwargs:dict(world_session='w',phase='done',blocks=[row]))
  return plan(_air_scan(c,[0,64,0],[0,66,0]),[.5,64,.5],[.5,64.1875,.5],[0,64,0],[0,66,0],foot_offset=.1)
 def test_button_in_real_two_high_corridor_does_not_block_the_return_route(self):
  for name in ['cherry_button','stone_button','polished_blackstone_button','oak_button']:
   with self.subTest(name=name):self.assertTrue(self.route(name))
 def test_hazards_and_unknown_blocks_do_not_become_air(self):
  for name in ['fire','campfire','wither_rose','cactus','unknown_button','stone']:
   with self.subTest(name=name),self.assertRaises(JobBlocked):self.route(name)
 def test_button_requires_all_safe_flags(self):
  for fields in [dict(passable=False),dict(fluid=True),dict(block_entity=True)]:
   with self.subTest(fields=fields),self.assertRaises(JobBlocked):self.route('cherry_button',**fields)
if __name__=='__main__':unittest.main()
