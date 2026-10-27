"""Harvest explicitly registered dry clay columns with the existing Kit owner.

An observed shaft, unchanged floor and ordinary air movement provide access.
Only stone needed for those columns and actual clay are mined. Every drop is
counted in the current backpack; an unresolved intent prevents any replay.
"""
import hashlib,json,math,time
from pathlib import Path
from kit_runtime.journal import write_json
from material_trip_policy import room_for_item
from material_manufacture import manufacture
from recipe_catalog import RecipeCatalog
from .acquisition import _scan,_safe,_tool,_choose_tool,_travel,block_id,carried
from .natural_block_pipeline import _dry_natural
from .colored_sources import _protected
from .local_air_path import move,plan
from .navigation import settled_state
from .protocol import JobBlocked,JobPaused
from .roof_harvest import light_supports
from drop_collection import collect_drop


def validate(region):
    low,high=region.get('min'),region.get('max');cfg=region.get('dry_columns')or{}
    def point(p):return isinstance(p,list)and len(p)==3 and all(type(v)is int for v in p)
    floor=cfg.get('floor_y');entry=cfg.get('entry');columns=cfg.get('columns');sky=cfg.get('cruise_y')
    if (region.get('authorized')is not True or region.get('source')!='natural_survey'
            or cfg.get('authorized')is not True or not point(low)or not point(high)
            or any(not 0<=b-a<=15 for a,b in zip(low,high))or type(floor)is not int
            or not -62<=floor<=300 or low[1]!=floor+1 or not point(entry)
            or entry[1]!=floor+1 or not all(low[i]<=entry[i]<=high[i]for i in (0,2))
            or type(sky)not in(int,float)or not math.isfinite(sky)or not high[1]+4<=sky<=315
            or not isinstance(columns,list)or not 1<=len(columns)<=32
            or any(not point(p)or p[1]<floor+3 or any(not low[i]<=p[i]<=high[i]for i in range(3))for p in columns)
            or len({(p[0],p[2])for p in columns})!=len(columns)):
        raise JobBlocked('Dry clay needs explicit bounded columns, a floor and a natural shaft entry')
    return cfg


def stage(c,sky,cfg,state,trace):
    here=state()['pos']
    if math.hypot(here[0]-sky[0],here[2]-sky[2])<=384:
        return _travel(c,sky,state,trace,keep_cruise=True)
    route=cfg.get('route')or{};points=route.get('points')
    if (route.get('authorized')is not True or route.get('source')!='verified_native_flight'
            or route.get('world_session')!=c.world or not isinstance(points,list)or not 1<=len(points)<=16
            or any(not isinstance(p,list)or len(p)!=3
                   or any(type(v)not in(int,float)or not math.isfinite(v)for v in p)
                   or p[1]!=sky[1]for p in points)
            or math.dist(points[-1],sky)>.01
            or any(math.dist(a,b)>320 for a,b in zip(points,points[1:]))):
        raise JobBlocked('Remote dry clay needs its explicit verified bounded flight route')
    index=min(range(len(points)),key=lambda i:math.hypot(here[0]-points[i][0],here[2]-points[i][2]))
    if math.hypot(here[0]-points[index][0],here[2]-points[index][2])>320:
        raise JobBlocked('Current pose is outside the registered dry clay route')
    c.checked('navigate',target=[here[0],sky[1],here[2]],arrival=.25,air_only=True,seconds=120)
    settled_state(c,[here[0],sky[1],here[2]],.55)
    for point in points[index:]:
        q=state()
        if math.hypot(q['pos'][0]-point[0],q['pos'][2]-point[2])>320:raise JobBlocked('Actual dry clay route leg changed')
        c.anchor=list(q['pos']);c.checked('guard',pve_only=True)
        c.checked('navigate',target=point,arrival=2,seconds=180);q=settled_state(c,seconds=8)
        if math.dist(q['pos'],point)>20:raise JobBlocked('Registered dry clay vicinity was not actually reached')
        c.checked('navigate',target=point,arrival=.25,air_only=True,seconds=90);q=settled_state(c,point,.55)
        c.anchor=list(q['pos']);trace.append({'target':point,'actual':q['pos'],'request_id':c.last})


def run(c,profile,region,item,target,out,checkpoint,*,max_blocks=48):
    cfg=validate(region)
    if item not in ('minecraft:clay','minecraft:clay_ball')or type(target)is not int or not 1<=target<=2304:
        raise ValueError('Dry clay target must be an absolute carried clay/ball count')
    if type(max_blocks)is not int or not 1<=max_blocks<=128:raise ValueError('Dry clay block budget must be1..128')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'dry-clay-columns.json'
    scope={'world_session':c.world,'item':item,'target':target,'region':region}
    if path.exists():
        book=json.loads(path.read_text())
        if book.get('scope')!=scope:raise JobBlocked('Dry clay journal belongs to a different scope')
        if book.get('pending'):raise JobBlocked('Original dry clay intent unresolved; no replay')
    else:book={'scope':scope,'pending':None,'receipts':[],'complete':False}
    shared_dir=Path(c.root)/'dry-clay-source-intents';shared_dir.mkdir(parents=True,exist_ok=True)
    shared_scope={'world_session':c.world,'server':profile.get('server'),'dimension':profile.get('dimension'),
                  'min':region['min'],'max':region['max']}
    key=hashlib.sha256(json.dumps(shared_scope,sort_keys=True).encode()).hexdigest()
    shared_path=shared_dir/(key+'.json')
    for existing in shared_dir.glob('*.json'):
        if existing.is_symlink()or existing.stat().st_size>16384:raise JobBlocked('Dry clay source intent record is unsafe')
        record=json.loads(existing.read_text())
        if not isinstance(record,dict)or record.get('pending')is not None and not isinstance(record['pending'],dict):
            raise JobBlocked('Dry clay source intent record is malformed')
        old=record.get('scope')or{}
        if (record.get('schema')!=1 or not isinstance(old,dict)
                or any(not isinstance(old.get(k),list)or len(old[k])!=3
                       or any(type(v)is not int for v in old[k])for k in ('min','max'))):
            raise JobBlocked('Dry clay source intent record is malformed')
        same=all(old.get(k)==shared_scope[k]for k in ('world_session','server','dimension'))
        overlap=all(old['min'][i]<=region['max'][i]and region['min'][i]<=old['max'][i]for i in range(3))
        if record.get('pending')and same and overlap:
            raise JobBlocked('Original overlapping dry clay intent unresolved across jobs; no replay')
    def save():
        write_json(path,book)
        write_json(shared_path,{'schema':1,'scope':shared_scope,'journal':str(path),
                               'pending':book['pending'],'last_request_id':getattr(c,'last',None)})
    def state():
        checkpoint();q=c.status()
        lease=q.get('supervision_lease')or{}
        if q.get('world_session')!=c.world or q.get('manual_movement'):raise JobPaused('Dry clay world or manual control changed')
        _safe(q)
        if (q.get('connected')is not True or q.get('flight')is not True
                or lease.get('kind')!='materials'or lease.get('job_session')!=c.task
                or lease.get('world_session')!=c.world or lease.get('revision')!=q.get('control_revision')
                or q.get('dimension')!=profile.get('dimension')
                or q.get('server','').removesuffix(':25565')!=profile.get('server','').removesuffix(':25565')):
            raise JobBlocked('Dry clay requires the current healthy guarded owner/profile')
        room_for_item(q,item);return q
    def motion(kind,fn):
        before_pose=state()['pos'];last=getattr(c,'last',None)
        book['pending']={'kind':kind,'before_pose':before_pose};save()
        try:result=fn()
        except Exception as error:
            if (getattr(c,'last',None)==last and getattr(c,'native_inflight',None)is None
                    and math.dist(state()['pos'],before_pose)<=.05):
                book['pending']=None;book.setdefault('refused_before_dispatch',[]).append({'kind':kind,'reason':str(error),'last_request_id':last});save()
            raise
        finally:
            if book['pending']is not None:
                book['pending']['last_request_id']=getattr(c,'last',None)
                book['pending']['native_inflight']=getattr(c,'native_inflight',None);save()
        if getattr(c,'native_inflight',None)is not None:raise JobBlocked('Dry clay route outcome unresolved; no replay')
        book['pending']=None;save();return result
    first=state();before=carried(first,item)
    if before>=target:return {'phase':'done','before':before,'after':before,'item':item}
    if book.get('complete'):
        return {'phase':'blocked','code':'COMPLETED_RECEIPT','detail':'Completed source stock was consumed; old mining is not replayed'}
    floor=cfg['floor_y'];base_y=floor+1.2;entry=[cfg['entry'][0]+.5,base_y,cfg['entry'][2]+.5]
    sky=[entry[0],float(cfg['cruise_y']),entry[2]]
    if any(_protected(p,profile,first)for p in cfg['columns']+[cfg['entry']]):
        raise JobBlocked('Dry clay columns or entry overlap protected construction')
    save();trace=[]
    motion('source_travel',lambda:stage(c,sky,cfg,state,trace))
    def enter():
        c.checked('navigate',target=entry,arrival=.2,air_only=True,seconds=180)
        settled_state(c,entry,.45)
    motion('shaft_descent',enter)
    floors={};mined=0
    def local(pos):return _scan(c,[p-2 for p in pos],[p+2 for p in pos],state)
    def mine(pos,face,station):
        nonlocal mined
        rows=local(pos)
        if not _dry_natural(rows):raise JobBlocked('Dry clay local hazards changed before mining')
        b=next((r for r in rows if r['pos']==pos),None)
        if b is None:return
        name=block_id(b)
        if name not in ('minecraft:stone','minecraft:clay')or tuple(pos)in light_supports(rows)or _protected(pos,profile,state()):
            raise JobBlocked('Only registered ordinary stone/clay may be removed')
        output='minecraft:clay_ball'if name=='minecraft:clay'else'minecraft:cobblestone';gain=4 if name=='minecraft:clay'else 1
        q=state()
        if room_for_item(q,output)<gain:raise JobBlocked('Dry clay output has no actual backpack capacity')
        tool=_tool(q,'shovel'if name=='minecraft:clay'else'pickaxe',33,no_silk=True);_choose_tool(c,tool,state)
        q=state();hand=q.get('hand')or{}
        if (any(hand.get(k)!=tool.get(k)for k in ('item','count','durability','max_durability'))
                or hand.get('enchantments',[])!=tool.get('enchantments',[])):
            raise JobBlocked('Dry clay tool selection was not actually observed')
        initial=carried(q,output);old_drops={e.get('uuid')for e in q.get('entities',[])if e.get('type')=='minecraft:item'}
        book['pending']={'kind':'mine','pos':pos,'output':output,'before':initial,'gain':gain};save()
        try:r=c.request('mine_block',pos=pos,face=face,expected_state=b['state'],seconds=20)
        finally:book['pending']['request_id']=c.last;save()
        rid=c.last
        if (r.get('id')!=rid or r.get('phase')!='done'or r.get('world_session')!=c.world
                or r.get('server_confirmed')is not True
                or r.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
                or type(r.get('native_sequence'))is not int or r['native_sequence']<=0
                or r.get('server_ack_sequence')!=r['native_sequence']or _scan(c,pos,pos,state)):
            raise JobBlocked('Dry clay mining receipt/removal unresolved; no replay')
        drops=[e for e in r.get('entities',[])if e.get('type')=='minecraft:item'and e.get('uuid')not in old_drops
               and e.get('stack',{}).get('item')==output and e['stack'].get('count')==gain
               and isinstance(e.get('pos'),list)and len(e['pos'])==3 and math.dist(e['pos'],pos)<4]
        drop=drops[0]if len(drops)==1 else None
        book['pending'].update(server_sequence=r['native_sequence'],drop_uuid=drop.get('uuid')if drop else None);save()
        move(c,station,out/('pickup-%d'%len(book['receipts'])),max_straight=4,foot_offset=.2)
        until=time.monotonic()+15;collection_sent=False
        while True:
            q=state();held=carried(q,output)
            live=next((e for e in q.get('entities',[])if drop and e.get('uuid')==drop['uuid']),None)
            if held==initial+gain and live is None:break
            if held not in (initial,initial+gain)or time.monotonic()>=until:
                raise JobBlocked('Dry clay exact drop delta unconfirmed; no replay')
            if live is not None and not collection_sent:
                if live.get('stack')!=drop['stack']:raise JobBlocked('Original dry clay drop stack changed; no substitution')
                book['pending']['pickup_uuid']=live['uuid'];save();collection_sent=True
                # A new scoped pickup of the actually visible item, never a
                # second mining dispatch or an uncertain movement replay.
                if not collect_drop(c,live,observation=q,seconds=25):
                    raise JobBlocked('Original dry clay pickup unconfirmed; no replay')
            time.sleep(.15)
        book['receipts'].append({**book['pending'],'after':initial+gain});book['pending']=None;mined+=1;save()
    def compact():
        if item!='minecraft:clay':return
        q=state();balls=carried(q,'minecraft:clay_ball');rounds=min(balls//4,target-carried(q,item))
        if rounds<1:return
        old=carried(q,item);book['pending']={'kind':'compact','balls':balls,'clay':old,'rounds':rounds};save()
        result=manufacture(c,RecipeCatalog(profile['recipe_jar']),{item:old+rounds})
        q=state()
        if not result.get('complete')or carried(q,item)!=old+rounds or carried(q,'minecraft:clay_ball')!=balls-4*rounds:
            raise JobBlocked('Dry clay recipe conservation unconfirmed')
        book['receipts'].append({**book['pending'],'after':old+rounds});book['pending']=None;save()
    compact()
    for top in cfg['columns']:
        if carried(state(),item)>=target or mined>=max_blocks:break
        x,_,z=top;floor_pos=[x,floor,z];floor_rows=_scan(c,floor_pos,floor_pos,state)
        column_rows=_scan(c,[x,floor+1,z],top,state)
        if not any(block_id(r)=='minecraft:clay'for r in column_rows):continue
        support=next((r for r in floor_rows if r['pos']==floor_pos),None)
        if not support or not support.get('solid')or support.get('fluid')or support.get('block_entity'):continue
        floor_state=support['state'];floors[str(floor_pos)]=floor_state
        body=_scan(c,[x,floor+1,z],[x,floor+2,z],state)
        if body:
            # A new column must touch current two-cell air at the work plane.
            stand=None;current=state()['pos']
            low=[min(region['min'][0],math.floor(current[0]))-3,floor-1,
                 min(region['min'][2],math.floor(current[2]))-3]
            high=[max(region['max'][0],math.floor(current[0]))+3,floor+4,
                  max(region['max'][2],math.floor(current[2]))+3]
            air_rows=_scan(c,low,high,state)
            for side_index,(dx,dz,face) in enumerate(((1,0,'east'),(-1,0,'west'),(0,1,'south'),(0,-1,'north'))):
                point=[x+dx+.5,base_y,z+dz+.5]
                try:plan(air_rows,current,point,low,high,max_straight=4,foot_offset=.2)
                except JobBlocked:continue
                motion('side_approach',lambda:move(c,point,out/('side-%d-%d-%d'%(len(book['receipts']),len(floors),side_index)),max_straight=4,foot_offset=.2))
                stand,side=point,face;break
            if stand is None:continue
            for y in (floor+2,floor+1):
                if mined>=max_blocks:break
                mine([x,y,z],side,stand)
            if _scan(c,[x,floor+1,z],[x,floor+2,z],state):continue
        station=[x+.5,base_y,z+.5]
        motion('column_entry',lambda:move(c,station,out/('column-%d'%len(floors)),max_straight=4,foot_offset=.2))
        for y in range(floor+3,top[1]+1):
            if mined>=max_blocks or carried(state(),item)>=target:break
            pose=[x+.5,max(base_y,y-2.8),z+.5]
            motion('column_rise',lambda:move(c,pose,out/('upper-%d-%d'%(len(floors),y)),max_straight=4,foot_offset=.2))
            mine([x,y,z],'down',station)
            if item=='minecraft:clay'and carried(state(),'minecraft:clay_ball')>=64:compact()
        compact()
        actual=_scan(c,floor_pos,floor_pos,state)
        if not actual or actual[0]['state']!=floor_state:
            book['pending']={'kind':'floor_changed','pos':floor_pos,'expected_state':floor_state};save()
            raise JobBlocked('Dry clay original floor changed')
    compact()
    motion('shaft_return',lambda:move(c,entry,out/'shaft-return',max_straight=4,foot_offset=.2))
    def ascend():
        c.checked('navigate',target=sky,arrival=.25,air_only=True,seconds=180);settled_state(c,sky,.55)
    motion('shaft_ascent',ascend)
    after=carried(state(),item);result={'phase':'done'if after>=target else'waiting','code':'SOURCE_BATCH'if after>before else'WAIT_SOURCE',
        'item':item,'before':before,'after':after,'requirements':{item:target},'mined_blocks':mined,'floor_states':floors}
    book.update(complete=True,result=result);save();return result
