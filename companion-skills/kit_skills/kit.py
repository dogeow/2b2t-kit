"""Read-only integration with Kit telemetry. Never opens or writes the action mailbox."""
import json,time,re
from pathlib import Path
from .learning import learn_transaction

def read_json(path,limit=2000000):
    p=Path(path)
    if p.stat().st_size>limit:raise ValueError('Input exceeds size limit')
    return json.loads(p.read_text())
def compact(s):
    keys=('time','id','last_request','connected','server','dimension','pos','health','food','screen','phase','op','detail','guard_busy','guard_armed','professional_printer','inventory','build_job','concrete','chopping','chopper_status','navigating')
    out={k:s[k] for k in keys if k in s}
    if 'professional_printer' in out:out['professional_printer']={k:v for k,v in out['professional_printer'].items() if k!='confirmation_seconds'}
    return out
class KitRecorder:
    def __init__(self,automation_dir,manager):self.root=Path(automation_dir);self.manager=manager;self.previous=None;self.pending={};self.seen=set()
    def poll(self,now=None):
        now=time.time() if now is None else now;s=read_json(self.root/'status.json');events=[]
        if not isinstance(s.get('time'),(int,float)) or abs(now*1000-s['time'])>10000:return []
        try:
            p=self.root/'request.json';request=read_json(p,16384);stamp=p.stat().st_mtime*1000;rid=request.get('id')
            if isinstance(rid,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}',rid) and rid not in self.seen:
                self.seen.add(rid)
                if self.previous and stamp-5000<=self.previous.get('time',0)<=stamp and self.previous.get('connected'):
                    self.pending[rid]=(request,self.previous)
                else:self.manager.lesson({'kind':'missing_before_snapshot','request_id':rid,'op':request.get('op')})
            if len(self.seen)>4096:self.seen={rid}
        except (FileNotFoundError,json.JSONDecodeError,ValueError):pass
        for rid,(request,before) in list(self.pending.items()):
            result=s if s.get('id')==rid and s.get('last_request',rid)==rid and s.get('phase') in ('done','stopped','waiting','error') else None
            if result is None:
                try:
                    reply=read_json(self.root/('reply-'+rid+'.json'))
                    if reply.get('id')==rid and reply.get('phase') in ('done','stopped','waiting','error'):result=reply
                except (FileNotFoundError,json.JSONDecodeError,ValueError):pass
            if result is not None:
                events.append(learn_transaction(self.manager,request,before,compact(result)));del self.pending[rid]
            elif now*1000-before.get('time',0)>700000:
                self.manager.lesson({'kind':'incomplete_trace','request_id':rid});del self.pending[rid]
        if self.previous:
            for field in ('build_job','concrete'):
                old=self.previous.get(field,{}) or {};new=s.get(field,{}) or {}
                if old.get('active') and not new.get('active'):
                    self.manager.lesson({'kind':'task_experience','module':field,'before':self.previous,'after':compact(s),'acceptance':'task stopped; exact goal requires separate verification'})
        self.previous=compact(s);return events
    def snapshot(self):
        s=read_json(self.root/'status.json');return {'heartbeat_age_seconds':round(time.time()-s.get('time',0)/1000,2),'connected':s.get('connected',False),'server':s.get('server'),'dimension':s.get('dimension'),'read_only':True}
def ingest_supervisor(manager,path):
    """Consumes the supervisor's JSONL journal using its own cursor; never edits that journal."""
    p=Path(path);key='journal:'+str(p.resolve());mark=manager.cursor(key,{'inode':None,'offset':0});st=p.stat()
    offset=mark['offset'] if mark['inode']==st.st_ino and mark['offset']<=st.st_size else 0
    count=0
    with p.open('rb') as f:
        f.seek(offset)
        for _ in range(1000):
            begin=f.tell();line=f.readline(65537)
            if not line or not line.endswith(b'\n'):f.seek(begin);break
            if len(line)>65536:raise ValueError('Oversized supervisor event')
            try:event=json.loads(line)
            except (json.JSONDecodeError,UnicodeDecodeError):continue
            manager.lesson({'kind':'supervisor_experience','event':event});count+=1
        manager.set_cursor(key,{'inode':st.st_ino,'offset':f.tell()})
    return count
