"""Deterministic event extraction and durable deduplication. No model or game control here."""
import hashlib,json,sqlite3,time,uuid
from pathlib import Path

MANUAL=('手动','接管','按键停止','停止全部','紧急停止','界面紧急','本地脚本停止','离开世界','退出游戏','切换','开始投影','开始混凝土')
MATERIAL=('待补材料','缺料','材料不足','背包已满','背包满','inventory-full','no-ammo','no-bow','no-tool','no-rod','shears-worn')
DONE=('全部匹配','达到设定数量','已达到','任务完成','采集完成','挖掘完成','已完成','到达目标')

def completed(reason):
    return not any(x in reason for x in ('未完成','没有完成','未达到','无法完成')) and (reason=='done' or any(x in reason for x in DONE))

def compact(s):
    out={k:s[k] for k in ('time','connected','server','dimension','pos','health','food','screen','guard_busy','guard_armed','phase','op','detail') if k in s}
    for key in ('build_job','concrete','professional_printer'):
        if isinstance(s.get(key),dict):out[key]={k:v for k,v in s[key].items() if k not in ('confirmation_seconds',)}
    def bounded(v):
        if isinstance(v,str):return v[:600]
        if isinstance(v,dict):return {k:bounded(x) for k,x in v.items()}
        if isinstance(v,list):return [bounded(x) for x in v[:16]]
        return v
    return bounded(out)

def tasks(s):
    b=s.get('build_job',{});c=s.get('concrete',{})
    return {
        'builder':{'active':bool(b.get('active')),'phase':b.get('phase',''),'reason':b.get('reason',''),'progress':b.get('matched',0)},
        'concrete':{'active':bool(c.get('active')),'phase':c.get('status',''),'reason':c.get('status',''),'progress':c.get('completed',0)},
        'chopper':{'active':bool(s.get('chopping')),'phase':s.get('chopper_status',''),'reason':s.get('chopper_status',''),'progress':sum(x.get('count',0) for x in s.get('inventory',[]) if str(x.get('item','')).endswith(('_log','_wood')))},
        'navigation':{'active':bool(s.get('navigating')),'phase':s.get('phase',''),'reason':s.get('detail',''),'progress':s.get('pos')},
    }

def route(event):
    kind=event['kind'];reason=event.get('reason','')
    if kind in ('task_started','completed','manual_takeover','disconnected','heartbeat_lost','danger'):return 'local'
    if any(x in reason for x in MANUAL):return 'local'
    if any(x in reason for x in ('找不到可通行路线','找不到路线','没有路线','不一致','接口不兼容','Exception')):return 'spark'
    if any(x in reason for x in MATERIAL):return 'local'
    return 'spark'

def local_advice(e):
    kind=e['kind'];r=e.get('reason','')
    if kind=='danger':return '危险由游戏内防护先处理；保留现场，不等待模型回应。'
    if kind in ('disconnected','heartbeat_lost'):return '连接或心跳中断，保持任务停止；恢复连接后重新核对现场。'
    if kind=='completed':return '任务结束已记录，下一步依据实际库存或场景验收。'
    if kind=='manual_takeover' or any(x in r for x in MANUAL):return '玩家已接管，保持停止，不自动重启。'
    if any(x in r for x in MATERIAL):return '等待补料或整理库存；不重复询问模型，不自动拿取未知箱子物品。'
    return '已记录，继续由现有游戏脚本执行。'

class Detector:
    def __init__(self,stall_seconds=45):
        self.previous=None;self.runs={};self.progress={};self.stall_seconds=stall_seconds;self.low=False
    def event(self,kind,module,reason,s,now):
        run=self.runs.get(module,'session')
        progress=tasks(s).get(module,{}).get('progress')
        location=[round(x/4)*4 for x in s.get('pos',[]) if isinstance(x,(int,float))]
        raw=json.dumps([s.get('server'),s.get('dimension'),module,kind,reason[:160],progress,location,int(now//30) if kind=='danger' else None],ensure_ascii=False)
        return {'id':uuid.uuid4().hex,'created':now,'kind':kind,'module':module,'reason':reason[:600],'fingerprint':hashlib.sha256(raw.encode()).hexdigest(),'snapshot':compact(s)}
    def observe(self,s,now=None):
        now=time.time() if now is None else now;events=[]
        if self.previous is None:
            self.previous=s
            for k,v in tasks(s).items():
                if v['active']:self.runs[k]=uuid.uuid4().hex
                self.progress[k]=(v['progress'],s.get('pos'),now)
            return events
        prev=self.previous;pt=tasks(prev);current=tasks(s)
        world_changed=(prev.get('server'),prev.get('dimension'))!=(s.get('server'),s.get('dimension'))
        if not s.get('connected') or world_changed:
            for k,v in pt.items():
                if v['active']:events.append(self.event('disconnected',k,'连接或维度改变，取消旧任务上下文',prev,now))
            self.previous=s;self.low=False;self.progress={};return events
        low=s.get('health',20)<10
        if low and not self.low and any(v['active'] for v in current.values()):events.append(self.event('danger','safety','生命值低于 10，游戏内防护优先',s,now))
        self.low=low
        for k,v in current.items():
            old=pt[k]
            if v['active'] and not old['active']:
                self.runs[k]=uuid.uuid4().hex;events.append(self.event('task_started',k,v['phase'],s,now));self.progress[k]=(v['progress'],s.get('pos'),now)
            if old['active'] and not v['active']:
                reason=v['reason'] or v['phase'];kind='needs_help'
                if any(x in reason for x in MANUAL):kind='manual_takeover'
                elif completed(reason) or (k=='navigation' and s.get('phase')=='done'):kind='completed'
                events.append(self.event(kind,k,reason,s,now))
            if v['active']:
                old_progress,old_pos,since=self.progress.get(k,(v['progress'],s.get('pos'),now))
                pos=s.get('pos');moved=pos is not None and old_pos is not None and sum((a-b)**2 for a,b in zip(pos,old_pos))>.04
                paused=bool(s.get('screen') or s.get('guard_busy') or s.get('health',20)<14 or '暂停' in v['phase'])
                if paused or moved or v['progress']!=old_progress:self.progress[k]=(v['progress'],pos,now)
                elif now-since>=self.stall_seconds:events.append(self.event('stalled',k,'任务持续运行但位置和进度均无变化',s,now))
        self.previous=s;return events

class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True);self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,fingerprint TEXT UNIQUE,created REAL,payload TEXT,status TEXT,tier TEXT,result TEXT);
        CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY,created REAL,tier TEXT,event_id TEXT,status TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);''')
    def put(self,e):
        cur=self.db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?)',(e['id'],e['fingerprint'],e['created'],json.dumps(e,ensure_ascii=False),'pending',route(e),None));self.db.commit();return cur.rowcount==1
    def setting(self,k,default=None):
        row=self.db.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone();return json.loads(row[0]) if row else default
    def set(self,k,v):self.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,json.dumps(v)));self.db.commit()
    def next(self):
        r=self.db.execute("SELECT payload,tier FROM events WHERE status='pending' ORDER BY created LIMIT 1").fetchone();return (json.loads(r[0]),r[1]) if r else None
    def finish(self,e,status,result):
        self.db.execute('UPDATE events SET status=?,result=? WHERE id=?',(status,json.dumps(result,ensure_ascii=False),e['id']));self.db.commit()
    def reserve(self,tier,event_id,limit,now=None):
        now=time.time() if now is None else now
        self.db.execute('BEGIN IMMEDIATE')
        count=self.db.execute('SELECT count(*) FROM calls WHERE tier=? AND created>?',(tier,now-3600)).fetchone()[0]
        if count>=limit:self.db.rollback();return False
        self.db.execute('INSERT INTO calls(created,tier,event_id,status) VALUES(?,?,?,?)',(now,tier,event_id,'reserved'));self.db.commit();return True
    def summary(self):
        return {'events':dict(self.db.execute('SELECT status,count(*) FROM events GROUP BY status')),'calls_last_hour':dict(self.db.execute('SELECT tier,count(*) FROM calls WHERE created>? GROUP BY tier',(time.time()-3600,))),'paused':self.setting('paused',False)}
    def recover(self):
        # A crash during an AI call is ambiguous. Never automatically pay for a duplicate call.
        self.db.execute("UPDATE events SET status='needs_attention' WHERE status='processing'");self.db.commit()
    def processing(self,e):self.db.execute("UPDATE events SET status='processing' WHERE id=?",(e['id'],));self.db.commit()
