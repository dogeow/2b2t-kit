"""Cooperative priority admission: formal work waits for idle input to stop first."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import threading
import time
import uuid

from kit_runtime.journal import write_json


def demands(root, world, *, now_ms=None):
    now=int(time.time()*1000) if now_ms is None else now_ms; result=[]
    directory=Path(root)/'idle-priority'
    if not directory.exists():return result
    for path in sorted(directory.glob('*.json')):
        if path.stat().st_size>8192:raise RuntimeError('Idle priority request is malformed')
        value=json.loads(path.read_text())
        if (value.get('schema')!=1 or not isinstance(value.get('id'),str)
                or not isinstance(value.get('world_session'),str) or type(value.get('expires_at'))is not int):
            raise RuntimeError('Idle priority request is malformed')
        if value['world_session']==world and value['expires_at']>=now:result.append(value)
    return result


def _idle_worker(root,world):
    path=Path(root)/'idle-service-owner.json'
    if not path.exists():return None
    owner=json.loads(path.read_text())
    if owner.get('world_session')!=world:return None
    lock_path=Path(owner.get('lock_path','')).resolve()
    if not lock_path.is_relative_to((Path(root)/'idle-services').resolve()) or lock_path.name!='worker.lock':
        raise RuntimeError('Idle ownership marker has an invalid worker lock')
    if not lock_path.is_file():return None
    with lock_path.open('rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return owner
        fcntl.flock(lock,fcntl.LOCK_UN)
    return None


class ForegroundDemand:
    def __init__(self,root,owner,world):
        if not isinstance(owner,str) or not owner.strip() or not isinstance(world,str) or not world:
            raise ValueError('Formal priority needs a named owner and world session')
        self.root=Path(root);self.id=uuid.uuid4().hex;self.world=world;self.owner=owner[:128]
        directory=self.root/'idle-priority';directory.mkdir(parents=True,exist_ok=True)
        self.path=directory/(self.id+'.json');self.closed=False;self.stop=threading.Event();self.thread=None
        self.publish()
    def publish(self):
        write_json(self.path,{'schema':1,'id':self.id,'owner':self.owner,'world_session':self.world,
                             'expires_at':int(time.time()*1000)+10000})
    def keepalive(self):
        while not self.stop.wait(1):
            try:self.publish()
            except OSError:return
    def wait(self,timeout_seconds=8,*,sleep=time.sleep,clock=time.monotonic,now_ms=lambda:int(time.time()*1000)):
        deadline=clock()+timeout_seconds
        while True:
            owner=_idle_worker(self.root,self.world)
            if owner is None:return self
            fresh=type(owner.get('updated_at'))is int and -1000<=now_ms()-owner['updated_at']<=2500
            if fresh and owner.get('input_released') is True:
                state=json.loads((self.root/'status.json').read_text())
                lease=state.get('supervision_lease') or {};cursor=(state.get('menu') or {}).get('cursor') or {}
                mailbox=self.root/'request.json';pending=json.loads(mailbox.read_text()) if mailbox.exists() else {}
                mailbox_clear=not pending or pending.get('id')==state.get('last_request') or pending.get('world_session')!=self.world or type(pending.get('expires_at'))is int and pending['expires_at']<now_ms()
                if (state.get('world_session')==self.world and state.get('connected') is True
                        and type(state.get('time'))is int and -1000<=now_ms()-state['time']<=2500
                        and (not owner.get('task_session') or lease.get('job_session')!=owner['task_session'])
                        and state.get('fisher_active') is False and cursor.get('count')==0
                        and state.get('navigating') is False and state.get('phase')!='running'
                        and state.get('manual_movement') is False and mailbox_clear):
                    return self
            if clock()>=deadline:raise RuntimeError('Idle input has not confirmed release; formal work was not admitted')
            sleep(.05)
    def close(self):
        if self.closed:return
        self.closed=True;self.stop.set()
        if self.thread is not None:self.thread.join(timeout=2)
        self.path.unlink(missing_ok=True)


def request_foreground(root,owner,world,timeout_seconds=8):
    """Root hooks this before formal MaterialClient/native work admission, then closes on exit."""
    token=ForegroundDemand(root,owner,world)
    token.thread=threading.Thread(target=token.keepalive,daemon=True,name='kit-idle-priority')
    token.thread.start()
    try:return token.wait(timeout_seconds)
    except BaseException:token.close();raise


@contextmanager
def foreground(root,owner,world,timeout_seconds=8):
    token=request_foreground(root,owner,world,timeout_seconds)
    try:yield token
    finally:token.close()
