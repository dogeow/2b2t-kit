import tempfile,unittest,math
from pathlib import Path
from unittest.mock import patch
from boat_towing import run
class DockingPrecisionTests(unittest.TestCase):
 def test_sub_block_docking_correction_is_sent_while_cruise_retains_legacy_tolerance(self):
  for tolerance,expected_calls in [(.6,0),(.15,1)]:
   with self.subTest(tolerance=tolerance),tempfile.TemporaryDirectory()as directory:
    q=dict(connected=True,world_session='w',dimension='minecraft:overworld',manual_movement=False,screen='',health=20,food=20,guard_armed=True,guard_pve_only=True,player_uuid='p',pos=[0,66.8,0],inventory=[],supervision_lease=dict(kind='materials',id='lease',job_session='t',world_session='w'))
    boat=dict(uuid='boat',alive=True,pos=[0,64,0],leashed=True,leash_resolved=True,leash_holder=dict(uuid='p'),bounds=dict(min=[-.6875,64,-.6875],max=[.6875,64.5625,.6875]),passengers=[dict(uuid='v',type='minecraft:villager',alive=True,is_baby=False,has_custom_name=False,health=20,bounds=dict(min=[-.3,64.1875,-.3],max=[.3,66.1375,.3]))])
    class Client:
     root=Path(directory)/'native';world='w';task='t';server='s';anchor=[0,66.8,0];last=None
     def __init__(self):self.calls=[];self.root.mkdir()
     def status(self):return q
     def checked(self,op,**params):
      if op!='scan':raise AssertionError(op)
      cells=math.prod(b-a+1 for a,b in zip(params['min'],params['max']));return dict(id='scan',phase='done',world_session='w',scan_cells_read=cells,scan_total_cells=cells,blocks=[])
     def request(self,op,**params):self.calls.append(params);q['pos']=params['target'];self.last='move';return dict(id='move',phase='done',world_session='w',pos=q['pos'])
     def set_progress(self,**kwargs):pass
    c=Client()
    with patch('boat_towing.read_frame',return_value=dict(vehicles=[boat],leashables=[])):
     r=run(c,'boat',['v'],[[.3,66.8,0]],[0,64,0],Path(directory)/'trip',lambda:None,waypoint_arrival=tolerance)
    self.assertTrue(r['complete']);self.assertEqual(len(c.calls),expected_calls)
    if c.calls:self.assertLessEqual(c.calls[0]['arrival'],.1)
 def test_invalid_precision_does_not_touch_a_controller(self):
  for value in [0,.01,.7,float('nan'),True]:
   with self.subTest(value=value),self.assertRaises(ValueError):run(None,'b',['v'],[[0,70,0]],[0,64,0],Path('/unused'),lambda:None,waypoint_arrival=value)
if __name__=='__main__':unittest.main()
