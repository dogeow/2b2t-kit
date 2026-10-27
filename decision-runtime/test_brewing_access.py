import unittest
from copy import deepcopy
from brewing_access import admitted
class BrewingAdmissionTest(unittest.TestCase):
 def setUp(self):self.s=dict(connected=True,world_session='w',control_revision=2,supervision_lease=dict(kind='materials',world_session='w',job_session='t',revision=2),health=20,manual_movement=False,screen='',menu=dict(type='InventoryMenu',id=0,cursor=dict(count=0)),pos=[1.5,64,2.5],velocity=[0,0,0],on_ground=True,guard_armed=True,guard_pve_only=True,under_water=False)
 def ok(self):return admitted(self.s,'w','t',2,[1.5,64,2.5])
 def test_healthy_exact_owner(self):self.assertTrue(self.ok())
 def test_reject_handoff_movement_injury_and_foreign_ui(self):
  for key,value in [('manual_movement',True),('screen','InventoryScreen'),('health',19),('world_session','other'),('velocity',[.1,0,0]),('pos',[4,64,2])]:
   with self.subTest(key=key):
    old=deepcopy(self.s);self.s[key]=value;self.assertFalse(self.ok());self.s=old
 def test_reject_nonfinite_pose(self):self.s['pos']=[float('nan'),64,2];self.assertFalse(self.ok())

 def test_stationary_native_gravity_is_not_horizontal_movement(self):
  self.s.update(velocity=[0,-.0784,0],on_ground=False,flight=True,air_only_navigation_protocol=2);self.assertTrue(self.ok())
  self.s['velocity']=[0,-.2,0];self.assertFalse(self.ok())
