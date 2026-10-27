"""One exact empty-boat attack through the current native material lease.

An attack receipt grants no recovery credit. The original request is retained
until real vehicle removal and the recovered item are both observed.
"""
import json,time,uuid,math
from pathlib import Path
from material_plan import inventory_counts
from vehicle_observation import read_frame
from kit_runtime.journal import write_json
from block_recovery import pickup

def request_for(s,boat,now,identity):
 lease=s.get('supervision_lease')or{}
 if(s.get('runtime_version')not in('1.8.25','1.8.26','1.8.27','1.8.28')or s.get('connected')is not True or s.get('health')!=20
  or s.get('food',0)<18 or s.get('manual_movement')is not False or s.get('screen')or s.get('guard_busy')
  or s.get('guard_armed')is not True or s.get('guard_pve_only')is not True
  or s.get('hand',{}).get('item','').endswith('_axe')is not True
  or s.get('safety_hold',{}).get('active')or s.get('health_recovery_hold')
  or not 0<=now-s.get('time',0)<=1000 or lease.get('kind')!='materials'
  or not lease.get('id')or not lease.get('job_session')or lease.get('world_session')!=s.get('world_session')
  or boat.get('alive')is not True or boat.get('has_custom_name')is not False or boat.get('passengers')!=[]
  or not boat.get('type','').endswith('_boat')or 'chest'in boat['type']
  or boat.get('leashed')and not(boat.get('leash_resolved')and boat.get('leash_holder',{}).get('uuid')==s.get('player_uuid'))
  or boat.get('on_ground')is not True or boat.get('in_water')is not False or boat.get('visible')is not True
  or math.dist(s['pos'],boat['pos'])>3
  or not any(r.get('slot',99)<36 and not r['count']for r in s['inventory'])):
  raise ValueError('Healthy idle owner, one exact ordinary empty dry boat, axe and inventory room required')
 uuid.UUID(boat['uuid']);uuid.UUID(s['player_uuid'])
 return dict(protocol=1,id=identity,world_session=s['world_session'],lease_id=lease['id'],task_session=lease['job_session'],
  player_uuid=s['player_uuid'],control_revision=s['control_revision'],boat_uuid=boat['uuid'],entity_id=boat['id'],issued_at=now,expires_at=now+5000)

def recover(builder,boat_uuid,out):
 out=Path(out);out.mkdir(exist_ok=False);root=Path(builder.root);s=builder.check();f=read_frame(root,s)
 if f is None:raise RuntimeError('Current complete vehicle frame required')
 boat=next(v for v in f['vehicles']if v['uuid']==boat_uuid);request=request_for(s,boat,int(time.time()*1000),'ebr-'+uuid.uuid4().hex[:20])
 if(root/('empty-boat-recovery-claim-'+boat_uuid+'.json')).exists():raise RuntimeError('Original empty boat attack is retained; no replay')
 current=root/'empty-boat-recovery.json'
 if current.exists():
  old=json.loads(current.read_text());state=json.loads((root/'empty-boat-recovery-state.json').read_text());outcome=root/('empty-boat-recovery-outcome-'+old['id']+'.json')
  known_rejection=state.get('id')==old['id']and state.get('phase')=='rejected_preflight'
  if not known_rejection and not(outcome.exists()and json.loads(outcome.read_text()).get('complete')is True):
   raise RuntimeError('Original recovery is unconfirmed; no replacement')
 command=json.loads((builder.out/'command.json').read_text());directory=builder.out/command['id']
 if not(directory/'result.json').exists()or(directory/'error.json').exists()or(builder.out/'control/unconfirmed-native-request.json').exists():
  raise RuntimeError('Original queued command is not a known idle terminal')
 before=inventory_counts(s);old_ids={e['uuid']for e in s.get('entities',[])};book=dict(complete=False,pending='attack',request=request,boat_before=boat,inventory_before=dict(before),recovery_credit=0);path=out/'recovery.json';write_json(path,book);write_json(current,request);end=time.monotonic()+6
 while True:
  builder.check();reply_path=root/'empty-boat-recovery-state.json';reply=json.loads(reply_path.read_text())if reply_path.exists()else{}
  if reply.get('id')==request['id']:
   book['native_receipt']=reply;write_json(path,book)
   if reply.get('phase')!='attack_sent':raise RuntimeError('Empty recovery retained: '+str(reply.get('phase')))
   break
  if time.monotonic()>end:raise RuntimeError('Original empty boat attack acknowledgement unknown; no replay')
  time.sleep(.1)
 book['pending']='observe_removal';write_json(path,book);frames=[];end=time.monotonic()+8
 while len(frames)<2:
  s=builder.check();f=read_frame(root,s)
  if f is not None and not any(v['uuid']==boat_uuid for v in f['vehicles']):
   if not frames or f['time']>frames[-1]:frames.append(f['time'])
  else:frames=[]
  if time.monotonic()>end:raise RuntimeError('Original boat removal remains unconfirmed; no second attack')
  time.sleep(.1)
 book['removal_frames']=frames;write_json(path,book);p=[math.floor(boat['pos'][0]),math.floor(boat['pos'][1])-1,math.floor(boat['pos'][2])]
 pickup(builder,boat['type'],before[boat['type']],old_ids,p)
 expected=before.copy();expected[boat['type']]+=1
 if boat.get('leashed'):
  pickup(builder,'minecraft:lead',before['minecraft:lead'],old_ids,p);expected['minecraft:lead']+=1
 actual=inventory_counts(builder.check())
 if actual!=expected:raise RuntimeError('Original boat recovery inventory conservation remains unconfirmed')
 book.update(complete=True,pending=None,inventory_after=dict(actual),recovery_credit=1);write_json(path,book);write_json(root/('empty-boat-recovery-outcome-'+request['id']+'.json'),book);return book
