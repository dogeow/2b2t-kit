"""Native material-task adapter for registered renewable joined dripstone."""
import math,json
from pathlib import Path

from kit_runtime.journal import write_json
from .acquisition import _safe,_scan,_travel,carried
from .dripstone_growth import exit_farm,growth_column,harvest
from .dry_hover_harvest import pickup
from .joined_dripstone import column,run as joined_harvest
from .navigation import settled_state
from .protocol import JobBlocked,server_key

ITEM='minecraft:pointed_dripstone'
OUTPUTS=frozenset((ITEM,))
TARGET_SCOPE='absolute_backpack'
MAX_TARGET_COUNT=128


def farm(profile,state):
    site=profile.get('renewable_pointed_dripstone')
    if (not isinstance(site,dict)or site.get('owned')is not True
            or server_key(site.get('server'))!=server_key(state.get('server'))
            or site.get('dimension')!=state.get('dimension')):
        raise JobBlocked('An owned current-world renewable dripstone farm is required')
    bounds=site.get('air_bounds')or{};lo,hi=bounds.get('min'),bounds.get('max')
    if (not isinstance(lo,list)or not isinstance(hi,list)or len(lo)!=3 or len(hi)!=3
            or any(type(v)is not int for v in lo+hi)or any(a>b for a,b in zip(lo,hi))
            or not -64<=lo[1]<=hi[1]<=319 or math.prod(b-a+1 for a,b in zip(lo,hi))>30000):
        raise JobBlocked('Farm air volume is invalid or too large')
    minimum=site.get('minimum_y');entries=site.get('joined_columns')
    if (type(minimum)is not int or not lo[1]<=minimum<hi[1]or not isinstance(entries,list)
            or not 1<=len(entries)<=8):raise JobBlocked('Bounded joined farm columns required')
    seen=set()
    for entry in entries:
        if not isinstance(entry,dict):raise JobBlocked('Farm joined column must be an object')
        root=entry.get('root');stand=entry.get('stand_column')
        if (not isinstance(root,list)or len(root)!=3 or any(type(v)is not int for v in root)
                or not all(lo[i]<=root[i]<=hi[i]for i in range(3))or root[1]+2>hi[1]
                or not 1<=root[1]-minimum<=16 or tuple(root)in seen
                or not isinstance(stand,list)or len(stand)!=2 or any(type(v)is not int for v in stand)
                or abs(root[0]-stand[0])+abs(root[2]-stand[1])!=1
                or not(lo[0]<=stand[0]<=hi[0]and lo[2]<=stand[1]<=hi[2])):
            raise JobBlocked('Farm root or adjacent standing column is invalid')
        seen.add(tuple(root))
    for key in ('approach','exit'):
        p=site.get(key)
        if (not isinstance(p,list)or len(p)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in p)
                or not all(lo[i]+.31<=p[i]<=hi[i]+.69 for i in (0,2))
                or not lo[1]<=p[1]<=hi[1]-1.8):raise JobBlocked('Farm approach or exit is outside its proved volume')
    roots=site.get('growth_roots',[])
    if (not isinstance(roots,list)or len(roots)>128 or any(not isinstance(p,list)or len(p)!=3
            or any(type(v)is not int for v in p)or not all(lo[i]<=p[i]<=hi[i]for i in range(3))
            or not 1<=p[1]-minimum<=16 or p[1]+2>hi[1]for p in roots)
            or len({tuple(p)for p in roots})!=len(roots)):
        raise JobBlocked('Farm growth roots are invalid')
    return site


def _run(c,profile,item,target_count,out,checkpoint):
    backend=getattr(c,'pointed_backend',None)or getattr(c,'material_backend',None)
    request=getattr(backend,'request',{})
    if (item!=ITEM or type(target_count)is not int or not 1<=target_count<=MAX_TARGET_COUNT
            or backend is None or getattr(backend,'client',None)is not c or getattr(backend,'profile',None)!=profile
            or request.get('mode')!='item' or request.get('targets',{}).get(item)!=target_count
            or request.get('context',{}).get('world_session')!=c.world):
        raise JobBlocked('Pointed dripstone requires the sole current item-task backend/client')
    initial=c.status();site=farm(profile,initial);key=initial['projection_selection']['key']
    def state():
        checkpoint();q=c.status();_safe(q)
        if q['world_session']!=c.world or q['projection_selection']['key']!=key:
            raise JobBlocked('Renewable dripstone world or projection changed')
        return q
    out=Path(out);out.mkdir(parents=True,exist_ok=True);file=out/'renewable-pointed-pipeline.json'
    if file.exists():raise JobBlocked('Original renewable pipeline retained; no replay')
    book={'world_session':c.world,'target':target_count,'target_scope':TARGET_SCOPE,'columns':[],'pending':None}
    write_json(file,book)
    if carried(state(),ITEM)>=target_count:
        book.update(actual_held=carried(state(),ITEM),phase='done',code='done',requirements={},ai_calls=0)
        write_json(file,book);return book
    if carried(state(),ITEM)<target_count:
        p=state()['pos'];lo,hi=site['air_bounds']['min'],site['air_bounds']['max']
        inside=(all(lo[i]+.31<=p[i]<=hi[i]+.69 for i in(0,2))and lo[1]<=p[1]and p[1]+1.8<=hi[1]+1)
        if not inside:_travel(c,site['approach'],state,[],keep_cruise=True)
        for index in range(4):
            q=state()
            if carried(q,ITEM)>=target_count:break
            drops=[e for e in q.get('entities',[])if e.get('stack',{}).get('item')==ITEM
                   and type(e['stack'].get('count'))is int and 1<=e['stack']['count']<=64
                   and all(lo[i]<=e['pos'][i]<=hi[i]+1 for i in range(3))]
            if not drops:break
            drop=min(drops,key=lambda e:math.dist(e['pos'],q['pos']));have=carried(q,ITEM)
            book['pending']={'kind':'existing_drop','uuid':drop['uuid'],'before':have,'count':drop['stack']['count']};write_json(file,book)
            if not pickup(c,drop,have,out/('existing-drop-%02d'%index),state,item=ITEM,
                          expected_count=drop['stack']['count'],air_bounds=site['air_bounds'],allow_cone_edges=True):
                raise JobBlocked('Current observed farm drop pickup unconfirmed')
            book.setdefault('existing_drop_receipts',[]).append(dict(book['pending']));book['pending']=None;write_json(file,book)
        for index,entry in enumerate(site['joined_columns']):
            if carried(state(),ITEM)>=target_count:break
            root=entry['root'];x,y,z=root
            rows=_scan(c,[x,site['minimum_y'],z],[x,y+2,z],state)
            try:observed=column(rows,root,site['minimum_y'])
            except JobBlocked as error:
                book['columns'].append({'root':root,'deferred':str(error),'mining_sent':False});write_json(file,book);continue
            sub=out/('joined-%02d'%index);book['pending']={'root':root,'journal':str(sub/'joined-harvest.json')};write_json(file,book)
            result=joined_harvest(c,root,site['minimum_y'],entry['stand_column'],site['air_bounds'],sub,state)
            book['columns'].append({'root':root,'mined':len(result['mining_receipts']),
                'actual_backpack_gain':result['actual_backpack_gain'],'journal':str(sub/'joined-harvest.json')})
            book['pending']=None;write_json(file,book)
        if carried(state(),ITEM)<target_count and site.get('growth_roots'):
            quarantine=set()
            for old_file in (Path(c.root)/'dripstone-growth-intents').glob('*.json'):
                if old_file.is_symlink()or old_file.stat().st_size>16384:raise JobBlocked('Unsafe growth intent')
                old=json.loads(old_file.read_text());scope=old.get('scope')or{};p=scope.get('root')
                if (old.get('pending')and server_key(scope.get('server'))==server_key(initial['server'])
                        and scope.get('dimension')==initial['dimension']and isinstance(p,list)):
                    quarantine.add((p[0],p[2]))
            rows=_scan(c,[lo[0],site['minimum_y'],lo[2]],[hi[0],max(p[1]for p in site['growth_roots'])+2,hi[2]],state)
            ready=[];grown=0
            for root in site['growth_roots']:
                if (root[0],root[2])in quarantine:continue
                try:observed=growth_column(rows,root,site['minimum_y'])
                except JobBlocked:continue
                amount=len(observed['chain'])-1
                if amount:ready.append(root);grown+=amount
            if ready:
                budget=min(grown,target_count-carried(state(),ITEM),128)
                book['pending']={'kind':'downward_growth','journal':str(out/'downward/growth-harvest.json')};write_json(file,book)
                result=harvest(c,ready,site['minimum_y'],out/'downward',state,max_segments=budget,air_bounds=site['air_bounds'])
                book['downward_actual_gain']=result['actual_gained'];book['pending']=None;write_json(file,book)
    # The native manager owns finish/heartbeat. Return it an already safe
    # current-world parking anchor rather than starting another controller.
    exit_farm(c,site['exit'],out/'verified-farm-exit',bounds=site['air_bounds'])
    q=settled_state(c);point=[q['pos'][0],q['pos'][1]+1,q['pos'][2]]
    c.checked('material_job_park',park_target=point);c.park_target=point
    held=carried(state(),ITEM);done=held>=target_count
    book.update(actual_held=held,phase='done'if done else'waiting',code='done'if done else'WAIT_GROWTH',
                detail='Actual renewable pointed dripstone in backpack'if done else'Joined growth not ready or target not yet met',
                requirements={}if done else{ITEM:target_count-held},ai_calls=0)
    write_json(file,book);return book


def run(c,profile,item,target_count,out,checkpoint):
    file=Path(out)/'renewable-pointed-pipeline.json';preexisting=file.exists()
    try:return _run(c,profile,item,target_count,out,checkpoint)
    except Exception:
        # Preserve failures and unknown mutations. For a known planning/drop
        # refusal, hand the manager a safe parking anchor before it finishes.
        if (not preexisting and file.exists() and getattr(c,'native_inflight',None)is None
                and getattr(c,'unconfirmed_native_request',None)is None):
            try:
                book=json.loads(file.read_text())if file.exists()else{}
                pending=book.get('pending')or{};unknown_mine=False
                child=pending.get('journal')
                if child and Path(child).is_file():
                    sub=json.loads(Path(child).read_text());action=sub.get('pending')or{}
                    unknown_mine=(action.get('kind')=='mine'or
                                  bool(action.get('pos'))and not action.get('drop_uuid')and 'kind'not in action)
                if not unknown_mine:
                    q=c.status();_safe(q);site=farm(profile,q)
                    exit_farm(c,site['exit'],Path(out)/'deferred-verified-exit',bounds=site['air_bounds'])
                    q=settled_state(c);point=[q['pos'][0],q['pos'][1]+1,q['pos'][2]]
                    c.checked('material_job_park',park_target=point);c.park_target=point
            except Exception:pass
        raise
