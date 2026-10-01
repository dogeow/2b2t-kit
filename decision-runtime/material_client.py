"""Shared native material client. Every action is scoped to a live world, revision and safety lease."""
import json,math,time,uuid
from collections import deque
from pathlib import Path
from build_supervisor import SafetyHeartbeat,stocks
from run_evidence import observed_delta,write_manifest
from sensitive_data import sanitize,scrub_confirmed_json
class Handoff(Exception):pass
def reply_observation(path):
 try:raw=path.read_text()
 except FileNotFoundError:return 'absent',None
 except (OSError,UnicodeError):return 'unreadable',None
 try:value=json.loads(raw)
 except (json.JSONDecodeError,UnicodeError):return 'invalid',None
 return ('valid',value) if isinstance(value,dict) else ('invalid',None)
def credit_guard_pause(deadline,paused,elapsed,busy,max_pause=180):
  credit=min(max(0,elapsed),max(0,max_pause-paused)) if busy else 0
  return deadline+credit,paused+credit
def credit_interface_pause(deadline,paused,elapsed,state):
 # Native protocol excludes inventory controls and emergency underwater returns.
 # A user's passive interface can remain open arbitrarily long; this is not work time.
 credit=max(0,elapsed) if state.get('interface_pause_protocol')==1 and state.get('interface_paused') is True else 0
 return deadline+credit,paused+credit
def high_park_clearance(rows,target_y):
  ground=[row['pos'][1]+1 for row in rows if row.get('fluid') or not row.get('passable',True)]
  if not ground:raise Handoff('High guard park has no verified ground column')
  return target_y-max(ground)
def bounded_canopy_path(rows,pos,target_y,radius=4):
 """A short, natural-ground walk to an observed open vertical column, or none."""
 if not isinstance(pos,list) or len(pos)!=3:return None
 x0,z0=math.floor(pos[0]),math.floor(pos[2]);y=math.floor(pos[1])
 # A .30-wide player half-body must fit the observed start cell before the
 # first native AABB sweep; off-centre starts yield instead of guessing.
 if abs(pos[0]-(x0+.5))>.18 or abs(pos[2]-(z0+.5))>.18:return None
 cells={}
 for row in rows:
  point=row.get('pos') if isinstance(row,dict) else None
  if not isinstance(point,list) or len(point)!=3 or any(type(v) is not int for v in point):return None
  key=tuple(point)
  if key in cells:return None
  cells[key]=row
 ground={'minecraft:grass_block','minecraft:dirt','minecraft:coarse_dirt',
         'minecraft:podzol','minecraft:stone','minecraft:cobblestone',
         'minecraft:deepslate','minecraft:moss_block',
         'minecraft:stone_bricks','minecraft:polished_andesite'}
 soft={'minecraft:short_grass','minecraft:tall_grass','minecraft:fern','minecraft:large_fern'}
 def block_id(row):
  state=row.get('state')
  return state.split('}',1)[0].removeprefix('Block{') if isinstance(state,str) else ''
 def body_clear(x,z):
  for head in (y,y+1):
   row=cells.get((x,head,z))
   if row and (block_id(row) not in soft or row.get('passable') is not True
               or row.get('fluid') is not False or row.get('block_entity') is not False):return False
  return True
 def floor_clear(x,z):
  row=cells.get((x,y-1,z))
  return bool(row and block_id(row) in ground and row.get('solid') is True
              and row.get('fluid') is False and row.get('block_entity') is False)
 def safe(x,z):return (abs(x-x0)<=radius and abs(z-z0)<=radius
                       and body_clear(x,z) and floor_clear(x,z))
 def open_column(x,z):return all((x,h,z) not in cells for h in range(y,math.ceil(target_y)+3))
 if not safe(x0,z0):return None
 queue=deque([(x0,z0)]);parent={(x0,z0):None};goal=None
 while queue:
  x,z=queue.popleft()
  if (x,z)!=(x0,z0) and open_column(x,z):goal=(x,z);break
  for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)):
   nxt=(x+dx,z+dz)
   if nxt not in parent and safe(*nxt):parent[nxt]=(x,z);queue.append(nxt)
 if goal is None:return None
 route=[]
 while goal is not None:
  route.append([goal[0]+.5,pos[1],goal[1]+.5]);goal=parent[goal]
 route=list(reversed(route))
 return route if len(route)-1<=4 else None
def underwater_action_allowed(state,op,params):
 from dive_safety import native_air_budget,pickup_air_floor
 budget=native_air_budget(state)
 floor=budget[1] if budget else 240
 if budget and (op=='collect_item' or op=='walk' and params.get('water_descend')):floor=pickup_air_floor(state)
 if state.get('air_return_active') and op in ('navigate','walk','collect_item','approach_block','mine_block'):
  return vertical_surface_escape(state,op,params)
 if not state.get('under_water') or state.get('water_breathing_effect') or state.get('conduit_power_effect') or state.get('air_supply',0)>=floor:return True
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
def pending_request_state(request,last_request,owned_last,world):
 if request.get('id')==last_request:return 'clear'
 if request.get('id')==owned_last and request.get('world_session')==world:return 'wait_owned'
 return 'foreign'
_REVISION_ADVANCING_OPS=frozenset(('navigate','chop','walk','walk_path','print','mine_block','recover_shulker','professional_print','projection_start','borer_start'))
def expected_native_revision(op,base):
 return base+(2 if op in ('stop','safe_logout') else 1 if op in _REVISION_ADVANCING_OPS else 0)
class Client:
 def __init__(self,root,out,server,min_health=18):
  self.root=Path(root);self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True);self.server=server
  s=self.raw();assert s.get('server','').removesuffix(':25565')==self.server.removesuffix(':25565') and s['dimension']=='minecraft:overworld'
  assert not s['screen'] and not s.get('manual_movement') and s['health']>=min_health
  assert not any(s.get(k) for k in ('borer_active','chopping','navigating'))
  self.anchor=list(s['pos']);self.world=s['world_session'];self.rev=s['control_revision'];self.owned=False;self.last=None;self.native_inflight=None
 def raw(self,wait_seconds=None):
  from live_snapshot import read_fresh
  s=read_fresh(self.root) if wait_seconds is None else read_fresh(self.root,wait_seconds=wait_seconds)
  from safety_interlock import require_unlocked
  require_unlocked(self.root,s)
  floor=getattr(self,'minimum_status_time',None)
  deadline=time.monotonic()+(6 if wait_seconds is None else max(0,wait_seconds))
  while (type(floor)is int and type(s.get('time'))is int and s['time']<floor
         and s.get('world_session')==getattr(self,'world',s.get('world_session'))):
   if time.monotonic()>=deadline:raise RuntimeError('Latest owned reply has not reached the status file; preserve the operation and do not replay')
   time.sleep(.025)
   s=read_fresh(self.root,wait_seconds=max(0,deadline-time.monotonic()))
   require_unlocked(self.root,s)
  return s
 def status(self,wait_seconds=None,*,wait_interface=True):
  while True:
   s=self.raw() if wait_seconds is None else self.raw(wait_seconds=wait_seconds)
   if not s.get('connected') or s.get('world_session')!=self.world or s.get('control_revision')!=self.rev or s.get('manual_movement'):
    self.last_owned_ground_walk=None
    raise Handoff('Control or world changed; no more commands')
   paused=s.get('interface_pause_protocol')==1 and s.get('interface_paused') is True
   if paused:
    if not wait_interface or s.get('health',20)<14:return s
    # raw() keeps the owned heartbeat and health observations alive while typing.
    time.sleep(.15);continue
   if s.get('screen') not in ('','ContainerScreen','InventoryScreen','CraftingScreen','ShulkerBoxScreen','FurnaceScreen','BlastFurnaceScreen','SmokerScreen','AnvilScreen','BrewingStandScreen'):raise Handoff('User opened a different interface')
   return s
 def request(self,op,**params):
  until=time.monotonic()+60
  while True:
   s=self.status(wait_interface=False) if op in ('stop','safe_logout','material_job_pause') else self.status()
   if op!='safe_logout' and s.get('health',0)<14 and not vertical_surface_escape(s,op,params):raise RuntimeError('Low health')
   if op in ('guard','snapshot','scan','scan_trees','safe_logout','use_item') or not s.get('guard_busy'):break
   vertical_escape=vertical_surface_escape(s,op,params)
   if s.get('under_water') and not vertical_escape:
    raise RuntimeError('Defense is busy underwater; surface before another action')
   if vertical_escape:break
   if time.monotonic()>until:raise RuntimeError('Defense remains busy')
   time.sleep(.25)
  if op!='safe_logout' and s.get('health',0)<14 and not vertical_surface_escape(s,op,params):raise RuntimeError('Low health')
  if not underwater_action_allowed(s,op,params):raise RuntimeError('Low oxygen: only a near-vertical surface ascent is allowed')
  path=self.root/'request.json'
  if path.exists():
   pending=json.loads(path.read_text())
   ownership=pending_request_state(pending,s.get('last_request'),self.last,self.world)
   if ownership=='foreign':raise Handoff('Another controller has a pending request')
   if ownership=='wait_owned':
    until_pending=time.monotonic()+1.5
    while time.monotonic()<until_pending:
     s=self.status()
     if s.get('last_request')==pending.get('id'):break
     time.sleep(.05)
    else:raise Handoff('Previous owned request was not acknowledged')
  rid='materials-'+uuid.uuid4().hex[:12]
  req={'id':rid,'op':op,'server':s['server'],'dimension':s['dimension'],'site':self.anchor,
       'world_session':self.world,'expected_revision':self.rev,'expires_at':int(time.time()*1000)+5000,**params}
  evidence_before=s;request_started=time.monotonic()
  if op not in ('snapshot','scan'):self.last_owned_ground_walk=None
  expected=expected_native_revision(op,self.rev)
  tmp=path.with_suffix('.materials.tmp');tmp.write_text(json.dumps(req))
  inflight={'request_id':req['id'],'op':req['op'],'world_session':req['world_session'],
            'task_session':req.get('task_session'),'lease_id':(s.get('supervision_lease') or {}).get('id'),
            'base_revision':self.rev,'request_revision':req['expected_revision'],'expected_revision':expected,
            'server':req['server'],'dimension':req['dimension']}
  # Publish the exact envelope before native code can consume the atomic mailbox.
  previous_last=self.last
  try:
   try:
    self.native_inflight=inflight;self.last=rid
    tmp.replace(path)
   except BaseException:
    self.last=previous_last;raise
   end=time.monotonic()+params.get('seconds',20)+15
   last_poll=time.monotonic();guard_pause=0;interface_pause=0;movement_samples=[]
   while time.monotonic()<end:
    current=self.raw()
    now=time.monotonic()
    # Guard combat may extend a dry task, but never buy extra underwater time:
    # oxygen keeps falling while the operation is paused.
    ui_paused=current.get('interface_pause_protocol')==1 and current.get('interface_paused') is True
    end,interface_pause=credit_interface_pause(end,interface_pause,now-last_poll,current)
    end,guard_pause=credit_guard_pause(end,guard_pause,now-last_poll,
                                       current.get('guard_busy',False) and not current.get('under_water',False) and not ui_paused)
    last_poll=now
    if current.get('world_session')!=self.world or not current.get('connected'):
     if op=='safe_logout':return current
     raise Handoff('World disconnected')
    reply=self.root/('reply-'+rid+'.json');reply_state,reply_result=reply_observation(reply)
    result=reply_result if reply_state=='valid' else current
    terminal=result.get('id')==rid and result.get('phase') in ('done','stopped','error','waiting')
    # Exact replies are written synchronously; status IO is coalesced off-thread.
    # Do not bind the new revision or inspect inventory against an older status.
    if (terminal and result.get('world_session')==self.world and type(result.get('time'))is int
        and type(current.get('time'))is int and result['time']>current['time']):
     self.minimum_status_time=result['time'];current=self.raw()
     ui_paused=current.get('interface_pause_protocol')==1 and current.get('interface_paused') is True
    if op in ('navigate','approach_block','walk','collect_item') and not terminal:
     movement_samples.append({k:current.get(k) for k in ('time','pos','velocity','movement_keys','guard_busy','build_supply','phase','detail')})
     movement_samples=movement_samples[-3:]
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
    if ui_paused and current.get('health',20)>=14 and op not in ('stop','safe_logout','material_job_pause'):
     time.sleep(.15);continue
    matching_reply=reply_state=='valid' and result.get('id')==rid
    status_terminal=(reply_state=='absent' and current.get('last_request')==rid
                     and current.get('id')==rid
                     and current.get('phase') in ('done','stopped','error','waiting'))
    if matching_reply or status_terminal:
     self.rev=current['control_revision']
     self.last_terminal_evidence={
      'request_id':rid,'task_session':getattr(self,'task',None),
      'world_session':self.world,'server':s.get('server'),'dimension':s.get('dimension'),
      'op':op,'params':sanitize(params),'phase':result.get('phase'),
      'detail':result.get('detail'),'position_before':evidence_before.get('pos'),
      'terminal_pos':current.get('pos'),'revision_before':evidence_before.get('control_revision'),
      'revision_after':current.get('control_revision'),
      'movement_keys':current.get('movement_keys'),'velocity':current.get('velocity'),
      'pre_dispatch_rejected':bool(result.get('phase')=='error'
        and result.get('detail')=='Air-only navigation requires the current material lease and a loaded clear dry path'
        and evidence_before.get('pos')==current.get('pos'))}
     if (op=='walk' and result.get('phase')=='done' and params.get('restore_flight') is False
         and owned_terminal and current.get('last_request')==rid):
      fields=('time','connected','world_session','control_revision','server','dimension','screen','last_request',
              'pos','health','flight','under_water','kill_aura','auto_log','navigating','native_material_busy',
              'guard_armed','guard_pve_only','guard_busy','manual_movement','recent_hurt_at','recent_attacker',
              'safety_hold','supervision_lease','movement_keys','velocity','on_ground')
      self.last_owned_ground_walk=json.loads(json.dumps({
       'request_id':rid,'task_session':getattr(self,'task',None),'world_session':self.world,
       'revision':current['control_revision'],'phase':'done','op':'walk','params':sanitize(params),
       'before_damage':{key:evidence_before.get(key) for key in ('recent_hurt_at','recent_attacker')},
       'before_safety_hold':evidence_before.get('safety_hold'),
       'terminal':{key:current.get(key) for key in fields}}))
     try:
      scrub_confirmed_json(path,rid,self.world)
      scrub_confirmed_json(reply,rid,self.world)
     except (OSError,ValueError,TypeError,json.JSONDecodeError) as error:
      try:
       with (self.out/'mailbox-scrub-errors.jsonl').open('a') as stream:
        stream.write(json.dumps({'request_id':rid,'error':type(error).__name__})+'\n')
      except OSError:pass
     if movement_samples and result.get('phase') in ('waiting','error','stopped'):
      try:(self.out/('movement-failure-'+rid+'.json')).write_text(json.dumps({'op':op,'params':sanitize(params),'detail':result.get('detail'),'last_inflight':movement_samples,'terminal_pos':current.get('pos')},ensure_ascii=False,indent=2))
      except OSError:pass
     with (self.out/'events.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'request_id':rid,'world_session':self.world,'op':op,'params':sanitize(params),'phase':result.get('phase'),'detail':result.get('detail'),'pos':current.get('pos'),'health':current.get('health'),'duration_ms':round((time.monotonic()-request_started)*1000),'guard_pause_ms':round(guard_pause*1000),'interface_pause_ms':round(interface_pause*1000),'evidence_scope':'native_operation_reply_not_goal_completion',**observed_delta(evidence_before,current)},ensure_ascii=False)+'\n')
     try:
      from experience_recording import record_native_transaction
      if getattr(self,'record_experience',False):record_native_transaction(sanitize(req),evidence_before,sanitize(result),getattr(self,'experience_state',None))
     except Exception as e:
      # An optional local recorder must never turn a completed game action into a retry.
      try:
       with (self.out/'experience-recording-errors.jsonl').open('a') as f:f.write(json.dumps({'request_id':rid,'error':str(e)})+'\n')
      except OSError:pass
     if op=='guard' and result.get('phase')=='done':self.owned=True
     return result
    time.sleep(.15)
   raise RuntimeError('Native operation timed out; do not replay it')
  finally:
   if getattr(self,'native_inflight',None) is inflight:self.native_inflight=None
 def checked(self,op,**params):
  r=self.request(op,**params)
  if r.get('phase')!='done':raise RuntimeError(r.get('detail',op+' failed'))
  from terminal_confirmation import verified
  if not verified(op,r,self.world,self.last,params):raise RuntimeError('Native done lacks matching server confirmation; preserve the receipt and do not replay')
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
  from kit_runtime.inventory import InventorySession,destination_capacity
  from kit_runtime.storage import move_amount
  if isinstance(target,bool) or not isinstance(target,int) or target<0:raise ValueError('Transfer target must be a nonnegative count')
  session=InventorySession(self)
  for _ in range(128):
   s=self.status();before=stocks(s).get(item,0)
   if before<=target if deposit else before>=target:return before
   menu=s['menu'];assert menu['type'] in ('ChestMenu','ShulkerBoxMenu') and menu['cursor']['count']==0
   boundary=len(menu['slots'])-36
   pool=menu['slots'][boundary:] if deposit else menu['slots'][:boundary]
   destinations=menu['slots'][:boundary] if deposit else menu['slots'][boundary:]
   source=next((v for v in pool if v['item']==item and v['count']),None)
   if source is None:return before
   destination=next((v for v in destinations if v['count'] and v['item']==item and v['count']<v.get('max_stack',64)),None)
   if destination is None:destination=next((v for v in destinations if not v['count']),None)
   if destination is None:raise RuntimeError('Destination has no space for '+item)
   needed=before-target if deposit else target-before
   if source['count']<=needed:
    session.click(s,source['slot'],'quick_move')
   else:
    room=destination_capacity(source,destination)-destination['count']
    move_amount(session,s,source,destination,min(needed,room))
   deadline=time.monotonic()+6
   while time.monotonic()<deadline:
    fresh=self.status()
    if fresh['menu']['id']!=menu['id']:raise Handoff('Container changed during transfer')
    after=stocks(fresh).get(item,0)
    if (after<target if deposit else after>target):raise RuntimeError('Inventory transfer crossed its requested target')
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
 def ascent_obstacles(self,state):
  """Fail closed before changing height within the current body column."""
  # Y 320 is the caller's supported high park. The world has no blocks above
  # 319; native air_only independently checks the complete player-body sweep.
  if type(self.park_target[1]) not in (int,float) or not math.isfinite(self.park_target[1]) or self.park_target[1]>320:
   raise RuntimeError('High park target height is outside the verified body range')
  pos=state.get('pos')
  if (not isinstance(pos,list) or len(pos)!=3 or
      any(type(v) not in (int,float) or not math.isfinite(v) for v in pos)):
   raise RuntimeError('Current paving park position is unverified')
  if abs(pos[1]-self.park_target[1])<=2:return []
  low_y=(math.floor(pos[1])+1 if pos[1]<self.park_target[1]
         else math.floor(self.park_target[1]))
  high_y=min(319,math.ceil(max(pos[1],self.park_target[1]))+2)
  low=[math.floor(pos[0]-.35),low_y,math.floor(pos[2]-.35)]
  high=[math.floor(pos[0]+.35),high_y,math.floor(pos[2]+.35)]
  if high[1]<low[1]:raise RuntimeError('High park ascent height is unverified')
  reply=self.request('scan',min=low,max=high,details=True)
  if (reply.get('phase') not in (None,'done') or reply.get('world_session')!=self.world
      or not isinstance(reply.get('blocks'),list)):
   raise RuntimeError('High park ascent column was not freshly scanned')
  blocks=[]
  for row in reply['blocks']:
   point=row.get('pos')
   if (not isinstance(point,list) or len(point)!=3 or any(type(v) is not int for v in point)
       or any(point[i]<low[i] or point[i]>high[i] for i in range(3))):
    raise RuntimeError('High park ascent scan returned an invalid block')
   blocks.append({'pos':point,'state':row.get('state')})
  return blocks
 def _finish_canopy_escape(self,state,obstacles):
  """Move at most four ground blocks only through a fresh, natural-floor scan."""
  if (state.get('health',0)<18 or state.get('under_water') or not state.get('guard_armed')
      or not state.get('flight') or any(not isinstance(row.get('state'),str)
      or not row['state'].split('}',1)[0].endswith('_leaves') for row in obstacles)):
   raise RuntimeError('Blocked park column has no eligible local canopy escape')
  start=list(state['pos']);x,z=math.floor(start[0]),math.floor(start[2]);y=math.floor(start[1])
  low=[x-4,y-1,z-4];high=[x+4,min(319,math.ceil(self.park_target[1])+2),z+4]
  reply=self.request('scan',min=low,max=high,details=True)
  if (reply.get('phase') not in (None,'done') or reply.get('world_session')!=self.world
      or not isinstance(reply.get('blocks'),list)):
   raise RuntimeError('Local canopy corridor was not completely scanned')
  for row in reply['blocks']:
   point=row.get('pos') if isinstance(row,dict) else None
   if (not isinstance(point,list) or len(point)!=3 or any(type(v) is not int for v in point)
       or any(point[i]<low[i] or point[i]>high[i] for i in range(3))):
    raise RuntimeError('Local canopy scan returned an invalid block')
  fresh=self.status()
  if (math.dist(fresh['pos'],start)>.25 or fresh.get('health',0)<18
      or not fresh.get('guard_armed') or not fresh.get('flight')):
   raise RuntimeError('Canopy position or protection changed after scan')
  route=bounded_canopy_path(reply['blocks'],start,self.park_target[1])
  if not route:
   raise RuntimeError('No verified short natural-ground exit from canopy')
  route_started=time.monotonic();start_step_deadline=route_started+12
  for waypoint in route[1:]:
   # Budget only NEW step initiation. An issued native request may take its
   # own bounded settlement window and must never be interrupted or replayed.
   remaining=start_step_deadline-time.monotonic()
   if remaining<=3:raise RuntimeError('Local canopy new-step budget ended before the next move')
   fresh=self.status();self._safe_canopy_step(fresh,waypoint)
   result=self.request('navigate',target=waypoint,arrival=.25,
                       seconds=min(6,max(5,math.ceil(remaining))),air_only=True)
   if result.get('phase')!='done':
    raise RuntimeError('Local canopy step was not confirmed: '+str(result.get('detail')))
   fresh=self.status()
   if (math.dist(fresh['pos'],waypoint)>.55 or fresh.get('health',0)<18
       or not fresh.get('guard_armed') or not fresh.get('flight')):
    raise RuntimeError('Local canopy step or protection changed')
   if time.monotonic()>start_step_deadline:
    raise RuntimeError('Local canopy new-step budget ended after a confirmed step')
  self._safe_canopy_step(fresh,fresh['pos'])
  (self.out/'park-canopy-route.json').write_text(json.dumps({
   'world_session':self.world,'from':start,'waypoints':route[1:],
   'actual':fresh['pos'],'confirmed':True,
   'elapsed_seconds':round(time.monotonic()-route_started,3),
   'new_step_initiation_budget_seconds':12},ensure_ascii=False,indent=2))
  return fresh
 def _safe_canopy_step(self,status,waypoint):
  entities=status.get('entities')
  if (status.get('guard_busy') or status.get('health',0)<18
      or not status.get('guard_armed') or not status.get('guard_pve_only')
      or not status.get('flight') or not isinstance(entities,list)):
   raise RuntimeError('Canopy movement lacks fresh independent protection or entity coverage')
  for entity in entities:
   position=entity.get('pos') if isinstance(entity,dict) else None
   if (not isinstance(position,list) or len(position)!=3
       or any(type(v) not in (int,float) or not math.isfinite(v) for v in position)):
    raise RuntimeError('Canopy entity observation is incomplete')
   if entity.get('hostile') is True:
    raise RuntimeError('Canopy movement paused for a nearby hostile')
   if (entity.get('type') not in ('minecraft:item','minecraft:experience_orb')
       and math.dist(position,waypoint)<3):
    raise RuntimeError('Canopy waypoint has a nearby entity')
 def _settle_owned_ground_walk(self,state):
  """Observe at most two seconds of one completed ground walk's tiny landing.

  Read-only scans may replace last_terminal_evidence, so keep a dedicated proof
  that every later movement/menu/inventory dispatch invalidates.
  """
  proof=getattr(self,'last_owned_ground_walk',None)
  if not isinstance(proof,dict):raise RuntimeError('Ground settlement has no owned completed walk')
  terminal=proof.get('terminal',{});params=proof.get('params',{})
  if (not isinstance(terminal,dict) or not isinstance(params,dict)
      or proof.get('op')!='walk' or proof.get('phase')!='done' or params.get('restore_flight') is not False
      or proof.get('world_session')!=self.world or proof.get('task_session')!=self.task
      or proof.get('revision')!=self.rev or not isinstance(proof.get('request_id'),str) or not proof['request_id']
      or params.get('water_descend') or 'freefall_brake_y' in params):
   raise RuntimeError('Ground settlement walk ownership is unverified')
  def vector(value):
   return (isinstance(value,list) and len(value)==3
           and all(type(v) in (int,float) and math.isfinite(v) for v in value))
  origin=terminal.get('pos');target=params.get('target');arrival=params.get('arrival',.65)
  if (not vector(origin) or not vector(target) or type(arrival) not in (int,float)
      or not math.isfinite(arrival) or not 0<arrival<=1
      or type(terminal.get('time')) is not int
      or type(terminal.get('recent_hurt_at')) is not int
      or terminal.get('last_request')!=proof['request_id']
      or proof.get('before_safety_hold')!=terminal.get('safety_hold')
      or proof.get('before_damage')!={key:terminal.get(key) for key in ('recent_hurt_at','recent_attacker')}):
   raise RuntimeError('Ground settlement pose, arrival or damage proof is incomplete')
  def safe(sample):
   lease=sample.get('supervision_lease') or {};hold=sample.get('safety_hold')
   if (sample.get('connected') is not True or sample.get('world_session')!=self.world
       or sample.get('control_revision')!=self.rev or sample.get('last_request')!=self.last
       or not isinstance(terminal.get('server'),str) or not terminal['server']
       or sample.get('server')!=terminal['server'] or sample.get('dimension')!=terminal.get('dimension')
       or sample.get('screen')!=''
       or sample.get('health')!=20 or sample.get('flight') is not False
       or sample.get('kill_aura') is not True or sample.get('auto_log') is not True
       or sample.get('guard_armed') is not True or sample.get('guard_pve_only') is not True
       or sample.get('guard_busy') is not False or sample.get('under_water') is not False
       or sample.get('manual_movement') is not False or sample.get('navigating') or sample.get('native_material_busy')
       or not isinstance(hold,dict) or hold.get('active') is not False or hold!=terminal.get('safety_hold')
       or any(sample.get(key)!=terminal.get(key) for key in ('recent_hurt_at','recent_attacker'))
       or lease.get('kind')!='materials' or lease.get('id')!=self.heartbeat.id
       or lease.get('job_session')!=self.task or lease.get('world_session')!=self.world
       or lease.get('revision')!=self.rev or lease.get('remote_finish')!='guard'):
    raise RuntimeError('Ground settlement ownership or protection changed')
   pos=sample.get('pos');keys=sample.get('movement_keys');velocity=sample.get('velocity')
   if (not vector(pos) or not vector(velocity) or not isinstance(keys,dict)
       or not {'forward','back','jump','sneak'}.issubset(keys)
       or any(value is not False for value in keys.values())
       or math.hypot(pos[0]-origin[0],pos[2]-origin[2])>1
       or math.hypot(pos[0]-target[0],pos[2]-target[2])>arrival
       or not -.5<=pos[1]-origin[1]<=.05
       or type(sample.get('time')) is not int or sample['time']<terminal['time']):
    raise RuntimeError('Ground settlement residual motion is outside the owned walk bounds')
   return pos,velocity
  # Check the actual terminal protection as well as every subsequent sample.
  safe({**terminal,'last_request':self.last})
  deadline=time.monotonic()+2;stable=None;sample=state
  while True:
   pos,velocity=safe(sample)
   if sample.get('on_ground') is True and math.hypot(velocity[0],velocity[2])<=.03 and abs(velocity[1])<=.1:
    if (stable is not None and sample['time']-stable['time']>=400
        and math.dist(pos,stable['pos'])<=.08):
     (self.out/'park-ground-settlement.json').write_text(json.dumps({
      'scope':'owned_completed_ground_walk_read_only_settlement','world_session':self.world,
      'request_id':proof['request_id'],'from':origin,'settled':pos,
      'observed_span_ms':sample['time']-stable['time'],'maximum_wait_seconds':2},ensure_ascii=False,indent=2))
     return sample
    if stable is None or math.dist(pos,stable['pos'])>.08:stable=sample
   else:stable=None
   remaining=deadline-time.monotonic()
   if remaining<=0:raise RuntimeError('Owned ground walk did not settle within two seconds')
   time.sleep(min(.05,remaining))
   sample=self.status(wait_seconds=0)
 def _finish_vertical(self,state,emergency=False):
  """One verified same-column route; never follow an uncertain reply with another move."""
  if (not emergency and state.get('flight') is False
      and getattr(self,'last_owned_ground_walk',None) is not None):
   state=self._settle_owned_ground_walk(state)
  start=list(state['pos']);target_y=self.park_target[1]
  if abs(start[1]-target_y)<=2:return state
  # Opening a ground-level chest deliberately disables Flight.  A normal
  # air-only navigate can restore it, but only treat that exact stable pose as
  # an eligible takeoff: emergency/partial-health/ascent-in-progress states
  # must retain the existing safe-logout fallback.
  grounded_takeoff=(not emergency and not state.get('flight')
                    and state.get('on_ground') is True
                    and state.get('health',0)>=20
                    and state.get('guard_armed')
                    and not state.get('guard_busy')
                    and not state.get('under_water'))
  obstacles=self.ascent_obstacles(state);canopy_escaped=False
  if obstacles:
   (self.out/'park-column-obstacle.json').write_text(json.dumps({
    'world_session':self.world,'player_pos':start,'park_target':self.park_target,
    'obstacles':obstacles[:16],'count':len(obstacles),
    'action':'bounded_canopy_egress_or_safe_logout'},ensure_ascii=False,indent=2))
   if emergency:raise RuntimeError('Critical health under blocked ascent; no lateral movement')
   state=self._finish_canopy_escape(state,obstacles)
   canopy_escaped=True
   obstacles=self.ascent_obstacles(state)
   if obstacles:raise RuntimeError('Canopy exit column changed; no upward movement sent')
   start=list(state['pos'])
  fresh=self.status()
  if canopy_escaped:self._safe_canopy_step(fresh,fresh['pos'])
  takeoff_still_safe=(grounded_takeoff and not fresh.get('flight')
                      and fresh.get('on_ground') is True
                      and fresh.get('health',0)>=20
                      and not fresh.get('guard_busy')
                      and not fresh.get('under_water'))
  if (math.dist(fresh['pos'],start)>.25 or not fresh.get('guard_armed')
      or not (fresh.get('flight') or takeoff_still_safe)):
   raise RuntimeError('High park ascent position or protection changed after scan')
  target=[fresh['pos'][0],target_y,fresh['pos'][2]]
  if emergency and fresh.get('guard_busy'):
   raise RuntimeError('Critical health with active defense; no ascent command sent')
  seconds=8 if emergency else min(90,max(12,math.ceil(abs(target_y-fresh['pos'][1])/2)+12))
  result=self.request('navigate',target=target,arrival=1,seconds=seconds,air_only=True)
  if result.get('phase')!='done':
   raise RuntimeError('High park vertical route was not confirmed: '+str(result.get('detail')))
  reached=self.status();pos=reached['pos']
  if (not reached.get('guard_armed') or not reached.get('flight')
      or abs(pos[1]-target_y)>2 or math.hypot(pos[0]-target[0],pos[2]-target[2])>.75):
   raise RuntimeError('High park vertical arrival or protection was not verified')
  return reached
 def __init__(self,root,out,server="simpcraft.com:25565",allow_empty_inventory=False,record_experience=True,experience_state=None,remote_finish='disconnect',park_target=None):
  if remote_finish not in ('disconnect','guard') or remote_finish=='guard' and (not isinstance(park_target,(list,tuple)) or len(park_target)!=3):raise ValueError('Guard finish requires a high park target')
  self.remote_finish=remote_finish;self.park_target=list(park_target) if park_target is not None else None
  self.heartbeat=None;self.owned_material_menu=None;self.owned_inventory_crafting=None;self.job_progress=None
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
 def _observe_owned_health(self,state):
  from safety_interlock import OwnedHealthExitEvidence
  if isinstance(getattr(self,'world',None),str) and isinstance(getattr(self,'task',None),str):
   witness=getattr(self,'health_exit_evidence',None)
   if witness is None:
    witness=self.health_exit_evidence=OwnedHealthExitEvidence(self.world,self.task)
   witness.observe(state)
  return state
 def _record_health_stop(self,reason,*,logout_attempted=False):
  witness=getattr(self,'health_exit_evidence',None)
  if witness is None or not (logout_attempted or witness.disconnected):return
  state=witness.exit_state()
  if state is not None:
   from safety_interlock import record_material_health_exit
   record_material_health_exit(self.root,state,reason)
 def raw(self,wait_seconds=None):
  s=super().raw(wait_seconds=wait_seconds)
  self._observe_owned_health(s)
  if self.heartbeat:self.heartbeat.touch()
  if getattr(self,'job_progress',None):
   # Only follow revisions already accepted by the owning Client request checks.
   self.job_progress.revision=self.rev
   self.job_progress.publish(s)
  return s
 def request(self,op,**params):
  previous=getattr(self,'last',None);returned=False
  try:
   for attempt in range(4):
    r=super().request(op,task_session=self.task,background_ok=True,**params);returned=True
    if r.get('phase')!='error' or r.get('detail')!='Construction guard is defending or eating; wait before changing items or starting work':return r
    # This exact native rejection happens before dispatch mutates game state; ambiguous failures are never replayed.
    self.status();time.sleep(.25)
   return r
  finally:
   if op=='safe_logout':
    self._record_health_stop('Safety logout after current owned health loss',
                             logout_attempted=returned or getattr(self,'last',None)!=previous)
 def start_progress(self,title,total,done=0,phase='准备中'):
  from job_progress import JobProgress
  self.job_progress=JobProgress(self.root,self.world,self.task,self.rev,title,total,done)
  self.set_progress(phase=phase)
 def set_progress(self,*,done=None,phase=None):
  if getattr(self,'job_progress',None):
   self.job_progress.update(done=done,phase=phase)
   try:self.raw()
   except (OSError,RuntimeError,ValueError):pass
 def advance_progress(self,amount):
  if getattr(self,'job_progress',None):self.set_progress(done=self.job_progress.done+amount)
 def advise(self,goal,candidates,scene=None,fallback='wait'):
  from decision_advisor import Advisor
  if not hasattr(self,'advisor'):self.advisor=Advisor(self.out)
  return self.advisor.select(goal,candidates,self.status,scene,fallback)
 def record_advice_outcome(self,decision,result,**evidence):
  if hasattr(self,'advisor'):self.advisor.outcome(decision,result,**evidence)
 def recover_park_health(self,seconds=60):
  """Pause work and use safe high parking for recovery; 19 HP is not a logout threshold."""
  from food_refuel_policy import PREFERRED
  initial=self.status()
  if initial['health']<14:raise RuntimeError('Critical health before guarded recovery')
  if not self.park_near(initial) or not initial.get('guard_armed') or not initial.get('flight'):
   raise RuntimeError('Recovery requires verified guarded high parking')
  options={'rest':'Remain at the verified high guarded position and wait up to 60 seconds for health regeneration.',
           'wait':'Use the local guarded recovery routine; no new mining or travel.'}
  if initial.get('food',20)<20 and any(v.get('slot',99)<9 and v.get('item') in PREFERRED and v.get('count',0)>0 for v in initial.get('inventory',[])):
   options['eat']='Eat an available hotbar meal here, then wait for recovery.'
  if initial.get('health',0)>=18 and initial.get('food',0)>=18:
   options['remain_guarded']='Finish this work session and keep native protection at this verified high safe position without logging out.'
  decision=self.advise('Recover from noncritical injury without unnecessary logout. Preserve player safety and food; do not resume mining below 19 health.',options,
                       {'verified_high_parking':True,'work_health_reserve':19,'parking_min_health':18,'critical_health':14})
  if decision['choice']=='remain_guarded':
   fresh=self.status()
   if fresh['health']>=18 and self.park_near(fresh) and fresh.get('guard_armed') and fresh.get('flight'):
    self.record_advice_outcome(decision,'kept_guarded',health=fresh['health']);return fresh
  deadline=time.monotonic()+seconds
  last_meal=None
  while True:
   state=self.status()
   if state['health']<14:raise RuntimeError('Critical health during guarded recovery')
   if not self.park_near(state) or not state.get('guard_armed') or not state.get('flight'):
    raise RuntimeError('Recovery requires verified guarded high parking')
   if state['health']>=19 or time.monotonic()>=deadline:
    self.record_advice_outcome(decision,'recovered' if state['health']>=19 else 'recovery_wait_finished',health=state['health'],food=state.get('food'))
    if getattr(self,'health_exit_evidence',None):self.health_exit_evidence.recovered(state)
    return state
   # Let Meteor finish its own meal. Native use_item independently rejects
   # hostile proximity and restores the originally held slot after eating.
   if state.get('food',20)<20 and not state.get('guard_busy') and not state.get('under_water'):
    hotbar={v['item']:v['count'] for v in state.get('inventory',[]) if v.get('slot',99)<9 and v.get('count',0)>0}
    meal=next((item for item in PREFERRED if hotbar.get(item)),None)
    key=(meal,hotbar.get(meal),state.get('food'))
    if meal and key!=last_meal:
     last_meal=key
     self.request('use_item',item=meal)
   time.sleep(.25)
 def _owned_guarded_finish_state(self,state,kind):
  lease=state.get('supervision_lease') or {}
  return bool(state.get('connected',True)
   and state.get('world_session')==self.world
   and state.get('health',0)>=18 and state.get('flight') is True
   and state.get('guard_armed') is True and state.get('guard_pve_only') is True
   and not state.get('under_water') and not state.get('manual_movement')
   and not (state.get('safety_hold') or {}).get('active')
   and lease.get('kind')==kind and lease.get('id')==self.heartbeat.id
   and lease.get('job_session')==self.task and lease.get('world_session')==self.world
   and lease.get('remote_finish')=='guard'
   and lease.get('revision')==state.get('control_revision'))
 def _rebase_guarded_finish(self,error):
  """Keep a healthy guarded flyer online at its latest verified column."""
  latest=self.status()
  if (not self._owned_guarded_finish_state(latest,'materials')
      or latest.get('navigating') or latest.get('native_material_busy')):
   return False
  pos=latest.get('pos')
  if (not isinstance(pos,list) or len(pos)!=3
      or any(type(value) not in (int,float) or not math.isfinite(value) for value in pos)
      or not -64<=pos[1]<320):return False
  target=list(pos)
  reply=self.request('material_job_park',park_target=target)
  if reply.get('phase')!='done':return False
  fresh=self.status();self.park_target=target
  if (not self._owned_guarded_finish_state(fresh,'materials')
      or not self.park_near(fresh)):return False
  (self.out/'park-rebase.json').write_text(json.dumps({
   'reason':str(error),'action':'KEEP_PVE_GUARD','world_session':self.world,
   'park_target':target,'observed_revision':fresh.get('control_revision'),
   'health':fresh.get('health'),'guard_armed':True,'flight':True},
   ensure_ascii=False,indent=2))
  return True
 def finish(self):
  try:
   self.set_progress(phase='安全收尾')
   from material_shutdown import drain_pending
   drained=drain_pending(self);state=drained.get('state') or {}
   (self.out/'finish-drain.json').write_text(json.dumps({**{k:v for k,v in drained.items() if k!='state'},'observed':{k:state.get(k) for k in ('time','world_session','control_revision','last_request','phase','health')}},ensure_ascii=False,indent=2))
   if not drained['safe_to_cleanup']:
    self.heartbeat.close()
    if drained['reason']=='low_health':
     from safety_interlock import record_material_health_exit
     record_material_health_exit(self.root,state,'Low health while waiting for the owned action to settle')
    self._observe_owned_health(state)
    self._record_health_stop('Material action disconnected after health loss')
    print('CLEANUP_YIELDED',drained['reason'],flush=True)
    return
   return self._finish()
  finally:
   if getattr(self,'job_progress',None):self.job_progress.close()
 def _finish(self):
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
   health_exit_state=None;guard_finish_started=time.monotonic()
   try:
    s=self._observe_owned_health(self.status())
    if not s.get('guard_armed'):raise RuntimeError('High parking needs PvE guard')
    if s['health']<14:
     health_exit_state=s
     if not s.get('under_water'):self._finish_vertical(s,emergency=True)
     raise RuntimeError('Critical health; rise before safety logout')
    if not self.park_near(s):
     deadline=time.monotonic()+12
     while True:
      s=self.status()
      if s['health']<14:
       health_exit_state=s
       if not s.get('under_water'):self._finish_vertical(s,emergency=True)
       raise RuntimeError('Critical health while reaching high parking')
      if self.park_near(s):break
      # World height does not indicate immersion: dry paving can leave the
      # player at Y63 in a one-block hole. The short local water exit may then
      # hit an overhead block and force an unnecessary logout. Only an actual
      # underwater state needs this near-vertical ascent before high parking.
      if s.get('under_water'):
       up=[s['pos'][0],70,s['pos'][2]]
       climb=self.request('navigate',target=up,arrival=1,seconds=8)
       if climb.get('phase')!='done':raise RuntimeError('Local water exit did not finish')
       continue
      if s.get('air_supply',0)<280:
       if time.monotonic()>=deadline:raise RuntimeError('Air did not recover before high parking')
       time.sleep(.25);continue
      if s.get('guard_busy'):
       if time.monotonic()>=deadline:raise RuntimeError('Defense stayed busy before high parking')
       time.sleep(.25);continue
      if abs(s['pos'][1]-self.park_target[1])>2:
       self._finish_vertical(s)
       continue
      r=self.request('navigate',target=self.park_target,arrival=2,seconds=120,air_only=True)
      if r.get('phase')=='done':break
      if (r.get('phase')=='error' and r.get('detail')=='Construction guard is defending or eating; wait before changing items or starting work'
          and time.monotonic()<deadline):
       time.sleep(.25);continue
      raise RuntimeError('High parking route did not finish: '+str(r.get('detail')))
    s=self.status()
    if 14<=s['health']<19:s=self.recover_park_health()
    if s['health']<18 or not s.get('guard_armed') or not self.park_near(s):
     if s['health']<18:health_exit_state=s
     raise RuntimeError('High parking position or guard not verified')
   except Handoff:
    self._record_health_stop('Owned material work disconnected after health loss')
    self.heartbeat.close();return
   except (RuntimeError,KeyError) as error:
    if health_exit_state is None:
     try:
      latest=self._observe_owned_health(self.status())
      if latest.get('health',20)<18:health_exit_state=latest
     except (Handoff,RuntimeError,KeyError):pass
    try:kept=self._rebase_guarded_finish(error)
    except (Handoff,RuntimeError,KeyError,OSError,ValueError):kept=False
    if kept:
     health_exit_state=None
    else:
     (self.out/'park-fallback.json').write_text(json.dumps({
      'reason':str(error),'action':'safe_logout',
      'elapsed_seconds':round(time.monotonic()-guard_finish_started,3)},ensure_ascii=False))
     attempted=False;previous=getattr(self,'last',None)
     try:self.request('safe_logout');attempted=True
     except (Handoff,RuntimeError):attempted=getattr(self,'last',None)!=previous
     finally:
      if health_exit_state is not None:
       from safety_interlock import record_material_health_exit
       record_material_health_exit(self.root,health_exit_state,str(error))
      else:self._record_health_stop(str(error),logout_attempted=attempted)
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
     if self._owned_guarded_finish_state(s,'parking') and self.park_near(s):
      (self.out/'stock-safety.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print('HIGH_GUARD_CONFIRMED',flush=True);return
    pending_disconnect=d.get('action')=='LOGOUT' and not d.get('confirmed')
    if d.get('confirmed'):
     if d.get('action')=='LOGOUT' and d.get('lease')==self.heartbeat.id and d.get('job_session')==self.task:
      if isinstance(d.get('snapshot'),dict):self._observe_owned_health(d['snapshot'])
      self._record_health_stop('Native material finish logged out after health loss',logout_attempted=True)
     (self.out/'stock-safety.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));print('DISCONNECT_CONFIRMED',d['action'],d['cause'],flush=True);return
   try:s=self.raw()
   except RuntimeError:
    print('Native finish acknowledgement unavailable; heartbeat has stopped',flush=True);return
   lease=s.get('supervision_lease',{})
   if lease.get('id')==self.heartbeat.id and lease.get('kind')=='parking':self.rev=s['control_revision']
   if s.get('world_session')!=self.world or s.get('manual_movement') or s.get('control_revision')!=self.rev and not pending_disconnect:
    self._record_health_stop('Material finish lost its connection after health loss');return
   if lease and lease.get('id')!=self.heartbeat.id:return
   time.sleep(.15)
  if self.remote_finish=='guard':
   try:
    s=self.raw();lease=s.get('supervision_lease') or {}
    kind=lease.get('kind')
    if kind in ('materials','parking') and self._owned_guarded_finish_state(s,kind) and self.park_near(s):
     (self.out/'stock-safety.json').write_text(json.dumps({
      'action':'KEEP_PVE_GUARD','lease':lease.get('id'),
      'job_session':lease.get('job_session'),'snapshot':s,
      'confirmed':False,'local_verified':True,
      'lease_transition_pending':kind=='materials'},ensure_ascii=False,indent=2))
     print('HIGH_GUARD_CONFIRMED',flush=True);return
   except (Handoff,RuntimeError,KeyError,OSError,ValueError):pass
   attempted=False;previous=getattr(self,'last',None)
   try:self.request('safe_logout');attempted=True
   except (Handoff,RuntimeError):attempted=getattr(self,'last',None)!=previous
   finally:self._record_health_stop('High hover acknowledgement failed after health loss',logout_attempted=attempted)
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
