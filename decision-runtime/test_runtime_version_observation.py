import unittest
from runtime_version_observation import observable
from test_storage_schema_refusal import StorageSchemaRefusalTest
class RuntimeVersionObservationTest(unittest.TestCase):
 def setUp(self):
  f=StorageSchemaRefusalTest();f.setUp();self.s=f.state;self.s.update(runtime_generation=3,runtime_version='old',navigation_runtime_version='old')
  self.c=dict(action='hot_runtime_update',version='new');self.e=dict(f.error,type='RuntimeError',error='Runtime version was not confirmed; do not repeat reload blindly')
  self.ev=dict(f.event,op='runtime_reload');self.r=dict(self.s,id='r',phase='done')
 def ok(self):return observable(self.c,self.e,self.r,self.ev,self.s,'w','t',2)
 def test_known_ack(self):self.assertTrue(self.ok())
 def test_unknown_or_wrong_generation_fails(self):
  self.e['native_inflight']='unknown';self.assertFalse(self.ok());self.e['native_inflight']=None
  self.s['runtime_generation']=4;self.assertFalse(self.ok())
 def test_changed_identity_fails(self):self.ev['request_id']='other';self.assertFalse(self.ok())
