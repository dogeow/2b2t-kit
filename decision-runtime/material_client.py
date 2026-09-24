"""Shared native material client. Every action is scoped to a live world, revision and safety lease."""
import json,math,time,uuid
from pathlib import Path
from build_supervisor import SafetyHeartbeat,stocks
from run_evidence import observed_delta,write_manifest
class Handoff(Exception):pass
def credit_guard_pause(deadline,paused,elapsed,busy,max_pause=180):
  credit=min(max(0,elapsed),max(0,max_pause-paused)) if busy else 0
  return deadline+credit,paused+credit
def high_park_clearance(rows,target_y):
  ground=[row['pos'][1]+1 for row in rows if row.get('fluid') or not row.get('passable',True)]
  if not ground:raise Handoff('High guard park has no verified ground column')
  return target_y-max(ground)
def underwater_action_allowed(state,op,params):
 if not state.get('under_water') or state.get('water_breathing_effect') or state.get('conduit_power_effect') or state.get('air_supply',0)>=240:return True
 if op not in ('navigate','walk','collect_item','approach_block','mine_block'):return True
 target=params.get('target')
 if op=='navigate' and isinstance(target,(list,tuple)) and len(target)==3:
  p=state.get('pos') or [0,0,0]
  if target[1]>=p[1]+2 and math.hypot(target[0]-p[0],target[2]-p[2])<=2:return True
 return False
def vertical_surface_escape(state,op,params):
 if op!='navigate':return False
 target=params.get('target')
 if not isinstance(target,(list,tuple)) or len(target)!=3:return False
 pos=state.get('pos') or [0,0,0]
 return target[1]>=pos[1]+2 and math.hypot(target[0]-pos[0],target[2]-pos[2])<=2
class Client:
 def __init__(self,root,out,server,min_health=18):
  self.root=Path(root);self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True);self.server=server
  s=self.raw();assert s.get('server','').removesuffix(':25565')==self.server.removesuffix(':25565') and s['dimension']=='minecraft:overworld'
  assert not s['screen'] and not s.get('manual_movement') and s['health']>=min_health
  assert not any(s.get(k) for k in ('borer_active','chopping','navigating'))
  self.anchor=list(s['pos']);self.world=s['world_session'];self.rev=s['control_revision'];self.owned=False;self.last=None
 def raw(self):
  s=json.loads((self.root/'status.json').read_text())
  from safety_interlock import require_unlocked
  require_unlocked(self.root,s)
  if time.time()*1000-s['time']>3000:raise RuntimeError('Game state is stale')
  return s
 def status(self):
  s=self.raw()
  if not s.get('connected') or s.get('world_session')!=self.world or s.get('control_revision')!=self.rev or s.get('manual_movement'):raise Handoff('Control or world changed; no more commands')
  if s.get('screen') not in ('','ContainerScreen','InventoryScreen','CraftingScreen','ShulkerBoxScreen','FurnaceScreen','BlastFurnaceScreen','SmokerScreen','AnvilScreen','BrewingStandScreen'):raise Handoff('User opened a different interface')
  return s
 def request(self,op,**params):
  until=time.monotonic()+60
  while True:
   s=self.status()
   if op!='safe_logout' and s.get('health',0)<14:raise RuntimeError('Low health')
   if op in ('guard','snapshot','scan','scan_trees','safe_logout','use_item') or not s.get('guard_busy'):break
   vertical_escape=vertical_surface_escape(s,op,params)
   if s.get('under_water') and not vertical_escape:
    raise RuntimeError('Defense is busy underwater; surface before another action')
   if vertical_escape:break
   if time.monotonic()>until:raise RuntimeError('Defense remains busy')
   time.sleep(.25)
  if op!='safe_logout' and s.get('health',0)<14:raise RuntimeError('Low health')
  if not underwater_action_allowed(s,op,params):raise RuntimeError('Low oxygen: only a near-vertical surface ascent is allowed')
  path=self.root/'request.json'
  if path.exists() and json.loads(path.read_text()).get('id')!=s.get('last_request'):raise Handoff('Another controller has a pending request')
  rid='materials-'+uuid.uuid4().hex[:12]
  req={'id':rid,'op':op,'server':s['server'],'dimension':s['dimension'],'site':self.anchor,
       'world_session':self.world,'expected_revision':self.rev,'expires_at':int(time.time()*1000)+5000,**params}
  evidence_before=s;request_started=time.monotonic()
  tmp=path.with_suffix('.materials.tmp');tmp.write_text(json.dumps(req));tmp.replace(path);self.last=rid
  expected=self.rev+(2 if op in ('stop','safe_logout') else 1 if op in ('navigate','chop','walk','walk_path','print','mine_block','recover_shulker','professional_print','projection_start','borer_start') else 0)
  end=time.monotonic()+params.get('seconds',20)+15
  last_poll=time.monotonic();guard_pause=0
  while time.monotonic()<end:
   current=self.raw()
   now=time.monotonic()
   # Guard combat may extend a dry task, but never buy extra underwater time:
   # oxygen keeps falling while the operation is paused.
   end,guard_pause=credit_guard_pause(end,guard_pause,now-last_poll,
                                      current.get('guard_busy',False) and not current.get('under_water',False))
   last_poll=now
   if current.get('world_session')!=self.world or not current.get('connected'):
    if op=='safe_logout':return current
    raise Handoff('World disconnected')
   reply=self.root/('reply-'+rid+'.json');result=json.loads(reply.read_text()) if reply.exists() else current
   terminal=result.get('id')==rid and result.get('phase') in ('done','stopped','error','waiting')
   lease=current.get('supervision_lease',{})
   native_stop=terminal and current.get('last_request')==rid and lease.get('job_session')==getattr(self,'task',None) and lease.get('revision')==current['control_revision'] and lease.get('kind')=='materials'
   # A native movement timeout may abort its own controller and advance the
   # revision twice before returning "waiting". The exact request ID and the
   # matching terminal snapshot prove this is our operation, so return that
   # result and let the caller surface; treating it as a foreign handoff left
   # an underwater player waiting for the heartbeat logout.
   owned_terminal=terminal and current.get('last_request')==rid and result.get('control_revision')==current['control_revision'] and result.get('world_session')==self.world
   # safe_logout may stop several client controllers before the disconnect
   # snapshot appears. The issued request ID proves this transition belongs to
   # our one-shot logout; do not retry or mistake its revision jump for a handoff.
   owned_logout=op=='safe_logout' and current.get('last_request')==rid
   if current.get('manual_movement') or current['control_revision'] not in (self.rev,expected) and not native_stop and not owned_terminal and not owned_logout:raise Handoff('Control revision changed outside the owned request')
   if reply.exists() or current.get('last_request')==rid and current.get('id')==rid and current.get('phase') in ('done','stopped','error','waiting'):
    self.rev=current['control_revision']
    with (self.out/'events.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'request_id':rid,'world_session':self.world,'op':op,'params':params,'phase':result.get('phase'),'detail':result.get('detail'),'pos':current.get('pos'),'health':current.get('health'),'duration_ms':round((time.monotonic()-request_started)*1000),'guard_pause_ms':round(guard_pause*1000),'evidence_scope':'native_operation_reply_not_goal_completion',**observed_delta(evidence_before,current)},ensure_ascii=False)+'\n')
    try:
     from experience_recording import record_native_transaction
     if getattr(self,'record_experience',False):record_native_transaction(req,evidence_before,result,getattr(self,'experience_state',None))
    except Exception as e:
     # An optional local recorder must never turn a completed game action into a retry.
     try:
      with (self.out/'experience-recording-errors.jsonl').open('a') as f:f.write(json.dumps({'request_id':rid,'error':str(e)})+'\n')
     except OSError:pass
    if op=='guard' and result.get('phase')=='done':self.owned=True
    return result
   time.sleep(.15)
  raise RuntimeError('Native operation timed out; do not replay it')
 def checked(self,op,**params):
  r=self.request(op,**params)
  if r.get('phase')!='done':raise RuntimeError(r.get('detail',op+' failed'))
  return r
 def finish(self):
  if not self.owned:return
  try:
   s=self.status()
   if s.get('guard_armed'):
    if s.get('phase')=='running':
     if s.get('last_request')!=self.last:return
     self.checked('stop')
    self.request('safe_logout')
  except Handoff:pass
 def transfer(self,item,target,deposit=False):
  for _ in range(16):
   s=self.status();before=stocks(s).get(item,0)
   if before<=target if deposit else before>=target:return before
   menu=s['menu'];assert menu['type'] in ('ChestMenu','ShulkerBoxMenu') and menu['cursor']['count']==0
   boundary=len(menu['slots'])-36
   pool=menu['slots'][boundary:] if deposit else menu['slots'][:boundary]
   if deposit and not any(v['count']==0 or v['item']==item and v['count']<v.get('max_stack',64) for v in menu['slots'][:boundary]):raise RuntimeError('Depot has no space for '+item)
   source=next((v for v in pool if v['item']==item and v['count']),None)
   if source is None:return before
   self.checked('slot_click',menu_id=menu['id'],slot=source['slot'],expected_item=item,expected_count=source['count'],kind='quick_move')
   deadline=time.monotonic()+6
   while time.monotonic()<deadline:
    after=stocks(self.status()).get(item,0)
    if (after<before if deposit else after>before):break
    time.sleep(.2)
   else:raise RuntimeError('Inventory transfer not confirmed; no duplicate click')
  raise RuntimeError('Transfer limit reached')
 def open(self,pos):
  self.checked('select_item',item='minecraft:diamond_sword')
  block=self.request('scan',min=pos,max=pos)['blocks'];assert len(block)==1 and 'minecraft:chest' in block[0]['state']
  self.checked('interact',pos=pos,face='south',expected_state=block[0]['state'],expected_hand='minecraft:diamond_sword')
  end=time.monotonic()+5
  while time.monotonic()<end:
   s=self.status()
   if s['menu']['type']=='ChestMenu':
    self.owned_material_menu=s['menu']['id'];return
   time.sleep(.2)
  raise RuntimeError('Chest was not opened')
class MaterialClient(Client):
 PARK_RADIUS_SQR=8*8
 def park_near(self,state):
  pos=state.get('pos')
  return bool(pos and abs(pos[1]-self.park_target[1])<=2 and
              (pos[0]-self.park_target[0])**2+(pos[2]-self.park_target[2])**2<=self.PARK_RADIUS_SQR)
 def __init__(self,root,out,server="simpcraft.com:25565",allow_empty_inventory=False,record_experience=True,experience_state=None,remote_finish='disconnect',park_target=None):
  if remote_finish not in ('disconnect','guard') or remote_finish=='guard' and (not isinstance(park_target,(list,tuple)) or len(park_target)!=3):raise ValueError('Guard finish requires a high park target')
  self.remote_finish=remote_finish;self.park_target=list(park_target) if park_target is not None else None
  self.heartbeat=None;self.owned_material_menu=None
  super().__init__(root,out,server,min_health=18)
  self.record_experience=record_experience;self.experience_state=experience_state
  s=self.raw()
  if remote_finish=='guard' and math.hypot(s['pos'][0]-self.park_target[0],s['pos'][2]-self.park_target[2])<=32:
   px,pz=math.floor(self.park_target[0]),math.floor(self.park_target[2])
   observed=Client.request(self,'scan',min=[px,-64,pz],max=[px,320,pz],details=True)
   if 'blocks' not in observed or high_park_clearance(observed['blocks'],self.park_target[1])<20:
    raise Handoff('High guard park must be at least 20 blocks above verified ground')
  if s.get('material_protocol',0)<2 or not s.get('inventory_isolation',{}).get('supported'):raise Handoff('Restart into Kit with verified inventory isolation before crafting')
  if not allow_empty_inventory and not any(v.get('count',0)>0 for v in s.get('inventory',[])):
   raise Handoff('Inventory is empty or not synchronized; material work cannot start')
  if s.get('professional_printer',{}).get('enabled'):
   if s.get('professional_printer',{}).get('owned') or s.get('build_job',{}).get('active') or s.get('supervision_lease',{}).get('kind') not in (None,'parking'):raise Handoff('Another task owns printing; do not interrupt it for material work')
   stopped=Client.request(self,'stop')
   s=self.status()
   if stopped.get('phase')!='stopped' or s.get('professional_printer',{}).get('enabled'):raise Handoff('External printer could not be suspended before material control')
  parking=s.get('supervision_lease',{});replace=parking.get('id') if parking.get('kind')=='parking' else None
  self.task='materials-'+uuid.uuid4().hex[:16]
  write_manifest(self.out,self.task,s)
  self.heartbeat=SafetyHeartbeat(self.root,self.world);self.heartbeat.start()
  try:
   self.checked('material_session',supervision_lease=self.heartbeat.id,remote_finish=self.remote_finish,
                **({'park_target':self.park_target} if self.park_target is not None else {}),
                **({'replace_parking_lease':replace} if replace else {}))
   self.heartbeat.attached=True
  except BaseException:self.heartbeat.close();raise
 def raw(self):
  s=super().raw()
  if self.heartbeat:self.heartbeat.touch()
  return s
 def request(self,op,**params):
  for attempt in range(4):
   r=super().request(op,task_session=self.task,background_ok=True,**params)
   if r.get('phase')!='error' or r.get('detail')!='Construction guard is defending or eating; wait before changing items or starting work':return r
   # This exact native rejection happens before dispatch mutates game state; ambiguous failures are never replayed.
   self.status();time.sleep(.25)
  return r
 def finish(self):
  # Recover owned temporary resources while heartbeat and defense are still alive.
  from material_cleanup import run as cleanup_resources
  cleanup_resources(self)
  # Recover only our exact workbench before releasing its native safety lease.
  try:
   from craft_recovery import clear_owned_workbench
   clear_owned_workbench(self)
   s=self.status();m=s.get('menu',{})
   clean_workbench=m.get('type')=='CraftingMenu' and all(not v['count'] for v in m['slots'][:10])
   clean_anvil=m.get('type')=='AnvilMenu' and all(not v['count'] for v in m['slots'][:3])
   clean_brewer=m.get('type')=='BrewingStandMenu' and all(not v['count'] for v in m['slots'][:5])
   storage=m.get('type') in ('ChestMenu','ShulkerBoxMenu')
   furnace=m.get('type') in ('FurnaceMenu','BlastFurnaceMenu','SmokerMenu')
   if self.owned_material_menu==m.get('id') and (clean_workbench or clean_anvil or clean_brewer or storage or furnace) and not m['cursor']['count']:
    self.checked('close_menu')
  except (Handoff,RuntimeError,KeyError):pass
  if self.remote_finish=='guard':
   try:
    s=self.status()
    if s['health']<18 or not s.get('guard_armed'):raise RuntimeError('High parking needs full health and PvE guard')
    if not self.park_near(s):
     r=self.request('navigate',target=self.park_target,arrival=2,seconds=120)
     if r.get('phase')!='done':raise RuntimeError('High parking route did not finish: '+str(r.get('detail')))
    s=self.status()
    if s['health']<18 or not s.get('guard_armed') or not self.park_near(s):
     raise RuntimeError('High parking position or guard not verified')
   except Handoff:
    self.heartbeat.close();return
   except (RuntimeError,KeyError) as error:
    (self.out/'park-fallback.json').write_text(json.dumps({'reason':str(error),'action':'safe_logout'},ensure_ascii=False))
    try:self.request('safe_logout')
    except (Handoff,RuntimeError):pass
    self.heartbeat.close();return
  self.heartbeat.close()
  p=self.root/('supervision-receipt-'+self.heartbeat.id+'.json')
  for _ in range(200 if self.remote_finish=='guard' else 600):
   pending_disconnect=False
   if p.exists():
    d=json.loads(p.read_text())
    if self.remote_finish=='guard' and d.get('action')=='KEEP_PVE_GUARD':
     try:s=self.raw()
     except RuntimeError:break
     if s.get('connected') and s.get('guard_armed') and s.get('health',0)>=18 and self.park_near(s):
      (self.out/'stock-safety.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print('HIGH_GUARD_CONFIRMED',flush=True);return
    pending_disconnect=d.get('action')=='LOGOUT' and not d.get('confirmed')
    if d.get('confirmed'):
     (self.out/'stock-safety.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print('DISCONNECT_CONFIRMED',d['action'],d['cause'],flush=True);return
   try:s=self.raw()
   except RuntimeError:
    print('Native finish acknowledgement unavailable; heartbeat has stopped',flush=True);return
   lease=s.get('supervision_lease',{})
   if lease.get('id')==self.heartbeat.id and lease.get('kind')=='parking':self.rev=s['control_revision']
   if s.get('world_session')!=self.world or s.get('manual_movement') or s.get('control_revision')!=self.rev and not pending_disconnect:return
   if lease and lease.get('id')!=self.heartbeat.id:return
   time.sleep(.15)
  if self.remote_finish=='guard':
   try:self.request('safe_logout')
   except (Handoff,RuntimeError):pass
   print('High hover was not confirmed; requested safe logout',flush=True)
 def fetch(self,pos,materials):
  r=self.request('collect_supply',source_key='minecraft:overworld:'+':'.join(map(str,pos)),materials={'minecraft:'+k:v for k,v in materials.items()},seconds=180)
  if r.get('phase')=='done':
   held=stocks(self.status())
   short={name:max(0,target-held.get('minecraft:'+name,0)) for name,target in materials.items()}
   short={name:count for name,count in short.items() if count}
   if short:
    r={**r,'phase':'waiting','native_phase':'done','detail':'Approved depot contains less than the requested stock','shortfall':short}
  print('FETCH',pos,r.get('phase'),r.get('detail'),r.get('build_supply'),flush=True)
  return r
