import unittest
from brewer_preflight_observation import observable
from test_storage_schema_refusal import StorageSchemaRefusalTest
class BrewerRefusalTest(unittest.TestCase):
 def setUp(self):
  f=StorageSchemaRefusalTest();f.setUp();self.c=dict(f.command,action='open_brewing_stand');self.e=dict(f.error,type='RuntimeError',error='Brewing stand pose or native owner changed; no input');self.b=f.baseline;self.ev=f.event;self.s=f.state
 def ok(self):return observable(self.c,self.e,self.b,self.ev,self.s,'w','t')
 def test_known_no_input(self):self.assertTrue(self.ok())
 def test_unknown_or_changed_terminal(self):
  self.e['native_inflight']='pending';self.assertFalse(self.ok());self.e['native_inflight']=None
  self.ev['op']='interact';self.assertFalse(self.ok())
