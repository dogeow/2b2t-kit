"""Harvest and refill the explicitly owned local mud-to-clay bed."""
import hashlib,json,math
from pathlib import Path
from material_manufacture import manufacture
from recipe_catalog import RecipeCatalog
from kit_runtime.journal import write_json
from .acquisition import _safe,_scan,carried,block_id,_travel
from .mud_conversion import column,refill_column,harvest,refill
from .direct_clay_refill import refill as refill_from_dirt
from .local_air_path import move
from .navigation import settled_state
from .protocol import JobBlocked,JobPaused


def reconcile_confirmed_refill(c,shared,harvest_journal,refill_journal,out,checkpoint):
    """Retire a confirmed old removal after a separately proved new refill.

    The original uncollected output remains uncredited and its journal stays
    intact. This never reconciles an unknown mining result or pickup request.
    """
    shared,harvest_journal,refill_journal=map(Path,(shared,harvest_journal,refill_journal))
    old=json.loads(shared.read_text());mine=json.loads(harvest_journal.read_text());refilled=json.loads(refill_journal.read_text())
    scope=old.get('scope')or{};pending=old.get('pending')or{};pos=mine.get('mud')
    carried_refill=(refilled.get('mud')==pos and refilled.get('pending')is False
        and type(refilled.get('inventory_before'))is int
        and refilled.get('inventory_after')==refilled['inventory_before']-1)
    direct_refill=(refilled.get('pos')==pos and refilled.get('pending')is None and refilled.get('complete')is True
        and refilled.get('dirt_consumed')==1 and refilled.get('known_owned_dirt_resumed')is False
        and [r.get('kind')for r in refilled.get('receipts',[])]==['place_dirt','water_to_mud']
        and all(isinstance(r.get('request_id'),str)and r['request_id'].startswith('materials-')for r in refilled.get('receipts',[])))
    if (scope.get('world_session')!=c.world or pending!={'kind':'harvest','pos':pos}
            or mine.get('world_session')!=c.world or mine.get('pending')is not True
            or refilled.get('world_session')!=c.world or not(carried_refill or direct_refill)
            or refilled.get('support_preserved')is not True
            or refilled.get('tip_preserved')is not True
            ):
        raise JobBlocked('Old farm removal and distinct refill scope are not proved')
    rid=mine.get('request_id')
    if not isinstance(rid,str)or not rid.startswith('materials-')or '/'in rid:raise JobBlocked('Original mining identity missing')
    reply_path=Path(c.root)/('reply-'+rid+'.json')
    reply=json.loads(reply_path.read_text())if reply_path.exists()else mine.get('mining_receipt')or{}
    seq=reply.get('native_sequence')
    if (reply.get('id')!=rid or reply.get('op')!='mine_block' or reply.get('phase')!='done'
            or reply.get('world_session')!=c.world or reply.get('mining_target')!=pos
            or reply.get('server_confirmed')is not True
            or reply.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
            or type(seq)is not int or seq<=0 or reply.get('server_ack_sequence')!=seq):
        raise JobBlocked('Unknown original mining cannot be retired by a new refill')
    checkpoint();q=c.status();_safe(q);lease=q.get('supervision_lease')or{}
    if lease.get('job_session')!=c.task or lease.get('revision')!=q.get('control_revision')or q.get('world_session')!=c.world:
        raise JobBlocked('Current farm reconciliation owner changed')
    rows=_scan(c,[pos[0],pos[1]-2,pos[2]],pos,checkpoint);bed=refill_column(rows,pos)
    if not bed or not bed['filled'] or bed['support']['state']!=mine['support']['state']or bed['tip']['state']!=mine['tip']['state']:
        raise JobBlocked('New filled column and retained support/tip not currently proved')
    resolution={'original_request_id':rid,'server_sequence':seq,'pos':pos,
                'original_harvest_journal':str(harvest_journal),'distinct_refill_journal':str(refill_journal),
                'old_output_credit':0,'old_output_collection_unproved':True,'mining_replayed':False,
                'world_session':c.world,'observed_at':q.get('time')}
    write_json(out,resolution)
    write_json(shared,{**old,'pending':None,'retired_uncredited_output':resolution})
    return resolution


def reconcile_rejected_refill(c,shared,farm_journal,rejection,refill_journal,out,checkpoint):
    """Retire a pre-dispatch bottle refusal after a distinct proved refill."""
    shared,farm_journal,refill_journal=map(Path,(shared,farm_journal,refill_journal))
    current=json.loads(shared.read_text());farm=json.loads(farm_journal.read_text());new=json.loads(refill_journal.read_text())
    pending=current.get('pending')or{};pos=pending.get('pos');native=rejection.get('native')or{};event=rejection.get('transaction')or{}
    message='Water bottle action requires the current healthy idle guarded material lease'
    harvested=next((r.get('result')for r in reversed(farm.get('receipts',[]))if r.get('kind')=='harvest'and r.get('pos')==pos),None)or{}
    mined=harvested.get('mining_receipt')or{};seq=mined.get('native_sequence')
    if ((current.get('scope')or{}).get('world_session')!=c.world or pending!={'kind':'direct_refill','pos':pos}
            or(farm.get('scope')or{}).get('world_session')!=c.world or farm.get('pending')!=pending
            or native.get('id')!=event.get('request_id') or not isinstance(native.get('id'),str)
            or native.get('world_session')!=c.world or event.get('world_session')!=c.world
            or native.get('phase')!='error' or event.get('phase')!='error' or event.get('op')!='bottle_fill'
            or native.get('detail')!=message or event.get('detail')!=message or native.get('bottle_water')is not None
            or harvested.get('world_session')!=c.world or harvested.get('mud')!=pos or harvested.get('pending')is not False
            or harvested.get('actual_clay_balls_gained')!=4 or harvested.get('support_preserved')is not True
            or harvested.get('tip_preserved')is not True or mined.get('phase')!='done' or mined.get('world_session')!=c.world
            or mined.get('mining_target')!=pos or mined.get('server_confirmed')is not True
            or mined.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
            or type(seq)is not int or seq<=0 or mined.get('server_ack_sequence')!=seq
            or new.get('world_session')!=c.world or new.get('pos')!=pos or new.get('pending')is not None
            or new.get('complete')is not True or new.get('dirt_consumed')!=1
            or new.get('known_owned_dirt_resumed')is not False or new.get('support_preserved')is not True
            or new.get('tip_preserved')is not True
            or [r.get('kind')for r in new.get('receipts',[])]!=['place_dirt','water_to_mud']):
        raise JobBlocked('Original bottle refusal, received harvest and distinct refill are not proved')
    checkpoint();q=c.status();_safe(q);lease=q.get('supervision_lease')or{}
    if q.get('world_session')!=c.world or lease.get('job_session')!=c.task or lease.get('revision')!=q.get('control_revision'):
        raise JobBlocked('Rejected refill reconciliation owner changed')
    rows=_scan(c,[pos[0],pos[1]-2,pos[2]],pos,checkpoint);bed=refill_column(rows,pos)
    if (not bed or not bed['filled']or bed['support']['state']!=harvested['support']['state']
            or bed['tip']['state']!=harvested['tip']['state']):
        raise JobBlocked('Distinct filled bed and retained support/tip changed')
    resolution={'world_session':c.world,'pos':pos,'original_refusal':native['id'],
                'original_farm_journal':str(farm_journal),'distinct_refill_journal':str(refill_journal),
                'original_refill_replayed':False,'harvest_replayed':False,'new_harvest_credit':0}
    write_json(out,resolution);write_json(shared,{**current,'pending':None,'retired_pre_dispatch_refill':resolution})
    return resolution


def reconcile_restored_bed(c,shared,farm_journal,old_worker,out,checkpoint):
    """Retire only a stopped refill workflow after its bed is filled again.

    The old harvest must already have an exact server ACK and received output.
    Child action journals and claims remain untouched, including unknown ones.
    A filled bed never serves as proof that an old bottle or placement worked.
    """
    shared,farm_journal,out=map(Path,(shared,farm_journal,out))
    if out.exists():raise JobBlocked('Original bed reconciliation retained; no replay')
    initial=shared.read_bytes();current=json.loads(initial);farm=json.loads(farm_journal.read_text())
    pending=current.get('pending')or{};pos=pending.get('pos')
    try:job_id=farm_journal.resolve().relative_to((Path(c.root)/'material-jobs').resolve()).parts[0]
    except (ValueError,IndexError):raise JobBlocked('Original farm worker scope is missing')
    harvested=next((r.get('result')for r in reversed(farm.get('receipts',[]))
                    if r.get('kind')=='harvest'and r.get('pos')==pos),None)or{}
    mined=harvested.get('mining_receipt')or{};seq=mined.get('native_sequence')
    if (not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos)
            or pending!={'kind':'direct_refill','pos':pos}or farm.get('pending')!=pending
            or current.get('journal')!=str(farm_journal)
            or (farm.get('scope')or{}).get('world_session')!=c.world
            or old_worker.get('id')!=job_id or old_worker.get('world_session')!=c.world
            or old_worker.get('state')not in('blocked','failed','cancelled','completed')
            or old_worker.get('process_alive')is not False or old_worker.get('occupied')is not False
            or harvested.get('world_session')!=c.world or harvested.get('mud')!=pos
            or harvested.get('pending')is not False or harvested.get('actual_clay_balls_gained')!=4
            or type(harvested.get('before'))is not int or harvested.get('after')!=harvested['before']+4
            or harvested.get('support_preserved')is not True or harvested.get('tip_preserved')is not True
            or harvested.get('request_id')!=mined.get('id')or mined.get('op')!='mine_block'
            or mined.get('phase')!='done'or mined.get('world_session')!=c.world or mined.get('mining_target')!=pos
            or mined.get('server_confirmed')is not True
            or mined.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
            or type(seq)is not int or seq<=0 or mined.get('server_ack_sequence')!=seq):
        raise JobBlocked('Stopped original refill and received acknowledged harvest are not proved')
    def state():
        checkpoint();q=c.status();_safe(q);lease=q.get('supervision_lease')or{}
        if (current.get('scope')!={k:q.get(k)for k in('world_session','server','dimension')}
                or q.get('world_session')!=c.world or q.get('manual_movement')is not False
                or (q.get('material_task')or{}).get('occupied')is not False or q.get('navigating')is not False
                or lease.get('kind')!='materials'or lease.get('job_session')!=c.task
                or lease.get('world_session')!=c.world or lease.get('revision')!=q.get('control_revision')):
            raise JobBlocked('Restored-bed reconciliation owner or worker changed')
        return q
    q=state();rows=_scan(c,[pos[0],pos[1]-2,pos[2]],pos,state);bed=refill_column(rows,pos)
    if (not bed or not bed['filled']or bed['support']['state']!=harvested['support']['state']
            or bed['tip']['state']!=harvested['tip']['state']):
        raise JobBlocked('Current filled bed and original support/tip are not proved')
    q=state()
    if shared.read_bytes()!=initial:raise JobBlocked('Original farm intent changed during verification')
    result={'world_session':c.world,'pos':pos,'original_farm_journal':str(farm_journal),
            'original_worker':old_worker,'current_column':rows,'observed_at':q['time'],
            'original_harvest_request':mined['id'],'original_server_sequence':seq,
            'original_refill_replayed':False,'harvest_replayed':False,'new_harvest_credit':0,
            'child_journals_and_claims_preserved':True,'old_refill_outcome_inferred':False}
    write_json(out,result)
    write_json(shared,{**current,'pending':None,'retired_restored_bed_workflow':result})
    return result


def validate(profile):
    cfg=profile.get('clay_conversion_farm')or{}
    positions=cfg.get('positions');approach=cfg.get('approach');exit=cfg.get('exit')
    if (cfg.get('authorized')is not True or not isinstance(positions,list)or not 1<=len(positions)<=128
            or any(not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)for p in positions)
            or len({tuple(p)for p in positions})!=len(positions)
            or any(not isinstance(p,list)or len(p)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in p)for p in (approach,exit))
            or any(math.hypot(p[0]-approach[0],p[2]-approach[2])>12 or abs(p[1]-approach[1])>64 for p in positions)
            or math.hypot(exit[0]-approach[0],exit[2]-approach[2])>12 or abs(exit[1]-approach[1])>64):
        raise JobBlocked('Local clay farm needs explicit bounded owned positions and current air access')
    return cfg


def run(c,profile,item,target,out,checkpoint):
    cfg=validate(profile)
    if item not in ('minecraft:clay','minecraft:clay_ball')or type(target)is not int or not 1<=target<=2304:
        raise ValueError('Expected absolute carried clay/ball target')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'home-clay-farm.json'
    scope={'world_session':c.world,'item':item,'target':target,'farm':cfg}
    if path.exists():
        book=json.loads(path.read_text())
        if book.get('scope')!=scope or book.get('pending'):raise JobBlocked('Original local farm intent retained; no replay')
        if book.get('complete'):return {'phase':'blocked','code':'COMPLETED_RECEIPT','detail':'Old farm collection is not replayed'}
    else:book={'scope':scope,'pending':None,'receipts':[],'complete':False}
    shared_dir=Path(c.root)/'home-clay-farm-intents';shared_dir.mkdir(parents=True,exist_ok=True)
    shared_scope={'world_session':c.world,'server':profile.get('server'),'dimension':profile.get('dimension')}
    shared=shared_dir/(hashlib.sha256(json.dumps(shared_scope,sort_keys=True).encode()).hexdigest()+'.json')
    if shared.exists():
        if shared.is_symlink()or shared.stat().st_size>16384:raise JobBlocked('Local farm shared intent record is unsafe')
        previous=json.loads(shared.read_text())
        if not isinstance(previous,dict)or previous.get('scope')!=shared_scope or previous.get('pending'):
            raise JobBlocked('Prior local farm action unresolved across jobs; no replay')
    def save():
        write_json(path,book)
        write_json(shared,{'scope':shared_scope,'journal':str(path),'pending':book['pending']})
    def state():
        checkpoint();q=c.status()
        if q.get('world_session')!=c.world or q.get('manual_movement'):raise JobPaused('Local farm world/manual control changed')
        _safe(q);lease=q.get('supervision_lease')or{}
        if (q.get('connected')is not True or lease.get('kind')!='materials'or lease.get('job_session')!=c.task
                or lease.get('world_session')!=c.world or lease.get('revision')!=q.get('control_revision')
                or q.get('server','').removesuffix(':25565')!=profile.get('server','').removesuffix(':25565')
                or q.get('dimension')!=profile.get('dimension')):
            raise JobBlocked('Local farm requires the current guarded owner/profile')
        return q
    before=carried(state(),item)
    if before>=target:return {'phase':'done','item':item,'before':before,'after':before}
    def operation(kind,pos,fn):
        book['pending']={'kind':kind,'pos':pos};save()
        result=fn();book['receipts'].append({**book['pending'],'result':result});book['pending']=None;save();return result
    operation('approach',cfg['approach'],lambda:_travel(c,cfg['approach'],state,[],keep_cruise=True))
    # Cruise retention deliberately preserves a higher current altitude.
    # An explicit native descent must prove the requested local work height.
    def descend():
        c.checked('navigate',target=cfg['approach'],arrival=.2,air_only=True,seconds=120)
        settled_state(c,cfg['approach'],.45)
    operation('descent',cfg['approach'],descend)
    observed=[]
    for index,pos in enumerate(cfg['positions']):
        rows=_scan(c,[pos[0],pos[1]-2,pos[2]],pos,state);bed=refill_column(rows,pos)
        top=next((b for b in rows if b['pos']==pos),None);name=block_id(top)if top else'minecraft:air'
        if (name=='minecraft:grass_block'and refill_column([r for r in rows if r['pos']!=pos],pos)
                and carried(state(),'minecraft:glass_bottle')
                and(profile.get('mud_bucket_source')or{}).get('authorized')is True):
            from .registered_grass_bed import run as recover_grass
            operation('recover_registered_grass',pos,lambda:recover_grass(c,pos,profile,out/('registered-grass-%d'%index),state))
            rows=_scan(c,[pos[0],pos[1]-2,pos[2]],pos,state);bed=refill_column(rows,pos)
            top=next((b for b in rows if b['pos']==pos),None);name=block_id(top)if top else'minecraft:air'
        if bed is None:raise JobBlocked('Registered clay bed support/tip changed; preserve current construction')
        observed.append({'pos':pos,'state':name})
        if name=='minecraft:clay'and carried(state(),item)<target:
            operation('harvest',pos,lambda:harvest(c,pos,out/('harvest-%d'%index),state))
            name='minecraft:air'
        if name=='minecraft:air'and carried(state(),'minecraft:mud'):
            operation('refill',pos,lambda:refill(c,pos,out/('refill-%d'%index),state))
        elif (name=='minecraft:air'and carried(state(),'minecraft:dirt')
                and carried(state(),'minecraft:glass_bottle')
                and (profile.get('mud_bucket_source')or{}).get('authorized')is True):
            operation('direct_refill',pos,lambda:refill_from_dirt(c,pos,profile,out/('direct-refill-%d'%index),state))
    if item=='minecraft:clay':
        q=state();balls=carried(q,'minecraft:clay_ball');rounds=min(balls//4,target-carried(q,item));initial=carried(q,item)
        if rounds>0:
            result=operation('compact',None,lambda:manufacture(c,RecipeCatalog(profile['recipe_jar']),{item:initial+rounds}))
            q=state()
            if not result.get('complete')or carried(q,item)!=initial+rounds or carried(q,'minecraft:clay_ball')!=balls-4*rounds:
                raise JobBlocked('Local clay recipe conservation unconfirmed')
    operation('exit',cfg['exit'],lambda:move(c,cfg['exit'],out/'known-air-exit',max_straight=8,foot_offset=.2))
    after=carried(state(),item)
    result={'phase':'done'if after>=target else'waiting','code':'HOME_CLAY_BATCH'if after>before else'WAIT_FARM_GROWTH',
            'item':item,'before':before,'after':after,'requirements':{item:target},'observed_beds':observed,
            'safe_to_leave':True,'remote_clay_fallback':False}
    book.update(complete=True,result=result);save();return result
