"""One scoped dose request, with independent debit and health evidence; never replay unknown use."""
import json,time,uuid,math
from pathlib import Path
from material_plan import inventory_counts
from kit_runtime.journal import write_json
THERAPEUTIC={'minecraft:healing','minecraft:strong_healing','minecraft:regeneration','minecraft:long_regeneration','minecraft:strong_regeneration'}
# Explicitly validated engine builds; unknown versions remain a pre-input stop.
SUPPORTED_RUNTIME_VERSIONS=frozenset({'1.8.30','1.8.58'})
def previous_dose_resolved(root,confirmed,now):
 """Accept a confirmed dose or an expired native rejection with no use claim."""
 root=Path(root);previous=root/'resident-potion.json'
 if not previous.exists():return True
 try:
  old=json.loads(previous.read_text());identity=str(uuid.UUID(old['id']))
  if identity!=old['id']:return False
  last=json.loads(Path(confirmed).read_text()) if Path(confirmed).exists() else {}
  if last.get('id')==identity and last.get('confirmed') is True:return True
  reply=json.loads((root/'resident-potion-state.json').read_text())
  world=str(uuid.UUID(old['world_session']))
  if world!=old['world_session']:return False
  issued,expires,observed=old['issued_at'],old['expires_at'],reply['time']
  if any(type(v)is not int for v in (now,issued,expires,observed)):return False
  claim=root/'resident-potion-claims'/world/(identity+'.json')
  return (reply.get('id')==identity and reply.get('phase')=='rejected_preflight'
          and issued<=observed<=now and issued<=expires<now and not claim.exists())
 except (OSError,ValueError,TypeError,KeyError,AttributeError):return False
def request_for(s,p,uid,effect,now,identity):
 lease=s.get('supervision_lease')or{};actors=[v for v in s.get('loaded_villagers',{}).get('villagers',[])if v.get('uuid')==uid];selected=s.get('selected_slot',-1)
 rows=[v for v in p.get('potions',[])if v.get('slot')==36+selected and v.get('nonempty_child_index')==-1]
 if(s.get('runtime_version') not in SUPPORTED_RUNTIME_VERSIONS or s.get('health')!=20 or s.get('screen')or s.get('manual_movement')is not False
    or s.get('guard_armed')is not True or s.get('guard_pve_only')is not True or s.get('guard_busy')is not False
    or s.get('phase')!='done'or s.get('connected')is not True or s.get('health_recovery_hold')or(s.get('safety_hold')or{}).get('active')
    or lease.get('kind')!='materials'or lease.get('world_session')!=s.get('world_session')or not lease.get('id')or not lease.get('job_session')
    or lease.get('revision')!=s.get('control_revision')or not 0<=now-s.get('time',0)<=750
    or effect not in THERAPEUTIC or len(actors)!=1 or type(selected)is not int or not 0<=selected<=8
    or len(rows)!=1 or rows[0].get('potion_contents')!={'potion':effect}or rows[0].get('item')!='minecraft:splash_potion'or rows[0].get('count')!=1
    or s.get('hand',{}).get('item')!='minecraft:splash_potion'or s['hand'].get('count')!=1
    or p.get('menu_id')!=0 or p.get('menu_type')!='InventoryMenu'or p.get('complete')is not True
    or not 0<=s['time']-p.get('observed_at',0)<1000):raise ValueError('Fresh exact held therapeutic potion and native owner required')
 actor=actors[0]
 if actor.get('is_baby')is not False or not 0<actor.get('health',0)<20:raise ValueError('Same injured adult required')
 return dict(protocol=1,id=str(uuid.UUID(identity)),world_session=s['world_session'],lease_id=lease['id'],task_session=lease['job_session'],player_uuid=s['player_uuid'],control_revision=s['control_revision'],issued_at=now,expires_at=now+4000,player_pos=s['pos'],target_uuid=uid,target_pos=actor['pos'],expected_health=actor['health'],potion_contents={'potion':effect})
def dose(c,uid,effect):
 previous=c.q.root/'resident-potion.json';confirmed=c.n/'last-confirmed-resident-dose.json'
 if not previous_dose_resolved(c.q.root,confirmed,int(time.time()*1000)):
  raise RuntimeError('Previous dose remains unresolved; no new use')
 s,p=c.potions();candidates=[v for v in p['potions']if v['nonempty_child_index']==-1 and v['item']=='minecraft:splash_potion'and v['potion_contents']=={'potion':effect}and (9<=v['slot']<=44)];assert candidates
 row=candidates[0];slot=row['slot']if row['slot']<36 else row['slot']-36;c.native('select_item',item='minecraft:splash_potion',slot=slot)
 s,p=c.potions();r=request_for(s,p,uid,effect,int(time.time()*1000),str(uuid.uuid4()));path=c.n/('dose-'+r['id']+'.json')
 before=inventory_counts(s);entry=dict(request=r,before_inventory=dict(before),before_health=r['expected_health'],complete=False,pending=True);write_json(path,entry);c.book.setdefault('doses',[]).append(str(path));c.save();write_json(previous,r)
 end=time.monotonic()+6;reply=None
 while time.monotonic()<end:
  c.s();result=c.q.root/'resident-potion-state.json'
  if result.exists():
   result=json.load(open(result))
   if result.get('id')==r['id']:reply=result;entry['native_use']=reply;write_json(path,entry);break
  time.sleep(.05)
 if reply is None or reply.get('phase')!='use_sent':raise RuntimeError('Dose refused or uncertain; retain original request: '+str(reply))
 end=time.monotonic()+9;stamps=[]
 while len(stamps)<2:
  after=c.s();actor=next(v for v in after['loaded_villagers']['villagers']if v['uuid']==uid);expected=before.copy();expected['minecraft:splash_potion']-=1
  if inventory_counts(after)==+expected and actor['health']>r['expected_health']and after['time']>r['issued_at']:
   if not stamps or after['time']>stamps[-1]:stamps.append(after['time'])
  else:stamps=[]
  assert time.monotonic()<end,'Dose debit or health increase unconfirmed; no second dose';time.sleep(.1)
 entry.update(complete=True,pending=False,after_inventory=dict(inventory_counts(after)),after_health=actor['health'],confirmed_frames=stamps);write_json(path,entry);write_json(confirmed,{'id':r['id'],'confirmed':True,'proof':str(path)});return entry
