"""Shared bounded Jev choices for Kit controllers and the operator CLI.

Candidates are supplied by local code. This module can never execute a game
command, unlock a health hold, or create a candidate from model output.
"""
from copy import deepcopy
import argparse
import fcntl
import hashlib
import json
import math
import time
import uuid
from pathlib import Path
from background_decision import DecisionMailbox
from kit_runtime.diagnostics import EventLog
from decisions import PRIVATE,Jev,choose,DecisionError,status

DEFAULTS={'enabled':True,'calls_per_hour':120,'timeout_seconds':4,
          'cache_seconds':60,'min_confidence':.5,'min_probability':.6,'provider_retry_seconds':30}
FIELDS=('world_session','control_revision','server','dimension','connected',
        'manual_movement','screen','health','food','under_water','guard_armed',
        'guard_busy','air_return_active')


def context(state):
    return {**{k:state.get(k) for k in FIELDS},
            'air_band':state.get('air_supply',0)//20,
            'inventory':[(v.get('slot'),v.get('item'),v.get('count'),v.get('durability'))
                         for v in state.get('inventory',[]) if v.get('count',0)>0]}


def stable(before,after):
    return (context(before)==context(after) and
            math.dist(before.get('pos',[0,0,0]),after.get('pos',[1e6]*3))<=2)


def safe_to_consult(state):
    return (state.get('connected') and not state.get('manual_movement') and
            not state.get('screen') and state.get('health',0)>=14 and
            state.get('guard_armed') and not state.get('guard_busy') and
            not state.get('under_water') and not state.get('air_return_active') and
            not state.get('safety_hold',{}).get('active'))


def reserve_call(path,limit,now):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX)
        stream.seek(0);text=stream.read()
        calls=json.loads(text) if text else []
        if not isinstance(calls,list) or any(isinstance(stamp,bool) or not isinstance(stamp,(int,float)) or not math.isfinite(stamp) or stamp<0 for stamp in calls):
            raise ValueError('Invalid shared model budget record')
        calls=[stamp for stamp in calls if now-stamp<3600]
        if len(calls)>=limit:return False
        calls.append(now);stream.seek(0);stream.truncate();json.dump(calls,stream);stream.flush()
        return True


def bounded_scene(scene,limit=12000):
    size=0
    try:
        for chunk in json.JSONEncoder(ensure_ascii=False,allow_nan=False).iterencode(scene):
            size+=len(chunk.encode('utf8'))
            if size>limit:return False
        return True
    except (TypeError,ValueError):return False


class Advisor:
    def __init__(self,out,settings_dir=None,model_factory=Jev):
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True)
        self.settings_dir=Path(settings_dir or PRIVATE/'decision-advisor')
        self.settings_dir.mkdir(parents=True,exist_ok=True)
        path=self.settings_dir/'settings.json'
        with path.with_suffix('.init.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if not path.exists():
                with path.open('x') as stream:json.dump(DEFAULTS,stream,indent=2)
            self.config={**DEFAULTS,**json.loads(path.read_text())}
        c=self.config
        if (not isinstance(c['enabled'],bool) or not 1<=c['calls_per_hour']<=600
                or not .1<=c['timeout_seconds']<=6 or not 0<=c['cache_seconds']<=300
                or not 0<=c['min_confidence']<=1 or not 0<=c['min_probability']<=1
                or not 1<=c['provider_retry_seconds']<=300):
            raise ValueError('Invalid Jev advisor settings')
        self.model_factory=model_factory;self.cache={};self.failures=0;self.retry_after=0
        self.events=EventLog(self.out/'jev-decisions.jsonl');self.logging_error=None
    def log(self,kind,**data):
        try:
            self.events.emit(kind,**data);self.logging_error=None;return True
        except (OSError,ValueError) as error:
            # A diagnostic sink failure must not change the selected safe action.
            self.logging_error=type(error).__name__;return False
    def provider_failed(self):
        self.failures+=1
        self.retry_after=time.monotonic()+min(300,self.config['provider_retry_seconds']*2**min(self.failures-1,4))
    def select(self,goal,candidates,read_state,scene=None,fallback='wait'):
        if not 2<=len(candidates)<=12 or 'wait' not in candidates or fallback not in candidates:
            raise ValueError('Provide 2..12 locally verified choices including wait and fallback')
        if any(not isinstance(k,str) or not 1<=len(k)<=64 or not isinstance(v,str) or not 1<=len(v)<=1000 for k,v in candidates.items()):
            raise ValueError('Candidate IDs and descriptions must be text')
        if not isinstance(goal,str) or not 1<=len(goal)<=500:raise ValueError('A short goal is required')
        before=deepcopy(read_state());candidates=deepcopy(candidates);scene=deepcopy(scene)
        decision_id=uuid.uuid4().hex
        model_call_scheduled=False
        def finish(choice,source,reason=None,answer=None):
            result={'id':decision_id,'choice':choice,'source':source,'reason':reason,
                    'model_call_scheduled':model_call_scheduled}
            if answer:result.update({k:answer[k] for k in ('model','elapsed_ms','confidence','probabilities','usage')})
            if source=='cache':result.update(elapsed_ms=0,usage={'input_tokens':0,'output_tokens':0})
            result['log_written']=self.log('decision',goal=goal,candidates=candidates,scene=scene or {},health=before.get('health'),**result)
            return result
        if not self.config['enabled']:return finish(fallback,'local','advisor_disabled')
        # Emergencies and manual control are never offered to the model.
        if not safe_to_consult(before):return finish('wait','local','urgent_or_unowned_state')
        if not bounded_scene(scene):return finish('wait','local','context_too_large_or_invalid')
        signature=hashlib.sha256(json.dumps([goal,candidates,scene,context(before),[math.floor(v) for v in before.get('pos',[])]],sort_keys=True).encode()).hexdigest()
        cached=self.cache.get(signature)
        if cached and time.monotonic()-cached[0]<self.config['cache_seconds']:
            fresh=read_state()
            if stable(before,fresh) and safe_to_consult(fresh):
                return finish(cached[1]['choice'],'cache',answer=cached[1])
            return finish('wait','local','state_changed')
        if time.monotonic()<self.retry_after:return finish(fallback,'local','provider_backoff')
        try:
            if not reserve_call(self.settings_dir/'calls.json',self.config['calls_per_hour'],time.time()):
                return finish(fallback,'local','hourly_budget')
        except (OSError,ValueError):return finish(fallback,'local','budget_unavailable')
        mailbox=DecisionMailbox()
        def work():
            model=self.model_factory()
            try:
                observation={'health':before.get('health'),'food':before.get('food'),
                             'air':before.get('air_supply'),'guarded':True,'under_water':False,
                             'facts':scene or {}}
                return choose(model,goal,candidates,observation)
            finally:model.close()
        mailbox.submit(context(before),work)
        model_call_scheduled=True
        start=time.monotonic()
        try:
            while time.monotonic()-start<self.config['timeout_seconds']:
                # Also refreshes the owning controller heartbeat. No gameplay
                # actions run in the network worker; stale answers are discarded.
                fresh=read_state()
                if not stable(before,fresh) or not safe_to_consult(fresh):
                    return finish('wait','local','state_changed')
                delivery=mailbox.take()
                if delivery:
                    if 'error' in delivery:
                        self.provider_failed()
                        self.log('provider_failure',error_type=type(delivery['error']).__name__)
                        return finish(fallback,'local','provider_error')
                    self.failures=0;self.retry_after=0
                    answer=delivery['response'];key=answer['choice']
                    if (answer['confidence']<self.config['min_confidence'] or
                            answer['probabilities'][key]<self.config['min_probability']):
                        return finish(fallback,'local','uncertain',answer)
                    self.cache[signature]=(time.monotonic(),answer)
                    return finish(key,'jev',answer=answer)
                time.sleep(.05)
            self.provider_failed()
            return finish(fallback,'local','timeout')
        finally:mailbox.close()
    def outcome(self,decision,result,**evidence):
        self.log('outcome',decision_id=decision['id'],choice=decision['choice'],result=result,evidence=evidence)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--automation',type=Path,default=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();plan=json.loads(args.plan.read_text())
    from safety_interlock import require_unlocked
    require_unlocked(args.automation)
    advisor=Advisor(args.out)
    answer=advisor.select(plan['goal'],plan['candidates'],lambda:status(args.automation),plan.get('scene'))
    (args.out/'decision.json').write_text(json.dumps(answer,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(answer,ensure_ascii=False))

if __name__=='__main__':main()
