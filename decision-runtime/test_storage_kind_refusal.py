import unittest
from test_storage_schema_refusal import StorageSchemaRefusalTest
from storage_kind_refusal import observable

class KindRefusalTest(unittest.TestCase):
    def setUp(self):
        fixture=StorageSchemaRefusalTest();fixture.setUp();self.c=fixture.command;self.s=fixture.state;self.b=fixture.baseline
        self.e=dict(fixture.error,type='OutdoorChestChanged',error='Expected outdoor chest changed')
        self.ev=dict(fixture.event,op='scan',params=dict(task_session='t',min=[1,2,3],max=[1,2,3]),revision_before=5,position_before=self.s['pos'])
        self.r=dict(self.b,scan_start_revision=5,scan_end_revision=5,scan_cells_read=1,scan_total_cells=1,blocks=[dict(pos=[1,2,3],state='Block{minecraft:ender_chest}')])
    def ok(self):return observable(self.c,self.e,self.b,self.r,self.ev,self.s,'w','t')
    def test_exact(self):self.assertTrue(self.ok())
    def test_reject_matching_kind(self):self.r['blocks'][0]['state']='Block{minecraft:chest}';self.assertFalse(self.ok())
    def test_reject_changed_or_uncertain(self):
        self.ev['op']='interact';self.assertFalse(self.ok());self.ev['op']='scan'
        self.e['native_inflight']='pending';self.assertFalse(self.ok());self.e['native_inflight']=None
        self.r['scan_end_revision']=6;self.assertFalse(self.ok())
