import unittest
from copy import deepcopy
from chop_goal_receipt import allow_deadline_goal_audit

class ChopGoalReceiptTest(unittest.TestCase):
    def setUp(self):
        self.args=dict(world='world',task='task',lease_id='lease',revision=12,
            inventory_before=16,expected_logs=16,dirt_before=4)
        self.reply=dict(id='request',phase='stopped',detail='脚本任务达到时间上限',
            world_session='world',control_revision=12,time=100,chopper_verified_trees=1,chopping=True)
        self.terminal=dict(request_id='request',op='chop',phase='stopped',world_session='world',
            task_session='task',revision_after=12)
        rows=[dict(slot=i,item='minecraft:air',count=0)for i in range(43)]
        rows[1].update(item='minecraft:cherry_log',count=32)
        rows[2].update(item='minecraft:dirt',count=4)
        self.current=dict(connected=True,world_session='world',last_request='request',control_revision=12,
            health=20,food=20,guard_armed=True,guard_pve_only=True,screen='',manual_movement=False,
            chopping=False,navigating=False,chopper_verified_trees=1,chopper_platforms=0,time=110,
            inventory=rows,supervision_lease=dict(kind='materials',id='lease',job_session='task',world_session='world',revision=12))
    def allowed(self,**args):
        return allow_deadline_goal_audit(self.reply,self.terminal,self.current,**(self.args|args))
    def test_known_stop_allows_audit_without_changing_original_receipt(self):
        original=deepcopy(self.reply);self.assertTrue(self.allowed());self.assertEqual(original,self.reply)
    def test_publication_race_requires_current_chopper_to_stop(self):
        self.current['chopping']=True;self.assertFalse(self.allowed())
    def test_unknown_or_inflight_request_never_allows_audit(self):
        self.assertFalse(self.allowed(unknown={'id':'request'}));self.assertFalse(self.allowed(native_inflight={'id':'request'}))
    def test_timeout_alone_does_not_prove_target_inventory(self):
        self.current['inventory'][1]['count']=31;self.assertFalse(self.allowed())
    def test_platform_reserve_must_be_returned(self):
        self.current['inventory'][2]['count']=3;self.assertFalse(self.allowed())
    def test_other_request_world_or_lease_is_rejected(self):
        for key,value in [('last_request','other'),('world_session','other')]:
            original=self.current[key];self.current[key]=value;self.assertFalse(self.allowed());self.current[key]=original
        self.current['supervision_lease']['id']='other';self.assertFalse(self.allowed())
    def test_injury_manual_input_and_guard_combat_reject_recovery(self):
        for key,value in [('health',19),('manual_movement',True),('guard_busy',True)]:
            original=self.current.get(key);self.current[key]=value;self.assertFalse(self.allowed());self.current[key]=original
    def test_no_verified_tree_or_incomplete_inventory_is_rejected(self):
        self.current['chopper_verified_trees']=0;self.assertFalse(self.allowed())
        self.current['chopper_verified_trees']=1;self.current['inventory'].pop();self.assertFalse(self.allowed())

if __name__=='__main__':unittest.main()
