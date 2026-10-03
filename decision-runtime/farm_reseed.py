"""Explicit maintenance of listed empty cells in a completed registered field.

Old planting/preparation bytes stay unchanged. Current occupied cells are only
observations, never counted as new planting actions. No hoe or expansion exists.
"""
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import uuid

from farm_preparation import preparation_lock
from kit_runtime.journal import write_json
from material_jobs.protocol import server_key
from potato_farm import (FarmWait,PROOF_SCOPE,_GuardedClient,_counts,_gate,_key,_properties,
                         _seed,action_proved,crop_descriptor,plan,survey_rows)


def read(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>4_000_000:raise ValueError('Original farm record is missing or oversized')
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise ValueError('Farm record must contain an object')
    return value


def registered(root,registry_path,cells,*,server=None):
    root=Path(root).resolve();path=Path(registry_path).resolve()
    if path.name!='registry.json' or not path.is_relative_to(root/'farms'):raise ValueError('Use the exact original local farm registry')
    registry=read(path);scope=registry.get('scope') or {};layout=scope.get('layout') or {};crop=crop_descriptor(layout)
    request={'authorized':True,'center':layout.get('center'),'radius':layout.get('radius',2),'crop':crop.name}
    key=hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()[:16]
    if (path.parent.name!=key or scope.get('dimension')!='minecraft:overworld'
            or server is not None and scope.get('server')!=server_key(server) or plan(request)!=layout):
        raise ValueError('Original server/dimension/hash/layout is inconsistent')
    if (not isinstance(cells,list) or not 1<=len(cells)<=4 or any(not isinstance(pos,list) or len(pos)!=3
            or any(type(v)is not int for v in pos) or pos not in layout['cells'] for pos in cells)
            or len({tuple(pos) for pos in cells})!=len(cells)):
        raise ValueError('Explicit maintenance cells must be1..4 unique originally registered floor cells')
    original=Path(registry['directory'])/(crop.journal_prefix+key+'.json');planted=read(original)
    if (planted.get('scope')!=scope or planted.get('world_session')!=registry.get('world_session')
            or planted.get('complete') is not True or planted.get('pending') or planted.get('cleanup_pending')
            or any(planted.get('cells',{}).get(_key(pos),{}).get('planted') is not True for pos in layout['cells'])):
        raise FarmWait('WAIT_RECONCILE','Original planting must be complete without unknown actions; maintenance cannot bypass them')
    harvest=path.parent/'harvest-active.json'
    if harvest.exists():
        prior=read(read(harvest)['journal'])
        if prior.get('pending') or prior.get('cleanup_pending'):raise FarmWait('WAIT_RECONCILE','Original harvest is unresolved')
    for prep in (root/'farm-preparation').glob('*/registry.json'):
        value=read(prep);registered_scope=value.get('scope') or {}
        if registered_scope.get('server')!=scope['server'] or registered_scope.get('center')!=layout['center']:continue
        identity=hashlib.sha256(json.dumps(registered_scope,sort_keys=True).encode()).hexdigest()[:16]
        book=read(Path(value['directory'])/('farm-preparation-'+identity+'.json'))
        if (book.get('scope')!=registered_scope or book.get('world_session')!=value.get('world_session')
                or book.get('complete') is not True or book.get('pending') or book.get('cleanup_pending')):
            raise FarmWait('WAIT_RECONCILE','Original preparation is incomplete or unresolved')
    return path,registry,scope,layout,crop,request,original


def prepare_journal(root,registry_path,cells,world,out=None,*,server=None):
    values=registered(root,registry_path,cells,server=server);path=values[0];scope=values[2]
    pointer=path.parent/'reseed-active.json'
    if pointer.exists():
        active=read(pointer);prior=Path(active['journal']);book=read(prior)
        if book.get('pending') or book.get('cleanup_pending'):
            raise FarmWait('WAIT_RECONCILE','Original maintenance is unresolved; preserve '+str(prior))
        if book.get('complete') is not True and book.get('closed_without_use') is not True:
            if book.get('world_session')!=world or book.get('requested_cells')!=cells or book.get('scope')!=scope:
                raise FarmWait('WAIT_RECONCILE','Original incomplete maintenance belongs to another request/world')
            return prior,values
    directory=Path(out).resolve() if out is not None else path.parent/'maintenance'
    directory.mkdir(parents=True,exist_ok=True);journal=directory/('farm-reseed-'+uuid.uuid4().hex+'.json')
    book={'schema':1,'kind':'explicit_existing_farmland_reseed','scope':scope,'world_session':world,
          'requested_cells':deepcopy(cells),'original_planting_journal':str(values[-1]),
          'original_planting_sha256':hashlib.sha256(values[-1].read_bytes()).hexdigest(),
          'observed_existing':{},'receipts':{},'pending':None,'new_reseed':0,'complete':False}
    write_json(journal,book);write_json(pointer,{'schema':1,'scope':scope,'world_session':world,'journal':str(journal)})
    return journal,values


class _TravelClient:
    """Record each existing planner leg before dispatch; never replay an unknown leg."""
    def __init__(self,c,book,journal,checkpoint,hurt):
        self.c,self.book,self.journal,self.checkpoint,self.hurt=c,book,journal,checkpoint,hurt
    def __getattr__(self,name):return getattr(self.c,name)
    def status(self):
        self.checkpoint();state=self.c.status();_gate(self.c,state,self.hurt);_counts(state);return state
    def request(self,op,**params):
        before=self.status()
        if op=='scan':
            reply=self.c.request(op,**params);_gate(self.c,reply,self.hurt);return reply
        if op!='navigate':raise FarmWait('WAIT_ROUTE','Maintenance travel only reuses existing scan/navigation')
        pending=self.book['pending']
        if pending.get('native_pending'):raise FarmWait('WAIT_RECONCILE','Original navigation leg is unresolved')
        pending['native_pending']={'op':op,'params':deepcopy(params),'world_session':self.c.world,
            'revision':self.c.rev,'position_before':before['pos'][:],'before_counts':dict(_counts(before)),
            'request_id_before':getattr(self.c,'last',None)}
        write_json(self.journal,self.book)
        reply=self.c.request(op,**params)
        pending['native_pending']['receipt']=deepcopy(reply);write_json(self.journal,self.book)
        after=self.status();nav=reply.get('material_air_navigation') or {}
        if (reply.get('phase')!='done' or reply.get('id')!=getattr(self.c,'last',None)
                or reply.get('world_session')!=self.c.world or nav.get('world_session')!=self.c.world
                or nav.get('phase')!='confirmed' or nav.get('outcome')!='done'
                or type(nav.get('stable_ticks'))is not int or nav['stable_ticks']<8
                or type(nav.get('restored_ticks'))is not int or nav['restored_ticks']<8
                or _counts(after)!=_counts(before) or math.dist(after['pos'],params['target'])>.55):
            raise FarmWait('WAIT_RECONCILE','Exact navigation arrival/restore or unchanged inventory is unproved; original intent retained')
        self.book.setdefault('navigation_receipts',[]).append(pending['native_pending']);pending['native_pending']=None
        write_json(self.journal,self.book);return reply


def run(c,registry_path,cells,out=None,checkpoint=lambda:None,*,allow_move=False,_locked=False,journal=None):
    if type(allow_move)is not bool or type(_locked)is not bool:raise ValueError('Maintenance movement/lock policy must be boolean')
    values=registered(c.root,registry_path,cells,server=c.server);registry,_,scope,layout,crop,request,_=values
    initial=c.status();context=nullcontext() if _locked else preparation_lock(c.root,initial,request)
    with context:
        if journal is None:journal,values=prepare_journal(c.root,registry,cells,c.world,out,server=c.server)
        journal=Path(journal);book=read(journal)
        if book.get('closed_without_use') is True:raise FarmWait('WAIT_CLOSED_REJECTION','This exact rejected request is archived; start a new explicit maintenance scope')
        if book.get('pending'):raise FarmWait('WAIT_RECONCILE','Saved maintenance single action cannot be replayed')
        if book.get('scope')!=scope or book.get('world_session')!=c.world or book.get('requested_cells')!=cells:
            raise FarmWait('WAIT_CONTROL','Maintenance journal/world changed')
        def save():write_json(journal,book)
        def result(code=None,detail=''):
            return {'phase':'done' if code is None else 'waiting','code':code,'detail':detail,'journal':str(journal),
                    'new_reseed':book['new_reseed'],'target_cells':len(cells),'observed_existing':len(book['observed_existing']),
                    'pending':bool(book.get('pending')),'verification_scope':PROOF_SCOPE,'server_verified':False,'automatic_retry_allowed':False}
        try:
            hurt=book.setdefault('recent_hurt_at',initial.get('recent_hurt_at'))
            if type(hurt)is not int:raise FarmWait('WAIT_SAFETY','Original injury marker is unavailable')
            proxy=_GuardedClient(c,checkpoint,hurt);_gate(c,initial,hurt);_counts(initial)
            wanted={tuple(pos) for pos in cells}
            def scan(*,planting=None):
                before=proxy.status();reply=c.request('scan',min=layout['scan_min'],max=layout['scan_max'],details=True)
                _gate(c,reply,hurt);_counts(reply)
                if reply.get('time',0)<=before['time']:raise FarmWait('WAIT_SCAN','A later native field frame is required')
                raw={tuple(row['pos']):row for row in reply.get('blocks',[]) if isinstance(row,dict) and isinstance(row.get('pos'),list)}
                observed={};ephemeral={}
                for pos in layout['cells']:
                    soil=raw.get(tuple(pos),{});above=raw.get((pos[0],pos[1]+1,pos[2]))
                    if _properties(soil,'farmland','moisture',7) is None:raise FarmWait('WAIT_EXISTING_FARMLAND','Every original cell must still be actual farmland; no till is permitted')
                    done=_key(pos) in book['receipts'];allowed_new=planting==pos or done
                    if above:
                        if _properties(above,crop.block,'age',crop.age_max) is None:raise FarmWait('WAIT_CROP','Occupied cells must contain only the originally registered crop')
                        if tuple(pos) in wanted and not allowed_new:raise FarmWait('WAIT_TARGET_NOT_EMPTY','An explicitly listed target is not AIR; no repeated planting')
                        ephemeral[_key(pos)]={'planted':True}
                        if tuple(pos) not in wanted:observed[_key(pos)]={'state':above['state'],'observed_time':reply['time'],'origin':'current_connection_observation_not_new_planting'}
                    elif tuple(pos) not in wanted or done:
                        raise FarmWait('WAIT_UNLISTED_EMPTY','An unlisted or already-maintained crop is missing; do not expand this maintenance request')
                rows=survey_rows(reply,layout,ephemeral,book.get('pending'))
                return reply,rows,observed
            first,_,observed=scan();second,_,observed2=scan()
            if second['time']<=first['time'] or set(observed)!=set(observed2):raise FarmWait('WAIT_SCAN','Two distinct stable field membership observations are required')
            book['observed_existing']=observed2;book['initial_observation_times']=[first['time'],second['time']];save()
            if _counts(second)[crop.item]<len([p for p in cells if _key(p) not in book['receipts']]):
                raise FarmWait(crop.wait_code,'Actual carried seeds are insufficient for the explicitly listed empty cells')
            for pos in cells:
                if _key(pos) in book['receipts']:continue
                if allow_move:
                    from material_jobs.acquisition import _travel
                    # Mature neighbouring crop OUTLINE shapes can occlude a
                    # diagonal use from the water center. Stand over this AIR
                    # cell so the ordinary requested up face is actually visible.
                    target=[pos[0]+.5,pos[1]+1.6,pos[2]+.5]
                    if math.dist(proxy.status()['pos'],target)>.15:
                        book['pending']={'operation':'travel','pos':pos[:],'target':target};save();trace=[]
                        _travel(_TravelClient(c,book,journal,checkpoint,hurt),target,checkpoint,trace)
                        book.setdefault('travel_receipts',[]).append({'pos':pos[:],'target':target,'trace':trace,'world_interaction':False});book['pending']=None;save()
                state,_,_=scan();player=state['pos']
                if math.dist([player[0],player[1]+1.62,player[2]],[pos[0]+.5,pos[1]+1,pos[2]+.5])>4.2:
                    raise FarmWait('WAIT_REACH','Listed cell is outside conservative ordinary planting reach')
                book['pending']={'operation':'prepare_seed','pos':pos[:],'before_counts':dict(_counts(state))};save()
                selected=_seed(proxy,crop,state)
                if _counts(selected)!=_counts(state):raise FarmWait('WAIT_RECONCILE','Seed selection changed carried quantities')
                book['pending']=None;save();before,rows,_=scan();hand=before.get('hand') or {}
                if hand.get('item')!=crop.item or hand.get('count',0)<1:raise FarmWait('WAIT_HAND','Actual selected seed no longer matches')
                book['pending']={'operation':'plant','pos':pos[:],'before_counts':dict(_counts(before)),
                    'hand_before':deepcopy(hand),'expected_state':rows[tuple(pos)]['state']};save();proxy.status()
                reply=c.request('interact',pos=pos,face='up',expected_state=rows[tuple(pos)]['state'],expected_hand=crop.item)
                book['pending']['native_receipt']={k:reply.get(k) for k in ('id','phase','time','detail')};save()
                if reply.get('phase')!='done':
                    from farm_reseed_reconcile import live_rejection,archive_rejection
                    proof=live_rejection(c,journal,book,reply)
                    if proof is not None:
                        archive_rejection(journal,book,proof);book.update(read(journal))
                        return result('REJECTED_WITHOUT_USE','Exact audited pre-use face rejection was archived; no seed/use/world action occurred. A fresh explicit request is required')
                    raise FarmWait('WAIT_RECONCILE','Single maintenance interact is unresolved; no second use')
                times=[]
                for _ in range(6):
                    after,actual,_=scan(planting=pos)
                    if not action_proved('plant',pos,before,after,actual,crop=crop) or _properties(actual.get((pos[0],pos[1]+1,pos[2]),{}),crop.block,'age',crop.age_max)!=0:
                        times=[];continue
                    if times and after['time']<=times[-1]:times=[];continue
                    times.append(after['time'])
                    if len(times)>=2:break
                if len(times)<2:raise FarmWait('WAIT_RECONCILE','Seed-minus-one and two actual age-zero crop frames are incomplete')
                book['receipts'][_key(pos)]={'native_receipt':book['pending']['native_receipt'],'observed_times':times,
                    'before_counts':dict(_counts(before)),'after_counts':dict(_counts(after)),'hand_before':hand,'hand_after':after['hand'],
                    'crop_state':actual[(pos[0],pos[1]+1,pos[2])]['state'],'origin':'new_explicit_maintenance_action'}
                book['new_reseed']+=1;book['pending']=None;save()
            book['complete']=True;save();return result()
        except FarmWait as waiting:
            book['last_wait']={'code':waiting.code,'detail':str(waiting)};save();return result(waiting.code,str(waiting))
        except Exception as error:return result('WAIT_CONTROL',type(error).__name__+': '+str(error))
