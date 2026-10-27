import unittest
from dataclasses import replace
from test_librarian_reset_enclosure import ResetEnclosureTests
from librarian_room import LibrarianRoom
from librarian_reset_enclosure import require_enclosed_reset

class TwoColumnTests(unittest.TestCase):
 def fixture(self):
  scene,old=ResetEnclosureTests().fixture();room=replace(old,interior_x_offsets=(-1,0));rows={tuple(v['pos']):v for v in scene['blocks']}
  def full(p):rows[p]={'pos':list(p),'state':'Block{minecraft:cobblestone}','solid':True,'fluid':False,'block_entity':False}
  for z in (97,98,99):
   for y in (65,66,67):rows.pop((99,y,z));full((98,y,z))
   full((99,64,z));full((99,68,z))
  for y in (65,66,67):full((99,y,96));full((99,y,100))
  full((99,64,100));scene['blocks']=list(rows.values());box=scene['scan_entities'][0]['bounds'];box['min'][0]=99.2;box['max'][0]=99.8
  return scene,room
 def test_full_two_column_shell_contains_the_actual_adult(self):
  scene,room=self.fixture();self.assertEqual([-1,0],require_enclosed_reset(scene,room)['interior_x_offsets']);self.assertEqual(98,room.bounds()[0][0]);self.assertEqual(101,room.bounds()[1][0])
 def test_each_added_floor_roof_wall_and_front_column_is_required(self):
  for pos in ([99,64,98],[99,68,98],[98,66,98],[99,66,96],[99,66,100]):
   scene,room=self.fixture();scene['blocks']=[r for r in scene['blocks']if r['pos']!=pos]
   with self.subTest(pos=pos),self.assertRaises(ValueError):require_enclosed_reset(scene,room)
 def test_actor_cannot_extend_outside_added_column(self):
  scene,room=self.fixture();scene['scan_entities'][0]['bounds']['min'][0]=98.99
  with self.assertRaises(ValueError):require_enclosed_reset(scene,room)
 def test_wider_geometry_is_never_inferred_from_actor_or_blocks(self):
  scene,room=self.fixture()
  with self.assertRaises(ValueError):require_enclosed_reset(scene,replace(room,interior_x_offsets=(0,)))
 def test_noncontiguous_oversized_missing_workpoint_or_boolean_offsets_refused(self):
  for offsets in ((-2,-1,0),(-1,1),(1,),(0,True),(0,0),[0]):
   with self.subTest(offsets=offsets),self.assertRaises(ValueError):LibrarianRoom('v',(0,64,0),-1,interior_x_offsets=offsets)
 def test_slot_requires_explicit_bounded_integer_offsets(self):
  slot={'id':'WN10','occupant_uuid':'v','work_block':[760991,64,797802],'interior_x_offsets':[-1,0]};room=LibrarianRoom.from_slot(slot);self.assertEqual((-1,0),room.interior_x_offsets)
  for offsets in ([-2,0],[0,True],None):
   with self.assertRaises(ValueError):LibrarianRoom.from_slot(dict(slot,interior_x_offsets=offsets))
if __name__=='__main__':unittest.main()

class SleepingStructureTests(unittest.TestCase):
 def test_structure_read_does_not_admit_sleeping_body_for_reset(self):
  from librarian_reset_enclosure import require_reset_shell
  scene,room=TwoColumnTests().fixture();scene['scan_entities'][0]['bounds']['max'][1]=scene['scan_entities'][0]['bounds']['min'][1]+.2
  self.assertEqual([99,100],require_reset_shell(scene,room)['columns'])
  with self.assertRaises(ValueError):require_enclosed_reset(scene,room)
