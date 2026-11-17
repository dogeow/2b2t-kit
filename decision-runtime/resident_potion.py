"""One scoped dose request, with independent debit and health evidence; never replay unknown use."""
import json,time,uuid,math
from pathlib import Path
import hashlib
from material_plan import inventory_counts
from kit_runtime.journal import write_json
THERAPEUTIC={'minecraft:healing','minecraft:strong_healing','minecraft:regeneration','minecraft:long_regeneration','minecraft:strong_regeneration'}
# Explicitly validated engine builds; unknown versions remain a pre-input stop.
SUPPORTED_RUNTIME_VERSIONS=frozenset({'1.8.30','1.8.58'})
# 1.8.71 was compared with the previously live-verified 1.8.30 treatment
# implementation. Admit only this exact loaded snapshot, not all 1.8.71 jars.
VERIFIED_LOADED_ENGINE_SHA256={'1.8.71':'3129911420c610e1708a21f4a4e761203695ae6d55e4b30b0e288e94104cf700'}

def supported_engine(version, loaded_sha256=None):
 return version in SUPPORTED_RUNTIME_VERSIONS or (version in VERIFIED_LOADED_ENGINE_SHA256 and loaded_sha256==VERIFIED_LOADED_ENGINE_SHA256[version])
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

def retained_patient_fence(root, uid):
 """Never issue another dose to an individual with an archived unknown dose."""
 directory=Path(root)/'resident-potion-retained'
 if not directory.exists():return
 for path in directory.glob('*.json'):
  record=json.loads(path.read_text())
  if record.get('target_uuid')==uid:
   raise RuntimeError('This patient has a retained unconfirmed dose; no new use')

def preserve_independent_prior(root,uid,current_world):
 """Retain a different patient's possibly sent, older-world dose unchanged.

 This does not credit, resolve, or replay the old use. Its patient remains
 fenced even after the shared request mailbox is used for another patient.
 """
 root=Path(root);request_path=root/'resident-potion.json'
 old=json.loads(request_path.read_text());identity=str(uuid.UUID(old['id']));world=str(uuid.UUID(old['world_session']))
 if identity!=old['id'] or world!=old['world_session'] or world==current_world or not old.get('target_uuid') or old['target_uuid']==uid:
  raise RuntimeError('Prior dose is not a different patient in an older world')
 claim_path=root/'resident-potion-claims'/world/(identity+'.json');claim=json.loads(claim_path.read_text())
 if (any(claim.get(key)!=value for key,value in old.items())
     or claim.get('id')!=identity or claim.get('world_session')!=world or claim.get('target_uuid')!=old['target_uuid']
     or claim.get('use_may_have_been_sent') is not True):
  raise RuntimeError('Original possibly-sent claim is not independently identifiable')
 response_path=root/'resident-potion-state.json';response=json.loads(response_path.read_text()) if response_path.exists() else None
 record={'id':identity,'world_session':world,'target_uuid':old['target_uuid'],'outcome':'unknown',
         'original_request':old,'original_claim':claim,'last_response':response,
         'healing_credit':0,'replayed':False}
 directory=root/'resident-potion-retained';directory.mkdir(parents=True,exist_ok=True);path=directory/(identity+'.json')
 if path.exists():
  if json.loads(path.read_text())!=record:raise RuntimeError('Retained dose evidence changed')
 else:
  with path.open('x',encoding='utf-8') as target:json.dump(record,target,ensure_ascii=False,indent=2);target.write('\n')
 return path
def request_for(s,p,uid,effect,now,identity,*,loaded_engine_sha256=None):
 lease=s.get('supervision_lease')or{};actors=[v for v in s.get('loaded_villagers',{}).get('villagers',[])if v.get('uuid')==uid];selected=s.get('selected_slot',-1)
 rows=[v for v in p.get('potions',[])if v.get('slot')==36+selected and v.get('nonempty_child_index')==-1]
 if(not supported_engine(s.get('runtime_version'),loaded_engine_sha256) or s.get('health')!=20 or s.get('screen')or s.get('manual_movement')is not False
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
def dose(c,uid,effect,*,allow_independent_prior=False):
 previous=c.q.root/'resident-potion.json';confirmed=c.n/'last-confirmed-resident-dose.json'
 retained_patient_fence(c.q.root,uid)
 if not previous_dose_resolved(c.q.root,confirmed,int(time.time()*1000)):
  if allow_independent_prior is not True:raise RuntimeError('Previous dose remains unresolved; no new use')
  state=c.s();preserve_independent_prior(c.q.root,uid,state['world_session'])
 s,p=c.potions()
 if s.get('runtime_version') in VERIFIED_LOADED_ENGINE_SHA256:
  snapshot=c.q.root.parent/'runtime'/'twob2tkit-engine.loaded.jar'
  if not supported_engine(s['runtime_version'],hashlib.sha256(snapshot.read_bytes()).hexdigest()):
   raise RuntimeError('Loaded treatment engine hash is not verified; no selection or use')
 elif not supported_engine(s.get('runtime_version')):
  raise RuntimeError('Treatment engine version is not verified; no selection or use')
 candidates=[v for v in p['potions']if v['nonempty_child_index']==-1 and v['item']=='minecraft:splash_potion'and v['potion_contents']=={'potion':effect}and (9<=v['slot']<=44)];assert candidates
 row=candidates[0];slot=row['slot']if row['slot']<36 else row['slot']-36;c.native('select_item',item='minecraft:splash_potion',slot=slot)
 s,p=c.potions();engine_hash=None
 if s.get('runtime_version') in VERIFIED_LOADED_ENGINE_SHA256:
  snapshot=c.q.root.parent/'runtime'/'twob2tkit-engine.loaded.jar'
  engine_hash=hashlib.sha256(snapshot.read_bytes()).hexdigest()
 r=request_for(s,p,uid,effect,int(time.time()*1000),str(uuid.uuid4()),loaded_engine_sha256=engine_hash);path=c.n/('dose-'+r['id']+'.json')
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
