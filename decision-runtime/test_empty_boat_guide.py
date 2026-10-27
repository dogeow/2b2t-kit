import unittest
from empty_boat_guide import eligible,harmless_contact,next_empty
import math
class Tests(unittest.TestCase):
 def test_empty_receiver_can_descend_faster_without_stretching_the_leash(self):
  here=[760756.5,90,798022.5];boat=[760756.5,84,798022.5]
  down=next_empty(here,[here[0],75.1,here[2]],boat)
  self.assertEqual(down[1],87);self.assertLessEqual(math.dist(down,boat),8.5)
  for offset in [3,5.1,6,7.5,8.4]:
   boat=[here[0],here[1]-offset,here[2]];p=next_empty(here,[here[0],110,here[2]],boat)
   self.assertLessEqual(math.dist(p,boat),8.500001);self.assertLessEqual(math.dist(p,here),3)
  with self.assertRaises(RuntimeError):next_empty(here,[here[0],110,here[2]],[here[0],81.3,here[2]])
 def test_empty_ground_contact_does_not_admit_fire_or_portals(self):
  self.assertTrue(harmless_contact([dict(state='Block{minecraft:grass_block}[snowy=false]')]))
  for name in ['fire','lava','nether_portal','cactus','magma_block']:
   self.assertFalse(harmless_contact([dict(state='Block{minecraft:'+name+'}')]))
 def test_only_a_current_healthy_player_and_exact_empty_resolved_boat_qualify(self):
  s=dict(health=20,food=20,connected=True,manual_movement=False,guard_armed=True,guard_pve_only=True,player_uuid='p');b=dict(alive=True,passengers=[],leashed=True,leash_resolved=True,leash_holder=dict(uuid='p'),type='minecraft:oak_boat');self.assertTrue(eligible(s,b))
  for edit in [dict(passengers=[{'uuid':'new'}]),dict(leash_resolved=False),dict(leash_holder=dict(uuid='other')),dict(alive=False),dict(type='minecraft:oak_chest_boat')]:self.assertFalse(eligible(s,dict(b,**edit)))
  for edit in [dict(health=19),dict(manual_movement=True),dict(guard_pve_only=False),dict(screen='InventoryScreen')]:self.assertFalse(eligible(dict(s,**edit),b))
