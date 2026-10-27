import tempfile,unittest
from pathlib import Path
from queued_village_owner import QueuedVillageOwner

class QueuedVillageOwnerTests(unittest.TestCase):
 def test_only_certified_inverse_uses_same_queue_while_ordinary_npc_health_guard_stays_closed(self):
  import test_boat_safety as fixtures
  from boat_safety import retreat_plan
  from unittest.mock import patch
  s,b,m,r,f=fixtures.BoatSafetyTests().fixture();s['supervision_lease']['search_origin']=[0,69,0]
  with tempfile.TemporaryDirectory()as directory:
   class Queue:
    calls=[]
    def status(self):return s
    def native(self,op,**params):self.calls.append((op,params));return dict(id='reverse',phase='done',world_session='w',control_revision=11,pos=params['target'])
   class Builder:
    root=out=Path(directory)
    q=Queue();book={};injured=False
    def check(self):
     if self.injured:raise RuntimeError('Protected NPC health changed')
     return s
    def n(self,*args,**kwargs):self.check();raise AssertionError('Ordinary input must stay blocked')
    def save(self):pass
   builder=Builder();owner=QueuedVillageOwner(builder);builder.injured=True
   with self.assertRaises(RuntimeError):owner.status()
   self.assertEqual(owner.last,'move')
   certificate=retreat_plan(s,b,m,r,f)
   with patch('vehicle_observation.read_frame',return_value=f):result=owner.cargo_safety_retreat(certificate)
   self.assertEqual(result['phase'],'done');self.assertEqual(builder.q.calls,[('navigate',dict(target=[0,69,0],arrival=.2,air_only=True,seconds=15))]);self.assertFalse(builder.book['pending_cargo_safety_return']['pending'])
   s['manual_movement']=True
   with patch('vehicle_observation.read_frame',return_value=f),self.assertRaises(RuntimeError):owner.cargo_safety_retreat(certificate)
   self.assertEqual(len(builder.q.calls),1)
 def test_every_transport_input_uses_existing_builder_and_cannot_rebase(self):
  with tempfile.TemporaryDirectory()as directory:
   class Builder:
    root=out=Path(directory)
    calls=[]
    def __init__(self):self.q=self
    def check(self):return dict(world_session='w',server='s',last_request='r',time=100,supervision_lease=dict(job_session='t',search_origin=[1,65,1]))
    def status(self):return self.check()
    def n(self,op,**params):self.calls.append((op,params));return {'phase':'done'}
   b=Builder();c=QueuedVillageOwner(b)
   self.assertEqual(c.request('navigate',target=[1,66,1]),{'phase':'done'})
   self.assertEqual(b.calls,[('navigate',dict(target=[1,66,1]))])
   self.assertEqual(c.last,'r')
   with self.assertRaises(RuntimeError):c.checked('guard',pve_only=True)
   self.assertEqual(len(b.calls),1)

if __name__=='__main__':unittest.main()
