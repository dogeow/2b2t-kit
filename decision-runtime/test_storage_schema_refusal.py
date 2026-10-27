import copy
import unittest
from storage_schema_refusal import observable

class StorageSchemaRefusalTest(unittest.TestCase):
    def setUp(self):
        self.command=dict(action='open_chest_from_pose',pos=[1,2,3],pose=[1.5,3.1,3.5],face='up')
        self.error=dict(type='ValueError',error='Indoor chest needs an exact position, registered stand and permitted face',native_inflight=None,unconfirmed_native_request=None,last_request='r')
        self.state=dict(last_request='r',world_session='w',control_revision=5,pos=[1.5,3.1,3.5],connected=True,health=20,manual_movement=False,screen='',menu=dict(type='InventoryMenu',id=0,cursor=dict(count=0)),movement_keys={},inventory=[])
        self.baseline=dict(self.state,id='r',phase='done')
        self.event=dict(request_id='r',op='navigate',phase='done',world_session='w',params=dict(task_session='t',target=[1.5,3.1,3.5]),inventory_delta={},revision_after=5,position_after=[1.5,3.1,3.5])
    def ok(self):return observable(self.command,self.error,self.baseline,self.event,self.state,'w','t')
    def test_exact(self):self.assertTrue(self.ok())
    def test_reject_changed_state_or_possible_input(self):
        for field,value in [('last_request','other'),('control_revision',6),('manual_movement',True),('screen','ContainerScreen'),('health',19),('pos',[2,3,4])]:
            with self.subTest(field=field):
                old=copy.deepcopy(self.state);self.state[field]=value;self.assertFalse(self.ok());self.state=old
    def test_reject_different_error_and_enabled_top(self):
        self.command['allow_top_face']=True;self.assertFalse(self.ok());self.command.pop('allow_top_face')
        self.error['native_inflight']={'id':'pending'};self.assertFalse(self.ok());self.error['native_inflight']=None
        self.error['error']='Other error';self.assertFalse(self.ok())
    def test_acknowledged_arrival_can_be_within_native_position_tolerance(self):
        self.event['params']['target']=[1.52,3.14,3.53];self.assertTrue(self.ok())
        self.event['params']['target']=[1.7,3.1,3.5];self.assertFalse(self.ok())
    def test_reject_other_native_operation(self):
        self.event['op']='interact';self.assertFalse(self.ok())

if __name__=='__main__':unittest.main()
