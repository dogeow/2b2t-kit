"""Local runtime bridge: selected strategy -> one Kit owner -> measured feedback."""
from pathlib import Path
from collections import Counter
import hashlib,json,time,uuid
from harness_strategy import choose,load_selected
from material_plan import inventory_counts
from kit_runtime.journal import write_json
KIT=Path(__file__).resolve().parents[1];LIVE=KIT/'work/harness2-live';ADOPTED=LIVE/'adopted-policy.json'

def selected():return load_selected(ADOPTED)
def free_slots(state):return sum(not r.get('count')for r in state.get('inventory',[])if 0<=r.get('slot',99)<36)
def attribution(policy):return {k:policy.get(k)for k in ('active','source','run_id','policy_sha256','experience_refs')}
def require_player(c):
 s=c.status();lease=s.get('supervision_lease')or{}
 if(s.get('connected')is not True or s['world_session']!=c.world or s.get('health')!=20
    or s.get('manual_movement')or s.get('screen')or s.get('health_recovery_hold')
    or(s.get('safety_hold')or{}).get('active')or lease.get('job_session')!=c.task):raise RuntimeError('Harness plan lost current healthy Kit owner')
 return s

def prepare_space(c,reserve,out):
 if type(reserve)is not int or not 1<=reserve<=8:raise ValueError('Reserve must be 1..8 main slots')
 s=c.status();p=selected();menu=s.get('menu')or{};owned=(menu.get('id',-1)==getattr(c,'owned_material_menu',None)and menu.get('type')in('ChestMenu','ShulkerBoxMenu')and menu.get('cursor',{}).get('count')==0)
 context=dict(stage='space',health=s['health'],manual=s.get('manual_movement',False),connected=s.get('connected'),free_slots=free_slots(s),required_slots=reserve,spare_beds=inventory_counts(s)['minecraft:white_bed'],fresh_owned_storage=owned,empty_container_slots=sum(not r['count']for r in menu.get('slots',[])[:-36])if owned else 0)
 decision=choose(p['policy'],context);before=inventory_counts(s);clicks=0
 if decision['action']=='deposit_beds':
  needed=max(0,reserve-free_slots(s));count=decision['deposit_beds']
  if not owned or not 0<count<=needed or count>context['empty_container_slots']:raise RuntimeError('Strategy cannot over-deposit or exceed current capacity')
  target=before['minecraft:white_bed']-count;actual=c.transfer('minecraft:white_bed',target,deposit=True);after=inventory_counts(c.status());expected=before.copy();expected['minecraft:white_bed']-=count
  if actual!=target or +expected!=after:raise RuntimeError('Selected space reservation lacks exact conserved result')
  clicks=count
 after=c.status();result=dict(phase='done',complete=decision['action']in('proceed','deposit_beds')and free_slots(after)>=reserve,scope='inventory_space_only_not_farm_completion',strategy=attribution(p),context=context,decision=decision,applied=p['active'],deposit_beds=clicks,free_slots_before=context['free_slots'],free_slots_after=free_slots(after),world_session=c.world)
 write_json(Path(out)/'harness-space-result.json',result);return result

def iron_plan(c,out):
 s=require_player(c);p=selected();project=json.loads((KIT/'work/village-trading-20261017/project-state.json').read_text());a=c.checked('scan',min=[761075,93,797804],max=[761086,97,797816],details=True)
 if a['scan_cells_read']!=a['scan_total_cells']:raise RuntimeError('Current complete water scene required')
 rows={tuple(r['pos']):r for r in a['blocks']};sources=[r['pos']for r in a['blocks']if r['state']=='Block{minecraft:water}[level=0]'and r['pos'][1]==95 and r['pos'][2]==797805];holes=[ [x,93,z]for x in range(761079,761082)for z in range(797813,797816)if rows.get((x,93,z),{}).get('state')!='Block{minecraft:cobblestone}']
 farm=project['iron_farm'];ctx=dict(stage='iron',health=s['health'],connected=True,manual=False,water_protocol=s.get('controlled_water_release_protocol')==1,source_count=len(sources),bait_open=bool(holes),zombie_captured=farm.get('hostile_captured',0)>0,water_released=farm.get('water_release_completed')is True)
 decision=choose(p['policy'],ctx);s=require_player(c);record=dict(schema=2,id='iron-plan-'+uuid.uuid4().hex,world_session=c.world,task_session=c.task,issued_at=s['time'],expires_at=s['time']+120000,strategy=attribution(p),context=ctx,decision=decision,source_cells=sources,bait_open_cells=holes,fresh_scan_id=a['id'],fresh_scan_time=a['time'],farm_completion_credit=0,live_action_authority='only_existing_native_safety_gates')
 path=Path(out)/'harness-plan.json';write_json(path,record);return dict(phase='done',complete=True,scope='strategy_plan_only',plan_path=str(path.resolve()),decision=decision,strategy=attribution(p),context=ctx,farm_completion_credit=0)

def run_iron_stage(c,plan_path,out,checkpoint):
 path=Path(plan_path).resolve();owner=Path(c.out).resolve().parent
 if owner not in path.parents or path.is_symlink():raise ValueError('Plan must belong to current sole owner')
 plan=json.loads(path.read_text());s=require_player(c);p=selected()
 if(plan.get('world_session')!=c.world or plan.get('task_session')!=c.task
    or not plan.get('issued_at',0)<=s['time']<=plan.get('expires_at',0)
    or plan.get('strategy',{}).get('policy_sha256')!=p['policy_sha256']):raise RuntimeError('Strategy plan is stale or changed; observe a new plan')
 action=plan['decision']['action']
 if action=='prepare_contained_sources':
  from iron_water_sources import run
  result=run(c,Path(out)/'contained-sources',checkpoint)
 elif action=='find_zombie':result=find_zombie(c,Path(out)/'surface-observation')
 else:raise RuntimeError('This bounded stage needs the existing construction workflow: '+action)
 result.update(strategy=attribution(p),selected_action=action,applied=p['active'],plan_id=plan['id'],farm_completion_credit=0);write_json(Path(out)/'harness-execution.json',result);return result

def find_zombie(c,out):
 from village_world_time import read
 s=require_player(c);p=selected()
 from loaded_hostiles import read as read_hostiles
 from bait_surface_survey import eligible
 frame=read_hostiles(c.root,s)
 if frame is not None:
  Path(out).mkdir(parents=True,exist_ok=True)
  candidates=[v for v in frame['hostiles']if eligible(v)and not v['on_fire']and v['main_hand']!='minecraft:trident']
  write_json(Path(out)/'loaded-hostiles.json',frame)
  return dict(phase='done',complete=True,scope='observation_only',observation_scope=frame['scope'],observation_id=frame['id'],
              candidates=candidates,capture_credit=0,finder_protocol=3,scan_count=0,truncated=frame['truncated'])
 if s.get('runtime_version')=='1.8.20':
  return dict(phase='waiting',complete=False,scope='observation_only',reason='live_hostile_observer_not_ready',candidates=[],capture_credit=0,finder_protocol=3,scan_count=0)
 sky=read(c.root,s)
 if sky is None or sky['period']!='dark':return dict(phase='done',complete=True,scope='observation_only',reason='bright_or_unknown_sky',candidates=[],capture_credit=0)
 from material_jobs.local_air_path import move
 if s['pos'][1]<72:move(c,[s['pos'][0],72.1,s['pos'][2]],Path(out)/'egress',foot_offset=.1,exact_target=True)
 s=require_player(c);c.checked('navigate',target=[s['pos'][0],111.2,s['pos'][2]],arrival=.1,air_only=True,seconds=40)
 from bait_surface_survey import WATCH_POSITION,scan_tiles,eligible
 target=[WATCH_POSITION[0],111.2,WATCH_POSITION[2]]
 import math
 while math.dist(require_player(c)['pos'],target)>64:
  start=c.status()['pos'];d=math.dist(start,target);c.checked('navigate',target=[start[i]+(target[i]-start[i])*60/d for i in range(3)],arrival=.1,air_only=True,seconds=40)
 c.checked('navigate',target=target,arrival=.1,air_only=True,seconds=40);bio=c.checked('scan_snow_biomes',center=[760952,797725],radius=32,stride=16)['snow_biome_survey'];water=all(any(w in v['biome']for w in ('ocean','river'))for v in bio['samples']);s=require_player(c);sky=read(c.root,s);ctx=dict(stage='search',effective_dark=sky is not None and sky['period']=='dark',water_biome=water);decision=choose(p['policy'],ctx)
 if decision['action']!='surface_scan':return dict(phase='done',complete=True,scope='observation_only',decision=decision,candidates=[],capture_credit=0)
 c.checked('navigate',target=WATCH_POSITION,arrival=.1,air_only=True,seconds=40);scenes=[];by_uuid={}
 for low,high in scan_tiles():
  require_player(c);a=c.checked('scan',min=low,max=high,details=True)
  if a.get('world_session')!=c.world:raise RuntimeError('Bait scan changed world')
  scenes.append(a)
  for e in a.get('scan_entities',[]):
   if eligible(e):by_uuid[e['uuid']]=e
 write_json(Path(out)/'native-scene.json',dict(scans=scenes,watch_position=WATCH_POSITION,scope='loaded_entities_only_not_complete_server_spawn_survey'))
 return dict(phase='done',complete=True,scope='observation_only',candidates=list(by_uuid.values()),capture_credit=0,decision=decision,finder_protocol=2,watch_position=WATCH_POSITION,scan_count=len(scenes))

def begin(owner,command,state):
 import os
 p=selected();LIVE.mkdir(parents=True,exist_ok=True)
 record=dict(time=int(time.time()*1000),command_id=command['id'],action=command['action'],op=command.get('op'),strategy=attribution(p),scope='command_started_not_outcome')
 write_json(LIVE/'runtime-status.json',dict(state='running',owner_pid=os.getpid(),strategy=attribution(p),last=record,policy_loaded=bool(p['active']),last_seen_at=record['time']))
 return attribution(p)

def feedback(owner,command,before,result,error,elapsed_ms,strategy_snapshot=None):
 LIVE.mkdir(parents=True,exist_ok=True);p=strategy_snapshot or dict(active=False,source='start_strategy_unavailable');record=dict(schema=2,time=int(time.time()*1000),owner=str(owner),command_id=command['id'],action=command['action'],op=command.get('op'),strategy=attribution(p),wall_ms=round(elapsed_ms),error=str(error)if error else None,scope='observed_command_not_global_goal_completion',result={k:result.get(k)for k in ('phase','complete','scope','applied','selected_action','free_slots_before','free_slots_after','source_count_before','source_count_after','native_inputs','reason','farm_completion_credit')}if isinstance(result,dict)else None)
 path=LIVE/'feedback.jsonl'
 with path.open('a')as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
 import os
 write_json(LIVE/'runtime-status.json',dict(state='needs_review'if error else'idle',owner_pid=os.getpid(),strategy=attribution(p),last=record,policy_loaded=bool(p['active']),last_seen_at=record['time']))
 if error:
  # Queue a local, data-only review; raw errors/coordinates stay in this file.
  signature=hashlib.sha256((record['action']+'|'+str(record['op'])+'|'+type(error).__name__).encode()).hexdigest()[:16];q=LIVE/'review-requests'/signature
  previous=json.loads(q.read_text())if q.exists()else dict(count=0)
  q.parent.mkdir(parents=True,exist_ok=True)
  write_json(q,dict(schema=2,count=previous['count']+1,signature=signature,state='needs_review',last_command=command['id'],last_seen_at=record['time'],model_payload='minimized_known_replay_cases_only',new_model_call_started=False))
 elif(command['action']=='harness_iron_stage' and isinstance(result,dict)
      and result.get('complete') is True and result.get('applied') is True
      and result.get('selected_action')=='prepare_contained_sources'
      and result.get('strategy',{}).get('policy_sha256')==p.get('policy_sha256')):
  # The worker revalidates every native receipt and minimizes evidence BEFORE
  # calling a model. This enqueue itself grants no game action or retry.
  identity='applied-'+hashlib.sha256(str(result.get('source_proof')).encode()).hexdigest()[:16]
  request=LIVE/'review-requests'/identity
  if not request.exists():
   acceptance=LIVE/'applications'/(identity+'.json')
   acceptance.parent.mkdir(parents=True,exist_ok=True);request.parent.mkdir(parents=True,exist_ok=True)
   write_json(acceptance,dict(complete=True,pending=None,stage=result,
       plan={'plan_path':command['plan']},policy_sha256=p['policy_sha256'],
       measured_stage_wall_ms=round(elapsed_ms),goal_complete=False))
   write_json(request,dict(schema=2,id=identity,kind='live_reflection',state='pending',
       acceptance=str(acceptance.resolve()),last_command=command['id'],
       model_payload='verified_minimized_receipts_only',game_retry_authorized=False))
 return record
