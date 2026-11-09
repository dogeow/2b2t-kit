"""Guarded, resumable plane recovery using vanilla mining and exact item identities.

Configuration pins a server, dimension, plane and owned storage. No action is
replayed after an uncertain outcome. Existing user equipment is never deposited.
"""
from __future__ import annotations
import argparse,fcntl,json,math,time,uuid
from pathlib import Path
from falling_drop_tracking import observe,intercept_pose
from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_plan import inventory_counts
from native_outcome_fence import RetainedUnknownMaterialClient
from container_access import open_chest_from_pose


def validate_profile(p):
    if not isinstance(p,dict) or p.get('schema')!=1 or p.get('authorized') is not True:raise ValueError('Explicit recovery profile required')
    for k in ('server','dimension','item','block_state','tool'):
        if not isinstance(p.get(k),str) or not p[k]:raise ValueError('Missing '+k)
    for k in ('min','max','chest','chest_pose','park_target'):
        v=p.get(k)
        if not isinstance(v,list) or len(v)!=3 or any(type(n) not in (int,float) or not math.isfinite(n) for n in v):raise ValueError('Invalid '+k)
    lo,hi=p['min'],p['max']
    if any(type(v)is not int for v in lo+hi) or lo[1]!=hi[1] or any(a>b for a,b in zip(lo,hi)) or (hi[0]-lo[0]+1)*(hi[2]-lo[2]+1)>15000:raise ValueError('Expected bounded single plane')
    if any(type(v)is not int for v in p['chest']) or p.get('chest_face') not in ('north','south','east','west','up'):raise ValueError('Exact chest geometry required')
    if type(p.get('foot_y')) not in (int,float) or not lo[1]-3<=p['foot_y']<=lo[1]-2.0:raise ValueError('Foot height must stay below target plane')
    if type(p.get('minimum_y'))not in(int,float) or not math.isfinite(p['minimum_y']) or p['minimum_y']>=p['foot_y']:raise ValueError('Invalid lower air limit')
    if type(p.get('batch_size'))is not int or not 1<=p['batch_size']<=32:raise ValueError('Batch size must be 1..32')
    if not isinstance(p.get('protected_columns'),list) or any(not isinstance(v,list) or len(v)!=2 or any(type(n)is not int for n in v) for v in p['protected_columns']):raise ValueError('Explicit protected storage columns required')
    return p


def actual_targets(scan,p):
    lo,hi=p['min'],p['max'];cells=(hi[0]-lo[0]+1)*(hi[2]-lo[2]+1)
    if (scan.get('scan_cells_read')!=cells or scan.get('scan_total_cells')!=cells or not isinstance(scan.get('blocks'),list)):
        raise RuntimeError('Plane scan incomplete; no mining')
    targets=[];seen=set()
    for v in scan['blocks']:
        pos=v.get('pos')
        if not isinstance(pos,list) or len(pos)!=3 or any(type(n)is not int for n in pos) or tuple(pos)in seen:raise RuntimeError('Malformed plane observation')
        seen.add(tuple(pos))
        if not all(lo[i]<=pos[i]<=hi[i] for i in range(3)):raise RuntimeError('Plane observation outside authorized bounds')
        if v.get('state')==p['block_state']:targets.append(pos)
    return targets


def choose_target(targets,pos):
    if not targets:return None
    return min(targets,key=lambda t:((t[0]+.5-pos[0])**2+(t[2]+.5-pos[2])**2,t[0],t[2]))


def side_stances(target, blocks, entities=()):
    """Return collision-free same-height neighboring cells and visible faces.

    The caller must freshly scan the full 3x5x3 neighborhood. A non-air block
    in any body/safe-descent cell rules that side out; no block is excavated.
    """
    x,y,z=target;occupied={tuple(v['pos']) for v in blocks};result=[]
    for dx,dz,face in ((1,0,'east'),(-1,0,'west'),(0,1,'south'),(0,-1,'north')):
        a,b=x+dx,z+dz
        if any((a,h,b) in occupied for h in range(y-3,y+2)):continue
        low=[a+.2,y+.05,b+.2];high=[a+.8,y+1.85,b+.8];blocked=False
        for e in entities:
            if e.get('type')=='minecraft:item' or e.get('alive') is False:continue
            box=e.get('bounds')or{};left,right=box.get('min'),box.get('max')
            if not isinstance(left,list) or not isinstance(right,list) or len(left)!=3 or len(right)!=3:
                blocked=True;break
            if all(right[i]>low[i] and left[i]<high[i] for i in range(3)):
                blocked=True;break
        if not blocked:result.append(([a+.5,y+.05,b+.5],face))
    return result


def exposed_targets(targets, occupied):
    """Select possible edge blocks; every choice still needs a fresh side scan."""
    return [t for t in targets if any((t[0]+dx,t[1],t[2]+dz) not in occupied
                                      for dx,dz in ((1,0),(-1,0),(0,1),(0,-1)))]


def healthy(c):
    s=c.status()
    def admissible(q):
        return (q.get('health',0)>=14 and q.get('guard_armed') is True and q.get('guard_busy') is False
                and q.get('manual_movement') is False and not q.get('screen') and q.get('flight') is True)
    if not admissible(s):raise RuntimeError('Player protection or input changed; stop')
    if s.get('health',0)>=19 and s.get('food',0)>=18:return s
    hurt=s.get('recent_hurt_at');foods=('minecraft:cooked_beef','minecraft:cooked_porkchop','minecraft:cooked_mutton','minecraft:bread','minecraft:golden_carrot')
    if s.get('food',0)<20:
        counts=inventory_counts(s);item=next((v for v in foods if counts[v]>0),None)
        if item is None:raise RuntimeError('Food reserve unavailable; stop')
        c.checked('use_item',item=item)
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        s=c.status()
        if not admissible(s) or s.get('recent_hurt_at')!=hurt:raise RuntimeError('Health recovery interrupted; stop')
        if s.get('health',0)>=19 and s.get('food',0)>=18:return s
        time.sleep(.3)
    raise RuntimeError('Health recovery did not settle; stop')


def goto_side(c,current,stance,foot_y):
    """Keep height when a fresh short swept path is empty; otherwise go below."""
    pos=current['pos']
    if math.dist(pos,stance)<=.2:return 'already_at_side'
    if abs(pos[1]-stance[1])<=.3 and math.hypot(pos[0]-stance[0],pos[2]-stance[2])<=3:
        lo=[math.floor(min(pos[i],stance[i])-(.32 if i!=1 else 0))for i in range(3)]
        hi=[math.floor(max(pos[i],stance[i])+(.32 if i!=1 else 1.8))for i in range(3)]
        scene=c.checked('scan',min=lo,max=hi,details=True)
        from material_jobs.acquisition import blocks_route
        if not any(blocks_route(v,current,stance)for v in scene['blocks']):
            c.checked('navigate',target=stance,arrival=.2,air_only=True,seconds=20);return 'clear_same_height'
    if pos[1]>foot_y+.5:c.checked('navigate',target=[pos[0],foot_y,pos[2]],arrival=.3,air_only=True,seconds=25)
    goto_storage(c,[stance[0],foot_y,stance[2]])
    c.checked('navigate',target=stance,arrival=.2,air_only=True,seconds=25);return 'below_then_side'


def clear_air_leg(c, state, target):
    """A read-only, bounded collision check; native Flight still enforces it."""
    origin=state['pos']
    low=[math.floor(min(origin[i],target[i])-(.32 if i!=1 else 0)) for i in range(3)]
    high=[math.floor(max(origin[i],target[i])+(.32 if i!=1 else 1.8)) for i in range(3)]
    scene=c.checked('scan',min=low,max=high,details=True)
    from material_jobs.acquisition import blocks_route
    return not any(blocks_route(v,state,target) for v in scene['blocks'])


def goto_storage(c, target):
    """Choose a clear direct or orthogonal air route without breaking blocks."""
    state=healthy(c)
    if math.dist(state['pos'],target)<=.25:return
    if clear_air_leg(c,state,target):
        c.checked('navigate',target=target,arrival=.25,air_only=True,seconds=50);return
    start=state['pos']
    for waypoint in ([start[0],target[1],target[2]],[target[0],target[1],start[2]]):
        if not clear_air_leg(c,state,waypoint):continue
        # A second segment can be checked from the proposed pose without
        # moving; native collision checks remain mandatory for both legs.
        virtual=dict(state,pos=waypoint)
        if not clear_air_leg(c,virtual,target):continue
        c.checked('navigate',target=waypoint,arrival=.25,air_only=True,seconds=25)
        c.checked('navigate',target=target,arrival=.25,air_only=True,seconds=25);return
    # The two-segment sweep can be overly conservative near a chest.
    # Reuse Kit's bounded three-dimensional air planner; it checks every
    # movement and never opens a route by mining.
    if math.hypot(start[0]-target[0],start[2]-target[2])<=24:
        from material_jobs.local_air_path import move
        move(c,target,Path(c.out)/('recovery-route-'+uuid.uuid4().hex[:8]),
             max_straight=4,foot_offset=.2,max_horizontal=24,exact_target=True)
        return
    raise RuntimeError('No verified bounded route to storage; no blocks disturbed')


def close_owned(c):
    c.checked('close_menu');end=time.monotonic()+5
    while time.monotonic()<end:
        q=c.status()
        if not q.get('screen') and (q.get('menu')or{}).get('type')=='InventoryMenu':return
        time.sleep(.2)
    raise RuntimeError('Original close not confirmed; no further inputs')


def deposit(c,p,book,path):
    q=healthy(c);amount=inventory_counts(q)[p['item']]
    if not amount:return
    if q['pos'][1]>p['foot_y']+.5:c.checked('navigate',target=[q['pos'][0],p['foot_y'],q['pos'][2]],arrival=.3,air_only=True,seconds=25)
    goto_storage(c,p['chest_pose'])
    q=open_chest_from_pose(c,p['chest'],c.status()['pos'],p['chest_face'],allow_empty=True,allow_hover=True,allow_top_face=p['chest_face']=='up');c.owned_material_menu=q['menu']['id'];n=len(q['menu']['slots'])-36
    if n not in (27,54):raise RuntimeError('Unexpected storage menu')
    stock=sum(v['count'] for v in q['menu']['slots'][:n] if v.get('item')==p['item'])
    capacity=sum((v.get('max_stack',64)-v['count']) if v.get('item')==p['item'] else 64 if not v.get('count') else 0 for v in q['menu']['slots'][:n])
    if capacity<amount:raise RuntimeError('Storage has insufficient capacity; no deposit')
    book['pending']={'op':'deposit','before':amount,'chest_before':stock};write_json(path,book)
    c.transfer(p['item'],0,deposit=True);frames=[];deadline=time.monotonic()+8
    while len(frames)<2:
        q=c.status();now=inventory_counts(q)[p['item']];end=sum(v['count']for v in q['menu']['slots'][:n]if v.get('item')==p['item'])
        if now==0 and end==stock+amount and not q['menu']['cursor']['count'] and (not frames or q['time']>frames[-1]):frames.append(q['time'])
        if time.monotonic()>deadline:raise RuntimeError('Original deposit unconfirmed; do not repeat')
        time.sleep(.2)
    close_owned(c);time.sleep(2)
    q=open_chest_from_pose(c,p['chest'],c.status()['pos'],p['chest_face'],allow_empty=True,allow_hover=True,allow_top_face=p['chest_face']=='up');c.owned_material_menu=q['menu']['id'];n=len(q['menu']['slots'])-36;reopened=sum(v['count']for v in q['menu']['slots'][:n]if v.get('item')==p['item'])
    if reopened!=stock+amount or inventory_counts(q)[p['item']]!=0:raise RuntimeError('Reopened storage differs; preserve evidence')
    book.setdefault('deposits',[]).append({'amount':amount,'chest_before':stock,'chest_after':reopened,'frames':frames});book['pending']=None;write_json(path,book);close_owned(c)


def pickup_state(c):
    """Observe an outstanding drop while PvE guard is active, without taking input."""
    s=c.status()
    if (s.get('health',0)<14 or not s.get('guard_armed') or s.get('manual_movement')
            or s.get('screen') or not s.get('flight')):
        raise RuntimeError('Player protection or input changed during pickup; stop')
    return s


def pickup_near_floor(pending,packet,minimum_y):
    if (pending.get('fall_recovery')or{}).get('floor_contact'):return True
    points=[pending.get('last_observed')]
    if isinstance(packet,dict):
        for name in ('source','joined_source'):
            source=packet.get(name)or{}
            points.append(source.get('pos') if isinstance(source,dict) else None)
    return any(isinstance(v,(list,tuple)) and len(v)==3 and type(v[1])in(int,float)
               and math.isfinite(v[1]) and v[1]<=minimum_y+1 for v in points)


def await_pickup(c,p,book,path,before,known,target,*,initial=None):
    tracked=None;last=None;attempts=0;start=time.monotonic();deadline=start+12;frames=[]
    seen_drop=None;packet=None;packet_amount=None
    def remember(frame,uid):
        entity=next((e for e in frame.get('entities',[]) if e.get('uuid')==uid),None)
        if not entity or type(entity.get('id'))is not int or type(frame.get('time'))is not int:return None
        return {'world_session':frame.get('world_session'),'runtime_generation':frame.get('runtime_generation'),
                'observed_at':frame['time'],'entity':entity}
    if isinstance(initial,dict) and isinstance(initial.get('inventory'),list):
        first=observe(item=p['item'],expected_count=1,before=before,current=inventory_counts(initial)[p['item']],entities=initial.get('entities',[]),known_ids=known,origin=[target[0]+.5,target[1]+.5,target[2]+.5],radius=32)
        if first.state=='track':
            tracked=first.uuid;seen_drop=remember(initial,tracked)
            book['pending']['drop_uuid']=tracked;book['pending']['last_observed']=list(first.position);write_json(path,book)

    while time.monotonic()<deadline:
        q=pickup_state(c);amount=inventory_counts(q)[p['item']]
        if seen_drop is not None and packet is None:
            from villager_events import read as read_events,joined_pickups
            frame=read_events(c.root,q);player=q.get('player_uuid')
            if frame is not None and isinstance(player,str):
                receipts=joined_pickups(frame,p['item'],{player},seen_drop)
                if len(receipts)==1 and receipts[0].get('amount')==1:packet=receipts[0]
        if packet is not None and amount>=before+1 and not any(e.get('uuid')==tracked for e in q.get('entities',[])):
            if packet_amount is None:packet_amount=amount
            if amount!=packet_amount:raise RuntimeError('Inventory changed while confirming pickup packet')
            if not frames or q['time']>frames[-1]:frames.append(q['time'])
            if len(frames)>=2:return {'frames':frames,'drop_uuid':tracked,'follow_attempts':attempts,'actual_after':amount,'surplus':amount-before-1,'server_pickup_receipt':packet,'floor_contact':pickup_near_floor(book['pending'],packet,p['minimum_y'])}
            time.sleep(.15);continue
        o=observe(item=p['item'],expected_count=1,before=before,current=amount,entities=q.get('entities',[]),known_ids=known,origin=[target[0]+.5,target[1]+.5,target[2]+.5],tracked_uuid=tracked,radius=32)
        if o.state=='collected':
            if not frames or q['time']>frames[-1]:frames.append(q['time'])
            if len(frames)>=2:return {'frames':frames,'drop_uuid':tracked,'follow_attempts':attempts,'actual_after':amount,'floor_contact':pickup_near_floor(book['pending'],packet,p['minimum_y'])}
        elif o.state=='stop':raise RuntimeError('Pickup evidence ambiguous: '+o.reason)
        elif o.state=='track':
            tracked=o.uuid;last=list(o.position)
            if seen_drop is None:seen_drop=remember(q,tracked)
            book['pending']['drop_uuid']=tracked;book['pending']['last_observed']=last;write_json(path,book)
            # Give a natural overlap one status frame; then pursue a newly
            # observed original item, never replaying a previous movement.
            if not q.get('guard_busy') and time.monotonic()-start>=1.1 and attempts<3:
                pose=intercept_pose(last,minimum_y=p['minimum_y'],vertical_lead=4)
                if pose is None:raise RuntimeError('Original item reached lower limit; preserve')
                if last[1]<=p['minimum_y']+1:raise RuntimeError('Original item near bedrock; stop further mining')
                player=q['pos'];lo=[math.floor(min(player[i],pose[i])-(.35 if i!=1 else 0))for i in range(3)];hi=[math.floor(max(player[i],pose[i])+(.35 if i!=1 else 1.8))for i in range(3)]
                scan=c.checked('scan',min=lo,max=hi,details=True)
                from material_jobs.acquisition import blocks_route
                if any(blocks_route(v,q,pose) for v in scan['blocks']):
                    # A natural pickup can complete while the route scan is in
                    # flight. Reobserve the exact item and stock before stopping.
                    fresh=pickup_state(c)
                    settled=observe(item=p['item'],expected_count=1,before=before,current=inventory_counts(fresh)[p['item']],entities=fresh.get('entities',[]),known_ids=known,origin=[target[0]+.5,target[1]+.5,target[2]+.5],tracked_uuid=tracked,radius=32)
                    if settled.state=='collected' or fresh.get('guard_busy'):continue
                    if settled.state!='track' or settled.uuid!=tracked:
                        raise RuntimeError('Original item intercept path obstructed; retain')
                    # A rectangular sweep can report a nearby block outside
                    # the actual path. Use the existing collision-checked air
                    # planner on the newly observed original entity instead.
                    revised=intercept_pose(settled.position,minimum_y=p['minimum_y'],vertical_lead=4)
                    if revised is None:raise RuntimeError('Original item reached lower limit; preserve')
                    book['pending']['intercept']={'target':revised,'from_drop':list(settled.position),'attempt':attempts+1,'route':'verified_local_air'};write_json(path,book)
                    from material_jobs.local_air_path import move
                    move(c,revised,path.parent/('pickup-air-'+uuid.uuid4().hex[:8]),max_straight=4,foot_offset=.2,exact_target=True,max_horizontal=12)
                    attempts+=1;continue
                book['pending']['intercept']={'target':pose,'from_drop':last,'attempt':attempts+1};write_json(path,book);c.checked('navigate',target=pose,arrival=.5,air_only=True,seconds=12);attempts+=1
        else:
            # A missing item is not proof of removal. No guessed or repeated mine.
            if tracked and not q.get('guard_busy') and time.monotonic()-start>3:
                # The status entity list is distance-limited. Search the bounded
                # fall column for this exact identity; never guess a new item.
                x,y,z=target;low=[x-6,math.floor(p['minimum_y'])-2,z-6];high=[x+6,y+1,z+6]
                scan=c.checked('scan',min=low,max=high,details=True)
                matches=[v for v in scan.get('scan_entities',[]) if v.get('uuid')==tracked and v.get('type')=='minecraft:item']
                if len(matches)!=1:raise RuntimeError('Tracked drop not visible in bounded column; retain identity')
                item_pos=matches[0].get('pos')
                if not isinstance(item_pos,list) or len(item_pos)!=3:raise RuntimeError('Tracked item position unavailable')
                floor_contact=item_pos[1]<=p['minimum_y']+1
                pose=[item_pos[0],p['minimum_y']-1.0 if floor_contact else max(p['minimum_y'],item_pos[1]-4),item_pos[2]]
                book['pending']['fall_recovery']={'uuid':tracked,'observed':item_pos,'target':pose,'floor_contact':floor_contact};write_json(path,book)
                c.checked('navigate',target=pose,arrival=.4,air_only=True,seconds=30);attempts+=1
                start=time.monotonic();deadline=start+8
        time.sleep(.15)
    raise RuntimeError('Original pickup not confirmed; stop without next mine')


def run(c,p,out,*,max_blocks=None,resume=False):
    out=Path(out);path=out/'progress.json';s=healthy(c)
    if resume:
        book=json.loads(path.read_text())
        if book.get('profile')!=p or book.get('pending') is not None or book.get('complete') or book.get('world_session')!=c.world:raise RuntimeError('Original recovery needs reconciliation; no replay')
    else:
        out.mkdir(parents=True,exist_ok=False);book={'schema':1,'profile':p,'world_session':c.world,'pending':None,'mined':[],'deposits':[],'complete':False};write_json(path,book)
    deposit(c,p,book,path);completed=0;targets=None;occupied=set();unavailable=set()
    while max_blocks is None or completed<max_blocks:
        if targets is None:
            q=c.checked('scan',min=p['min'],max=p['max'],details=True);targets=actual_targets(q,p)
            occupied={tuple(v['pos']) for v in q['blocks']};unavailable=set()
        if not targets:
            deposit(c,p,book,path)
            if book.get('unresolved'):
                book['remaining_blocks']=0;write_json(path,book)
                raise RuntimeError('Plane cleared but original pickup provenance remains unresolved')
            book['complete']=True;write_json(path,book);return book
        candidates=[v for v in exposed_targets(targets,occupied) if tuple(v) not in unavailable]
        if not candidates:raise RuntimeError('No verified side access; stop without digging another route')
        target=choose_target(candidates,c.status()['pos']);x,y,z=target
        # Check both the adjacent standing space and a vertical route to it.
        scene=c.checked('scan',min=[x-1,y-3,z-1],max=[x+1,y+1,z+1],details=True)
        cells={tuple(v['pos']):v['state']for v in scene['blocks']}
        if cells.get(tuple(target))!=p['block_state']:
            raise RuntimeError('Target changed after plane scan; refresh rather than credit')
        choices=side_stances(target,scene['blocks'],scene.get('scan_entities',[]))
        if not choices:
            unavailable.add(tuple(target));continue
        current=healthy(c);stance,face=min(choices,key=lambda a:math.dist(a[0],current['pos']))
        approach=goto_side(c,current,stance,p['foot_y'])
        q=healthy(c);tool=next((v for v in q.get('inventory',[]) if v.get('item')==p['tool'] and v.get('slot',99)<9),None)
        if not tool or type(tool.get('durability'))is not int or tool['durability']<=64:raise RuntimeError('Safe pickaxe durability reserve reached')
        c.checked('select_item',item=p['tool'],slot=tool['slot'])
        verify=c.checked('scan',min=target,max=target,details=True)
        if len(verify['blocks'])!=1 or verify['blocks'][0]['state']!=p['block_state']:raise RuntimeError('Target changed before mining')
        s=healthy(c);before=inventory_counts(s)[p['item']];known={v['uuid'] for v in s.get('entities',[]) if v.get('uuid')};book['pending']={'op':'mine','target':target,'before':before};write_json(path,book)
        reply=c.checked('mine_block',pos=target,face=face,expected_state=p['block_state'],seconds=15)
        if reply.get('server_confirmed')is not True or reply.get('native_sequence',0)<=0 or reply.get('server_ack_sequence')!=reply.get('native_sequence'):raise RuntimeError('Original mine not confirmed')
        book['pending']['request_id']=reply['id'];write_json(path,book);proof=await_pickup(c,p,book,path,before,known,target,initial=reply)
        book['mined'].append({'target':target,'stance':stance,'face':face,'approach':approach,'request_id':reply['id'],'before':before,'after':proof.get('actual_after',before+1),'pickup':proof});book['pending']=None;write_json(path,book);completed+=1;targets.remove(target);occupied.discard(tuple(target));unavailable.clear()
        print('RECOVERED',len(book['mined']),target,flush=True)
        if proof.get('floor_contact'):
            deposit(c,p,book,path);raise RuntimeError('One item reached the lower surface and was recovered; stop to improve interception')
        if inventory_counts(c.status())[p['item']]>=p['batch_size']:
            deposit(c,p,book,path);targets=None
    deposit(c,p,book,path);return book


def reconcile_pending(root,p,out):
    """Resolve only a confirmed original mine whose exact stock gain is observed.

    No game input other than read-only scans is sent. The old pending record is
    copied to a separate immutable proof before the resumable ledger advances.
    """
    root,out=Path(root),Path(out);path=out/'progress.json';original=path.read_bytes();book=json.loads(original);pending=book.get('pending') or {}
    if book.get('profile')!=p or pending.get('op')!='mine' or not pending.get('request_id') or not pending.get('drop_uuid'):
        raise RuntimeError('Pending item lacks exact original identities')
    target=pending.get('target');before=pending.get('before');rid=pending['request_id'];drop=pending['drop_uuid']
    if not isinstance(target,list) or len(target)!=3 or type(before)is not int:raise RuntimeError('Malformed original mining record')
    reply_path=root/('reply-'+rid+'.json')
    if not reply_path.is_file():raise RuntimeError('Original native mining receipt unavailable')
    reply=json.loads(reply_path.read_text());seq=reply.get('native_sequence')
    if (reply.get('id')!=rid or reply.get('world_session')!=book['world_session'] or reply.get('phase')!='done'
            or reply.get('server_confirmed') is not True or type(seq)is not int or seq<=0
            or reply.get('server_ack_sequence')!=seq or reply.get('mining_target')!=target):
        raise RuntimeError('Original server-confirmed mine identity unavailable')
    s=read_fresh(root)
    if (not s.get('connected') or s.get('world_session')!=book['world_session'] or s.get('server')!=p['server']
            or s.get('dimension')!=p['dimension'] or s.get('health',0)<19 or not s.get('guard_armed')
            or s.get('guard_busy') or s.get('manual_movement') or s.get('screen') or s.get('supervision_lease')):
        raise RuntimeError('Current world or protection changed; no reconciliation')
    from material_client import Client
    qdir=out/('reconcile-read-'+uuid.uuid4().hex[:8]);c=Client(root,qdir,p['server'],dimension=p['dimension']);times=[];observed=None
    for _ in range(2):
        x,y,z=target
        q=c.checked('scan',min=[x-6,math.floor(p['minimum_y'])-2,z-6],max=[x+6,y+2,z+6],details=True)
        amount=inventory_counts(q)[p['item']]
        if (q.get('world_session')!=book['world_session'] or amount<before+1
                or observed is not None and amount!=observed
                or any(v.get('pos')==target for v in q.get('blocks',[]))
                or any(v.get('uuid')==drop for v in q.get('scan_entities',[]))):
            raise RuntimeError('Original pickup remains unconfirmed; no replay')
        observed=amount;times.append(q['time']);time.sleep(1.1)
    if times[1]<=times[0] or path.read_bytes()!=original:raise RuntimeError('Observation or ledger changed; no reconciliation')
    exact=observed==before+1
    proof={'classification':('server_confirmed_mine_with_exact_inventory_gain_and_uuid_absent' if exact else
                            'server_confirmed_mine_with_unattributed_inventory_surplus'),
           'request_id':rid,'drop_uuid':drop,'before':before,'after':observed,'times':times,
           'pickup_attributed':False,'observation_scope':'loaded client entities; inventory gain is not entity-level pickup provenance',
           'original_pending':pending,'original_replayed':False}
    proofpath=out/('reconciliation-'+rid+'.json')
    if proofpath.exists():raise RuntimeError('Original reconciliation already exists; no overwrite')
    write_json(proofpath,proof)
    entry={'target':target,'request_id':rid,'before':before,'after':observed,'pickup':proof}
    if exact:book['mined'].append(entry)
    else:book.setdefault('unresolved',[]).append(entry)
    book['pending']=None;write_json(path,book)
    return proof


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);parser.add_argument('--resume',action='store_true');parser.add_argument('--reconcile',action='store_true');parser.add_argument('--max-blocks',type=int)
    a=parser.parse_args();p=validate_profile(json.loads(a.profile.read_text()));
    if a.max_blocks is not None and a.max_blocks<1:raise ValueError('Positive batch limit required')
    root=Path('/Applications/.minecraft/versions/26.2/config/twob2tkit/automation')
    if a.reconcile:
        if a.resume or a.max_blocks is not None:raise ValueError('Reconciliation cannot also start mining')
        with Path(p['lock_path']).open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            print('RECONCILED',reconcile_pending(root,p,a.out),flush=True)
        return
    s=read_fresh(root)
    if (s.get('server')!=p['server'] or s.get('dimension')!=p['dimension'] or not s.get('connected') or s.get('manual_movement') or s.get('screen') or s.get('supervision_lease') or s.get('guard_busy') or s.get('health',0)<19 or s.get('food',0)<18 or (s.get('professional_printer')or{}).get('enabled')):raise RuntimeError('Current game is not ready for guarded recovery')
    lock=Path(p['lock_path']).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);c=None
    try:
        if a.resume:
            saved=json.loads((a.out/'progress.json').read_text())
            if saved.get('profile')!=p or saved.get('pending') is not None or saved.get('complete') or saved.get('world_session')!=s.get('world_session'):
                raise RuntimeError('Original recovery needs reconciliation; no new controller')
        elif a.out.exists():raise RuntimeError('Recovery ledger already exists; use its explicit resume path')
        control=a.out.parent/(a.out.name+'-control-'+uuid.uuid4().hex[:8]);c=RetainedUnknownMaterialClient(root,control,p['server'],record_experience=False,remote_finish='guard',park_target=p['park_target'],dimension=p['dimension']);c.printer_handoff_revision=s['professional_printer']['external_mode_revision'];c.checked('guard',pve_only=True)
        result=run(c,p,a.out,max_blocks=a.max_blocks,resume=a.resume);print('RUN_RESULT',{'complete':result['complete'],'total_mined':len(result['mined']),'deposits':len(result['deposits'])},flush=True)
    finally:
        if c and not c.unconfirmed_native_request and not c.native_inflight:
            state=c.raw();menu=state.get('menu')or{};cursor=menu.get('cursor')or{}
            if state.get('screen') and c.owned_material_menu==menu.get('id') and not cursor.get('count'):c.checked('close_menu')
            if (c.raw().get('supervision_lease')or{}).get('job_session')==c.task:c.checked('material_job_pause',release=True)
        if c and c.heartbeat:c.heartbeat.close()
        if c and c.foreground_token:c.foreground_token.close()
        lock.close()

if __name__=='__main__':main()
