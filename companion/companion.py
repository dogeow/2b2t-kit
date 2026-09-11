#!/usr/bin/env python3
"""Minecraft event supervisor. Filesystem events wake rules; rules selectively wake Codex."""
import argparse,fcntl,json,os,re,select,signal,sys,threading,time,traceback
from pathlib import Path
from core import Detector,Store,compact,local_advice,tasks,completed
from agents import CodexWorker
from desktop import Desktop,DesktopBusy,DeliveryUnknown

DEFAULT={'spark_model':'gpt-5.3-codex-spark','main_model':'gpt-6-astra','spark_calls_per_hour':4,'main_calls_per_hour':1,'analysis_timeout':90,'stall_seconds':45,'codex':'/Applications/ChatGPT.app/Contents/Resources/codex','status_file':'/Applications/.minecraft/config/twob2tkit/automation/status.json','borer_log':'/Applications/.minecraft/config/twob2tkit/borer.log','read_only':True,'main_backend':'desktop','desktop_delivery_enabled':False,'desktop_calls_per_hour':1,'desktop_thread_id':'01a07a81-49c0-73d1-846c-685d941abdb0','desktop_bundle_version':''}

def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(path)
def load(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default
def append(path,item):
    with Path(path).open('a') as f:f.write(json.dumps(item,ensure_ascii=False)+'\n')

class FileEvents:
    def __init__(self,paths):
        self.fds=[];self.kq=select.kqueue() if hasattr(select,'kqueue') else None
        if self.kq:
            for p in set(Path(p).parent for p in paths):
                if p.is_dir():
                    fd=os.open(p,os.O_RDONLY);self.fds.append(fd)
                    self.kq.control([select.kevent(fd,filter=select.KQ_FILTER_VNODE,flags=select.KQ_EV_ADD|select.KQ_EV_CLEAR,fflags=select.KQ_NOTE_WRITE|select.KQ_NOTE_RENAME|select.KQ_NOTE_DELETE)],0,0)
    def wait(self):
        if self.kq:self.kq.control(None,8,1)
        else:time.sleep(1)
    def close(self):
        if self.kq:self.kq.close()
        for fd in self.fds:os.close(fd)

class LogCursor:
    def __init__(self,path):self.path=Path(path);self.inode=None;self.offset=None
    def read(self):
        try:
            st=self.path.stat()
            if self.offset is None or self.inode!=st.st_ino:self.inode=st.st_ino;self.offset=st.st_size;return []
            if st.st_size<self.offset:self.offset=0
            if st.st_size==self.offset:return []
            with self.path.open('rb') as f:
                f.seek(max(self.offset,st.st_size-8192));raw=f.read(8192);self.offset=f.tell()
            return raw.decode(errors='replace').splitlines()
        except OSError:return []

def relevant(e,s):
    if e.get('demo'):return True
    old=e.get('snapshot',{})
    if not s or not s.get('connected') or time.time()-s.get('time',0)/1000>10:return False
    if (old.get('server'),old.get('dimension'))!=(s.get('server'),s.get('dimension')):return False
    module=e['module'];current=tasks(s).get(module)
    if e['kind']=='needs_help' and current and current['active']:return False
    if current and any(x in current['reason'] for x in ('手动','接管','停止全部','紧急停止','本地脚本停止')):return False
    return True

def worker(state,config,stop):
    store=Store(state/'events.sqlite3');workspace=state/'agent-workspace';workspace.mkdir(exist_ok=True)
    agent=CodexWorker(config['codex'],workspace,state/'logs',config['analysis_timeout'])
    try:
        while not stop.wait(.25):
            if store.setting('paused',False):continue
            job=store.next()
            if not job:continue
            e,tier=job;store.processing(e);result={}
            try:
                if not e.get('demo') and time.time()-e['created']>120:store.finish(e,'expired',{'message':'事件已过期，等待新现场'});continue
                if tier=='local':result={'via':'rules','message':local_advice(e)}
                elif not relevant(e,load(config['status_file'])):store.finish(e,'superseded',{'message':'现场已经改变，取消旧异常的模型请求'});continue
                elif time.time()<store.setting('ai_backoff_until',0):store.finish(e,'needs_attention',{'message':'模型暂不可用，保留现场且不重试刷额度'});continue
                elif not store.reserve('spark',e['id'],config['spark_calls_per_hour']):store.finish(e,'budget_limited',{'message':'本小时分析次数已达上限，保留事件'});continue
                else:
                    spark=agent.analyze(e,config['spark_model'],'low');result={'via':'spark','spark':spark}
                    a=spark['answer']
                    if a['needs_main_agent'] or a['confidence']<.7:
                        if config.get('main_backend')=='desktop':
                            result['desktop_pending']=True;result['via']='desktop_queue'
                        elif store.setting('paused',False) or not relevant(e,load(config['status_file'])):result['main_skipped']='玩家已接管或现场改变'
                        elif time.time()<store.setting('main_backoff_until',0):result['main_skipped']='主模型暂不可用，已保留 Spark 诊断'
                        elif store.reserve('main',e['id'],config['main_calls_per_hour']):
                            try:
                                result['main']=agent.analyze({'incident':e,'spark_diagnosis':a,'request':'给出可执行的后续排查计划；本轮只诊断，不操作游戏。'},config['main_model'],'high');result['via']='main'
                            except Exception as ex:
                                result['main_error']=str(ex)[:1000];store.set('main_backoff_until',time.time()+3600)
                        else:result['main_skipped']='本小时主模型分析次数已达上限'
                status='handled' if tier=='local' else ('awaiting_desktop' if result.get('desktop_pending') else ('needs_attention' if result.get('main_error') else ('reviewed' if relevant(e,load(config['status_file'])) else 'superseded')))
                store.finish(e,status,result);append(state/'decisions.jsonl',{'event_id':e['id'],'time':time.time(),'status':status,'result':result})
            except Exception as ex:
                result={'message':str(ex)[:1000]};store.finish(e,'needs_attention',result);store.set('ai_backoff_until',time.time()+3600)
                append(state/'decisions.jsonl',{'event_id':e['id'],'time':time.time(),'status':'needs_attention','result':result})
            finally:publish_inbox(state,store)
    finally:agent.close();store.db.close()

def desktop_worker(state,config,stop):
    store=Store(state/'events.sqlite3')
    try:
        while not stop.wait(3):
            if store.setting('paused',False):continue
            enabled=store.setting('desktop_delivery_enabled',config.get('desktop_delivery_enabled',False))
            one_shot=store.setting('approved_desktop_event',None)
            if not enabled and not one_shot:continue
            if enabled:row=store.db.execute("SELECT payload,result FROM events WHERE status='awaiting_desktop' ORDER BY created LIMIT 1").fetchone()
            else:row=store.db.execute("SELECT payload,result FROM events WHERE status='awaiting_desktop' AND id=?",(one_shot,)).fetchone()
            if not row:continue
            e=json.loads(row[0]);result=json.loads(row[1]);desktop=None
            try:
                if not relevant(e,load(config['status_file'])) or not e.get('demo') and time.time()-e['created']>600:
                    store.finish(e,'superseded',{**result,'desktop_error':'现场已改变或事件已过期，不唤醒桌面任务'});continue
                if not result.get('desktop_reserved'):
                    if not store.reserve('desktop_test' if e['kind']=='connection_probe' else 'desktop',e['id'],config.get('desktop_calls_per_hour',1)):
                        store.finish(e,'budget_limited',{**result,'desktop_error':'桌面唤醒次数已达上限'});continue
                    result['desktop_reserved']=True;store.finish(e,'awaiting_desktop',result)
                desktop=Desktop(config['desktop_thread_id'],config['desktop_bundle_version'])
                acknowledgement=desktop.deliver(e,result.get('spark',{}).get('answer',{}))
                result['desktop']=acknowledgement;result['via']='desktop';store.finish(e,'desktop_delivered',result)
                if one_shot==e['id']:store.set('approved_desktop_event',None)
                append(state/'decisions.jsonl',{'event_id':e['id'],'time':time.time(),'status':'desktop_delivered','result':result})
            except DesktopBusy:
                pass # The app explicitly rejected before injection. Retry later without another model call.
            except DeliveryUnknown as ex:
                store.finish(e,'delivery_unknown',{**result,'desktop_error':str(ex)})
            except Exception as ex:
                store.finish(e,'needs_attention',{**result,'desktop_error':str(ex)[:1000]})
            finally:
                if desktop:desktop.close()
                publish_inbox(state,store)
    finally:store.db.close()

def publish_inbox(state,store):
    rows=store.db.execute("SELECT created,payload,status,result FROM events WHERE status NOT IN ('pending','processing') ORDER BY created DESC LIMIT 12").fetchall()
    messages=[{'time':t,'event':json.loads(p),'status':s,'result':json.loads(r) if r else {}} for t,p,s,r in rows]
    atomic(state/'inbox.json',messages)
    lines=['# Minecraft 事件收件箱','','本机规则持续监测，未知问题才调用模型。模型当前负责诊断，不直接操作游戏。','']
    for item in messages:
        e=item['event'];r=item['result'];answer=r.get('main',r.get('spark',{})).get('answer',{})
        lines.extend([f"- {time.strftime('%H:%M:%S',time.localtime(item['time']))} · {e['module']} · {e['kind']} · {item['status']}",f"  {'模型诊断（待验证）：' if answer else ''}{answer.get('cause',r.get('message',e.get('reason','')))}"])
        if answer.get('next_step'):lines.append('  下一步：'+answer['next_step'])
    p=state/'inbox.md';tmp=p.with_suffix('.md.tmp');tmp.write_text('\n'.join(lines)+'\n');tmp.replace(p)

def run(state,config):
    state.mkdir(parents=True,exist_ok=True);(state/'logs').mkdir(exist_ok=True)
    lock=(state/'service.lock').open('w')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit('Companion is already running')
    lock.write(str(os.getpid()));lock.flush()
    store=Store(state/'events.sqlite3');store.recover();detector=Detector(config['stall_seconds']);cursor=LogCursor(config['borer_log']);cursor.read()
    stop=threading.Event();signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    thread=threading.Thread(target=worker,args=(state,config,stop),daemon=True);thread.start()
    desktop_thread=threading.Thread(target=desktop_worker,args=(state,config,stop),daemon=True);desktop_thread.start()
    watches=FileEvents([config['status_file'],config['borer_log']]);last_stamp=None;last_seen=None;last_beat=0;borer_active=False;last_borer_activity=0;stale_reported=False
    def emit(e):
        if store.put(e):append(state/'events.jsonl',e)
    try:
        while not stop.is_set():
            now=time.time();s=load(config['status_file'])
            if s and abs(now-s.get('time',0)/1000)<10 and s.get('time')!=last_stamp:
                last_stamp=s.get('time');last_seen=now;stale_reported=False
                if not store.setting('paused',False):
                    for e in detector.observe(s,now):emit(e)
                else:detector=Detector(config['stall_seconds'])
            if last_seen and now-last_seen>8 and not stale_reported:
                stale_reported=True
                if detector.previous and any(x['active'] for x in tasks(detector.previous).values()):emit(detector.event('heartbeat_lost','client','8 秒没有新心跳；不自动重连',detector.previous,now))
            if s and abs(now-s.get('time',0)/1000)<10 and s.get('connected') and not store.setting('paused',False):
                for line in cursor.read():
                    if 'start mode=' in line or 'action=' in line:borer_active=True;last_borer_activity=now
                    if 'stop reason=' in line and borer_active:
                        reason=line.split('stop reason=',1)[1].strip()[:500];kind='manual_takeover' if any(x in reason for x in ('按键','手动','紧急','接管','停止全部')) else ('completed' if completed(reason) else 'needs_help')
                        emit(detector.event(kind,'borer',reason,s,now));borer_active=False
                    elif borer_active and any(x in line for x in ('tool-worn','no-tool','ore-stuck','route-failed')):emit(detector.event('needs_help','borer',line.rsplit('] ',1)[-1][:500],s,now))
            else:cursor.read();borer_active=False
            if now-last_beat>=5:
                atomic(state/'service-status.json',{'pid':os.getpid(),'time':now,'watcher':'kqueue' if watches.kq else 'poll','game_heartbeat_age':None if last_seen is None else round(now-last_seen,2),'read_only':True,'main_backend':config.get('main_backend'),'desktop_delivery_enabled':store.setting('desktop_delivery_enabled',config.get('desktop_delivery_enabled',False)),**store.summary()});last_beat=now
            watches.wait()
    finally:
        stop.set();thread.join(timeout=5);desktop_thread.join(timeout=2);watches.close();atomic(state/'service-status.json',{'pid':None,'time':time.time(),'stopped':True});lock.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['run','status','pause','resume','replay']);p.add_argument('--state-dir',required=True);p.add_argument('--config');p.add_argument('--replay-file');a=p.parse_args()
    state=Path(a.state_dir).expanduser().resolve();state.mkdir(parents=True,exist_ok=True);config={**DEFAULT,**(load(a.config,{}) if a.config else {})}
    if a.command=='run':run(state,config);return
    store=Store(state/'events.sqlite3')
    if a.command in ('pause','resume'):
        store.set('paused',a.command=='pause')
        if a.command=='pause':store.db.execute("UPDATE events SET status='cancelled' WHERE status='pending'");store.db.commit()
    elif a.command=='replay':
        if not a.replay_file:raise SystemExit('--replay-file is required')
        detector=Detector(config['stall_seconds']);rows=load(a.replay_file,[]);n=0
        for s in rows:
            for e in detector.observe(s,s['time']/1000):e['demo']=True;e['created']=time.time();e['fingerprint']='demo-'+e['fingerprint'];n+=store.put(e)
        print(json.dumps({'queued':n}));return
    print(json.dumps({'service':load(state/'service-status.json',{}),**store.summary()},ensure_ascii=False))
if __name__=='__main__':main()
