"""One owned pre-dispatch lit-state change may reopen, never reload a furnace."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from furnace_batches import snapshot

POS=[761030,65,797843]
TRUE='Block{minecraft:furnace}[facing=west,lit=true]'
FALSE='Block{minecraft:furnace}[facing=west,lit=false]'


class Client:
    def __init__(self,rows=None,errors=None,*,pos=POS,out=None):
        self.world='world';self.task='task';self.rev=7;self.last=None
        self.pos=pos;self.out=Path(out) if out is not None else None
        self.rows=rows or [TRUE,TRUE,FALSE];self.errors=list(errors or []);self.actions=[];self.scans=0
        self.last_terminal_evidence={};self.proof_change=lambda proof:None
        self.scan_world=self.world
        self.scan_revision=self.rev;self.scan_change=lambda index,reply:None
        self.approach_reply={'phase':'done'}
        self.state={'connected':True,'world_session':self.world,'control_revision':self.rev,
            'hand':{'item':'minecraft:bow'},'inventory':[{'slot':0,'item':'minecraft:diamond_sword','count':1}],
            'manual_movement':False,'screen':'','health':20,'guard_armed':True,'guard_pve_only':True,
            'guard_busy':False,'safety_hold':{'active':False},
            'menu':{'id':0,'type':'InventoryMenu','cursor':{'item':'minecraft:air','count':0}},
            'supervision_lease':{'kind':'materials','job_session':self.task,
                'world_session':self.world,'revision':self.rev}}
    def status(self):return copy.deepcopy(self.state)
    def request(self,op,**params):
        if op=='approach_block':
            assert params['pos']==self.pos
            self.actions.append((op,params));self.last='approach-'+str(len(self.actions))
            return copy.deepcopy(self.approach_reply)
        assert op=='scan' and params=={'min':self.pos,'max':self.pos}
        value=self.rows[min(self.scans,len(self.rows)-1)];self.scans+=1;self.last='scan-'+str(self.scans)
        reply={'phase':'done','world_session':self.scan_world,'control_revision':self.scan_revision,
               'blocks':[] if value is None else [{'pos':self.pos,'state':value}]}
        self.scan_change(self.scans,reply);return reply
    def checked(self,op,**params):
        self.actions.append((op,params));assert op in ('select_item','interact')
        if op=='select_item':self.state['hand']['item']=params['item'];return {'phase':'done'}
        self.last='interact-'+str(len(self.actions))
        if self.errors:
            error=self.errors.pop(0)
            proof={'request_id':self.last,'world_session':self.world,'task_session':self.task,
                'op':op,'phase':'error','detail':str(error),'params':{'task_session':self.task,**params}}
            self.proof_change(proof);self.last_terminal_evidence=proof
            raise error
        return {'phase':'done'}


class FurnaceOpenRecoveryTest(unittest.TestCase):
    def approach_failure(self,c,change=lambda p:None):
        c.last='owned-approach-rejection'
        proof={'request_id':c.last,'world_session':c.world,'task_session':c.task,
               'op':'approach_block','phase':'error','detail':'Work block state changed',
               'revision_before':c.rev,'revision_after':c.rev,
               'params':{'task_session':c.task,'pos':POS,'face':'up','expected_state':TRUE,'seconds':45}}
        change(proof);c.last_terminal_evidence=proof
        raise RuntimeError('Work block state changed')

    def test_exact_unstarted_approach_lit_flip_gets_one_fresh_approach(self):
        c=Client(rows=[TRUE,FALSE,FALSE]);calls=[]
        def approach(*args,**kwargs):
            calls.append(args[2])
            if len(calls)==1:self.approach_failure(c)
            return 'up'
        with patch('furnace_batches.approach_faces',side_effect=approach),patch('furnace_batches.wait_container_contents',return_value={'opened':True}):
            self.assertEqual({'opened':True},snapshot(c,POS))
        self.assertEqual([TRUE,FALSE],calls);self.assertEqual(1,len(self.uses(c)))

    def test_foreign_moved_unknown_or_non_lit_approach_is_not_repeated(self):
        for change in (lambda p:p.update(request_id='foreign'),lambda p:p.update(phase='waiting'),
                       lambda p:p.update(revision_after=8),lambda p:p.update(world_session='foreign')):
            c=Client(rows=[TRUE,FALSE,FALSE])
            with patch('furnace_batches.approach_faces',side_effect=lambda *a,**k:self.approach_failure(c,change))as approach:
                with self.assertRaises(RuntimeError):snapshot(c,POS)
            self.assertEqual(1,approach.call_count);self.assertEqual([],self.uses(c))
        c=Client(rows=[TRUE,TRUE])
        with patch('furnace_batches.approach_faces',side_effect=lambda *a,**k:self.approach_failure(c))as approach:
            with self.assertRaises(RuntimeError):snapshot(c,POS)
        self.assertEqual(1,approach.call_count)

    def test_second_approach_rejection_stops_without_a_third_request(self):
        c=Client(rows=[TRUE,FALSE,FALSE])
        with patch('furnace_batches.approach_faces',side_effect=lambda *a,**k:self.approach_failure(c))as approach:
            with self.assertRaises(RuntimeError):snapshot(c,POS)
        self.assertEqual(2,approach.call_count);self.assertEqual([],self.uses(c))
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

    def test_exact_predispatch_occluded_face_uses_one_fresh_other_face(self):
        c=Client(rows=[FALSE]*4,errors=[RuntimeError('Target interaction face is occluded or out of reach')])
        with patch('furnace_batches.approach_faces',side_effect=['up','north']) as approach, \
             patch('furnace_batches.wait_container_contents',return_value={'opened':True}):
            self.assertEqual({'opened':True},snapshot(c,POS))
        self.assertEqual(['up','north'],[p['face']for p in self.uses(c)])
        self.assertNotIn('up',approach.call_args_list[1].args[3])

    def test_foreign_or_unknown_occluded_face_receipt_never_issues_another_use(self):
        for change in (lambda p:p.update(request_id='foreign'),lambda p:p.update(phase='waiting'),
                       lambda p:p['params'].update(face='south')):
            c=Client(rows=[FALSE]*4,errors=[RuntimeError('Target interaction face is occluded or out of reach')]);c.proof_change=change
            with self.assertRaises(RuntimeError):self.opening(c)
            self.assertEqual(1,len(self.uses(c)))


class FurnaceAccessLitTest(unittest.TestCase):
    pos=[761027,65,797846]
    lit='Block{minecraft:furnace}[facing=north,lit=true]'
    dark='Block{minecraft:furnace}[facing=north,lit=false]'

    def client(self,out,rows):
        c=Client(rows=rows,pos=self.pos,out=out)
        c.world='ad994b60-e404-4de7-ae84-b2ef2a84eb67';c.rev=348
        c.scan_world=c.world;c.scan_revision=c.rev
        c.state.update(world_session=c.world,control_revision=c.rev)
        c.state['supervision_lease'].update(world_session=c.world,revision=c.rev)
        return c

    def opening(self,c):
        # Keep the actual work_access.approach_faces path. Only menu polling is mocked.
        with patch('furnace_batches.wait_container_contents',return_value={'opened':True}):
            return snapshot(c,self.pos)

    def test_actual_north_furnace_true_to_false_uses_latest_access_state(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.client(d,[self.lit,self.dark,self.dark]);self.assertEqual({'opened':True},self.opening(c))
            self.assertEqual(['approach_block','select_item','interact'],[op for op,_ in c.actions])
            self.assertEqual(self.dark,c.actions[0][1]['expected_state'])
            self.assertEqual(self.dark,c.actions[-1][1]['expected_state']);self.assertEqual(3,c.scans)

    def test_use_scans_again_after_selection_instead_of_reusing_access_state(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.client(d,[self.lit,self.dark,self.lit]);self.opening(c)
            self.assertEqual(self.dark,c.actions[0][1]['expected_state'])
            self.assertEqual(self.lit,c.actions[-1][1]['expected_state'])

    def test_default_approach_remains_strict_even_for_a_lit_flip(self):
        from work_access import approach_faces
        with tempfile.TemporaryDirectory() as d:
            c=self.client(d,[self.dark])
            with self.assertRaisesRegex(RuntimeError,'Work target changed'):
                approach_faces(c,self.pos,self.lit,['up'])
            self.assertEqual([],c.actions)

    def test_kind_facing_or_missing_target_is_rejected_before_access(self):
        for observed in ('Block{minecraft:furnace}[facing=west,lit=false]',
                         'Block{minecraft:smoker}[facing=north,lit=false]',
                         'Block{minecraft:blast_furnace}[facing=north,lit=false]',None):
            with self.subTest(observed=observed),tempfile.TemporaryDirectory() as d:
                c=self.client(d,[self.lit,observed])
                with self.assertRaises(RuntimeError):self.opening(c)
                self.assertEqual([],c.actions)

    def test_foreign_world_revision_position_or_incomplete_scan_is_rejected(self):
        changes=[lambda r:r.update(world_session='foreign'),lambda r:r.update(control_revision=349),
                 lambda r:r.update(phase='waiting'),lambda r:r['blocks'][0].update(pos=[0,0,0])]
        for change in changes:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                c=self.client(d,[self.lit,self.dark])
                c.scan_change=lambda n,r:change(r) if n==2 else None
                with self.assertRaises(RuntimeError):self.opening(c)
                self.assertEqual([],c.actions)

    def test_foreign_revision_adopted_during_scan_cannot_authorize_access(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.client(d,[self.lit,self.dark])
            def foreign(n,reply):
                if n==2:
                    c.rev=349;c.state['control_revision']=349;reply['control_revision']=349
            c.scan_change=foreign
            with self.assertRaises(RuntimeError):self.opening(c)
            self.assertEqual([],c.actions)

    def test_identity_or_revision_change_after_selection_stops_before_use(self):
        for kind in ('facing','world','revision'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                c=self.client(d,[self.lit,self.dark,
                    'Block{minecraft:furnace}[facing=west,lit=false]' if kind=='facing' else self.dark])
                def change(n,reply):
                    if n==3 and kind!='facing':reply['world_session' if kind=='world' else 'control_revision']='foreign' if kind=='world' else 349
                c.scan_change=change
                with self.assertRaises(RuntimeError):self.opening(c)
                self.assertEqual(['approach_block','select_item'],[op for op,_ in c.actions])

    def test_unknown_interact_or_access_is_never_repeated_or_followed_by_loading(self):
        with tempfile.TemporaryDirectory() as d:
            c=self.client(d,[self.lit,self.dark,self.dark]);c.errors=[RuntimeError('Native operation timed out; do not replay it')]
            with self.assertRaises(RuntimeError):self.opening(c)
            self.assertEqual(['approach_block','select_item','interact'],[op for op,_ in c.actions]);self.assertEqual(3,c.scans)
        with tempfile.TemporaryDirectory() as d:
            c=self.client(d,[self.lit,self.dark]);c.approach_reply={'phase':'waiting','detail':'time limit reached'}
            with self.assertRaises(RuntimeError):self.opening(c)
            self.assertEqual(['approach_block'],[op for op,_ in c.actions]);self.assertEqual(2,c.scans)


if __name__=='__main__':unittest.main()
