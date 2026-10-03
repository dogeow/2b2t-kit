"""Opt-in deterministic idle jobs. Formal work, player input and protection win."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import math
from pathlib import Path
import time
import uuid

from farm_caretaker import validate_profile as validate_caretaker
from idle_priority import demands
from kit_runtime.journal import write_json
from material_jobs.protocol import server_key
from safety_interlock import require_unlocked

JOBS=('harvest_store','breed','cook_store','plant','fish')
FLAGS=('borer_active','chopping','navigating','printing','planter_active','feeder_active',
       'fisher_active','guide_active','guard_busy','health_recovery_hold','air_return_active','guard_reconnect_pending')
DEFAULT_COOLDOWNS={'harvest_store':120,'breed':300,'cook_store':300,'plant':600,'fish':240}


class IdleYield(BaseException):
    """Intentional cancellation escapes primitive/finish error fallback; scheduler alone handles it."""
    pass


def read(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>2_000_000:raise ValueError('Idle service file is missing or oversized: '+str(path))
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise ValueError('Idle service file must contain an object')
    return value


def default_profile(caretaker_profile=None):
    return {'schema':1,'authorized':False,'server':'example.test','dimension':'minecraft:overworld',
            'caretaker_profile':caretaker_profile,'plant_registries':[],
            'jobs':['harvest_store','breed','cook_store','plant','fish'],
            'poll_seconds':.2,'quiet_seconds':5,'cooldowns':dict(DEFAULT_COOLDOWNS),
            'fishing':{'enabled':False,'shore':None,'duration_seconds':90,'minimum_free_slots':8}}


def validate_profile(value):
    p=deepcopy(value)
    if (not isinstance(p,dict) or p.get('schema')!=1 or p.get('authorized') is not True
            or not isinstance(p.get('server'),str) or not p['server'].strip()
            or p.get('dimension')!='minecraft:overworld'):
        raise ValueError('An explicitly authorized idle profile for one registered Overworld is required')
    p['server']=server_key(p['server'])
    jobs=p.setdefault('jobs',list(JOBS))
    if not isinstance(jobs,list) or not jobs or len(set(jobs))!=len(jobs) or any(j not in JOBS for j in jobs):
        raise ValueError('Idle jobs must be a unique bounded supported list')
    for key,default,low,high in (('poll_seconds',.2,.1,1),('quiet_seconds',5,5,60)):
        p.setdefault(key,default)
        if type(p[key]) not in (int,float) or not math.isfinite(p[key]) or not low<=p[key]<=high:raise ValueError('Invalid idle '+key)
    cooldowns=p.setdefault('cooldowns',dict(DEFAULT_COOLDOWNS))
    if not isinstance(cooldowns,dict):raise ValueError('Idle cooldowns must be an object')
    for job in JOBS:
        cooldowns.setdefault(job,DEFAULT_COOLDOWNS[job])
        if type(cooldowns[job])is not int or not 10<=cooldowns[job]<=86400:raise ValueError('Invalid job cooldown')
    if p.get('caretaker_profile') is not None and not isinstance(p['caretaker_profile'],str):raise ValueError('Caretaker profile must be an explicit path')
    registries=p.setdefault('plant_registries',[])
    if not isinstance(registries,list) or len(registries)>8 or any(not isinstance(path,str) for path in registries):raise ValueError('Use at most eight explicit planting registries')
    fishing=p.setdefault('fishing',{'enabled':False,'shore':None})
    if not isinstance(fishing,dict) or type(fishing.get('enabled'))is not bool:raise ValueError('Fishing must be explicitly enabled or disabled')
    fishing.setdefault('duration_seconds',90);fishing.setdefault('minimum_free_slots',8)
    if type(fishing['duration_seconds'])is not int or not 10<=fishing['duration_seconds']<=300:raise ValueError('Fishing duration must be10..300 seconds')
    if type(fishing['minimum_free_slots'])is not int or not 8<=fishing['minimum_free_slots']<=16:raise ValueError('Fishing requires8..16 empty slots')
    if fishing['enabled']:
        shore=fishing.get('shore')
        if not isinstance(shore,dict) or shore.get('authorized') is not True:raise ValueError('Fishing needs an explicitly registered safe shore')
        for name in ('stand','water'):
            pos=shore.get(name)
            if (not isinstance(pos,list) or len(pos)!=3 or any(type(v)not in(int,float) or not math.isfinite(v) for v in pos)
                    or abs(pos[0])>30_000_000 or abs(pos[2])>30_000_000 or not -63<=pos[1]<=315
                    or name=='water' and any(type(v)is not int for v in pos)):
                raise ValueError('Fishing shore needs bounded stand/water coordinates')
        if not .5<=math.dist(shore['stand'],shore['water'])<=5:raise ValueError('Fishing water must be near the registered dry shore')
        for key in ('yaw','pitch'):
            if type(shore.get(key))not in(int,float) or not math.isfinite(shore[key]):raise ValueError('Register the exact fishing view')
        if not 0<=shore['pitch']<=60:raise ValueError('Fishing view must face the verified near water')
    return p


def owns_read_only_request(runner,state):
    c=getattr(runner,'client',None)
    if c is None:return False
    inflight=getattr(c,'native_inflight',None);envelope=inflight
    if not isinstance(envelope,dict) or envelope.get('op')not in ('scan','snapshot'):
        evidence=getattr(c,'last_terminal_evidence',None)
        if not isinstance(evidence,dict) or evidence.get('phase')!='done':return False
        envelope={**evidence,'expected_revision':evidence.get('revision_after')}
    last_matches=envelope.get('request_id')==getattr(c,'last',None)
    if not last_matches and isinstance(inflight,dict) and inflight.get('op')=='material_session':
        # A new session mailbox can be published while status still describes
        # the just-completed constructor scan. Admit only that exact predecessor
        # with the unchanged original parking lease and revision.
        opening=getattr(runner,'opening_state',None)or{}
        last_matches=bool(inflight.get('request_id')==getattr(c,'last',None)
            and inflight.get('world_session')==state.get('world_session')
            and inflight.get('base_revision')==state.get('control_revision')
            and state.get('supervision_lease')==opening.get('supervision_lease'))
    return bool(envelope.get('op') in ('scan','snapshot')
        and last_matches and envelope.get('request_id')==state.get('last_request')
        and envelope.get('world_session')==getattr(c,'world',None)==state.get('world_session')
        and envelope.get('expected_revision')==state.get('control_revision')==getattr(c,'rev',None)
        and (state.get('idle_activity')or{}).get('conflicts')==[envelope['op']])


def busy_reason(root,profile,state,*,runner=None,hid_idle=None,now_ms=None):
    now=int(time.time()*1000) if now_ms is None else now_ms
    if type(state.get('time'))is not int or not -1000<=now-state['time']<=2500:return 'STALE_STATE'
    if (state.get('connected') is not True or server_key(state.get('server'))!=profile['server']
            or state.get('dimension')!=profile['dimension'] or not isinstance(state.get('world_session'),str)
            or not state['world_session'] or type(state.get('control_revision'))is not int or state['control_revision']<0):return 'WORLD_UNAVAILABLE'
    pos=state.get('pos')
    if not isinstance(pos,list) or len(pos)!=3 or any(type(v)not in(int,float) or not math.isfinite(v) for v in pos):return 'POSITION_UNAVAILABLE'
    try:require_unlocked(root,state)
    except (RuntimeError,ValueError,OSError):return 'SAFETY_HOLD'
    if state.get('health')!=20 or type(state.get('food'))is not int or state['food']<18 or state.get('under_water') is not False:return 'SURVIVAL_NOT_READY'
    if state.get('manual_movement') is not False or state.get('screen')!='':return 'PLAYER_INPUT'
    # Foreground/background or CmdTab is not movement. Real game input and
    # pose stillness govern the service's continuous quiet timer below.
    menu=state.get('menu') or {};cursor=menu.get('cursor') or {}
    if menu.get('type')!='InventoryMenu' or type(cursor.get('count'))is not int or cursor['count']!=0:return 'INVENTORY_BUSY'
    activity=state.get('idle_activity')
    if (state.get('idle_activity_protocol')!=1 or not isinstance(activity,dict)
            or type(activity.get('busy'))is not bool or not isinstance(activity.get('conflicts'),list)):
        return 'WAIT_ACTIVITY_CAPABILITY'
    own_read=owns_read_only_request(runner,state)
    if activity['busy'] and not own_read:return 'OTHER_INPUT_OWNER:'+','.join(map(str,activity['conflicts']))
    owned=runner is not None and runner.owns(state)
    if state.get('native_material_busy') is True and not owned:return 'NATIVE_BUSY'
    for flag in FLAGS:
        if state.get(flag) is True and not (owned and flag=='fisher_active' and runner.job=='fish' or owned and flag=='navigating'):
            return 'BUSY:'+flag
        if flag in state and type(state[flag])is not bool:return 'UNKNOWN_ACTIVITY:'+flag
    task=state.get('material_task')
    if not isinstance(task,dict) or any(type(task.get(k))is not bool for k in ('occupied','process_alive','cancelling')):return 'UNKNOWN_MATERIAL_TASK'
    if any(task[k] for k in ('occupied','process_alive','cancelling')):return 'FORMAL_MATERIAL_TASK'
    for name in ('build_job','concrete','professional_printer','gravel','projection_batch'):
        job=state.get(name) or {}
        if not isinstance(job,dict):return 'UNKNOWN_ACTIVITY:'+name
        if job.get('active') is True or name=='professional_printer' and job.get('enabled') is True:return 'BUSY:'+name
    lease=state.get('supervision_lease') or {}
    if not isinstance(lease,dict):return 'UNKNOWN_LEASE'
    if lease and not owned:
        if not (lease.get('kind')=='parking' and lease.get('world_session')==state['world_session']
                and lease.get('revision')==state.get('control_revision') and state.get('guard_armed') is True
                and state.get('guard_pve_only') is True and state.get('flight') is True):return 'FOREIGN_LEASE'
    if state.get('phase')=='running' and not owned and not own_read:return 'NATIVE_BUSY'
    if demands(root,state['world_session'],now_ms=now):return 'FOREGROUND_DEMAND'
    return None


class IdleService:
    def __init__(self,root,profile,*,observer=None,runner_factory=None,clock=time.time,hid_idle=None):
        self.root=Path(root);self.profile=validate_profile(profile);self.clock=clock
        self.key=hashlib.sha256((self.profile['server']+'|'+self.profile['dimension']).encode()).hexdigest()[:20]
        self.home=self.root/'idle-services'/self.key;self.home.mkdir(parents=True,exist_ok=True)
        self.path=self.home/'service.json';self.lock_path=self.home/'worker.lock';self.control=self.home/'control.json'
        self.lock_path.touch(exist_ok=True)
        self.book=read(self.path) if self.path.exists() else {'schema':1,'profile':self.profile,'enabled':False,'paused':False,
            'reason':'NOT_STARTED','world_session':None,'sequence':0,'pending':None,'active_job':None,'rotation':0,'due':{},'ai_calls':0}
        if self.book.get('schema')!=1 or self.book.get('profile')!=self.profile or self.book.get('ai_calls')!=0:raise ValueError('Original idle profile/journal changed; no bypass')
        self.observer=observer or self._observe;self.runner_factory=runner_factory or self._runner
        # Retain the optional legacy argument for callers, but never sample OS HID.
        self.runner=None;self.quiet_since=None;self.quiet_pos=None;self.last_owner=0
        self.last_owner_identity=None
        self.last_saved=self.path.read_text() if self.path.exists() else None;self.last_event=None
        if not self.path.exists():self.save()
    def _observe(self):
        from live_snapshot import read_fresh
        return read_fresh(self.root)
    def _runner(self,service,job,directory):
        from idle_service_native import NativeRunner
        return NativeRunner(service,job,directory)
    def status(self):return deepcopy(self.book)
    def save(self):
        payload=json.dumps(self.book,sort_keys=True,ensure_ascii=False)
        if payload!=self.last_saved:write_json(self.path,self.book);self.last_saved=payload
    def event(self,reason):
        value={'phase':self.book.get('active_job') or 'waiting','reason':reason,'pending_unknown':bool(self.book.get('pending') and self.book.get('reason')=='WAIT_RECONCILE')}
        if value!=self.last_event:
            with (self.home/'events.jsonl').open('a') as stream:stream.write(json.dumps({'time':self.clock(),**value},ensure_ascii=False)+'\n')
            self.last_event=value
    @contextmanager
    def worker_lock(self):
        with self.lock_path.open('rb') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as error:raise RuntimeError('Another idle worker owns this server/dimension') from error
            try:yield
            finally:fcntl.flock(lock,fcntl.LOCK_UN)
    def command(self,action):
        if action not in ('pause','stop','resume'):raise ValueError('Invalid idle control')
        request={'id':uuid.uuid4().hex,'action':action,'key':self.key};write_json(self.control,request);return request
    def _controls(self):
        if not self.control.exists():return
        control=read(self.control)
        if control.get('key')!=self.key or control.get('action') not in ('pause','stop','resume'):raise RuntimeError('Invalid idle control file')
        if control.get('id')==self.book.get('last_control'):return
        self.book['last_control']=control['id']
        if control['action']=='resume':
            if self.book.get('pending'):self.book['reason']='WAIT_RECONCILE'
            else:self.book.update(enabled=True,paused=False,reason='');self.quiet_since=None
        else:
            self.book.update(paused=True,reason='USER_'+control['action'].upper())
            if control['action']=='stop':self.book['enabled']=False
        self.save()
    def publish_owner(self,state,*,released=False,force=False):
        identity=self.runner.identity() if self.runner else {}
        signature=(self.book.get('world_session'),identity.get('task_session'),identity.get('lease_id'),state.get('control_revision'),released)
        if not force and signature==self.last_owner_identity and self.clock()-self.last_owner<.4:return
        self.last_owner=self.clock();self.last_owner_identity=signature
        write_json(self.root/'idle-service-owner.json',{'schema':1,'idle_service_id':self.key,'pid':__import__('os').getpid(),
            'lock_path':str(self.lock_path.resolve()),'world_session':self.book.get('world_session'),
            'updated_at':int(self.clock()*1000),'input_released':released,'phase':self.book.get('reason'),
            'pending_unknown':bool(self.book.get('pending')),'task_session':identity.get('task_session'),
            'lease_id':identity.get('lease_id'),'revision':state.get('control_revision')})
    def checkpoint(self,state=None):
        self._controls();state=state or self.observer();self.publish_owner(state)
        if self.book.get('world_session') is not None and state.get('world_session')!=self.book['world_session']:raise IdleYield('WORLD_SESSION_CHANGED')
        if demands(self.root,state.get('world_session'),now_ms=int(self.clock()*1000)):raise IdleYield('FOREGROUND_DEMAND')
        activity=state.get('idle_activity') or {}
        # Native movement advances revision before the next owner file/status frame.
        # Publish the strict witnessed revision, then re-observe instead of treating
        # the old snapshot's own-input conflict as a foreign controller.
        if (self.runner is not None and self.runner.owns(state) and state.get('idle_activity_protocol')==1
                and (activity.get('busy') is True or activity.get('idle_task_session')!=self.runner.identity().get('task_session'))):
            deadline=time.monotonic()+.5
            while time.monotonic()<deadline:
                self._controls()
                if self.book['paused']or not self.book['enabled']:raise IdleYield(self.book['reason']or'USER_STOP')
                if demands(self.root,state.get('world_session'),now_ms=int(self.clock()*1000)):raise IdleYield('FOREGROUND_DEMAND')
                fresh=self.observer()
                if fresh.get('manual_movement') is not False or fresh.get('screen')!='':raise IdleYield('PLAYER_INPUT')
                try:require_unlocked(self.root,fresh)
                except (RuntimeError,ValueError,OSError):raise IdleYield('SAFETY_HOLD')
                if fresh.get('world_session')!=self.book['world_session']:raise IdleYield('WORLD_SESSION_CHANGED')
                if fresh.get('health')!=20 or fresh.get('food',0)<18 or fresh.get('under_water')is not False:raise IdleYield('SURVIVAL_NOT_READY')
                if fresh.get('guard_busy')is True:raise IdleYield('BUSY:guard_busy')
                if type(fresh.get('time'))is int and fresh['time']>state.get('time',0):
                    state=fresh;self.publish_owner(state)
                    if not self.runner.owns(state):break
                    activity=state.get('idle_activity')or{}
                    if (activity.get('busy')is False and activity.get('idle_task_session')==self.runner.identity().get('task_session')):break
                time.sleep(.025)
        reason='USER_STOP' if not self.book['enabled'] else self.book['reason'] if self.book['paused'] else busy_reason(
            self.root,self.profile,state,runner=self.runner,now_ms=int(self.clock()*1000))
        if reason:raise IdleYield(reason)
    def start(self):
        if self.book.get('pending'):raise RuntimeError('Unknown original idle action must be reviewed; no replay')
        state=self.observer();require_unlocked(self.root,state)
        if state.get('connected') is not True or server_key(state.get('server'))!=self.profile['server'] or state.get('dimension')!=self.profile['dimension']:raise RuntimeError('Idle service scope is unavailable')
        self.book.update(enabled=True,paused=False,reason='',world_session=state['world_session']);self.quiet_since=None;self.save()
    def _finish(self,reason,normal=False):
        if self.runner is None:return
        runner=self.runner
        try:reply=runner.stop(reason,normal=normal)
        except IdleYield as yielded:reply=runner.stop(str(yielded),normal=False)
        except Exception as error:reply={'released':False,'unknown':True,'detail':str(error)}
        unknown=reply.get('unknown') is not False or reply.get('released') is not True
        if unknown:self.book.update(paused=True,reason='WAIT_RECONCILE')
        else:
            job=self.book['active_job'];self.book['due'][job]=self.clock()+self.profile['cooldowns'][job]
            self.book.update(pending=None,active_job=None,reason=reason)
        self.book['last_stop']=reply;self.runner=None;self.quiet_since=None;self.save()
        self.publish_owner(self.observer(),released=reply.get('released') is True,force=True);self.event(self.book['reason'])
    def tick(self):
        try:
            self._controls();state=self.observer()
            if self.book.get('world_session') is not None and state.get('world_session')!=self.book['world_session']:
                self._finish('WORLD_SESSION_CHANGED');self.book.update(enabled=False,paused=True,reason='WORLD_SESSION_CHANGED');self.save();return self.status()
            reason=busy_reason(self.root,self.profile,state,runner=self.runner,now_ms=int(self.clock()*1000))
            if self.runner is not None:
                if reason or self.book['paused'] or not self.book['enabled']:
                    self._finish(reason or self.book['reason'] or 'USER_STOP');return self.status()
                if self.runner.job=='fish':
                    if self.runner.should_finish(state):self._finish('FISH_INTERVAL_COMPLETE',normal=True)
                    else:self.publish_owner(state)
                    return self.status()
            if self.book.get('pending'):
                self.book.update(paused=True,reason='WAIT_RECONCILE');self.save();self.event('WAIT_RECONCILE');self.publish_owner(state,released=self.book.get('last_stop',{}).get('released') is True);return self.status()
            if self.book['paused'] or not self.book['enabled']:
                self.publish_owner(state,released=True);return self.status()
            if reason:
                self.quiet_since=None;self.book['reason']=reason;self.save();self.event(reason);self.publish_owner(state,released=True);return self.status()
            pos=state.get('pos')
            if not isinstance(pos,list) or len(pos)!=3:return self.status()
            if self.quiet_pos is None or math.dist(pos,self.quiet_pos)>.05:self.quiet_since=None
            self.quiet_pos=pos[:]
            if self.quiet_since is None:self.quiet_since=self.clock()
            if self.clock()-self.quiet_since<self.profile['quiet_seconds']:
                self.book['reason']='WAIT_QUIET';self.save();self.publish_owner(state,released=True);return self.status()
            available=[j for j in self.profile['jobs'] if self.book['due'].get(j,0)<=self.clock()]
            if not available:
                self.book['reason']='WAIT_COOLDOWN';self.save();self.event('WAIT_COOLDOWN');self.publish_owner(state,released=True);return self.status()
            jobs=self.profile['jobs'];job=next(jobs[(self.book['rotation']+i)%len(jobs)] for i in range(len(jobs)) if jobs[(self.book['rotation']+i)%len(jobs)] in available)
            self.book['rotation']=(jobs.index(job)+1)%len(jobs);self.book['sequence']+=1
            directory=self.home/('job-%06d-%s'%(self.book['sequence'],job));directory.mkdir()
            self.book.update(active_job=job,reason='',pending={'job':job,'directory':str(directory),'world_session':state['world_session']});self.save();self.event('DISPATCH')
            self.runner=self.runner_factory(self,job,directory);self.publish_owner(state,force=True)
            try:reply=self.runner.run(state)
            except IdleYield as yielded:self._finish(str(yielded));return self.status()
            if not isinstance(reply,dict) or reply.get('pending') is not False:
                self._finish('WAIT_RECONCILE');return self.status()
            self.book['last_result']=reply;self.save()
            if reply.get('phase')=='active':return self.status()
            self._finish(reply.get('code') or reply.get('phase') or 'JOB_COMPLETE',normal=reply.get('phase') in ('done','idle'))
        except Exception as error:
            self._finish('WAIT_SERVICE');self.book.update(paused=True,reason='WAIT_SERVICE',detail=str(error));self.save();self.event('WAIT_SERVICE')
        return self.status()
    def run(self,*,sleep=time.sleep):
        with self.worker_lock():
            self.book=read(self.path);self.start()
            try:
                while self.book['enabled']:
                    self.tick();sleep(self.profile['poll_seconds'])
            finally:self._finish('WORKER_STOPPED')
        return self.status()
