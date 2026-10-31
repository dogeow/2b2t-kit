import unittest
from material_jobs.stationary_approach import eligible_reply,stationary_owner,dry_body,DRIFT
class StationaryApproachTest(unittest.TestCase):
 def state(self):
  return dict(connected=True,world_session='w',control_revision=7,health=20,recent_hurt_at=1,safety_hold={'active':False},screen='',manual_movement=False,guard_armed=True,guard_pve_only=True,guard_busy=False,flight=True,under_water=False,air_supply=300,navigating=False,native_material_busy=False,pending_scan=None,movement_keys={'forward':False,'jump':False},pos=[10.6,63.43125,20.5],velocity=[0,-.0784,0],supervision_lease=dict(kind='materials',job_session='t',id='l',world_session='w',revision=7))
 def valid(self,s):return stationary_owner(s,[10.5,63.4,20.5],'w','t','l',7,1)
 def test_only_known_no_injury_drift_terminal(self):
  r=dict(phase='stopped',detail=DRIFT,world_session='w',id='r',material_air_navigation={'injury_interrupted':False});self.assertTrue(eligible_reply(r,'w'))
  for patch in [dict(detail='脚本世界或人物状态已变化'),dict(phase='waiting'),dict(world_session='other'),dict(material_air_navigation={'injury_interrupted':True})]:self.assertFalse(eligible_reply(r|patch,'w'))
 def test_actual_nearby_stationary_pose(self):self.assertTrue(self.valid(self.state()))
 def test_manual_health_water_and_protection_changes(self):
  for key,value in [('connected',False),('health',19.9),('recent_hurt_at',2),('manual_movement',True),('guard_busy',True),('guard_armed',False),('guard_pve_only',False),('flight',False),('screen','ChatScreen'),('control_revision',8),('navigating',True),('native_material_busy',True),('pending_scan',{'id':1}),('safety_hold',{'active':True}),('movement_keys',{'jump':True}),('under_water',True),('air_supply',200)]:
   with self.subTest(key=key):s=self.state();s[key]=value;self.assertFalse(self.valid(s))
 def test_foreign_lease(self):
  for key,value in [('id','other'),('job_session','other'),('world_session','other'),('kind','parking'),('revision',8)]:s=self.state();s['supervision_lease'][key]=value;self.assertFalse(self.valid(s))
 def test_moving_far_and_nonfinite(self):
  for key,value in [('pos',[11.3,63.4,20.5]),('pos',[10.5,63.7,20.5]),('velocity',[.02,0,0]),('velocity',[0,.11,0]),('pos',[float('nan'),63.4,20.5])]:s=self.state();s[key]=value;self.assertFalse(self.valid(s))
 def test_fresh_body_requires_air_or_actual_dry_ceiling_clearance(self):
  self.assertTrue(dry_body({'blocks':[]},[10.5,63.4,20.5]));row={'pos':[10,65,20],'state':'Block{minecraft:cobblestone_slab}[type=top,waterlogged=false]'}
  self.assertTrue(dry_body({'blocks':[row]},[10.5,63.4,20.5]));self.assertFalse(dry_body({'blocks':[row]},[10.5,63.8,20.5]))
  for state in ['Block{minecraft:water}[level=1]','Block{minecraft:cobblestone}','Block{minecraft:cobblestone_slab}[type=top,waterlogged=true]']:self.assertFalse(dry_body({'blocks':[row|{'state':state}]},[10.5,63.4,20.5]))
 def test_three_read_only_frames_keep_the_original_failure_and_never_retry_navigation(self):
  from material_jobs.stationary_approach import observe_nearby
  from types import SimpleNamespace
  from unittest.mock import patch
  from pathlib import Path
  import tempfile,copy
  state=self.state();state['last_request']='r';ops=[]
  class Client:
   world='w';task='t';heartbeat=SimpleNamespace(id='l');unconfirmed_native_request=None;native_inflight=None
   def status(self):return copy.deepcopy(state)
   def checked(self,op,**kw):ops.append(op);return {'time':len(ops),'blocks':[]}
  reply=dict(phase='stopped',detail=DRIFT,world_session='w',id='r',material_air_navigation={'injury_interrupted':False})
  with tempfile.TemporaryDirectory()as d,patch('material_jobs.stationary_approach.coherent',return_value=True),patch('material_jobs.stationary_approach.wait_exact_idle_terminal',side_effect=lambda c:c.status()),patch('material_jobs.stationary_approach.time.sleep'):
   result=observe_nearby(Client(),reply,[10.5,63.4,20.5],Path(d)/'proof')
  self.assertEqual(['scan']*3,ops);self.assertEqual('stopped',reply['phase']);self.assertFalse(result['exact_waypoint_confirmed']);self.assertEqual(3,len(result['frames']))
 def test_movement_during_a_scan_rejects_the_pose_without_retry(self):
  from material_jobs.stationary_approach import observe_nearby
  from types import SimpleNamespace
  from unittest.mock import patch
  from pathlib import Path
  import tempfile,copy
  state=self.state();state['last_request']='r';ops=[]
  class Client:
   world='w';task='t';heartbeat=SimpleNamespace(id='l');unconfirmed_native_request=None;native_inflight=None
   def status(self):return copy.deepcopy(state)
   def checked(self,op,**kw):ops.append(op);state['pos'][0]+=.02;return {'time':1,'blocks':[]}
  reply=dict(phase='stopped',detail=DRIFT,world_session='w',id='r',material_air_navigation={'injury_interrupted':False})
  with tempfile.TemporaryDirectory()as d,patch('material_jobs.stationary_approach.coherent',return_value=True),patch('material_jobs.stationary_approach.wait_exact_idle_terminal',side_effect=lambda c:c.status()):
   with self.assertRaises(RuntimeError):observe_nearby(Client(),reply,[10.5,63.4,20.5],Path(d)/'proof')
  self.assertEqual(['scan'],ops)
if __name__=='__main__':unittest.main()
