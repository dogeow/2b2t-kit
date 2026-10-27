"""Run existing bounded kernels through the retained owner's native queue.

No second client, material lease, game mailbox or recovery authority is created.
"""
from kit_runtime.journal import write_json
from dataclasses import dataclass
import json

@dataclass(frozen=True)
class _ExistingLeaseIdentity:
    # Read-only identity of the retained owner, not another heartbeat sender.
    id: str

class QueuedVillageOwner:
    def __init__(self,builder):
        self.builder=builder;self.root=builder.root;self.out=builder.out
        state=builder.check();lease=state['supervision_lease']
        self.world=state['world_session'];self.task=lease['job_session'];self.server=state['server']
        self.anchor=list(lease['search_origin'])
        self.heartbeat=_ExistingLeaseIdentity(lease.get('id'))
        self.native_inflight=None;self.unconfirmed_native_request=None
    @property
    def last_terminal_evidence(self):
        state=self.builder.q.status();lease=state.get('supervision_lease')or{}
        if(not self.heartbeat.id or lease.get('id')!=self.heartbeat.id
                or lease.get('job_session')!=self.task or lease.get('world_session')!=self.world):
            return None
        try:
            lines=(self.out/'control/events.jsonl').read_text().splitlines()
            event=json.loads(lines[-1])
        except (OSError,ValueError,IndexError):return None
        if(event.get('request_id')!=state.get('last_request')
                or event.get('world_session')!=self.world
                or event.get('params',{}).get('task_session')!=self.task
                or event.get('revision_after')!=state.get('control_revision')):
            return None
        return event
    @property
    def last(self):return self.builder.q.status()['last_request']
    def status(self):return self.builder.check()
    def safety_status(self):return self.builder.q.status()
    def cargo_safety_retreat(self,certificate):
        from boat_safety import retreat_plan
        from vehicle_observation import read_frame
        state=self.safety_status();frame=read_frame(self.root,state,allow_dead_passengers=True)
        plan=retreat_plan(state,certificate['trip_scope'],certificate['original_move'],certificate['original_reply'],frame)
        if plan is None or plan['target']!=certificate.get('target'):
            raise RuntimeError('Cargo safety return no longer matches the last known movement')
        if(self.builder.book.get('pending_cargo_safety_return')or{}).get('pending'):
            raise RuntimeError('Original cargo safety return is unconfirmed; never replay')
        record=dict(pending=True,certificate=certificate);self.builder.book['pending_cargo_safety_return']=record;self.builder.save()
        result=self.builder.q.native('navigate',target=plan['target'],arrival=.2,air_only=True,seconds=15)
        record.update(pending=False,reply={k:result.get(k)for k in ['id','phase','world_session','control_revision','pos']});self.builder.save();return result
    def checked(self,op,**params):
        if op=='guard':
            raise RuntimeError('Queued transport cannot rebase its retained owner; keep the route in its existing anchor')
        return self.builder.n(op,**params)
    def request(self,op,**params):return self.checked(op,**params)
    def set_progress(self,**values):
        state=self.status()
        write_json(self.out/'queued-transport-progress.json',dict(time=state['time'],world_session=self.world,task_session=self.task,**values))
