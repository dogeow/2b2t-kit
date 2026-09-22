"""Exclusive, expiring requests and server-result checks for local survival trials."""
import json
import math
import time
import uuid
from pathlib import Path
from decisions import DecisionError,status

MENUS={'','CraftingScreen','FurnaceScreen'}

class Paused(DecisionError): pass

def inventory(s):
    counts={}
    for row in s['inventory']:
        name=row['item'].removeprefix('minecraft:')
        if name!='air':counts[name]=counts.get(name,0)+row['count']
    return counts

def valid(s,world,session=None,background=False):
    if s.get('bridge_version',0)<2:raise Paused('需要安装支持生存试运行的 Kit 1.9.39 或更新版本。')
    if not s.get('connected') or s.get('server')!='singleplayer' or s.get('dimension')!='minecraft:overworld' or s.get('game_mode')!='survival':raise Paused('只在本机主世界的生存模式试运行。')
    if s.get('world_name')!=world or (session and s.get('world_session')!=session):raise Paused('存档或连接已改变，请手动重新开始。')
    if s.get('health',0)<16 or s.get('food',0)<8 or s.get('manual_movement') or (not background and not s.get('window_active')) or s.get('screen') not in MENUS:raise Paused('低血量、饥饿、菜单或人工操作，已交还控制。')
    if s.get('flight') or s.get('guard_busy') or s.get('chopping') or s.get('navigating') or s.get('printing'):raise Paused('有其他功能接管，先停止它再手动开始试运行。')
    if any(e.get('hostile') and e.get('visible',True) and math.dist(e['pos'],s['pos'])<10 for e in s.get('entities',[])):raise Paused('附近出现敌对生物，暂停开局试运行。')

class Bridge:
    def __init__(self,root,world,events=lambda *a,**k:None,background=False):
        self.root=Path(root);self.world=world;self.events=events;self.background=background
        s=status(self.root);valid(s,world,background=background)
        if s.get('screen') or s.get('phase')=='running':raise Paused('请关闭界面并停止其他任务。')
        self.session=s['world_session'];self.revision=s['control_revision'];self.last=s.get('last_request','')
        self.origin=s['pos'];self.radius=24;self.active=None;self.state=s;self.owned=False;self.halted=False
    def read(self):
        if self.halted:raise Paused('本轮控制已停止，必须手动重新开始。')
        s=status(self.root)
        try:valid(s,self.world,self.session,background=self.background)
        except Paused:self.halted=True;raise
        if s.get('control_revision')!=self.revision or s.get('last_request','')!=self.last:
            self.halted=True;raise Paused('急停或其他操作已接管，循环不会自动恢复。')
        if math.dist([s['pos'][0],s['pos'][2]],[self.origin[0],self.origin[2]])>self.radius:raise Paused('已到达本轮开局范围边界。')
        self.state=s;return s
    def request(self,op,**args):
        s=self.read();pending=self.root/'request.json'
        if pending.exists() and json.loads(pending.read_text()).get('id')!=self.last:raise Paused('已有未处理请求。')
        request={'id':'survival-'+uuid.uuid4().hex[:16],'op':op,'server':'singleplayer','dimension':'minecraft:overworld',
                 'site':self.origin,'world_session':self.session,'local_survival':True,'expected_revision':self.revision,
                 'expires_at':int(time.time()*1000)+10000,'background_ok':self.background,**args}
        self.events('request',id=request['id'],op=op,arguments=args)
        admitted_revision=self.revision+(1 if op in ('walk','walk_path','mine_block','navigate','chop','print') else 0)
        temp=self.root/(request['id']+'.tmp');temp.write_text(json.dumps(request));temp.replace(pending)
        self.owned=True;self.active=request['id'];deadline=time.monotonic()+max(8,args.get('seconds',0)+5)
        while time.monotonic()<deadline:
            reply=self.root/('reply-'+request['id']+'.json')
            current=status(self.root)
            if current.get('world_session')!=self.session:raise Paused('执行时世界连接改变。')
            if current.get('id')==request['id'] and current.get('last_request')==request['id'] and current.get('phase')=='running':
                self.revision=current['control_revision']
            try:valid(current,self.world,self.session,background=self.background)
            except Paused:self.halted=True;raise
            result=json.loads(reply.read_text()) if reply.exists() else current
            matched=result.get('id')==request['id'] and (reply.exists() or result.get('last_request')==request['id'])
            if matched and (op=='scan' and 'blocks' in result or result.get('phase') in ('done','error','waiting','stopped')):
                if result['control_revision']>admitted_revision:self.halted=True
                self.last=request['id'];self.revision=result['control_revision'];self.state=result;self.active=None
                if result.get('phase') in ('error','waiting','stopped') and 'blocks' not in result:
                    if result.get('phase')=='stopped':self.owned=False;self.halted=True
                    raise Paused(result.get('detail','动作未完成'))
                valid(result,self.world,self.session,background=self.background)
                self.events('confirmed',id=request['id'],op=op,position=result.get('pos'))
                return result
            if current.get('last_request') not in (self.last,request['id']):raise Paused('执行时其他控制器接管。')
            time.sleep(.1)
        self.halted=True;raise Paused('动作已发送但未确认，停止并保留现场，不盲目重试。')
    def stop_owned(self):
        try:
            if not self.owned:return
            s=status(self.root)
            pending=self.root/'request.json'
            if pending.exists() and json.loads(pending.read_text()).get('id') not in (self.last,self.active):return
            if s.get('world_session')!=self.session or s.get('last_request') not in (self.last,self.active):return
            if s.get('control_revision')!=self.revision:return
            request={'id':'survival-stop-'+uuid.uuid4().hex[:12],'op':'stop','world_session':self.session,'expected_revision':s['control_revision']}
            temp=self.root/(request['id']+'.tmp');temp.write_text(json.dumps(request));temp.replace(self.root/'request.json')
        except (OSError,ValueError,DecisionError):pass
    def click(self,slot,kind='pickup',button=0):
        s=self.read();row=s['menu']['slots'][slot]
        return self.request('slot_click',menu_id=s['menu']['id'],slot=slot,kind=kind,button=button,expected_item=row['item'],expected_count=row['count'])
    def select(self,item):return self.request('select_item',item='minecraft:'+item)
    def close(self):
        if self.read()['menu']['id']!=0:return self.request('close_menu')
    def wait(self,seconds):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:self.read();time.sleep(.2)
