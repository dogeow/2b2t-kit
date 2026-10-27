import unittest
from village_station_room import south_relocation, south_installation

class StationRoomTest(unittest.TestCase):
 def slot(self,x=761006):
  return dict(occupant_uuid='own-resident',profession='shepherd',bed_foot=[x,64,797796],bed_head=[x,64,797797],work_block=[x,64,797794])
 def test_each_station_uses_its_own_x_and_scanned_resident(self):
  for x in [761000,761006,761010]:
   with self.subTest(x=x):
    r=south_relocation(self.slot(x));self.assertEqual(r['new'],[x,64,797795]);self.assertEqual(r['scan_min'][0],x-1);self.assertEqual(r['scan_max'][0],x+1);self.assertEqual(r['public_roof'],[x,67,797793]);self.assertEqual(r['private_roof'],[x,67,797796]);self.assertEqual(r['occupant_uuid'],'own-resident')
 def test_moved_or_north_or_ambiguous_stall_is_not_mined(self):
  for change in [{'work_block':[761006,64,797795]},{'bed_head':[761006,64,797795]},{'occupant_uuid':''},{'work_block':[761010,64,797794]},{'bed_foot':[761006,64.0,797796]}]:
   s=self.slot();s.update(change)
   with self.subTest(change=change),self.assertRaises(ValueError):south_relocation(s)
 def test_container_profession_is_rejected(self):
  s=self.slot();s['profession']='fisherman'
  with self.assertRaises(ValueError):south_relocation(s)
 def test_container_installation_requires_preserving_the_original(self):
  for profession,item in [('butcher','minecraft:smoker'),('fisherman','minecraft:barrel')]:
   s=self.slot();s['profession']=profession;r=south_installation(s);self.assertTrue(r['preserve_original_workstation']);self.assertEqual(r['item'],item);self.assertEqual(r['new'],[761006,64,797795])
   with self.assertRaises(ValueError):south_relocation(s)
 def test_bed_refit_does_not_make_an_installed_station_look_original(self):
  s=self.slot();s.update(profession='fisherman',original_container_preserved=True,work_block=[761006,64,797795],bed_foot=[761006,64,797797],bed_head=[761006,64,797798])
  with self.assertRaises(ValueError):south_installation(s)
  s['profession']='shepherd';s['closer_station_experiment']=True
  with self.assertRaises(ValueError):south_relocation(s)
if __name__=='__main__':unittest.main()
