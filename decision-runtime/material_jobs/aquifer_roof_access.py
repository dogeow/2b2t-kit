"""Finite dry access above a real dark-water pocket; never excavate liquids."""
from collections import deque
from pathlib import Path
import heapq,math,time
from functools import lru_cache
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from .colored_sources import _protected
from .roof_harvest import light_supports
from .acquisition import _choose_tool

NATURAL={'minecraft:'+n for n in('stone','granite','diorite','andesite','deepslate','tuff','calcite','dripstone_block')}
DROPS={name:('minecraft:cobblestone'if name=='minecraft:stone'else'minecraft:cobbled_deepslate'if name=='minecraft:deepslate'else name)for name in NATURAL}
FALLING={'minecraft:'+n for n in('sand','red_sand','gravel','pointed_dripstone','anvil','chipped_anvil','damaged_anvil')}
HOT={'minecraft:'+n for n in('lava','fire','soul_fire','magma_block','cactus','sweet_berry_bush','wither_rose','powder_snow','cobweb','nether_portal')}
DIRECTIONS=((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))
def bid(row):return row.get('state','').split('}')[0].removeprefix('Block{')
def water(row):return bid(row)=='minecraft:water'and row.get('state','').endswith('[level=0]')and row.get('fluid')is True

def safe_mine_cell(by,pos,protected=lambda p:False):
    row=by.get(tuple(pos))
    if not row or bid(row)not in NATURAL or row.get('fluid')or row.get('block_entity')or protected(pos):return False
    for dx,dy,dz in DIRECTIONS:
        neighbour=by.get((pos[0]+dx,pos[1]+dy,pos[2]+dz),{})
        # Water below the ceiling remains in place. No side/upper liquid is
        # opened into the dry tunnel, and lava below is never admitted.
        if neighbour.get('fluid')and not((dx,dy,dz)==(0,-1,0)and water(neighbour)):return False
        if bid(neighbour)in FALLING or bid(neighbour)in HOT:return False
    return True


def plan(scan,low,high,start,pool_seed,*,protected=lambda p:False,max_mines=64,target_radius=8):
    expected=math.prod(high[i]-low[i]+1 for i in range(3))
    if(scan.get('phase')!='done'or scan.get('scan_cells_read')!=expected
       or scan.get('scan_total_cells')!=expected or not isinstance(scan.get('blocks'),list)):
        raise ValueError('Complete current server scan required')
    by={tuple(r['pos']):r for r in scan['blocks']}
    if len(by)!=len(scan['blocks'])or any(not all(low[i]<=p[i]<=high[i]for i in range(3))for p in by):raise ValueError('Ambiguous scan cells')
    if any(bid(r)in('minecraft:sculk_shrieker','minecraft:sculk_sensor','minecraft:calibrated_sculk_sensor')for r in by.values()):raise ValueError('Sculk habitat preserved')
    waters={p for p,r in by.items()if water(r)};seed=tuple(pool_seed)
    if seed not in waters:raise ValueError('Actual source water at the observed squid pocket required')
    pool={seed};queue=deque([seed])
    while queue:
        p=queue.popleft()
        for d in DIRECTIONS:
            q=tuple(p[i]+d[i]for i in range(3))
            if q in waters and q not in pool:pool.add(q);queue.append(q)
    lights=light_supports(scan['blocks'])
    def can_mine(p):return p not in lights and safe_mine_cell(by,p,protected)
    @lru_cache(maxsize=None)
    def body_cost(p):
        x,y,z=p
        if not(low[0]<x<high[0]and low[1]<y<=high[1]-2 and low[2]<z<high[2]):return None
        for xx in range(x-1,x+2):
            for yy in range(y-1,y+3):
                for zz in range(z-1,z+2):
                    row=by.get((xx,yy,zz),{});name=bid(row)
                    if name in HOT or name in('minecraft:campfire','minecraft:soul_campfire')and'lit=true'in row.get('state',''):return None
        cells=((x,y,z),(x,y+1,z));cost=0
        for cell in cells:
            if cell in by:
                if not can_mine(cell):return None
                cost+=1
        return cost
    # A connected underground water network can also reach the old open bay.
    # That bay is not access to the observed upper pocket. Keep the actual
    # target's height and neighbourhood instead of reporting the easy shore.
    target_water={p for p in pool if p[1]>=seed[1] and math.dist(p,seed)<=target_radius}
    goals={(x,y+1,z)for x,y,z in target_water if(x,y+1,z)not in waters and body_cost((x,y+1,z))is not None}
    first=tuple(math.floor(v)for v in start)
    if body_cost(first)!=0:raise ValueError('Current dry two-cell air start required')
    distances={first:(0,0)};previous={first:None};front=[(0,0,first)];finish=None
    while front:
        mines,length,p=heapq.heappop(front)
        if distances.get(p)!=(mines,length):continue
        if p in goals:finish=p;break
        if length>=96:continue
        for d in DIRECTIONS:
            q=tuple(p[i]+d[i]for i in range(3));cost=body_cost(q)
            if cost is None or mines+cost>max_mines:continue
            # Never dig the floor beneath the current standing column.
            if d==(0,-1,0)and q in by:continue
            candidate=(mines+cost,length+1)
            if candidate<distances.get(q,(max_mines+1,999)):
                distances[q]=candidate;previous[q]=p;heapq.heappush(front,(*candidate,q))
    if finish is None:raise ValueError('No finite dry access within the ordinary-block budget')
    path=[];p=finish
    while p is not None:path.append(p);p=previous[p]
    path.reverse();targets={p for x,y,z in path for p in((x,y,z),(x,y+1,z))if p in by}
    if len(targets)>max_mines:raise ValueError('Actual unique mining budget exceeded')
    return {'world_session':scan['world_session'],'scan_time':scan['time'],'low':low,'high':high,'start':start,'pool_seed':pool_seed,'target_radius':target_radius,'target_source_water_cells':len(target_water),'actual_connected_source_water_cells':len(pool),'body_path':path,'goal':[finish[0]+.5,finish[1]+.1,finish[2]+.5],'new_targets':[by[p]for p in sorted(targets)],'maximum_new_mines':max_mines,'actual_planned_mines':len(targets),'liquids_removed':False,'protected_cells_removed':False}


def authorized_targets(plan, world):
    """Bind a human exception to exact cells, not an enclosing protected box."""
    rows=plan.get('new_targets',[]);path=plan.get('body_path',[])
    if (plan.get('world_session')!=world or plan.get('execution_authorized')is not True
            or plan.get('authorization_scope')!='only_the_exact_17_new_targets_in_this_plan'
            or not plan.get('user_authorization') or plan.get('maximum_new_mines')!=17
            or plan.get('actual_planned_mines')!=17 or len(rows)!=17):
        raise ValueError('Explicit current-world exact17 authorization required')
    targets={tuple(r['pos']):r for r in rows}
    if len(targets)!=17 or any(bid(r)not in NATURAL or r.get('fluid')or r.get('block_entity')for r in rows):
        raise ValueError('Distinct ordinary authorized cells required')
    if (not path or any(len(p)!=3 or any(type(v)is not int for v in p)for p in path)
            or any(sum(abs(a[i]-b[i])for i in range(3))!=1 for a,b in zip(path,path[1:]))):
        raise ValueError('Adjacent body path required')
    body={p for x,y,z in path for p in((x,y,z),(x,y+1,z))}
    if not set(targets)<=body:raise ValueError('Authorized targets must belong to the body path')
    return targets


def run(c, approved, out, checkpoint):
    """Execute one fresh exact-cell exception, retaining every native receipt."""
    from collections import Counter
    from .acquisition import _scan
    from .dry_hover_harvest import visible_face
    from .navigation import _air_move, _body_sweep
    targets=authorized_targets(approved,c.world)
    out=Path(out);out.mkdir(parents=True,exist_ok=False);journal=out/'opening.json'
    initial=checkpoint();path=approved['body_path']
    if [math.floor(v)for v in initial['pos']]!=path[0]:raise RuntimeError('Actual approved start changed')
    book={'world_session':c.world,'authorization':approved,'pending':None,'mines':[],
          'moves':[],'inventory_before':dict(inventory_counts(initial)),
          'protected_configuration_changed':False,'complete':False}
    write_json(journal,book);removed=set();expected=Counter()
    def state():
        q=checkpoint()
        if (q.get('world_session')!=c.world or q.get('health')!=20 or q.get('guard_busy')
                or q.get('under_water')or q.get('air_supply')!=300 or not q.get('flight')):
            raise RuntimeError('Healthy owned dry Flight pose required')
        return q
    def move(point,label):
        q=state();rows=_scan(c,*_body_sweep(q['pos'],point),state)
        if rows:raise RuntimeError('Actual body clearance changed; no move sent')
        book['pending']={'kind':'dry_air_move','target':point};write_json(journal,book)
        try:_air_move(c,point,20,arrival=.08)
        finally:
            book['pending']['request_id']=c.last;write_json(journal,book)
        q=state();book['moves'].append({'target':point,'actual':q['pos'],'request_id':c.last})
        book['pending']=None;write_json(journal,book)
    first=path[0];point=[first[0]+.5,first[1]+.1,first[2]+.5]
    if math.dist(state()['pos'],point)>.08:move(point,'start')
    for index,cell in enumerate(path[1:],1):
        q=state();previous=path[index-1]
        if math.dist(q['pos'],[previous[0]+.5,previous[1]+.1,previous[2]+.5])>.2:
            raise RuntimeError('Actual preceding body pose changed')
        for p in((cell[0],cell[1]+1,cell[2]),tuple(cell)):
            rows=_scan(c,[v-1 for v in p],[v+1 for v in p],state)
            by={tuple(r['pos']):r for r in rows};live=by.get(p)
            if p in removed:
                if live is not None:raise RuntimeError('Previously removed cell changed; no replay')
                continue
            if p not in targets:
                if live is not None:raise RuntimeError('Unapproved body blocker; no additional mine')
                continue
            row=targets[p];q=state();support=(math.floor(q['pos'][0]),math.floor(q['pos'][1])-1,math.floor(q['pos'][2]))
            if (not live or live['state']!=row['state']or p==support
                    or p in light_supports(rows)or not safe_mine_cell(by,p,lambda p:tuple(p)not in targets)):
                raise RuntimeError('Exact target, water, falling block or light support changed')
            item=DROPS[bid(live)]
            if len(removed)>=17 or room_for_item(q,item)<1:raise RuntimeError('Exact budget or retained drop capacity exhausted')
            tools=[t for t in q['inventory']if 0<=t.get('slot',99)<36 and t.get('count')==1
                   and t.get('item')in('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')
                   and t.get('durability',0)>=96 and not any(e['id']=='minecraft:silk_touch'for e in t.get('enchantments',[]))]
            if not tools:raise RuntimeError('Actual non-Silk pickaxe reserve required')
            tool=max(tools,key=lambda t:(max((e['level']for e in t.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),t['durability']))
            _choose_tool(c,tool,state);q=state()
            faces=[f for f in('down','up','south','north','west','east')if visible_face(rows,q['pos'],list(p),f)]
            if not faces:raise RuntimeError('Authorized target has no actual visible face')
            below_water=water(by.get((p[0],p[1]-1,p[2]),{}))
            if below_water and q.get('dry_roof_mining_protocol',0)<1:
                raise RuntimeError('This host needs dry_roof_mining_protocol1 before the water-below cell; no mine dispatched')
            book['pending']={'kind':'exact_authorized_mine','pos':list(p),'expected_state':row['state'],'item':item};write_json(journal,book)
            try:r=c.request('mine_block',pos=list(p),face=faces[0],expected_state=row['state'],seconds=15,
                            **({'dry_roof_water_below':True}if below_water else{}))
            finally:
                book['pending']['request_id']=c.last;write_json(journal,book)
            write_json(out/('mine-%02d-native.json'%len(removed)),r)
            if (r.get('id')!=c.last or r.get('world_session')!=c.world or r.get('phase')!='done'
                    or r.get('server_confirmed')is not True or r.get('mining_target')!=list(p)
                    or r.get('server_observed_state')!='Block{minecraft:air}'):
                raise RuntimeError('Exact ordinary removal not confirmed; never replay')
            removed.add(p);expected[item]+=1;book['mines'].append({**book['pending'],'server_confirmed':True})
            book['pending']=None;write_json(journal,book)
        point=[cell[0]+.5,cell[1]+.1,cell[2]+.5];move(point,'step-%02d'%index)
        until=time.monotonic()+5
        while any(inventory_counts(state())[item]<book['inventory_before'].get(item,0)+n for item,n in expected.items()):
            if time.monotonic()>until:raise RuntimeError('Mined byproducts not yet retained; no further excavation')
            time.sleep(.15)
        c.set_progress(phase='限定通道 · 已开%d／17格'%len(removed))
        write_json(journal,book)
    q=state()
    if removed!=set(targets):raise RuntimeError('Not all and only the17 authorized cells were opened')
    floor=[path[-1][0],path[-1][1]-1,path[-1][2]]
    water_rows=_scan(c,floor,floor,state)
    if len(water_rows)!=1 or not water(water_rows[0]):raise RuntimeError('Original source water not confirmed below final dry pose')
    book.update(complete=True,actual=q['pos'],new_mines=len(removed),all_byproducts_retained=True,
                inventory_after=dict(inventory_counts(q)),water_retained=water_rows[0])
    write_json(journal,book);return book
