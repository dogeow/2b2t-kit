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
        prior=sum(r.get('outcome')=='prior_finish_unknown' for r in self.book.get('pending_reconciliations',[]))
        if len(self.book['supplies'])+prior>=self.maximum:raise WorkflowWaiting('Explicit supply budget reached')
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
    def reconcile_prior_finish(self, *, expected_job, expected_steps=7, expected_boxes=2, process_probe=None):
        """Archive a settled blocked supply; do not complete or replay its old finish.

        Only local evidence and read-only native task status are consulted. The
        next explicit lighting resume uses fresh carried stock in its new world.
        """
        from copy import deepcopy
        import hashlib
        import os
        import re
        from material_jobs.protocol import fingerprint
        if (not isinstance(expected_job,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',expected_job)
                or type(expected_steps)is not int or not 1<=expected_steps<=256
                or type(expected_boxes)is not int or not 0<=expected_boxes<=36):
            raise ValueError('Exact original job and bounded evidence counts are required')
        def reject(detail):raise WorkflowWaiting(detail)
        def dead(pid):
            if type(pid)is not int or pid<=0:reject('Original worker PID is unavailable')
            if process_probe is not None:return process_probe(pid)is False
            try:os.kill(pid,0)
            except ProcessLookupError:return True
            except PermissionError:return False
            return False
        def safe_current(state):
            self.gate(state)
            lease=state.get('supervision_lease')or{}
            native=state.get('material_task')or{}
            if (type(state.get('time'))is not int or not -1000<=time.time()*1000-state['time']<=3000
                    or not state.get('world_session') or state.get('health')!=20 or state.get('food',0)<18
                    or state.get('under_water')is not False or state.get('flight')is not True
                    or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
                    or stock(state)<self.target or native.get('occupied')is not False
                    or native.get('process_alive')is not False or native.get('cancelling')is not False
                    or native.get('id')!=expected_job or native.get('state')!='blocked'
                    or state.get('native_task_session') or state.get('build_job',{}).get('active')
                    or state.get('professional_printer',{}).get('enabled')
                    or any(state.get(k) for k in ('borer_active','planter_active','feeder_active','fisher_active',
                        'navigating','chopping','printing','native_material_busy','guard_busy'))
                    or lease and (lease.get('kind')!='parking' or lease.get('world_session')!=state['world_session']
                        or lease.get('revision')!=state.get('control_revision'))):
                reject('Fresh guarded inventory or idle native controllers are not confirmed')
        with (self.out/'.supply-workflow.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            worker=self.factory()
            with worker.worker_lock():
                if worker.book.get('pending'):reject('Original lighting outcome remains unresolved')
                raw_workflow=self.path.read_bytes()
                if json.loads(raw_workflow)!=self.book:reject('Workflow changed during reconciliation')
                pending=deepcopy(self.book.get('pending'))
                if not pending or pending.get('job_id')!=expected_job:reject('Exact original pending supply is required')
                original=pending.get('request')or{};world=pending.get('world_session')
                if (original.get('op')!='material_task_start' or original.get('mode')!='item'
                        or original.get('item')!='minecraft:torch' or original.get('count')!=self.target
                        or original.get('world_session')!=world):reject('Original supply request differs')
                evidence={}
                job=(self.root/'material-jobs'/expected_job).resolve()
                def read(path,lines=False):
                    path=Path(path)
                    if path.is_symlink():reject('Evidence symlink is not accepted')
                    raw=path.read_bytes()
                    if len(raw)>8*1024*1024:reject('Evidence exceeds bounded read')
                    evidence[path]=raw
                    return [json.loads(row) for row in raw.splitlines() if row.strip()] if lines else json.loads(raw)
                request=read(job/'request.json');saved=read(job/'status.json');events=read(job/'events.jsonl',True)
                context=request.get('context')or{}
                if (request.get('id')!=expected_job or request.get('mode')!='item'
                        or request.get('targets')!={'minecraft:torch':self.target}
                        or context.get('world_session')!=world or server_key(context.get('server'))!=self.profile['server']
                        or context.get('dimension')!=self.profile['dimension'] or saved.get('id')!=expected_job
                        or saved.get('state')!='blocked' or saved.get('terminal')is not True
                        or saved.get('work_state_before_finish')!='completed'
                        or saved.get('done')!=self.target or saved.get('total')!=self.target
                        or saved.get('steps')!=expected_steps or saved.get('requirements')!={}):
                    reject('Original blocked supply work was not fully settled')
                native_session=saved.get('native_task_session')
                controls=list(job.glob('control-*'))
                if len(controls)!=1:reject('Exactly one original controller journal is required')
                control=controls[0]
                manifest=read(control/('run-manifest-'+str(native_session)+'.json'))
                if (manifest.get('task_session')!=native_session or manifest.get('world_session')!=world
                        or manifest.get('dimension')!=self.profile['dimension'] or manifest.get('complete')is not False):
                    reject('Original incomplete finish manifest differs')
                if len(events)!=expected_steps*2+1 or events[-1].get('kind')!='finish_failed':
                    reject('Action journal has an unknown or unreceipted action')
                receipts=[]
                paths=sorted((job/'receipts').glob('*.json'))
                if len(paths)!=expected_steps:reject('Original action receipt count differs')
                for sequence,path in enumerate(paths,1):
                    record=read(path);receipt=record.get('receipt')or{}
                    started,ended=events[(sequence-1)*2:sequence*2]
                    if (path.name!=f'{sequence:06d}.json' or record.get('job_id')!=expected_job
                            or record.get('sequence')!=sequence or started.get('kind')!='action_started'
                            or ended.get('kind')!='action_receipt' or ended.get('sequence')!=sequence
                            or ended.get('operation')!=record.get('operation') or ended.get('receipt')!=receipt
                            or started!={**{k:v for k,v in record.items() if k!='receipt'},
                                'kind':'action_started','time':started.get('time')}
                            or record.get('operation') not in ('fetch','craft','acquire')
                            or receipt.get('phase') not in ('done','waiting')
                            or receipt.get('phase')=='waiting' and (record['operation']!='fetch'
                                or not receipt.get('missing') or any(type(v)is not int or v<=0 for v in receipt['missing'].values()))
                            or record['operation']=='craft' and (receipt.get('complete')is not True
                                or receipt.get('remaining_targets')!={} )):
                        reject('An original action has no exact settled receipt')
                    receipts.append(record)
                active=read(job/'active-operation.json')
                last=receipts[-1]
                directory=Path(active.get('directory','')).resolve()
                if (directory.parent!=job.resolve() or active.get('name')!=last['operation']
                        or active.get('operation_fingerprint')!=fingerprint({k:v for k,v in last.items() if k!='receipt'})):
                    reject('Active-operation breadcrumb has no matching final receipt')
                result=read(directory/'result.json')
                if (result.get('complete')is not True or result.get('remaining_targets')!={}
                        or any(result.get(k)!=last['receipt'].get(k) for k in result)):
                    reject('Final operation result remains unresolved')
                native_events=read(control/'events.jsonl',True)
                if not native_events:reject('Original native event journal is absent')
                for event in native_events:
                    if (event.get('world_session')!=world or event.get('params',{}).get('task_session')!=native_session
                            or event.get('op') not in ('snapshot','scan') and event.get('phase')!='done'):
                        reject('Original native mutation has an unknown terminal outcome')
                first=native_events[0];lease=first.get('params',{}).get('supervision_lease','')
                if first.get('op')!='material_session' or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',lease):
                    reject('Original native material lease is unavailable')
                finish_receipt=read(self.root/('supervision-receipt-'+lease+'.json'))
                if (finish_receipt.get('lease')!=lease or finish_receipt.get('job_session')!=native_session
                        or (finish_receipt.get('snapshot')or{}).get('world_session')!=world):
                    reject('Original finish receipt belongs to a different job')
                drain=read(control/'finish-drain.json')
                if (drain.get('safe_to_cleanup')is not True or drain.get('reason')!='owned_action_settled'
                        or drain.get('observed',{}).get('world_session')!=world
                        or not any(e.get('request_id')==drain['observed'].get('last_request') and e.get('phase')=='done'
                            for e in native_events)):
                    reject('Original mutation drain is unconfirmed')
                boxes=read(control/'packed-transfers.jsonl',True);packed=read(control/'packed-transfer-active.json')
                identities=set()
                for box in boxes:
                    source=box.get('source')or{};counts=box.get('initial_counts')or{};taken=box.get('taken')or{}
                    identity=(tuple(source.get('position',[])),box.get('slot'))
                    if (box.get('stage')!='returned' or box.get('world_session')!=world
                            or box.get('ownership_preflight',{}).get('world_session')!=world
                            or box.get('ownership_preflight',{}).get('cursor_clean')is not True
                            or source.get('slot')!=box.get('slot') or source.get('count')!=1
                            or source.get('counts')!=counts or identity in identities
                            or any(type(v)is not int or v<0 for v in list(counts.values())+list(taken.values()))
                            or any(k not in counts or v>counts[k] for k,v in taken.items())
                            or box.get('remaining_counts')!={k:v-taken.get(k,0) for k,v in counts.items() if v-taken.get(k,0)>0}):
                        reject('A packed source box return is unresolved')
                    identities.add(identity)
                if len(boxes)!=expected_boxes or expected_boxes and packed!=boxes[-1]:
                    reject('Original packed-box return count differs')
                if any(job.rglob('inflight.json')):reject('Original mutation intent is still in flight')
                state=self.observe();safe_current(state)
                reply=self.task_status(expected_job);task=reply.get('material_task')or{}
                if (reply.get('phase')!='done' or task.get('id')!=expected_job or task.get('state')!='blocked'
                        or task.get('world_session')!=world or task.get('native_task_session')!=native_session
                        or task.get('occupied')is not False or task.get('process_alive')is not False
                        or task.get('cancelling')is not False or not dead(task.get('pid'))):
                    reject('Exact original native task or dead process is unconfirmed')
                self.sleep(.35);fresh=self.observe();safe_current(fresh)
                if (fresh['time']<=state['time'] or fresh['world_session']!=state['world_session']
                        or fresh.get('control_revision')!=state.get('control_revision')
                        or fresh.get('pos')!=state.get('pos')):reject('Current inventory/control observation is unstable')
                mailbox=self.root/'request.json'
                if mailbox.exists():
                    current_request=read(mailbox)
                    if current_request.get('id')!=fresh.get('last_request'):
                        reject('An unacknowledged native mailbox request remains')
                if any(path.read_bytes()!=raw for path,raw in evidence.items()) or self.path.read_bytes()!=raw_workflow:
                    reject('Original evidence changed during reconciliation')
                archive=self.out/'supply-reconciliations'/(expected_job+'-'+hashlib.sha256(raw_workflow).hexdigest()[:16]+'-'+str(fresh['time']))
                archive.mkdir(parents=True,exist_ok=True)
                preserved={'original-workflow.json':raw_workflow,
                    'current-state.json':json.dumps(fresh,ensure_ascii=False,indent=2).encode(),
                    'current-task-status.json':json.dumps(reply,ensure_ascii=False,indent=2).encode()}
                for path,raw in evidence.items():
                    relative=path.relative_to(job) if path.is_relative_to(job) else Path('native')/path.name
                    preserved[str(relative)]=raw
                for relative,raw in preserved.items():
                    destination=archive/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                    if destination.exists() and destination.read_bytes()!=raw:reject('Archived evidence differs; never overwrite')
                    if not destination.exists():destination.write_bytes(raw)
                record={'outcome':'prior_finish_unknown','prior_finish_completed':False,'request_replayed':False,
                    'original_pending':pending,'original_task':deepcopy(task),'archive':str(archive),
                    'evidence_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in preserved.items()},
                    'settled_action_receipts':expected_steps,'returned_packed_boxes':expected_boxes,
                    'fresh_backpack_torches':stock(fresh),'observed_at':fresh['time'],'world_session':fresh['world_session']}
                previous=self.book;self.book=deepcopy(previous)
                self.book.setdefault('pending_reconciliations',[]).append(record)
                self.book.update(pending=None,phase='ready',reason='Prior finish remains unknown; fresh backpack permits a new lighting resume')
                try:self.save()
                except BaseException:
                    self.book=previous;raise
                return record
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


def main(argv=None):
    """Explicit reconciliation entry point; never starts a lighting worker."""
    import argparse
    from kit_cli import DEFAULT_GAME
    from lighting_regions_cli import RegionsWorker
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('reconcile-prior-finish',))
    parser.add_argument('--game-dir',type=Path,default=DEFAULT_GAME)
    parser.add_argument('--profile',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--job-id',required=True)
    parser.add_argument('--torch-target',type=int,default=128)
    parser.add_argument('--max-supplies',type=int,default=32)
    parser.add_argument('--expected-steps',type=int,default=7)
    parser.add_argument('--expected-boxes',type=int,default=2)
    args=parser.parse_args(argv)
    root=args.game_dir/'config/twob2tkit/automation'
    try:
        profile=json.loads(args.profile.read_text())
        flow=LightingSupplyWorkflow(lambda:RegionsWorker(root,profile,args.out),target=args.torch_target,max_supplies=args.max_supplies)
        result=flow.reconcile_prior_finish(expected_job=args.job_id,expected_steps=args.expected_steps,expected_boxes=args.expected_boxes)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (RuntimeError,ValueError,OSError,KeyError) as error:
        print(json.dumps({'phase':'waiting','reason':type(error).__name__+': '+str(error)},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
