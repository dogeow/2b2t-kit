"""One finite native stage: renew nine upper sources, keep the outlet dam closed."""
from pathlib import Path
from collections import Counter
import json,math,time
from material_plan import inventory_counts
from kit_runtime.journal import write_json
STONE='Block{minecraft:cobblestone}';WATER='Block{minecraft:water}[level=0]'
LOW=[761075,93,797804];HIGH=[761086,97,797816]
RELEASE={'min':[761075,94,797804],'max':[761085,97,797807]}

def enclosed(rows,target,bounds):
 """Independent preview; the host rechecks actual loaded collision shapes."""
 queue=[tuple(target)];seen=set()
 while queue:
  p=queue.pop()
  if p in seen:continue
  seen.add(p)
  if any(not a<=v<=b for a,v,b in zip(bounds['min'],p,bounds['max'])):return False
  row=rows.get(p)
  if p!=tuple(target)and row and row['state']==STONE:continue
  if p!=tuple(target)and row and not row['state'].startswith('Block{minecraft:water}'):return False
  x,y,z=p;queue.extend([(x,y-1,z),(x-1,y,z),(x+1,y,z),(x,y,z-1),(x,y,z+1)])
 return True

def run(c,out,checkpoint):
 from harness_runtime import require_player,free_slots,LIVE
 out=Path(out);out.mkdir(parents=True,exist_ok=True);s=require_player(c);stage=LIVE/'native-stages'/s['world_session']/'upper-sources.json';stage.parent.mkdir(parents=True,exist_ok=True)
 if stage.exists():raise RuntimeError('Original source stage is retained; inspect its known results before any new stage')
 b=dict(schema=1,complete=False,pending=None,world_session=c.world,task_session=c.task,lease_id=s['supervision_lease']['id'],inventory_before=dict(inventory_counts(s)),receipts=[],removed=[],water_uses=[],farm_completion_credit=0)
 def save():write_json(stage,b);write_json(out/'stage.json',b)
 def check():
  checkpoint();s=require_player(c)
  if s.get('under_water')or s.get('on_fire')or s['supervision_lease']['id']!=b['lease_id']:raise RuntimeError('Dry current source-stage owner required')
  return s
 def one(op,**params):
  check();b['pending']=dict(op=op,params=params,request_id=None);save();previous=c.last
  try:r=c.checked(op,**params)
  finally:b['pending']['request_id']=c.last if c.last!=previous else None;save()
  b['receipts'].append(dict(op=op,id=r['id'],phase=r['phase']));b['pending']=None;save();return r
 def scan(lo=LOW,hi=HIGH):
  a=one('scan',min=lo,max=hi,details=True)
  if a['scan_cells_read']!=a['scan_total_cells']or a['world_session']!=c.world:raise RuntimeError('Incomplete current source scene')
  return a,{tuple(r['pos']):r for r in a['blocks']}
 def nav(p):return one('navigate',target=p,arrival=.1,air_only=True,seconds=40)
 def singleton(item):
  s=check();r=next((r for r in s['inventory']if 0<=r['slot']<36 and r['item']==item and r['count']==1),None)
  if r is None:raise RuntimeError('Actual singleton bucket required')
  return one('select_item',item=item,slot=r['slot'])
 def use_bucket(mode,p):
  a,rows=scan([p[0]-1,p[1]-1,p[2]-1],[p[0]+1,p[1]+1,p[2]+1]);before=inventory_counts(check())
  if mode=='bucket_fill':
   if rows.get(tuple(p),{}).get('state')!=WATER:raise RuntimeError('Exact renewable source required')
   singleton('minecraft:bucket');params=dict(pos=p,expected_state=WATER,expected_hand='minecraft:bucket')
  else:
   support=[p[0],p[1]-1,p[2]]
   if tuple(p)in rows or rows.get(tuple(support),{}).get('state')!=STONE or not all(rows.get((p[0]+dx,p[1],p[2]+dz),{}).get('state')==STONE for dx,dz in [(1,0),(-1,0),(0,1),(0,-1)]):raise RuntimeError('Four dry full sides required before new bucket use')
   singleton('minecraft:water_bucket');params=dict(pos=p,support=support,face='up',expected_state='Block{minecraft:air}',expected_support_state=STONE,expected_hand='minecraft:water_bucket')
  r=one(mode,**params);ack=r['bucket_water'];after=inventory_counts(check());delta=-1 if mode=='bucket_fill'else 1
  if not(ack['confirmed']and not ack['unknown_outcome']and ack['use_count']==1 and ack['request_id']==r['id']and ack['world_session']==c.world and after['minecraft:bucket']==before['minecraft:bucket']+delta and after['minecraft:water_bucket']==before['minecraft:water_bucket']-delta):raise RuntimeError('Original bucket use lacks independent exact receipts; no repeat')
  b['water_uses'].append(ack);save()
 try:
  save()
  if free_slots(s)<3 or inventory_counts(s)['minecraft:bucket']!=2 or inventory_counts(s)['minecraft:water_bucket']!=0 or s.get('controlled_water_release_protocol')!=1:raise RuntimeError('Three free slots, two empty buckets and supported host required')
  if s['pos'][1]<72:
   from material_jobs.local_air_path import move
   b['egress']=move(c,[s['pos'][0],72.1,s['pos'][2]],out/'existing-air-egress',foot_offset=.1,exact_target=True);save()
  s=check();nav([s['pos'][0],111.2,s['pos'][2]]);target=[761077.5,111.2,797805.5]
  while math.dist(check()['pos'],target)>64:
   start=check()['pos'];d=math.dist(start,target);nav([start[i]+(target[i]-start[i])*60/d for i in range(3)])
  nav(target);nav([761077.5,97.2,797805.5]);a,rows=scan();b['scene_before']=a;b['source_count_before']=sum(rows.get((x,95,797805),{}).get('state')==WATER for x in range(761076,761085));b['bait_roof_before']={str((x,93,z)):rows.get((x,93,z),{}).get('state')for x in range(761079,761082)for z in range(797813,797816)};save()
  if b['source_count_before']!=2 or any(rows.get((x,95,797806),{}).get('state')!=STONE for x in range(761076,761085)):raise RuntimeError('Original contained two-source layout and intact outlet dam required')
  # Split a stack of two empty buckets by normal two-click inventory input.
  s=check();menu=s['menu'];stack=next((r for r in menu['slots']if 9<=r['slot']<=44 and r['item']=='minecraft:bucket'and r['count']==2),None)
  if stack:
   empty=next(r for r in menu['slots']if 9<=r['slot']<=44 and not r['count']);one('slot_click',menu_id=menu['id'],slot=stack['slot'],expected_item='minecraft:bucket',expected_count=2,expected_cursor='minecraft:air',expected_cursor_count=0,kind='pickup',button=1)
   s=check()
   from kit_runtime.inventory import InventorySession
   session=InventorySession(c);b['pending_inventory_ack']={'kind':'half_pickup','request_id':c.last};save()
   s=session._wait_pickup(s,menu['id'],stack['slot'],'minecraft:bucket',1,1,full_stack=False,settle_prediction=True);b['pending_inventory_ack']=None;save()
   if s['menu']['cursor']['item']!='minecraft:bucket'or s['menu']['cursor']['count']!=1:raise RuntimeError('Original bucket split cursor not confirmed; no repeated click')
   one('slot_click',menu_id=menu['id'],slot=empty['slot'],expected_item='minecraft:air',expected_count=0,expected_cursor='minecraft:bucket',expected_cursor_count=1,kind='pickup',button=0)
   b['pending_inventory_ack']={'kind':'singleton_placement','request_id':c.last};save();s=session._wait(check(),menu['id'],lambda m:m['cursor']['count']==0 and m['slots'][empty['slot']]['item']=='minecraft:bucket'and m['slots'][empty['slot']]['count']==1 and m['slots'][stack['slot']]['count']==1,'bucket_singletons',confirmations=2,fresh=True);b['pending_inventory_ack']=None;save()
   if s['menu']['cursor']['count']!=0:raise RuntimeError('Bucket split did not settle')
  for x in [761077,761079,761081,761083]:
   if x!=761077:
    nav([761077.5,97.2,797805.5]);use_bucket('bucket_fill',[761077,95,797805]);right=x+1;nav([right+.5,97.2,797805.5]);use_bucket('bucket_place',[right,95,797805])
   p=[x,95,797805];nav([x+.5,97.2,797805.5]);a,rows=scan();before=inventory_counts(check())['minecraft:cobblestone']
   if rows.get(tuple(p),{}).get('state')!=STONE or not enclosed(rows,p,RELEASE):raise RuntimeError('Current source retainer is not dry and contained')
   one('select_item',item='minecraft:diamond_pickaxe');r=one('mine_block',pos=p,face='up',expected_state=STONE,controlled_water_release=True,water_release_bounds=RELEASE,seconds=15)
   if not r.get('server_confirmed')or r.get('server_ack_sequence',0)<r.get('native_sequence',1):raise RuntimeError('Original retainer removal not server-confirmed')
   nav([x+.5,96.2,797805.5]);until=time.monotonic()+8;times=[]
   while len(times)<2:
    a,m=scan(p,p);s=check()
    if m.get(tuple(p),{}).get('state')==WATER and inventory_counts(s)['minecraft:cobblestone']==before+1 and(not times or s['time']>times[-1]):times.append(s['time'])
    else:times=[]
    if time.monotonic()>until:raise RuntimeError('Original retainer material/source unresolved; no repeat')
    time.sleep(.1)
   b['removed'].append(dict(pos=p,request=r['id'],times=times,recovered=True));save();nav([x+.5,97.2,797805.5])
  frames=[]
  for _ in range(2):
   a,m=scan();assert all(m.get((x,95,797805),{}).get('state')==WATER and m.get((x,95,797806),{}).get('state')==STONE for x in range(761076,761085));assert {str((x,93,z)):m.get((x,93,z),{}).get('state')for x in range(761079,761082)for z in range(797813,797816)}==b['bait_roof_before'];frames.append(a)
  after=inventory_counts(check());expected=Counter(b['inventory_before']);expected['minecraft:cobblestone']+=4
  if after!=+expected:raise RuntimeError('Source-stage item conservation failed')
  b.update(complete=True,pending=None,source_count_after=9,outlet_dam_preserved=True,bait_access_preserved=True,inventory_after=dict(after),scene_after=frames[-1],water_release_completed=False,farm_completion_credit=0);save()
  project_path=Path(__file__).resolve().parents[1]/'work/village-trading-20261017/project-state.json';project=json.loads(project_path.read_text());project['iron_farm'].update(water_sources_placed=9,upper_source_count=9,upper_source_proof=str((out/'stage.json').resolve()),water_release_completed=False,formal_complete=False);write_json(project_path,project)
  return dict(phase='done',complete=True,scope='upper_source_preparation_only',source_count_before=b['source_count_before'],source_count_after=9,retainers_recovered=4,water_release_completed=False,source_proof=str((out/'stage.json').resolve()),native_inputs=sum(r['op']not in('scan','snapshot')for r in b['receipts']),farm_completion_credit=0)
 except Exception as error:b['error']=repr(error);save();raise
