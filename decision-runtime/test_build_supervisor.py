import copy
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from build_supervisor import Supervisor,DEFAULTS,allowed,fingerprint,routine_supply_choice

def snapshot():
    return {'connected':True,'server':'test.example','world_session':'world1','dimension':'minecraft:overworld',
            'bridge_version':3,'supervision_protocol':1,'control_revision':2,'health':20,'food':20,'screen':'','guard_busy':False,
            'phase':'done','last_request':'before','pos':[0,64,0],
            'inventory':[{'slot':i,'item':'minecraft:air','count':0} for i in range(36)],
            'professional_printer':{'waiting_for_server':False},
            'build_job':{'active':True,'session':'job1','placement_key':'plot1','phase':'打印中','outcome':'running',
                         'matched':10,'total':100,'loading':False,'queue_settled':True,'auto_move':True,'material_deficits':{},'blocked_blocks':0}}
class Log:
    def __init__(self):self.events=[];self.handoffs=[];self.outcomes=[]
    def event(self,kind,**data):self.events.append((kind,data))
    def learned(self,*args):return None
    def handoff(self,*args):self.handoffs.append(args)
    def outcome(self,*args):self.outcomes.append(args)
class Model:
    def __init__(self,choice='replan'):self.calls=0;self.choice=choice
    def predict(self,state,questions):
        self.calls+=1;keys=questions['action']['criteria']
        return {'answers':{'action':{'type':'choice','choice':self.choice,'confidence':1,
                                   'probabilities':{key:float(key==self.choice) for key in keys}}}}

class InlineDecisions:
    """Deterministic policy test worker; real-thread behavior is tested separately."""
    def __init__(self):self.delivery=None
    @property
    def busy(self):return self.delivery is not None
    def submit(self,context,work):
        self.delivery={'context':copy.deepcopy(context),'response':work(),'valid':True,'age':0,'elapsed':0};return True
    def take(self):
        result=self.delivery;self.delivery=None;return result
    def invalidate(self,reason='changed'):
        if self.delivery:self.delivery['valid']=False
    def close(self):self.delivery=None

class SupervisorTests(unittest.TestCase):
    def test_usable_supply_resumes_without_asking_model_to_give_up(self):
        s=snapshot();s['build_job'].update(active=False,outcome='missing_materials',material_needs={'minecraft:stone_bricks':272})
        s['inventory'][0]={'slot':0,'item':'minecraft:stone_bricks','count':64}
        self.assertEqual(routine_supply_choice(s,allowed(s)),'resume_after_supply')
        s['build_job']['outcome']='manual_stop';self.assertIsNone(routine_supply_choice(s,allowed(s)))

    def test_missing_planks_with_logs_offers_real_recipe_recovery(self):
        s=snapshot();s['build_job'].update(active=False,outcome='missing_materials',material_needs={'minecraft:oak_planks':8})
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_log','count':2}
        self.assertIn('craft_planks',allowed(s));self.assertNotIn('resume_after_supply',allowed(s))
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_planks','count':8}
        self.assertNotIn('craft_planks',allowed(s));self.assertIn('resume_after_supply',allowed(s))
        s['build_job']['outcome']='manual_stop';self.assertEqual(allowed(s),{})
    def test_depot_is_offered_only_with_native_protocol_and_authorized_candidates(self):
        s=snapshot();s['build_job'].update(active=False,outcome='missing_materials',material_needs={'minecraft:oak_planks':8})
        self.assertNotIn('fetch_supply',allowed(s))
        s.update(supply_protocol=1,supply_candidates=[{'key':'known','recorded_items':{'minecraft:oak_log':4}}])
        self.assertIn('fetch_supply',allowed(s))
        s['build_job']['outcome']='manual_stop';self.assertNotIn('fetch_supply',allowed(s))
    def test_full_inventory_builds_with_carried_materials_before_fetching_or_crafting(self):
        s=snapshot();s['build_job'].update(active=False,outcome='missing_materials',material_needs={'minecraft:oak_planks':5,'minecraft:glass':2})
        s['inventory']=[{'slot':i,'item':'minecraft:dirt','count':64} for i in range(36)]
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_log','count':64}
        s['inventory'][1]={'slot':1,'item':'minecraft:glass','count':20}
        s.update(supply_protocol=1,supply_candidates=[{'key':'box','recorded_items':{'minecraft:oak_planks':3}}])
        options=allowed(s);self.assertIn('resume_after_supply',options);self.assertNotIn('craft_planks',options);self.assertNotIn('fetch_supply',options)
        s['inventory'][2]={'slot':2,'item':'minecraft:air','count':0};self.assertIn('craft_planks',allowed(s))
    def test_blocked_route_can_craft_new_materials_but_cannot_loop_on_unchanged_stock(self):
        s=snapshot();s['build_job'].update(active=False,outcome='blocked',supply_wait=True,supply_resume_ready=False,material_needs={'minecraft:oak_planks':5,'minecraft:glass':2})
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_log','count':10}
        s['inventory'][1]={'slot':1,'item':'minecraft:glass','count':20}
        self.assertIn('craft_planks',allowed(s));self.assertNotIn('resume_after_supply',allowed(s))
        s['build_job']['supply_resume_ready']=True;self.assertIn('resume_after_supply',allowed(s))
        s['build_job']['outcome']='manual_stop';self.assertEqual(allowed(s),{})
    def test_recipe_proposal_respects_output_capacity(self):
        from build_supervisor import compact
        s=snapshot();s['build_job'].update(material_needs={'minecraft:oak_planks':68})
        s['inventory']=[{'slot':i,'item':'minecraft:dirt','count':64} for i in range(36)]
        s['inventory'][0]={'slot':0,'item':'minecraft:oak_planks','count':60,'max_stack':64}
        s['inventory'][1]={'slot':1,'item':'minecraft:oak_log','count':5,'max_stack':64}
        self.assertEqual(compact(s)['recipe_plan']['output_count'],4)
        self.assertFalse(compact(s)['recipe_plan']['covers_current_deficit'])
    def test_utility_choice_can_proceed_among_locally_valid_options_but_must_be_a_clear_winner(self):
        from build_supervisor import utility_choice_clear
        a={'choice':'fetch_supply','confidence':.67,'probabilities':{'fetch_supply':.75,'craft_planks':.21,'pause_and_report':.04}}
        self.assertTrue(utility_choice_clear(a,DEFAULTS))
        a['probabilities']={'fetch_supply':.2,'craft_planks':.76,'pause_and_report':.04};self.assertFalse(utility_choice_clear(a,DEFAULTS))
        a['confidence']=.4;a['probabilities']={'fetch_supply':.9,'craft_planks':.06,'pause_and_report':.04};self.assertFalse(utility_choice_clear(a,DEFAULTS))
    def test_knowledge_from_a_different_kit_release_requires_new_validation(self):
        s=snapshot();s['kit_version']='1.9.44';a,_=fingerprint(s);s['kit_version']='1.9.45';b,_=fingerprint(s);self.assertNotEqual(a,b)
    def test_default_port_does_not_split_the_same_server_learning_scope(self):
        s=snapshot();a,_=fingerprint(s);s['server']='TEST.EXAMPLE:25565';b,_=fingerprint(s);self.assertEqual(a,b)
    def make(self,tmp,control=False):
        log=Log();model=Model();c=Supervisor(Path(tmp),'test.example',log,model,DEFAULTS,control,decision_worker=InlineDecisions())
        c.ensure_safety=lambda state:True # These cases isolate decision policy; lease tests below use the real implementation.
        return c,log,model
    def test_healthy_native_progress_uses_no_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp);s=snapshot();c.poll(s,0)
            for t in (10,50,100,150):s['build_job']['matched']+=1;self.assertEqual(c.poll(s,t),'progress')
            self.assertEqual(m.calls,0)
    def test_real_stall_offers_multiple_grounded_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp);s=snapshot();c.poll(s,0);self.assertEqual(c.poll(s,36),'decision')
            self.assertEqual(m.calls,1)
            decision=next(data for kind,data in log.events if kind=='jev_decision')
            self.assertIn('replan',decision['options']);self.assertIn('rescan',decision['options'])
            self.assertEqual(decision['snapshot']['matched'],10)
            self.assertFalse((Path(tmp)/'request.json').exists())
    def test_manual_stop_is_not_a_fault_or_an_automatic_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp,True);s=snapshot();c.poll(s,0);s['build_job'].update(active=False,outcome='manual_stop')
            self.assertEqual(c.poll(s,100),'stopped');self.assertEqual(m.calls,0);self.assertFalse(log.handoffs)
    def test_projection_change_revokes_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp,True);s=snapshot();c.poll(s,0);s['build_job']['placement_key']='different'
            self.assertEqual(c.poll(s,100),'scope_changed');self.assertEqual(m.calls,0)
    def test_server_queue_forbids_replanning(self):
        s=snapshot();s['build_job']['queue_settled']=False
        self.assertNotIn('rescan',allowed(s));self.assertNotIn('replan',allowed(s));self.assertIn('wait',allowed(s))
    def test_fresh_state_rechecked_after_inference(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp,True);s=snapshot();c.poll(s,0);changed=copy.deepcopy(s);changed['build_job']['active']=False
            with patch('build_supervisor.status',return_value=changed),self.assertRaises(Exception):c.poll(s,40)
            self.assertFalse((Path(tmp)/'request.json').exists())
    def test_completed_requires_actual_full_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp);s=snapshot();c.poll(s,0);s['build_job'].update(active=False,outcome='complete',matched=99)
            self.assertNotEqual(c.poll(s,5),'complete')
    def test_repeated_unresolved_stall_is_batched_for_code_improvement(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp);s=snapshot();c.poll(s,0)
            c.poll(s,36);c.poll(s,70)
            self.assertEqual(c.poll(s,105),'needs_review');self.assertEqual(m.calls,2);self.assertEqual(len(log.handoffs),1)
    def test_log_withdrawal_is_verified_without_requiring_already_crafted_planks(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp);s=snapshot();c.poll(s,0)
            c.pending={'key':'supply','choice':'fetch_supply','before':{'matched':10},'sent':0,'request_id':'take1'}
            s.update(last_request='take1',phase='done',build_supply={'phase':'done','taken':{'minecraft:oak_log':6}})
            c.poll(s,20);self.assertIsNone(c.pending);self.assertTrue(log.outcomes[0][-1]);self.assertEqual(m.calls,0)
    def test_successful_recovery_clears_consecutive_failure_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            c,log,m=self.make(tmp);s=snapshot();c.poll(s,0);key,_=fingerprint(s);c.attempts[key]=2
            c.pending={'key':key,'choice':'replan','before':{'matched':10},'sent':0,'request_id':'recovery1'}
            s['last_request']='recovery1';s['build_job']['matched']=11;c.poll(s,10)
            self.assertEqual(c.attempts[key],0);self.assertTrue(log.outcomes[0][-1])

class SafetyLeaseTests(unittest.TestCase):
    def test_explicit_launcher_start_attaches_native_safety_in_the_same_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Supervisor(Path(tmp),'test.example',Log(),Model(),DEFAULTS,True);s=snapshot()
            s['build_job'].update(active=False,outcome='idle');s['projection_selection']={'key':'plot1','name':'house'}
            def acknowledge(root):
                req=json.loads((Path(tmp)/'request.json').read_text());fresh=snapshot();fresh['last_request']=req['id'];fresh['build_job']['session']='new-job';return fresh
            try:
                with patch('build_supervisor.status',side_effect=acknowledge):c.start_selected(s)
                req=json.loads((Path(tmp)/'request.json').read_text());self.assertTrue(req['manual_start']);self.assertEqual(req['supervision_lease'],c.safety.id)
                self.assertEqual(c.job,'new-job');self.assertEqual(c.client.calls,0)
            finally:
                if c.safety:c.safety.close()
    def test_already_finished_tiny_build_is_adopted_from_its_native_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Supervisor(Path(tmp),'test.example',Log(),Model(),DEFAULTS,True);s=snapshot()
            s['build_job'].update(active=False,outcome='idle');s['projection_selection']={'key':'plot1'}
            def fast_finish(root):
                fresh=snapshot();fresh['build_job'].update(active=False,outcome='complete',matched=100,session='new-job')
                receipt={'lease':c.safety.id,'job_session':'new-job','cause':'complete','action':'LOGOUT','confirmed':True,'snapshot':fresh}
                (Path(tmp)/('supervision-receipt-'+c.safety.id+'.json')).write_text(json.dumps(receipt));return {'connected':False}
            try:
                with patch('build_supervisor.status',side_effect=fast_finish):c.start_selected(s)
                self.assertEqual(c.poll({},1),'complete');self.assertEqual(c.client.calls,0)
            finally:
                if c.safety:c.safety.close()

    def test_controller_does_not_act_before_native_watchdog_acknowledges(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Supervisor(Path(tmp),'test.example',Log(),Model(),DEFAULTS,True);s=snapshot()
            try:
                self.assertEqual(c.poll(s,0),'attaching_safety')
                req=json.loads((Path(tmp)/'request.json').read_text())
                self.assertEqual(req['op'],'supervision_attach');self.assertEqual(req['remote_finish'],'disconnect')
                self.assertEqual(c.client.calls,0)
                s['build_job'].update(active=False,outcome='manual_stop')
                self.assertEqual(c.poll(s,20),'stopped')
                self.assertEqual(json.loads((Path(tmp)/'request.json').read_text())['id'],req['id'])
            finally:
                if c.safety:c.safety.close()
    def test_receipt_is_bound_to_lease_job_and_world_and_survival(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Supervisor(Path(tmp),'test.example',Log(),Model(),DEFAULTS,True);s=snapshot()
            try:
                c.poll(s,0);s['build_job'].update(active=False,outcome='complete',matched=100)
                p=Path(tmp)/('supervision-receipt-'+c.safety.id+'.json')
                receipt={'confirmed':True,'lease':c.safety.id,'job_session':'job1','cause':'complete','action':'LOGOUT','snapshot':s}
                p.write_text(json.dumps(receipt));self.assertEqual(c.poll({},2),'complete')
                receipt['job_session']='old-job';p.write_text(json.dumps(receipt));self.assertIsNone(c.safety_receipt())
                receipt['job_session']='job1';receipt['snapshot']['health']=0
                p.write_text(json.dumps(receipt));self.assertEqual(c.poll({},3),'native_safe_stop')
            finally:
                if c.safety:c.safety.close()
    def test_pending_completion_does_not_reattach_or_time_out_original_attachment(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Supervisor(Path(tmp),'test.example',Log(),Model(),DEFAULTS,True);s=snapshot()
            try:
                c.poll(s,0);req=(Path(tmp)/'request.json').read_text();c.safety_requested_at-=100
                s['supervision_safety']={'lease':c.safety.id,'confirmed':False}
                s['build_job'].update(active=False,outcome='complete',matched=100)
                self.assertEqual(c.poll(s,2),'attaching_safety')
                self.assertEqual((Path(tmp)/'request.json').read_text(),req)
                self.assertEqual(c.client.calls,0)
            finally:
                if c.safety:c.safety.close()
    def test_close_signals_native_parking_instead_of_leaving_player_idle(self):
        from build_supervisor import SafetyHeartbeat
        with tempfile.TemporaryDirectory() as tmp:
            h=SafetyHeartbeat(tmp,'w');h.start();h.attached=True;h.close()
            beat=json.loads((Path(tmp)/('supervision-heartbeat-'+h.id+'.json')).read_text())
            self.assertTrue(beat['finished']);self.assertEqual(beat['world_session'],'w')
    def test_hung_loop_does_not_keep_player_online_forever(self):
        from build_supervisor import SafetyHeartbeat
        with tempfile.TemporaryDirectory() as tmp:
            h=SafetyHeartbeat(tmp,'w');h.last_poll=time.monotonic()-20;h.start()
            h.thread.join(timeout=3);self.assertFalse(h.thread.is_alive());h.close()

if __name__=='__main__':unittest.main()
