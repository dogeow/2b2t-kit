"""Opt-in standing authorization for paused workers; no game actions or receipt edits."""
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from safety_interlock import require_unlocked
from .protocol import server_key


class StationaryResume:
    def __init__(self, automation, *, clock=time.monotonic):
        self.root=Path(automation);self.clock=clock;self.anchor=None;self.since=None

    def reset(self):
        self.anchor=None;self.since=None

    def poll(self, job):
        """Resume the original paused intent only after three stable current seconds."""
        try:
            policy=json.loads((self.root/'autonomous-policy.json').read_text())
            if policy.get('schema')!=1 or policy.get('resume_paused_when_stationary') is not True:
                self.reset();return False
            state=read_fresh(self.root)
            require_unlocked(self.root,state)
        except (OSError,ValueError,RuntimeError,AttributeError):
            self.reset();return False
        original=job.request['context'];menu=state.get('menu') or {};lease=state.get('supervision_lease') or {}
        position=state.get('pos');velocity=state.get('velocity')
        scalar=lambda value:type(value) in (int,float) and math.isfinite(value)
        vector=lambda value:isinstance(value,list) and len(value)==3 and all(scalar(n) for n in value)
        expected_task=job.state.get('native_task_session')
        lease_available=(not lease or lease.get('kind')=='parking' and bool(expected_task)
                         and lease.get('job_session')==expected_task
                         and lease.get('world_session')==state.get('world_session')
                         and lease.get('revision')==state.get('control_revision'))
        allowed=(job.state.get('state')=='paused' and state.get('connected') is True
                 and state.get('manual_movement') is False and not state.get('screen')
                 and server_key(state.get('server'))==server_key(original['server'])
                 and state.get('dimension')==original['dimension']
                 and state.get('world_session')==original['world_session']
                 and scalar(state.get('health')) and state['health']>=19
                 and type(state.get('food')) is int and state['food']>=8
                 and menu.get('id')==0 and menu.get('type')=='InventoryMenu'
                 and menu.get('cursor',{}).get('count')==0
                 and not state.get('under_water') and not state.get('guard_busy')
                 and not any(state.get(k) for k in ('borer_active','chopping','navigating','native_material_busy'))
                 and state.get('pending_scan') is None and not state.get('build_job',{}).get('active')
                 and lease_available and type(state.get('control_revision')) is int
                 and type(state.get('time')) is int and state['time']>job.last_control
                 and vector(position) and vector(velocity))
        if job.request['mode']=='projection':
            allowed=allowed and state.get('projection_selection',{}).get('key')==job.request['projection_key']
        if allowed:
            axes=(0,2) if state.get('on_ground') else (0,1,2)
            allowed=math.sqrt(sum(velocity[i]**2 for i in axes))<=.03
        if not allowed:
            self.reset();return False
        scope=(state['world_session'],state['control_revision'])
        now=self.clock()
        if self.anchor is None or self.anchor[0]!=scope or math.dist(self.anchor[1],position)>.08:
            self.anchor=(scope,list(position),state['time']);self.since=now;return False
        if now-self.since<3 or state['time']<=self.anchor[2]:return False
        context={k:state[k] for k in ('server','dimension','world_session')}
        context.update(expected_revision=state['control_revision'],start_pos=list(position))
        context=job._validate_resume_context(context)
        stamp=state['time']
        write_json(job.out/'resume-context.json',{'id':job.request['id'],'created_at':stamp,
                   'context':context,'source':'standing_stationary_policy'})
        job.context=context;job.last_control=stamp
        job._event('automatic_resume_when_stationary',context=context,policy='autonomous-policy.json')
        self.reset();return True
