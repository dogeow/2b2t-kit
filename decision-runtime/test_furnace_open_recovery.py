"""One owned pre-dispatch lit-state change may reopen, never reload a furnace."""
import copy
import unittest
from unittest.mock import patch
from furnace_batches import snapshot

POS=[761030,65,797843]
TRUE='Block{minecraft:furnace}[facing=west,lit=true]'
FALSE='Block{minecraft:furnace}[facing=west,lit=false]'


class Client:
    def __init__(self,rows=None,errors=None):
        self.world='world';self.task='task';self.rev=7;self.last=None
        self.rows=rows or [TRUE,TRUE,FALSE];self.errors=list(errors or []);self.actions=[];self.scans=0
        self.last_terminal_evidence={};self.proof_change=lambda proof:None
        self.scan_world=self.world
        self.state={'connected':True,'world_session':self.world,'control_revision':self.rev,
            'manual_movement':False,'screen':'','health':20,'guard_armed':True,'guard_pve_only':True,
            'guard_busy':False,'safety_hold':{'active':False},
            'menu':{'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0}},
            'supervision_lease':{'kind':'materials','job_session':self.task,
                'world_session':self.world,'revision':self.rev}}
    def status(self):return copy.deepcopy(self.state)
    def request(self,op,**params):
        assert op=='scan' and params=={'min':POS,'max':POS}
        value=self.rows[min(self.scans,len(self.rows)-1)];self.scans+=1;self.last='scan-'+str(self.scans)
        return {'world_session':self.scan_world,'blocks':[] if value is None else [{'pos':POS,'state':value}]}
    def checked(self,op,**params):
        self.actions.append((op,params));assert op in ('select_item','interact')
        if op=='select_item':return {'phase':'done'}
        self.last='interact-'+str(len(self.actions))
        if self.errors:
            error=self.errors.pop(0)
            proof={'request_id':self.last,'world_session':self.world,'task_session':self.task,
                'op':op,'phase':'error','detail':str(error),'params':{'task_session':self.task,**params}}
            self.proof_change(proof);self.last_terminal_evidence=proof
            raise error
        return {'phase':'done'}


class FurnaceOpenRecoveryTest(unittest.TestCase):
    def opening(self,c):
        with patch('furnace_batches.approach_faces',return_value='up'), \
             patch('furnace_batches.wait_container_contents',return_value={'opened':True}) as menu:
            result=snapshot(c,POS)
        menu.assert_called_once_with(c,'FurnaceMenu',require_nonempty=False)
        return result
    def uses(self,c):return [params for op,params in c.actions if op=='interact']
    def test_refresh_after_selection_uses_the_actual_west_furnace_state(self):
        c=Client(rows=[TRUE,FALSE]);self.assertEqual({'opened':True},self.opening(c))
        self.assertEqual(2,c.scans);self.assertEqual(1,len(self.uses(c)))
        self.assertEqual(FALSE,self.uses(c)[0]['expected_state'])
        self.assertEqual('select_item',c.actions[0][0])
    def test_exact_owned_predispatch_lit_flip_allows_only_one_reopen(self):
        c=Client(errors=[RuntimeError('Target block changed')])
        self.opening(c)
        self.assertEqual([TRUE,FALSE],[params['expected_state'] for params in self.uses(c)])
        self.assertEqual(3,c.scans)
        self.assertEqual(1,sum(op=='select_item' for op,_ in c.actions))
        self.assertTrue(all(op in ('select_item','interact') for op,_ in c.actions))
    def test_unchanged_facing_kind_or_missing_block_is_not_a_lit_recovery(self):
        for after in (TRUE,'Block{minecraft:furnace}[facing=east,lit=false]',
                      'Block{minecraft:smoker}[facing=west,lit=false]',None):
            with self.subTest(after=after):
                c=Client(rows=[TRUE,TRUE,after],errors=[RuntimeError('Target block changed')])
                with self.assertRaises(RuntimeError):self.opening(c)
                self.assertEqual(1,len(self.uses(c)))
    def test_timeout_and_unknown_or_foreign_receipts_never_repeat_use(self):
        changes=[lambda p:p.update(request_id='foreign'),lambda p:p.update(world_session='foreign'),
                 lambda p:p.update(task_session='foreign'),lambda p:p.update(phase='waiting'),
                 lambda p:p.update(op='slot_click'),lambda p:p.update(detail='another failure'),
                 lambda p:p['params'].update(expected_state=FALSE),
                 lambda p:p['params'].update(task_session='foreign')]
        for change in changes:
            c=Client(errors=[RuntimeError('Target block changed')]);c.proof_change=change
            with self.assertRaises(RuntimeError):self.opening(c)
            self.assertEqual(2,c.scans);self.assertEqual(1,len(self.uses(c)))
        c=Client(errors=[RuntimeError('Native operation timed out; do not replay it')])
        with self.assertRaises(RuntimeError):self.opening(c)
        self.assertEqual(2,c.scans);self.assertEqual(1,len(self.uses(c)))
    def test_new_control_world_user_menu_guard_or_cursor_stops_before_fresh_retry_scan(self):
        changes=[lambda s:s.update(connected=False),lambda s:s.update(world_session='foreign'),
            lambda s:s.update(control_revision=8),lambda s:s.update(manual_movement=True),
            lambda s:s.update(screen='ContainerScreen'),lambda s:s.update(guard_busy=True),
            lambda s:s.update(menu=['unknown']),lambda s:s.update(supervision_lease=['unknown']),
            lambda s:s.update(health=13),lambda s:s['safety_hold'].update(active=True),
            lambda s:s['menu']['cursor'].update(item='minecraft:potato',count=1),
            lambda s:s['supervision_lease'].update(job_session='foreign'),
            lambda s:s['supervision_lease'].update(kind='parking')]
        for change in changes:
            c=Client(errors=[RuntimeError('Target block changed')]);change(c.state)
            with self.assertRaises(RuntimeError):self.opening(c)
            self.assertEqual(2,c.scans);self.assertEqual(1,len(self.uses(c)))
    def test_retry_scan_from_another_world_is_not_used(self):
        c=Client(errors=[RuntimeError('Target block changed')])
        def changed(proof):c.scan_world='foreign'
        c.proof_change=changed
        with self.assertRaises(RuntimeError):self.opening(c)
        self.assertEqual(3,c.scans);self.assertEqual(1,len(self.uses(c)))
    def test_second_rejection_is_preserved_without_a_third_open_or_loading(self):
        c=Client(errors=[RuntimeError('Target block changed'),RuntimeError('Target block changed')])
        with self.assertRaisesRegex(RuntimeError,'Target block changed'):self.opening(c)
        self.assertEqual(3,c.scans);self.assertEqual(2,len(self.uses(c)))
        self.assertFalse(any(op in ('slot_click','distribute') for op,_ in c.actions))


if __name__=='__main__':unittest.main()
