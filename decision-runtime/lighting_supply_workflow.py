"""Local lighting + native torch restock; no model, UI, reconnect or request replay."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import time

from lighting_cli import stock, write_json
from material_task_client import MaterialTaskClient, make_request, send
from safety_interlock import require_unlocked
from material_jobs.protocol import server_key


class WorkflowWaiting(RuntimeError):pass


class LightingSupplyWorkflow:
    def __init__(self, factory, *, target=128, max_supplies=32, observer=None,
                 sender=None, task_status=None, sleeper=time.sleep):
        if type(target)is not int or not 64<=target<=512 or type(max_supplies)is not int or not 1<=max_supplies<=64:
            raise ValueError('Use a bounded torch backpack target and supply budget')
        self.factory,self.target,self.maximum=factory,target,max_supplies
        worker=factory();self.root,self.out=worker.root,worker.out
        self.path=self.out/'supply-workflow.json';self.profile=worker.profile
        self.observe=observer or worker.observer;self.sleep=sleeper
        self.send=sender or (lambda request:send(self.root,request))
        self.task_status=task_status or MaterialTaskClient(self.root).status
        self.book=json.loads(self.path.read_text()) if self.path.exists() else {
            'schema':1,'profile':self.profile,'target':target,'max_supplies':max_supplies,
            'pending':None,'supplies':[],'phase':'ready','ai_calls':0}
        if any(self.book.get(k)!=v for k,v in (('schema',1),('profile',self.profile),('target',target),('max_supplies',max_supplies))):
            raise WorkflowWaiting('Original workflow configuration changed')
    def save(self):write_json(self.path,self.book)
    def gate(self,state,world=None):
        require_unlocked(self.root,state)
        if (state.get('connected')is not True or state.get('manual_movement')is not False
                or server_key(state.get('server'))!=self.profile['server']
                or state.get('dimension')!=self.profile['dimension']
                or state.get('health',0)<18 or state.get('screen')
                or world is not None and state.get('world_session')!=world):
            raise WorkflowWaiting('World, safety, or human control changed; no new work')
    def begin_supply(self):
        if self.book['pending']:raise WorkflowWaiting('Original supply already exists; never resubmit')
        state=self.observe();self.gate(state)
        lease=state.get('supervision_lease')or{}
        if (state.get('material_task',{}).get('occupied') or state.get('material_task',{}).get('process_alive')
                or any(state.get(key) for key in ('borer_active','planter_active','feeder_active','fisher_active',
                                                  'navigating','chopping','printing','native_material_busy','guard_busy'))
                or state.get('health')!=20 or state.get('flight')is not True
                or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
                or lease.get('kind')!='parking' or lease.get('world_session')!=state['world_session']
                or lease.get('revision')!=state.get('control_revision')):
            raise WorkflowWaiting('Another controller or unsafe parking is active')
        if len(self.book['supplies'])>=self.maximum:raise WorkflowWaiting('Explicit supply budget reached')
        request=make_request('material_task_start',state,mode='item',item='minecraft:torch',count=self.target)
        self.book['pending']={'request':request,'world_session':state['world_session'],'job_id':None}
        self.book['phase']='supply_intent';self.save()
        reply=self.send(request)
        if reply.get('phase')!='done' or not reply.get('material_task',{}).get('id'):
            self.book['pending']['rejection']=reply;self.save()
            raise WorkflowWaiting('Original supply was rejected; kept for inspection')
        self.book['pending']['job_id']=reply['material_task']['id']
        self.book['pending']['acceptance']=reply;self.book['phase']='supplying';self.save()
    def finish_supply(self):
        pending=self.book['pending'];world=pending['world_session'];job=pending.get('job_id')
        if not job:raise WorkflowWaiting('Original start outcome unknown; no replay')
        while True:
            state=self.observe();self.gate(state,world)
            reply=self.task_status(job);task=reply.get('material_task')or{}
            if reply.get('phase')!='done' or task.get('id')!=job:
                raise WorkflowWaiting('Exact native supply task cannot be confirmed')
            if task.get('state') in ('blocked','paused','cancelled','failed'):
                pending['last_task']=task;self.save();raise WorkflowWaiting('Original supply needs attention')
            if task.get('state')=='completed' and task.get('process_alive')is False and task.get('occupied')is False:
                final=self.observe();self.gate(final,world)
                lease=final.get('supervision_lease')or{}
                native=task.get('native_task_session')
                if (stock(final)<self.target or final.get('health')!=20 or final.get('guard_armed')is not True
                        or final.get('guard_pve_only')is not True or final.get('flight')is not True
                        or lease.get('kind')!='parking' or lease.get('revision')!=final.get('control_revision')
                        or native and lease.get('job_session')!=native):
                    raise WorkflowWaiting('Completed task lacks verified inventory or owned guard parking')
                self.book['supplies'].append({'original':pending,'task':task,'backpack_torches':stock(final),
                    'observed_at':final['time'],'world_session':world,'replayed':False})
                self.book.update(pending=None,phase='ready');self.save();return
            self.sleep(1)
    def run(self):
        with (self.out/'.supply-workflow.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:
                while True:
                    worker=self.factory()
                    if worker.status().get('worker_running'):
                        # Observe the specific existing region worker; never compete
                        # for its movement lease or construct another material client.
                        self.gate(self.observe());self.book['phase']='waiting_existing_worker';self.save()
                        self.sleep(2);continue
                    if self.book['pending']:self.finish_supply();continue
                    result=worker.run(resume=True)
                    if result.get('pending'):
                        from lighting_entity_reconcile import ERRORS, reconcile
                        if result['pending'].get('error') in ERRORS:
                            # The exact read-only proof gate retains every original
                            # byte and refuses unknown placement or owner changes.
                            reconcile(worker,allowed_error=result['pending']['error']);continue
                        raise WorkflowWaiting('Original lighting batch needs reconciliation')
                    if result.get('phase')!='waiting_materials':
                        self.book.update(phase=result.get('phase','waiting'),lighting_result=result)
                        self.save();return self.book
                    self.begin_supply();self.finish_supply()
            except (RuntimeError,ValueError,OSError,KeyError) as error:
                self.book.update(phase='waiting',reason=type(error).__name__+': '+str(error));self.save()
                return self.book
