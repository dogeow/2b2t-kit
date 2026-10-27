import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from boat_safety import retreat_plan,return_after_known_move
from boat_towing import finish_known_leg

class BoatSafetyTests(unittest.TestCase):
 def fixture(self):
  state=dict(connected=True,world_session='w',server='s',dimension='d',player_uuid='player',time=1000,manual_movement=False,health=20,food=20,screen='',guard_armed=True,guard_pve_only=True,guard_busy=False,navigating=False,native_material_busy=False,movement_keys={'forward':False},last_request='move',control_revision=10,pos=[0,70.5,0],supervision_lease=dict(kind='materials',id='lease',job_session='task',world_session='w'))
  move=dict(op='navigate',request_id='move',**{'from':[0,69,0]},boat_before=dict(passengers=[dict(uuid='v',health=20)]))
  reply=dict(id='move',phase='done',world_session='w',control_revision=10,pos=[0,70.5,0])
  boat=dict(uuid='boat',alive=True,pos=[0,64,0],leashed=True,leash_resolved=True,leash_holder=dict(uuid='player'),passengers=[dict(uuid='v',alive=True,health=19)])
  frame={**{k:state[k]for k in ['world_session','server','dimension','player_uuid','time']},'vehicles':[boat]}
  book=dict(world_session='w',uuid='boat',lease_id='lease',task_session='task',baseline_health={'v':20},pending=move)
  return state,book,move,reply,frame
 def test_injury_after_known_completed_leg_can_only_reverse_that_leg(self):
  args=self.fixture();self.assertEqual(retreat_plan(*args)['target'],[0,69,0])
  for change in ('manual','player_health','world','owner','unknown','different_request','too_far','held','no_injury','foreign_rope'):
   s,b,m,r,f=copy.deepcopy(args)
   if change=='manual':s['manual_movement']=True
   if change=='player_health':s['health']=19
   if change=='world':s['world_session']='other'
   if change=='owner':s['supervision_lease']['id']='other'
   if change=='unknown':r['phase']='waiting'
   if change=='different_request':s['last_request']='other'
   if change=='too_far':m['from']=[0,60,0]
   if change=='held':s['movement_keys']['forward']=True
   if change=='no_injury':f['vehicles'][0]['passengers'][0]['health']=20
   if change=='foreign_rope':f['vehicles'][0]['leash_holder']['uuid']='other'
   with self.subTest(change=change):self.assertIsNone(retreat_plan(s,b,m,r,f))
 def test_lost_passenger_and_new_animal_do_not_block_rescuing_survivors(self):
  s,b,m,r,f=self.fixture();f['vehicles'][0]['passengers']=[dict(uuid='sheep',health=8,alive=True)]
  self.assertIsNotNone(retreat_plan(s,b,m,r,f))
 def test_completed_read_only_scan_does_not_hide_a_late_cargo_health_drop(self):
  s,b,m,r,f=self.fixture();s['last_request']='scan';b['last_read_only']=dict(id='scan',phase='done',world_session='w',control_revision=10)
  self.assertIsNotNone(retreat_plan(s,b,m,r,f));b['last_read_only']['phase']='waiting';self.assertIsNone(retreat_plan(s,b,m,r,f))
 def test_health_abort_returns_once_before_waiting_for_leash_and_never_resumes_route(self):
  s,b,m,r,f=self.fixture()
  class Client:
   root=Path('/unused');native_inflight=None;unconfirmed_native_request=None
   def __init__(self):self.calls=[]
   def status(self):return s
   def request(self,op,**params):
    self.calls.append((op,params));s.update(last_request='back',control_revision=11,pos=[0,69,0]);return dict(id='back',phase='done',world_session='w',control_revision=11,pos=[0,69,0])
  c=Client()
  def observe():return s,f['vehicles'][0]
  with tempfile.TemporaryDirectory()as directory,patch('boat_safety.read_frame',return_value=f):
   path=Path(directory)/'tow.json'
   with self.assertRaisesRegex(RuntimeError,'health changed'):finish_known_leg(c,observe,b,r,[0,70.5,0],path)
   self.assertEqual(len(c.calls),1);self.assertEqual(c.calls[0][1]['target'],[0,69,0]);self.assertTrue(b['safety_returns'][0]['complete']);self.assertTrue(b['safety_returns'][0]['transport_resume_forbidden'])
   return_after_known_move(c,b,m,r,path);self.assertEqual(len(c.calls),1)
 def test_unconfirmed_native_move_never_creates_a_safety_input(self):
  s,b,m,r,f=self.fixture();r['phase']='waiting'
  class Client:
   root=Path('/unused');native_inflight=None;unconfirmed_native_request=None
   def status(self):return s
   def request(self,*args,**kwargs):raise AssertionError('No second action allowed')
  with tempfile.TemporaryDirectory()as directory,patch('boat_safety.read_frame',return_value=f):
   self.assertIsNone(return_after_known_move(Client(),b,m,r,Path(directory)/'tow.json'));self.assertNotIn('safety_returns',b)

if __name__=='__main__':unittest.main()
