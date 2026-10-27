"""Register one leased empty receiver before ordinary combat can select its bait."""
import json,time,uuid,math
from pathlib import Path
from vehicle_observation import read_frame
from kit_runtime.journal import write_json

def request_for(state,boat,now,identity,*,allow_unleashed=False):
 lease=state.get('supervision_lease')or{}
 if type(allow_unleashed)is not bool or allow_unleashed and state.get('runtime_version')not in('1.8.24','1.8.25','1.8.26','1.8.27','1.8.28'):raise ValueError('Unleashed receiver requires runtime 1.8.24')
 own_leash=(boat.get('leashed')is True and boat.get('leash_resolved')is True and boat.get('leash_holder',{}).get('uuid')==state.get('player_uuid'))
 if(state.get('runtime_version')not in('1.8.22','1.8.23','1.8.24','1.8.25','1.8.26','1.8.27','1.8.28')or state.get('connected')is not True or state.get('health')!=20
  or state.get('food',0)<18 or state.get('manual_movement')is not False or state.get('screen')
  or not 0<=now-state.get('time',0)<=1000 or state.get('safety_hold',{}).get('active')or state.get('health_recovery_hold')
  or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
  or lease.get('kind')!='materials'or not lease.get('id')or not lease.get('job_session')
  or lease.get('world_session')!=state.get('world_session')or boat.get('alive')is not True
  or boat.get('passengers')!=[]or not(own_leash or allow_unleashed and boat.get('leashed')is False)
  or not boat.get('type','').endswith('_boat')or 'chest'in boat['type']or boat.get('has_custom_name')
  or math.dist(boat['pos'],state['pos'])>9):raise ValueError('Exact empty leashed receiver and healthy current owner required')
 uuid.UUID(boat['uuid']);uuid.UUID(state['player_uuid'])
 if not identity.isalnum()or len(identity)>16:raise ValueError('Short unique receiver identity required')
 return dict(protocol=1,id=identity,purpose='iron_farm_zombie_capture',world_session=state['world_session'],
  lease_id=lease['id'],task_session=lease['job_session'],control_revision=state['control_revision'],player_uuid=state['player_uuid'],
  boat_uuid=boat['uuid'],issued_at=now,expires_at=now+600000,allow_unleashed=allow_unleashed)

def arm(queue,boat_uuid,out,*,allow_unleashed=False):
 out=Path(out);out.mkdir(exist_ok=False);s=queue.status();frame=read_frame(queue.root,s)
 if frame is None:raise RuntimeError('Current complete boat observation required')
 boat=next(v for v in frame['vehicles']if v['uuid']==boat_uuid);now=int(time.time()*1000)
 request=request_for(s,boat,now,'r'+uuid.uuid4().hex[:12],allow_unleashed=allow_unleashed);root=Path(queue.root)
 ack_path=root/'capture-target-state.json';old=json.loads(ack_path.read_text())if ack_path.exists()else{}
 if old.get('active'):raise RuntimeError('Existing protected target is retained')
 path=root/'capture-receiver.json'
 if path.exists():
  prior=json.loads(path.read_text())
  if(prior.get('world_session')==request['world_session']and prior.get('lease_id')==request['lease_id']
   and prior.get('expires_at',0)>now and not(old.get('receiver_id')==prior.get('id')and old.get('receiver_consumed'))):
   raise RuntimeError('Original pending receiver remains registered; no replacement')
 book=dict(complete=False,pending='registration',request=request,boat_before=boat,capture_credit=0)
 write_json(out/'receiver.json',book);write_json(path,request);end=time.monotonic()+5
 while time.monotonic()<end:
  queue.status();ack=json.loads(ack_path.read_text())if ack_path.exists()else{}
  if(ack.get('runtime_version')in('1.8.22','1.8.23','1.8.24','1.8.25','1.8.26','1.8.27','1.8.28')and ack.get('receiver_id')==request['id']
   and 0<=int(time.time()*1000)-ack.get('time',0)<=750):
   book.update(complete=True,pending=None,acknowledgement=ack);write_json(out/'receiver.json',book);return book
  time.sleep(.1)
 raise RuntimeError('Original receiver registration is unconfirmed; retained without replay')
