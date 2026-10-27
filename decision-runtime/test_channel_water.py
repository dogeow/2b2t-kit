import unittest,copy
from channel_water import request_for,confirmed,WATER
class ChannelTests(unittest.TestCase):
 def state(self):return dict(runtime_version='1.8.27',connected=True,health=20,food=20,screen='',manual_movement=False,guard_armed=True,guard_pve_only=True,guard_busy=False,phase='done',world_session='w',dimension='minecraft:overworld',player_uuid='p',control_revision=2,time=1000,pos=[0,67.2,0],hand=dict(item='minecraft:water_bucket',count=1),supervision_lease=dict(kind='materials',id='l',job_session='j',world_session='w'),inventory=[dict(slot=0,item='minecraft:water_bucket',count=1)])
 def test_only_two_actual_source_rows_are_admitted(self):
  s=self.state();r=request_for(s,[0,65,0],8,1,'Block{minecraft:water}[level=1]',1100,'test');self.assertEqual(r['row'],1);self.assertEqual(r['expires_at']-r['issued_at'],4000)
  for field,value in [('health',19),('manual_movement',True),('guard_busy',True),('runtime_version','1.8.25'),('dimension','minecraft:the_nether'),('world_session','other')]:
   bad=copy.deepcopy(s);bad[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):request_for(bad,[0,65,0],8,0,'Block{minecraft:air}',1100,'x')
  for length,row,state in [(9,0,'Block{minecraft:air}'),(8,2,'Block{minecraft:air}'),(8,0,WATER)]:
   with self.assertRaises(ValueError):request_for(s,[0,65,0],length,row,state,1100,'x')
 def test_exact_material_delta_and_prediction_free_source_are_both_required(self):
  before=self.state();after=copy.deepcopy(before);after['inventory']=[dict(slot=0,item='minecraft:bucket',count=1)];frame=dict(world_session='w',scan_total_cells=1,scan_cells_read=1,scan_predictions=dict(complete=True,pending_count=0,pending_positions=[]),blocks=[dict(pos=[0,65,0],state=WATER)])
  self.assertTrue(confirmed(before,after,frame,[0,65,0]))
  for bad in ['prediction','water','material','world','revision']:
   a=copy.deepcopy(after);f=copy.deepcopy(frame)
   if bad=='prediction':f['scan_predictions']['pending_count']=1
   if bad=='water':f['blocks'][0]['state']='Block{minecraft:water}[level=1]'
   if bad=='material':a['inventory']=[]
   if bad=='world':f['world_session']='old'
   if bad=='revision':a['control_revision']=3
   with self.subTest(bad=bad):self.assertFalse(confirmed(before,a,f,[0,65,0]))
if __name__=='__main__':unittest.main()
