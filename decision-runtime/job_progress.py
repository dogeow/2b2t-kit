"""Small, session-scoped display mailbox. Never issues game controls or infers completion."""
import json
import os
import time
from pathlib import Path

class JobProgress:
    def __init__(self,root,world,task,revision,title,total,done=0):
        if total<0 or done<0:raise ValueError('Progress must be non-negative')
        self.path=Path(root)/'job-progress.json'
        self.world,self.task,self.revision=world,task,revision
        self.title,self.total,self.done,self.phase=title,total,done,''
        self.last_write=0;self.active=True
    def update(self,*,done=None,phase=None):
        if done is not None:
            if done<0:raise ValueError('Progress must be non-negative')
            self.done=done
        if phase is not None:self.phase=phase
        self.last_write=0
    def publish(self,state,now=None):
        now=time.time() if now is None else now
        lease=state.get('supervision_lease') or {}
        valid=(self.active and state.get('connected') and state.get('world_session')==self.world
               and state.get('control_revision')==self.revision and not state.get('manual_movement')
               and lease.get('job_session')==self.task)
        if not valid:return
        if now-self.last_write<.25:return
        payload=dict(active=True,world_session=self.world,task_session=self.task,control_revision=self.revision,
                     title=self.title[:60],done=self.done,total=self.total,phase=self.phase[:60],updated_at=int(now*1000))
        temp=self.path.with_suffix('.'+self.task+'.tmp')
        try:
            temp.write_text(json.dumps(payload,ensure_ascii=False));os.replace(temp,self.path);self.last_write=now
        except OSError:
            # The optional display must not break material work or safety cleanup.
            try:temp.unlink(missing_ok=True)
            except OSError:pass
    def close(self):
        self.active=False
        try:
            existing=json.loads(self.path.read_text())
            if existing.get('task_session')==self.task and existing.get('world_session')==self.world:self.path.unlink(missing_ok=True)
        except (OSError,ValueError):pass
