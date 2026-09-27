"""Direct native material-task control through its independent local mailbox.

Never writes gameplay request.json, launches Minecraft, clears safety holds,
replays a timed-out operation, sends keys, or uses a model.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from live_snapshot import read_fresh
from safety_interlock import require_assistant_control_allowed, require_unlocked


OPS={'material_task_'+name for name in ('start','status','pause','resume','cancel')}
CONTROLS={'material_task_pause','material_task_resume','material_task_cancel'}
ID=re.compile(r'[A-Za-z0-9_-]{1,96}')
COMMON={'id','op','schema'}
SCOPE={'server','dimension','world_session','expected_revision','expires_at'}
MAX_BYTES=65536
MAX_REQUEST_BYTES=16384


class MaterialTaskError(RuntimeError):
    def __init__(self,detail,*,submitted=False,request_id=None,op=None):
        super().__init__(detail)
        self.submitted,self.request_id,self.op=submitted,request_id,op


def _identifier(value):
    if not isinstance(value,str) or not ID.fullmatch(value):
        raise MaterialTaskError('材料任务标识无效')
    return value


def _read(path):
    if path.stat().st_size>MAX_BYTES:raise MaterialTaskError('材料任务消息过大，停止处理')
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise MaterialTaskError('材料任务消息格式无效')
    return value


def _context(state,now):
    if (not isinstance(state,dict) or state.get('connected') is not True
            or any(not isinstance(state.get(key),str) or not state[key] for key in ('server','dimension','world_session'))
            or type(state.get('control_revision')) is not int or state['control_revision']<0):
        raise MaterialTaskError('当前世界或控制状态尚未就绪')
    if type(state.get('material_task_api_protocol')) is not int or state['material_task_api_protocol']<1:
        raise MaterialTaskError('当前 Kit 尚未提供材料任务 API，请更新主包')
    observed=state.get('time')
    if type(observed) is not int or not -1000<=now-observed<=3000:
        raise MaterialTaskError('游戏状态已过期，不发送材料控制命令')
    return {key:state[key] for key in ('server','dimension','world_session')}|{
        'expected_revision':state['control_revision'],'expires_at':now+5000}


def make_request(op,state=None,*,job_id=None,mode=None,item=None,count=None,placement_key=None,now_ms=None):
    if op not in OPS:raise MaterialTaskError('未知材料任务 API 操作')
    now=int(time.time()*1000) if now_ms is None else now_ms
    request={'id':'materialcli-'+uuid.uuid4().hex,'op':op}
    if op=='material_task_status':
        if job_id is not None:request['job_id']=_identifier(job_id)
        return request
    request.update(_context(state,now))
    if op in CONTROLS:request['job_id']=_identifier(job_id)
    elif job_id is not None:raise MaterialTaskError('新任务不能指定旧任务编号')
    if op in ('material_task_start','material_task_resume'):
        if state.get('manual_movement'):raise MaterialTaskError('玩家正在移动，材料任务不会接管')
        request['manual_start']=True
    if op=='material_task_start':
        if mode=='projection':
            current=(state.get('projection_selection') or {}).get('key')
            if not isinstance(current,str) or not current or len(current)>8192:
                raise MaterialTaskError('请先选定并锁定一份投影')
            if placement_key is not None and placement_key!=current:
                raise MaterialTaskError('投影已改变，不沿用旧投影编号')
            if item is not None or count is not None:raise MaterialTaskError('投影任务不能附带单物品参数')
            request.update(mode=mode,placement_key=current)
        elif mode=='item':
            if (not isinstance(item,str) or not re.fullmatch(r'minecraft:[a-z0-9_]+',item)
                    or item=='minecraft:air' or type(count) is not int or not 1<=count<=1_000_000):
                raise MaterialTaskError('请选择原版物品完整 ID 和 1–1000000 的数量')
            if placement_key is not None:raise MaterialTaskError('单物品任务不能附带投影编号')
            request.update(mode=mode,item=item,count=count)
        else:raise MaterialTaskError('材料任务必须选择单物品或投影模式')
    return request


def _shape(request):
    if not isinstance(request,dict):raise MaterialTaskError('材料任务请求格式无效')
    _identifier(request.get('id'));op=request.get('op')
    if op not in OPS:raise MaterialTaskError('未知材料任务操作')
    if 'schema' in request and (type(request['schema']) is not int or request['schema']!=1):raise MaterialTaskError('材料任务协议版本无效')
    allowed=set(COMMON)
    if op=='material_task_status':
        allowed.add('job_id')
        if 'job_id' in request:_identifier(request['job_id'])
    else:
        allowed.update(SCOPE)
        if (any(not isinstance(request.get(key),str) or not request[key] for key in ('server','dimension','world_session'))
                or type(request.get('expected_revision')) is not int or request['expected_revision']<0):
            raise MaterialTaskError('材料任务控制上下文无效')
    if op in CONTROLS:allowed.add('job_id');_identifier(request.get('job_id'))
    if op in ('material_task_start','material_task_resume'):
        allowed.add('manual_start')
        if request.get('manual_start') is not True:raise MaterialTaskError('启动和继续必须是明确的操作')
    if op=='material_task_start':
        allowed.update(('mode','item','count','placement_key'))
        mode=request.get('mode')
        if mode=='item':
            if (not isinstance(request.get('item'),str) or not re.fullmatch(r'minecraft:[a-z0-9_]+',request['item'])
                    or request['item']=='minecraft:air' or type(request.get('count')) is not int
                    or not 1<=request['count']<=1_000_000 or 'placement_key' in request):
                raise MaterialTaskError('单物品请求无效')
        elif mode=='projection':
            if not isinstance(request.get('placement_key'),str) or not request['placement_key'] or len(request['placement_key'])>8192 or 'item' in request or 'count' in request:
                raise MaterialTaskError('投影请求无效')
        else:raise MaterialTaskError('材料任务模式无效')
    if set(request)-allowed:raise MaterialTaskError('材料任务请求包含不允许的字段')
    _request_bytes(request)


def _request_bytes(request):
    data=json.dumps(request,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    if len(data)>MAX_REQUEST_BYTES:raise MaterialTaskError('材料任务请求超过宿主 16384 字节上限，未发送')
    return data


def _validate_live(root,request):
    if request['op']=='material_task_status':return
    state=read_fresh(root,wait_seconds=2);now=int(time.time()*1000);context=_context(state,now)
    if any(request.get(key)!=context[key] for key in ('server','dimension','world_session','expected_revision')):
        raise MaterialTaskError('世界或控制权已变化，旧命令未发送')
    expiry=request.get('expires_at')
    if type(expiry) is not int or not 0<=expiry-now<=15000:
        raise MaterialTaskError('材料控制请求已过期，未发送')
    require_assistant_control_allowed(root)
    if request['op'] in ('material_task_start','material_task_resume'):
        require_unlocked(root,state)
        if state.get('manual_movement'):raise MaterialTaskError('玩家正在移动，命令未发送')
    if request['op']=='material_task_start' and request.get('mode')=='projection':
        if (state.get('projection_selection') or {}).get('key')!=request['placement_key']:
            raise MaterialTaskError('投影选择已变化，命令未发送')


@contextmanager
def _locked(root):
    with (root/'.material-task-client.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:raise MaterialTaskError('另一材料控制命令正在等待回执，请勿并发发送') from error
        try:yield
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def _same_reply(reply,request):
    return (reply.get('schema')==1 and reply.get('id')==request['id'] and reply.get('op')==request['op']
            and reply.get('phase') in ('done','error'))


def _ensure_consumed(root,path):
    if not path.exists():return
    previous=_read(path);_identifier(previous.get('id'))
    if not isinstance(previous.get('op'),str):raise MaterialTaskError('现有材料请求无法核验，不覆盖')
    reply=root/('material-task-reply-'+previous['id']+'.json')
    if not reply.is_file() or not _same_reply(_read(reply),previous):
        raise MaterialTaskError('已有未消费的材料任务请求；保持原文件，不覆盖或重发')


def _publish(path,request):
    data=_request_bytes(request)
    fd,temporary=tempfile.mkstemp(prefix='.material-task-',suffix='.json',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def send(root,request,*,timeout=8,poll_seconds=.05):
    root=Path(root);_shape(request)
    if not root.is_dir():raise MaterialTaskError('Kit 自动化目录不存在，不会自动启动游戏')
    if not 0<timeout<=60 or not 0<poll_seconds<=1:raise MaterialTaskError('回执等待时间无效')
    path=root/'material-task-request.json';submitted=False
    try:
        with _locked(root):
            _validate_live(root,request);_ensure_consumed(root,path)
            _publish(path,request);submitted=True;sent_at=int(time.time()*1000)
            reply_path=root/('material-task-reply-'+request['id']+'.json')
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                if reply_path.is_file():
                    reply=_read(reply_path)
                    if not _same_reply(reply,request):raise MaterialTaskError('材料任务回执编号或操作不匹配')
                    observed=reply.get('observed_at')
                    if type(observed) is not int or not sent_at-1000<=observed<=int(time.time()*1000)+1000:
                        raise MaterialTaskError('材料任务回执时间无法核验')
                    if reply['phase']=='done':
                        if not isinstance(reply.get('material_task'),dict):raise MaterialTaskError('材料任务回执缺少实际任务状态')
                        if request['op']!='material_task_status' and reply.get('world_session')!=request['world_session']:
                            raise MaterialTaskError('材料任务回执属于另一世界')
                        if request.get('job_id') and reply['material_task'].get('id')!=request['job_id']:
                            raise MaterialTaskError('材料任务回执属于另一任务')
                    return reply
                time.sleep(poll_seconds)
            raise MaterialTaskError('材料任务命令未收到回执；已保留原请求，不会自动重发')
    except MaterialTaskError as error:
        error.submitted|=submitted;error.request_id=request['id'];error.op=request['op'];raise
    except (OSError,ValueError,KeyError,RuntimeError) as error:
        raise MaterialTaskError(str(error),submitted=submitted,request_id=request['id'],op=request['op']) from error


def compact(reply):
    task=reply.get('material_task') or {}
    return {'schema':1,'id':reply.get('id'),'op':reply.get('op'),'phase':reply.get('phase'),
            'detail':reply.get('detail',''),'accepted':reply.get('phase')=='done',
            'observed_at':reply.get('observed_at'),'material_task':{key:task[key] for key in
                ('id','state','detail','done','total','process_alive','pid','world_session','occupied','cancelling','mode','placement_key','native_task_session') if key in task}}


class MaterialTaskClient:
    def __init__(self,automation_root,*,timeout=8):self.root=Path(automation_root);self.timeout=timeout
    def status(self,job_id=None):return send(self.root,make_request('material_task_status',job_id=job_id),timeout=self.timeout)
    def _write(self,op,**kwargs):
        state=read_fresh(self.root,wait_seconds=2)
        return send(self.root,make_request(op,state,**kwargs),timeout=self.timeout)
    def start_projection(self):return self._write('material_task_start',mode='projection')
    def start_item(self,item,count):return self._write('material_task_start',mode='item',item=item,count=count)
    def pause(self,job_id):return self._write('material_task_pause',job_id=job_id)
    def resume(self,job_id):return self._write('material_task_resume',job_id=job_id)
    def cancel(self,job_id):return self._write('material_task_cancel',job_id=job_id)
