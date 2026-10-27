"""One normal channel-bucket use through the existing owner; no second lease and no replay."""
from pathlib import Path
from collections import Counter
import json,time,uuid
from material_plan import inventory_counts
from kit_runtime.journal import write_json
WATER='Block{minecraft:water}[level=0]'

def request_for(s,origin,length,row,expected,now,identity):
 lease=s.get('supervision_lease')or{}
 if (s.get('runtime_version')not in('1.8.27','1.8.28') or s.get('connected')is not True or s.get('health')!=20
     or s.get('food',0)<18 or s.get('screen')or s.get('manual_movement')is not False
     or s.get('guard_armed')is not True or s.get('guard_pve_only')is not True or s.get('guard_busy')is not False
     or s.get('health_recovery_hold')or s.get('safety_hold',{}).get('active')or s.get('phase')!='done'
     or lease.get('kind')!='materials'or lease.get('world_session')!=s.get('world_session')
     or not lease.get('id')or not lease.get('job_session')or not 0<=now-s.get('time',0)<=750
     or s.get('dimension')!='minecraft:overworld'or s.get('hand',{}).get('item')!='minecraft:water_bucket'
     or s.get('hand',{}).get('count')!=1 or s.get('build_job',{}).get('active')or s.get('professional_printer',{}).get('owned')
     or not isinstance(origin,list)or len(origin)!=3 or any(type(v)is not int for v in origin)
     or type(length)is not int or not 2<=length<=8 or type(row)is not int or row not in (0,1)
     or expected not in ['Block{minecraft:air}']+[f'Block{{minecraft:water}}[level={n}]'for n in range(1,8)]
     or s['pos'][1]<origin[1]+1.8):raise ValueError('Fresh idle healthy owner, singleton bucket, and an unfilled bounded channel source required')
 return dict(protocol=1,id=identity,world_session=s['world_session'],lease_id=lease['id'],task_session=lease['job_session'],
  player_uuid=s['player_uuid'],control_revision=s['control_revision'],issued_at=now,expires_at=now+4000,
  channel_origin=origin,length=length,row=row,expected_state=expected)

def confirmed(before,after,frame,target):
 pred=frame.get('scan_predictions')or{};expected=Counter(inventory_counts(before));expected['minecraft:water_bucket']-=1;expected['minecraft:bucket']+=1
 return (after.get('world_session')==before.get('world_session')==frame.get('world_session')
     and after.get('health')==20 and after.get('supervision_lease')==before.get('supervision_lease')
     and after.get('control_revision')==before.get('control_revision')and after.get('manual_movement')is False
     and frame.get('scan_total_cells')==frame.get('scan_cells_read')==1 and not frame.get('unloaded_chunks')
     and pred.get('complete')is True and pred.get('pending_count')==0 and pred.get('pending_positions')==[]
     and len(frame.get('blocks',[]))==1 and frame['blocks'][0].get('pos')==target and frame['blocks'][0].get('state')==WATER
     and +expected==inventory_counts(after))

def place(q,origin,length,row,out):
 out=Path(out);out.mkdir(exist_ok=False);target=[origin[0],origin[1],origin[2]+row]
 frame=q.native('scan',min=target,max=target,details=True,include_predictions=True)
 if frame.get('scan_predictions',{}).get('pending_count')!=0:raise RuntimeError('Source prediction remains pending; no input')
 expected=next((v['state']for v in frame['blocks']if v['pos']==target),'Block{minecraft:air}');s=q.status();r=request_for(s,origin,length,row,expected,int(time.time()*1000),'channel-'+uuid.uuid4().hex)
 book=dict(complete=False,pending='single_bucket_use',request=r,before=s,water_credit=0);write_json(out/'progress.json',book);write_json(q.root/'channel-water.json',r)
 end=time.monotonic()+6;reply=None
 while time.monotonic()<end:
  q.status();p=q.root/'channel-water-state.json'
  if p.exists():
   value=json.loads(p.read_text())
   if value.get('id')==r['id']:
    reply=value;write_json(out/'native-use.json',reply);break
  time.sleep(.05)
 if reply is None or reply.get('phase')!='use_sent':raise RuntimeError('Original channel use not admitted or unknown; retain journal, never replay')
 end=time.monotonic()+10;stamps=[]
 while len(stamps)<2:
  frame=q.native('scan',min=target,max=target,details=True,include_predictions=True);after=q.status()
  if confirmed(s,after,frame,target)and after['time']not in stamps:stamps.append(after['time'])
  if time.monotonic()>end:raise RuntimeError('Original channel use lacks prediction-free source and exact inventory proof; no replay')
  time.sleep(.15)
 book.update(complete=True,pending=None,water_credit=1,after=after,source_frame=frame,confirmations=stamps,native_use=reply)
 write_json(out/'progress.json',book);return book
