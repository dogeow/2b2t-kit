import unittest,tempfile,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from guarded_workstation_print import print_once,PREFIX
class PrintWaitTests(unittest.TestCase):
 def fixture(self,root,change=None):
  out=Path(root);(out/'mask').mkdir();(out/'control').mkdir();command=dict(id='mask',action='native',op='projection_batch_set',params=dict(placement_key='k',positions=[[1,2,3]]));(out/'command.json').write_text(json.dumps(command));(out/'mask/result.json').write_text(json.dumps(dict(phase='done',world_session='w',control_revision=2)))
  state=dict(world_session='w',health=20,manual_movement=False,control_revision=2,inventory=[dict(slot=0,item='minecraft:lectern',count=1)],projection_batch=dict(active=True,count=1,placement_key='k',task_session='t'),professional_printer=dict(enabled=False));b=SimpleNamespace(q=SimpleNamespace(out=out,world='w',lease={'job_session':'t'}),book={},save=lambda:None,check=lambda:state);calls=[]
  def native(op,**params):
   calls.append(op)
   if len(calls)==1:
    if change=='dispatch':(out/'command.json').write_text(json.dumps(dict(id='sent')))
    if change=='unknown':(out/'control/unconfirmed-native-request.json').write_text('{}')
    if change=='world':state['world_session']='other'
    if change=='count':state['inventory'][0]['count']=0
    if change=='mask':state['projection_batch']['placement_key']='other'
    if change=='manual':state['manual_movement']=True
    if change=='native_error':raise RuntimeError('Original village action did not complete: waiting')
    raise RuntimeError(PREFIX+'villager')
   return dict(phase='done',id='first_actual_print')
  b.n=native;return b,calls
 def test_local_unqueued_refusal_can_wait_then_send_first_actual_print(self):
  with tempfile.TemporaryDirectory()as d,patch('guarded_workstation_print.time.sleep'):
   b,calls=self.fixture(d);r=print_once(b,'k',[1,2,3],1);self.assertEqual('first_actual_print',r['id']);self.assertEqual(2,len(calls));self.assertTrue(b.book['unissued_print_containment_waits'][0]['no_print_dispatched'])
 def test_possible_native_input_or_changed_owner_never_retried(self):
  for change in ['dispatch','unknown','world','count','mask','manual','native_error']:
   with self.subTest(change=change),tempfile.TemporaryDirectory()as d,patch('guarded_workstation_print.time.sleep'):
    b,calls=self.fixture(d,change)
    with self.assertRaises(RuntimeError):print_once(b,'k',[1,2,3],1)
    self.assertEqual(1,len(calls))
 def test_expired_wait_remains_unissued_without_repeating_attempt(self):
  with tempfile.TemporaryDirectory()as d:
   b,calls=self.fixture(d)
   with self.assertRaises(RuntimeError):print_once(b,'k',[1,2,3],1,timeout=0)
   self.assertEqual(1,len(calls))
