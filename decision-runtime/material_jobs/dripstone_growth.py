"""Harvest downward growth bottom-up while retaining every attached root."""
import math,time,json,hashlib
from pathlib import Path
from kit_runtime.journal import write_json
from projection_completion import block_state
from drop_collection import collect_drop
from work_access import approach_faces,ApproachUnavailable
from .acquisition import _scan,_safe,_tool,_choose_tool,block_id,carried
from .protocol import JobBlocked

ITEM='minecraft:pointed_dripstone'


def exit_farm(c,target,out,*,bounds=None):
    """Leave the hanging platform through existing body air, without a ground floor."""
    from .local_air_path import move,move_replanning_once
    q=c.status();_safe(q);lease=q.get('supervision_lease')or{}
    if (q.get('world_session')!=c.world or q.get('flight')is not True
            or lease.get('kind')!='materials'or lease.get('job_session')!=c.task
            or lease.get('revision')!=q.get('control_revision')
            or getattr(c,'native_inflight',None)is not None
            or getattr(c,'unconfirmed_native_request',None)is not None):
        raise JobBlocked('Growth air exit requires the current settled flying owner')
    mover=move_replanning_once if bounds is not None else move
    return mover(c,target,out,max_straight=8,foot_offset=.2,max_horizontal=24,
                **({'scan_bounds':bounds}if bounds is not None else{}))


def access(c,tip,out,*,bounds=None):
    # Dense neighbouring roots can occlude the native eye-height stations.
    # Prove a lower side pose in the existing two-block-high air space instead.
    from .local_air_path import move,plan,move_replanning_once,ObservedAirPathBlocked
    from .navigation import _air_scan,settled_state
    from .dry_hover_harvest import visible_face
    start=c.status()['pos'];x,y,z=tip['pos']
    options=[([x+.5,y-1.8,z-.5],'down'),([x+.5,y-1.8,z+1.5],'down'),
             ([x-.5,y-1.8,z+.5],'down'),([x+1.5,y-1.8,z+.5],'down')]
    # Raised terrain can close all four immediately adjacent body columns.
    # A lower diagonal or two-block stand still reaches the bottom face, while
    # preserving that terrain and every neighbouring growth root.
    offsets=[(dx,dz)for radius in(1,2)for dx,dz in
             ((-radius,-radius),(-radius,radius),(radius,-radius),(radius,radius))]
    offsets.extend((dx,dz)for dx,dz in ((-2,0),(2,0),(0,-2),(0,2),(0,0)))
    options.extend(([x+dx+.5,y-1.8,z+dz+.5],'down')for dx,dz in offsets)
    if block_state(tip['state'])[1].get('thickness')=='tip_merge':
        # The upward partner can hide the bottom face. A side ray stays out of
        # that partner's voxel; the same complete body/visibility checks apply.
        options.extend((([x+.5,y-1.8,z-.5],'north'),([x+.5,y-1.8,z+1.5],'south'),
                        ([x-.5,y-1.8,z+.5],'west'),([x+1.5,y-1.8,z+.5],'east')))
    options.sort(key=lambda pair:math.dist(start,pair[0]))
    shared=None
    if bounds is not None:
        low,high=bounds['min'],bounds['max']
        if math.prod(b-a+1 for a,b in zip(low,high))>30000:raise JobBlocked('Growth access volume is too large')
        shared=_air_scan(c,low,high)
    for target,face in options:
        if bounds is None:
            low=[math.floor(min(a,b))-3 for a,b in zip(start,target)]
            high=[math.floor(max(a,b))+3 for a,b in zip(start,target)]
        if math.prod(b-a+1 for a,b in zip(low,high))>30000:continue
        rows=shared if shared is not None else _air_scan(c,low,high)
        face_visible=visible_face(rows,target,tip['pos'],face)
        if not face_visible and not visible_face(rows,target,tip['pos'],'center'):continue
        try:plan(rows,start,target,low,high,max_straight=8,foot_offset=.2)
        except JobBlocked:continue
        mover=move_replanning_once if bounds is not None else move
        try:mover(c,target,out,max_straight=8,foot_offset=.2,**({'scan_bounds':bounds}if bounds is not None else{}))
        except JobBlocked as error:
            known_planning=isinstance(error,ObservedAirPathBlocked)or str(error)in(
                '局部空气路线起点或终点未完整确认','已存在空气空间没有连通，不挖掘新通道')
            if (known_planning and getattr(c,'native_inflight',None)is None
                    and getattr(c,'unconfirmed_native_request',None)is None):
                raise ApproachUnavailable('Observed growth blocked this access route; retain the column')from error
            raise
        settled_state(c,target,.45)
        return face if face_visible else None
    raise ApproachUnavailable('No proved lower side station; retain the original column')


def actual_mining_face(c,tip,fallback):
    """Use the current settled eye, preferring the native block-centre aim."""
    from .navigation import _air_scan
    from .dry_hover_harvest import visible_face
    current=c.status()['pos'];target=tip['pos']
    low=[math.floor(min(a,b))-1 for a,b in zip(current,target)]
    high=[math.floor(max(a,b))+2 for a,b in zip(current,target)]
    rows=_air_scan(c,low,high)
    for face in dict.fromkeys(('center',)+((fallback,)if fallback is not None else())):
        if visible_face(rows,current,target,face):return None if face=='center'else face
    raise ApproachUnavailable('Current settled eye has no clear mining ray; no mining sent')


def collect_from_air(c,drop,out,state,*,bounds=None):
    """A distinct scanned air approach above a falling/floating tip; no remine."""
    from .dry_hover_harvest import pickup
    q=state();current=next((e for e in q.get('entities',[])if e.get('uuid')==drop['uuid']),None)
    if (not current or current.get('stack')!=drop.get('stack')or drop.get('stack',{}).get('item')!=ITEM
            or drop['stack']['count']!=1 or q.get('flight')is not True
            or getattr(c,'native_inflight',None)is not None):return False
    before=carried(q,ITEM)
    # A falling tip can land in a one-high pocket. Select a real adjoining
    # two-air-cell pickup position instead of standing inside that pocket.
    return pickup(c,current,before,out,state,item=ITEM,allow_cone_edges=True,
                  **({'air_bounds':bounds}if bounds is not None else{}))


def growth_column(rows,root,minimum_y):
    cells={tuple(b['pos']):b for b in rows};x,y,z=root
    support=cells.get((x,y+1,z));water=cells.get((x,y+2,z))
    if (not support or block_id(support)!='minecraft:dripstone_block'
            or support.get('fluid')is not False or support.get('block_entity')is not False
            or not water or water['state']!='Block{minecraft:water}[level=0]'):
        raise JobBlocked('Growth support or source water changed; retain the farm')
    chain=[]
    for height in range(y,minimum_y-1,-1):
        b=cells.get((x,height,z))
        if not b or block_id(b)!=ITEM:break
        _,props=block_state(b['state'])
        if props.get('vertical_direction')!='down' or props.get('waterlogged')!='false':
            raise JobBlocked('Only a connected dry downward growth column may be harvested')
        chain.append(b)
        if props.get('thickness')in('tip','tip_merge'):break
    if (not chain or chain[0]['pos']!=root
            or block_state(chain[-1]['state'])[1].get('thickness')not in('tip','tip_merge')):
        raise JobBlocked('Growth column root or full bottom tip is unconfirmed')
    if block_state(chain[-1]['state'])[1].get('thickness')=='tip_merge':
        partner=cells.get((x,chain[-1]['pos'][1]-1,z))
        if (not partner or block_id(partner)!=ITEM or block_state(partner['state'])[1]!=
                {'thickness':'tip_merge','vertical_direction':'up','waterlogged':'false'}):
            raise JobBlocked('Merged growth partner is unconfirmed; retain the column')
    return {'root':root,'support':support,'water':water,'chain':chain,
            'next':chain[-1]if len(chain)>1 else None}


def harvest(c,roots,minimum_y,out,checkpoint,*,max_segments=128,air_bounds=None):
    if (not isinstance(roots,list)or not 1<=len(roots)<=128
            or any(not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)for p in roots)
            or len({tuple(p)for p in roots})!=len(roots)
            or type(minimum_y)is not int or any(not 1<=p[1]-minimum_y<=16 for p in roots)
            or type(max_segments)is not int or not 1<=max_segments<=128):
        raise ValueError('Explicit bounded roots and harvesting budget required')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'growth-harvest.json'
    if path.exists():raise JobBlocked('Original growth harvest journal retained; no replay')
    book={'world_session':c.world,'roots':roots,'pending':None,'receipts':[],'complete':False}
    shared_dir=Path(c.root)/'dripstone-growth-intents';shared_dir.mkdir(parents=True,exist_ok=True)
    initial=c.status();shared={}
    for root in roots:
        scope={'world_session':c.world,'server':initial.get('server'),'dimension':initial.get('dimension'),'root':root}
        record=shared_dir/(hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()+'.json')
        if record.exists():
            if record.is_symlink()or record.stat().st_size>16384:raise JobBlocked('Growth shared journal is unsafe')
            old=json.loads(record.read_text())
            if not isinstance(old,dict)or old.get('scope')!=scope or old.get('pending'):
                raise JobBlocked('Original growth action unresolved across jobs; no replay')
        shared[tuple(root)]=(record,scope)
    def save():
        write_json(path,book)
        if book['pending']:
            record,scope=shared[tuple(book['pending']['root'])]
            write_json(record,{'scope':scope,'journal':str(path),'pending':book['pending']})
    def state():
        checkpoint();q=c.status();_safe(q);lease=q.get('supervision_lease')or{}
        if (q.get('world_session')!=c.world or lease.get('kind')!='materials'
                or lease.get('job_session')!=c.task or lease.get('revision')!=q.get('control_revision')):
            raise JobBlocked('Growth farm control/world changed')
        return q
    def observe(root):
        x,y,z=root;return growth_column(_scan(c,[x,minimum_y,z],[x,y+2,z],state),root,minimum_y)
    before_total=carried(state(),ITEM);save()
    # Bound this run to growth already observed. New random growth remains for
    # the next run, rather than turning one harvest into an unbounded loop.
    plans=[(root,len(observe(root)['chain'])-1)for root in roots]
    for root,amount in plans:
        for _ in range(amount):
            if len(book['receipts'])>=max_segments:break
            original=observe(root);tip=original['next']
            if tip is None:break
            try:
                face=access(c,tip,out/('lower-access-%d-%d-%d-%d'%(*root,len(book['receipts']))),
                            **({'bounds':air_bounds}if air_bounds is not None else{}))
                face=actual_mining_face(c,tip,face)
            except ApproachUnavailable as error:
                # Access planning sends no mining. Defer this one connected
                # column rather than ending a finite harvest of other roots.
                book.setdefault('deferred_columns',[]).append({'root':root,'reason':str(error),'mining_sent':False})
                save();break
            _choose_tool(c,_tool(state(),'pickaxe',33),state)
            fresh=observe(root)
            if fresh['next'] is None or fresh['next']['state']!=tip['state'] or fresh['next']['pos']!=tip['pos']:
                book.setdefault('deferred_columns',[]).append({'root':root,'reason':'Growth changed before mining',
                    'mining_sent':False})
                save();break
            q=state();before=carried(q,ITEM)
            old={e['uuid']for e in q.get('entities',[])if e.get('type')=='minecraft:item'}
            book['pending']={'pos':tip['pos'],'root':root,'before':before};save()
            try:reply=c.request('mine_block',pos=tip['pos'],expected_state=tip['state'],seconds=20,
                                **({'face':face}if face is not None else{}))
            finally:book['pending']['request_id']=c.last;save()
            from .dry_hover_harvest import rejected_without_mining
            if rejected_without_mining(reply,c.last,c.world,tip['pos']):
                record,scope=shared[tuple(root)]
                write_json(record,{'scope':scope,'journal':str(path),'pending':None,
                    'rejected_without_mining':dict(book['pending']),
                    'rejection_receipt':{k:reply.get(k)for k in ('id','op','phase','detail','world_session','mining_target',
                        'server_confirmed','outcome_pending','server_update_seen','native_sequence','server_ack_sequence')}})
                book.setdefault('deferred_columns',[]).append({'root':root,'reason':reply['detail'],
                    'mining_sent':False,'known_rejected_request':dict(book['pending'])})
                book['pending']=None;save();break
            # Native mining must acknowledge the original server removal.
            if (reply.get('id')!=c.last or reply.get('world_session')!=c.world
                    or reply.get('phase')!='done' or reply.get('server_confirmed')is not True
                    or reply.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
                    or type(reply.get('native_sequence'))is not int or reply['native_sequence']<=0
                    or reply.get('server_ack_sequence')!=reply['native_sequence']
                    or _scan(c,tip['pos'],tip['pos'],state)):
                raise JobBlocked('Original grown-tip mining unconfirmed; no replay')
            deadline=time.monotonic()+15
            while True:
                q=state();after=carried(q,ITEM)
                if after==before+1:break
                if after!=before:raise JobBlocked('Grown-tip inventory changed unexpectedly')
                drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'
                       and e.get('uuid')not in old and e.get('stack',{}).get('item')==ITEM
                       and math.dist(e['pos'],tip['pos'])<12]
                if len(drops)==1 and drops[0]['stack']['count']==1:
                    book['pending']['drop_uuid']=drops[0]['uuid'];save()
                    if not collect_from_air(c,drops[0],out/('air-pickup-%d'%len(book['receipts'])),state,
                                            **({'bounds':air_bounds}if air_bounds is not None else{})):
                        raise JobBlocked('Original grown-tip pickup unconfirmed; no mining replay')
                    if carried(state(),ITEM)!=before+1:raise JobBlocked('Exact grown-tip gain missing')
                    break
                if drops or time.monotonic()>=deadline:raise JobBlocked('One original grown-tip drop not identified')
                time.sleep(.15)
            retained=observe(root)
            if (retained['support']['state']!=original['support']['state']
                    or retained['water']['state']!=original['water']['state']):
                raise JobBlocked('Growth support/water changed after harvest')
            book['receipts'].append({**book['pending'],'actual_gain':1,'root_retained':True,
                                     'support_preserved':True,'water_preserved':True})
            record,scope=shared[tuple(root)];write_json(record,{'scope':scope,'journal':str(path),'pending':None})
            book['pending']=None;save()
            c.set_progress(done=len(book['receipts']),phase='采收下段，保留顶端')
            print('GROWN_SEGMENT_COLLECTED',len(book['receipts']),tip['pos'],flush=True)
    for root in roots:observe(root)
    book.update(complete=True,actual_gained=carried(state(),ITEM)-before_total)
    save();return book
