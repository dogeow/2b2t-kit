"""All unattended entry points must fail closed after a native safety exit.

This module deliberately has no clear/unlock API. A later native Kit user
acknowledgement can satisfy a hold; unattended callers never clear one.
"""
import json,time,os,tempfile,math
from pathlib import Path

def require_assistant_control_allowed(root):
    path=Path(root)/'assistant-control-hold.json'
    if not path.exists():return
    try:
        hold=json.loads(path.read_text())
        if not isinstance(hold.get('active'),bool):raise ValueError('Invalid assistant control hold')
    except (OSError,ValueError,AttributeError) as error:
        raise RuntimeError('Assistant control hold unreadable; do not probe or control the game') from error
    if hold['active']:
        raise RuntimeError('User requested offline Kit work; wait for explicit server-ready authorization')


def require_unlocked(root, status=None):
    require_assistant_control_allowed(root)
    native={}
    path = Path(root) / 'safety-hold.json'
    if path.exists():
        try:
            record = json.loads(path.read_text())
            if not isinstance(record.get('active'), bool):
                raise ValueError('Invalid safety record')
        except (OSError, ValueError, AttributeError) as error:
            raise RuntimeError('Safety record unreadable; await manual in-game confirmation') from error
        if record['active']:
            raise RuntimeError('Safety lock active; do not reconnect or resume automatically')
        native=record
    if (status or {}).get('safety_hold', {}).get('active'):
        raise RuntimeError('Native safety lock active; await manual in-game confirmation')
    script=Path(root)/'material-health-hold.json'
    if script.exists():
        try:
            hold=json.loads(script.read_text())
            if not isinstance(hold.get('active'),bool) or type(hold.get('time')) is not int or hold['time']<0:
                raise ValueError('Invalid material health record')
        except (OSError,ValueError,AttributeError) as error:
            raise RuntimeError('Material health record unreadable; await manual confirmation') from error
        acknowledged=(native.get('cleared_by')=='game_ui'
                      and native.get('cleared_at',0)>hold['time'])
        if hold['active'] and not acknowledged:
            raise RuntimeError('Material task exited for health; player must recover and explicitly confirm before automation resumes')


class OwnedHealthExitEvidence:
    """Small per-client witness; historical hurt markers never create an exit cause."""
    def __init__(self,world,task):
        self.world,self.task=world,task
        self.last=None;self.decline=None;self.disconnected=False
    def observe(self,state):
        if state.get('connected') is False:
            self.disconnected=self.last is not None
            return
        lease=state.get('supervision_lease') or {}
        health,stamp=state.get('health'),state.get('time')
        if (state.get('connected') is not True or state.get('world_session')!=self.world
                or state.get('manual_movement') or not isinstance(lease,dict)
                or lease.get('kind') not in ('materials','parking') or lease.get('job_session')!=self.task
                or lease.get('world_session')!=self.world
                or lease.get('revision')!=state.get('control_revision')
                or type(health) not in (int,float) or not math.isfinite(health)
                or type(stamp) is not int or self.last and stamp<=self.last['time']):
            return
        current={key:state.get(key) for key in ('time','health','pos','server','world_session','recent_hurt_at')}
        if self.last and health<self.last['health']:
            self.decline=current
        if health>=20:self.decline=None
        self.last=current;self.disconnected=False
    def recovered(self,state):
        # Only the caller's verified guarded recovery routine invokes this.
        if type(state.get('health')) in (int,float) and state['health']>=19:
            self.decline=None
    def exit_state(self):
        if self.last and self.last['health']<18:return dict(self.last)
        return dict(self.decline) if self.decline else None


def record_material_health_exit(root,state,reason):
    """A conservative script health exit also requires the existing user-only Kit acknowledgement."""
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    record={'active':True,'time':int(state.get('time',time.time()*1000)),
            'health':state.get('health'),'pos':state.get('pos'),
            'server':state.get('server'),'world_session':state.get('world_session'),
            'reason':reason,'acknowledgement':'Explicit player recovery confirmation; a newer Kit game_ui acknowledgement is accepted'}
    fd,tmp=tempfile.mkstemp(prefix='.material-health-',suffix='.json',dir=root)
    try:
        with os.fdopen(fd,'w') as stream:json.dump(record,stream,ensure_ascii=False)
        os.replace(tmp,root/'material-health-hold.json')
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return record
