import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from decision_advisor import Advisor,reserve_call


def state():
    return {'connected':True,'world_session':'world','control_revision':1,'server':'test','dimension':'minecraft:overworld',
            'health':18.9,'food':18,'guard_armed':True,'guard_busy':False,'pos':[1,100,1],
            'air_supply':300,'inventory':[{'slot':3,'item':'minecraft:cooked_porkchop','count':2}]}

class Model:
    calls=0
    def predict(self,s,q):
        self.calls+=1;choices=q['action']['criteria']
        return {'model':'test-jev','answers':{'action':{'type':'choice','choice':'eat','confidence':.9,
            'probabilities':{k:(1 if k=='eat' else 0) for k in choices}}}}
    def close(self):pass

class AdvisorTest(unittest.TestCase):
    def make(self,path,model,**settings):
        path=Path(path);(path/'settings.json').write_text(json.dumps(settings))
        return Advisor(path,path,lambda:model)
    def test_typed_decision_cached_with_logged_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=Model();a=self.make(tmp,model);s=state();options={'eat':'Eat safely','wait':'Wait'}
            first=a.select('Recover safely',options,lambda:s)
            self.assertEqual(('jev','eat'),(first['source'],first['choice']))
            second=a.select('Recover safely',options,lambda:s)
            self.assertEqual('cache',second['source']);self.assertEqual(1,model.calls)
            a.outcome(first,'food_increased',before=18,after=20)
            rows=[json.loads(v) for v in (Path(tmp)/'jev-decisions.jsonl').read_text().splitlines()]
            self.assertEqual(first['id'],rows[-1]['decision_id'])
    def test_no_model_call_during_urgent_or_manual_state(self):
        for change in ({'health':13},{'under_water':True},{'guard_busy':True},{'manual_movement':True},{'safety_hold':{'active':True}}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as tmp:
                model=Model();a=self.make(tmp,model);s={**state(),**change}
                r=a.select('Recover safely',{'eat':'Eat','wait':'Wait'},lambda:s)
                self.assertEqual('wait',r['choice']);self.assertEqual(0,model.calls)
    def test_late_answer_after_manual_input_is_discarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate=threading.Event();s=state()
            class Slow(Model):
                def predict(self,st,q):gate.wait(.5);return super().predict(st,q)
            a=self.make(tmp,Slow());reads=[0]
            def read():
                reads[0]+=1
                if reads[0]>2:s['manual_movement']=True
                return dict(s)
            try:
                r=a.select('Recover safely',{'eat':'Eat','wait':'Wait'},read)
                self.assertEqual('state_changed',r['reason'])
            finally:gate.set()
    def test_budget_shared_across_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=Model();a=self.make(tmp,m,calls_per_hour=1);b=Advisor(tmp,tmp,lambda:m)
            a.select('Recover safely',{'eat':'Eat','wait':'Wait'},state)
            self.assertEqual('hourly_budget',b.select('Recover safely',{'eat':'Eat','wait':'Wait'},state)['reason'])
            self.assertEqual(1,m.calls)
    def test_timeout_is_bounded_and_does_not_block_safety_polls(self):
        with tempfile.TemporaryDirectory() as tmp:
            gate=threading.Event();polls=[]
            class Slow(Model):
                def predict(self,s,q):gate.wait(1);return super().predict(s,q)
            a=self.make(tmp,Slow(),timeout_seconds=.1)
            def read():polls.append(time.monotonic());return state()
            try:
                r=a.select('Recover safely',{'eat':'Eat','wait':'Wait'},read)
                self.assertEqual('timeout',r['reason']);self.assertGreaterEqual(len(polls),3)
            finally:gate.set()
    def test_unoffered_model_action_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=self.make(tmp,Model())
            r=a.select('Recover safely',{'rest':'Rest','wait':'Wait'},state)
            self.assertEqual(('wait','provider_error'),(r['choice'],r['reason']))
    def test_inventory_change_invalidates_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=Model();a=self.make(tmp,m);s=state();options={'eat':'Eat','wait':'Wait'}
            a.select('Recover safely',options,lambda:s)
            s['inventory'][0]['count']=1
            self.assertEqual('jev',a.select('Recover safely',options,lambda:s)['source'])
            self.assertEqual(2,m.calls)

if __name__=='__main__':unittest.main()

class AdvisorReliabilityTest(unittest.TestCase):
 def test_mutable_inventory_cannot_rewrite_the_original_decision_snapshot(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=state();gate=threading.Event();reads=[0]
   class Slow(Model):
    def predict(self,st,q):gate.wait(.5);return super().predict(st,q)
   a=Advisor(tmp,Path(tmp)/'settings',lambda:Slow())
   def read():
    reads[0]+=1
    if reads[0]>1:s['inventory'][0]['count']=1
    return s
   try:self.assertEqual('state_changed',a.select('Recover',{'eat':'Eat','wait':'Wait'},read)['reason'])
   finally:gate.set()
 def test_provider_failure_backs_off_without_spending_another_call(self):
  with tempfile.TemporaryDirectory() as tmp:
   class Failing(Model):
    def predict(self,s,q):self.calls+=1;raise RuntimeError('offline provider')
   m=Failing();a=Advisor(tmp,Path(tmp)/'settings',lambda:m);options={'eat':'Eat','wait':'Wait'}
   self.assertEqual('provider_error',a.select('Recover',options,state)['reason']);self.assertEqual('provider_backoff',a.select('Recover',options,state)['reason']);self.assertEqual(1,m.calls)
 def test_broken_diagnostic_sink_does_not_change_validated_choice(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   a=Advisor(tmp,Path(tmp)/'settings',lambda:Model())
   with patch.object(a.events,'emit',side_effect=OSError('read-only')):result=a.select('Recover',{'eat':'Eat','wait':'Wait'},state)
   self.assertEqual('eat',result['choice']);self.assertFalse(result['log_written'])
 def test_corrupt_shared_budget_fails_closed_without_a_provider_request(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=Model();settings=Path(tmp)/'settings';a=Advisor(tmp,settings,lambda:m);(settings/'calls.json').write_text('[{"bad":1}]')
   self.assertEqual('budget_unavailable',a.select('Recover',{'eat':'Eat','wait':'Wait'},state)['reason']);self.assertEqual(0,m.calls)

class AdvisorCacheBudgetTest(unittest.TestCase):
 def test_fresh_safety_hold_or_changed_state_discards_a_cached_action(self):
  for change in ({'safety_hold':{'active':True}}, {'guard_busy':True},
                 {'manual_movement':True}, {'health':13}, {'pos':[4,100,1]}):
   with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
    m=Model();a=Advisor(tmp,Path(tmp)/'settings',lambda:m);options={'eat':'Eat','wait':'Wait'}
    self.assertEqual('jev',a.select('Recover',options,state)['source'])
    readings=iter((state(),{**state(),**change}))
    result=a.select('Recover',options,lambda:next(readings))
    self.assertEqual(('wait','local','state_changed'),
                     (result['choice'],result['source'],result['reason']))
    self.assertEqual(1,m.calls)
 def test_cache_is_available_during_provider_backoff_without_repeat_token_usage(self):
  with tempfile.TemporaryDirectory() as tmp:
   class Metered(Model):
    def predict(self,s,q):return {**super().predict(s,q),'usage':{'input_tokens':12,'output_tokens':3}}
   m=Metered();a=Advisor(tmp,Path(tmp)/'settings',lambda:m);options={'eat':'Eat','wait':'Wait'}
   first=a.select('Recover',options,state);self.assertEqual(12,first['usage']['input_tokens'])
   a.provider_failed();cached=a.select('Recover',options,state)
   self.assertEqual('cache',cached['source']);self.assertEqual(0,cached['elapsed_ms']);self.assertEqual(0,cached['usage']['input_tokens']);self.assertEqual(1,m.calls)

class AdvisorInputBudgetTest(unittest.TestCase):
 def test_raw_world_dump_is_not_sent_to_the_model(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=Model();a=Advisor(tmp,Path(tmp)/'settings',lambda:m)
   r=a.select('Recover',{'eat':'Eat','wait':'Wait'},state,{'raw_world':'x'*12001})
   self.assertEqual('context_too_large_or_invalid',r['reason']);self.assertEqual(0,m.calls)
 def test_nonfinite_context_is_not_sent_to_the_model(self):
  with tempfile.TemporaryDirectory() as tmp:
   m=Model();a=Advisor(tmp,Path(tmp)/'settings',lambda:m)
   r=a.select('Recover',{'eat':'Eat','wait':'Wait'},state,{'risk':float('nan')})
   self.assertEqual('context_too_large_or_invalid',r['reason']);self.assertEqual(0,m.calls)
