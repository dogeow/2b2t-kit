"""Bounded natural wall openings toward a surveyed dripstone source."""
import heapq,math,time
from collections import Counter
from pathlib import Path
from kit_runtime.journal import write_json
from material_trip_policy import room_for_item
from .acquisition import _scan,_safe,_choose_tool,carried,block_id
from .dry_hover_harvest import harvest_context,stations,visible_face,pickup,run as harvest
from .roof_harvest import retained_light,light_supports
from .local_air_path import move
from .colored_sources import _protected

STONE={'minecraft:stone','minecraft:granite','minecraft:diorite','minecraft:andesite'}
ITEM='minecraft:dripstone_block'

def plan(rows,low,high,player,*,budget=8,max_nodes=50000,protected=()):
    """Find current air or a small ordinary wall opening; leave all roots/floors."""
    if type(budget)is not int or not 0<=budget<=32:raise ValueError('Bounded access budget 0..32 required')
    cells={tuple(r['pos']):r for r in rows};lights=light_supports(rows);cache={};protected=set(protected)
    def local(p):
        return [cells[(x,y,z)]for x in range(p[0]-2,p[0]+3)for y in range(p[1]-2,p[1]+3)
                for z in range(p[2]-2,p[2]+3)if(x,y,z)in cells]
    def opening(at):
        if at in cache:return cache[at]
        if not all(low[i]<=at[i]<=high[i]for i in range(3))or at[1]>=high[1]:return None
        blocked=[cells[p]for p in (at,(at[0],at[1]+1,at[2]))if p in cells and not retained_light(cells[p])]
        for row in blocked:
            p=row['pos']
            if (block_id(row)not in STONE or tuple(p)in lights or tuple(p)in protected
                    or not all(low[i]+2<=p[i]<=high[i]-2 for i in range(3))
                    or not harvest_context(local(p),p)):
                cache[at]=None;return None
        cache[at]=blocked;return blocked
    goals={}
    for row in rows:
        p=row['pos']
        if block_id(row)!=ITEM or tuple(p)in lights or tuple(p)in protected or not all(low[i]+2<=p[i]<=high[i]-2 for i in range(3)):continue
        context=local(p)
        if not harvest_context(context,p):continue
        for point,face in stations(p):
            at=tuple(math.floor(v)for v in point);blocks=opening(at)
            if blocks is None:continue
            removed={tuple(b['pos'])for b in blocks}
            if visible_face([b for b in context if tuple(b['pos'])not in removed],point,p,face):goals[at]=p
    first=tuple(math.floor(v)for v in player)
    if opening(first)!=[]:raise RuntimeError('Current cave start is not confirmed body air')
    best={first:(0,0)};parents={first:None};queue=[(0,0,first)];end=None
    while queue and len(best)<=max_nodes:
        cost,length,at=heapq.heappop(queue)
        if best.get(at)!=(cost,length):continue
        if at in goals:end=at;break
        if length>=128:continue
        for delta in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)):
            nxt=tuple(at[i]+delta[i]for i in range(3));blocks=opening(nxt)
            if blocks is None:continue
            # Never plan to remove the current supporting floor underfoot.
            if delta==(0,-1,0)and any(tuple(b['pos'])==nxt for b in blocks):continue
            score=(cost+len(blocks),length+1)
            if score[0]>budget or score>=best.get(nxt,(math.inf,math.inf)):continue
            best[nxt]=score;parents[nxt]=at;heapq.heappush(queue,(*score,nxt))
    if end is None:return None
    path=[];at=end
    while at is not None:path.append(at);at=parents[at]
    path.reverse();first_open=None
    for i,at in enumerate(path[1:],1):
        blocks=opening(at)
        if blocks:first_open=(i,at,blocks);break
    if first_open:
        index,at,blocks=first_open;points=path[:index]
        return {'target':goals[end],'air_cells':points,'next_body':at,
                'opening':sorted(blocks,key=lambda b:-b['pos'][1]),'total_planned_blocks':best[end][0]}
    return {'target':goals[end],'air_cells':path,'next_body':None,'opening':[],'total_planned_blocks':0}

def _route(c,cells,out):
    # Keep only turns and eight-block straight legs, with fresh body proof.
    kept=[cells[0]];last=None
    for i in range(1,len(cells)):
        direction=tuple(cells[i][a]-cells[i-1][a]for a in range(3))
        if last is not None and direction!=last and kept[-1]!=cells[i-1]:kept.append(cells[i-1])
        if math.dist(kept[-1],cells[i])>=8:kept.append(cells[i])
        last=direction
    if kept[-1]!=cells[-1]:kept.append(cells[-1])
    for i,(x,y,z)in enumerate(kept):
        point=[x+.5,y+.2,z+.5]
        if math.dist(c.status()['pos'],point)>.3:move(c,point,Path(out)/str(i),max_straight=8,foot_offset=.2)

def run(c,profile,region,target,out,checkpoint,*,max_access_blocks=32,max_batches=64):
    if region.get('authorized')is not True or region.get('source')!='natural_survey':raise ValueError('Actual authorized natural survey required')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);file=out/'cave-harvest.json'
    if file.exists():raise RuntimeError('Original cave journal retained; no replay')
    def state():
        checkpoint();s=c.status();_safe(s)
        if s.get('flight')is not True:raise RuntimeError('Cave access requires actual controlled Flight')
        return s
    book={'world_session':c.world,'initial':carried(state(),ITEM),'target':target,'pending':None,'access':[],'batches':[]}
    def save():write_json(file,book)
    save();low,high=region['min'],region['max'];rows=_scan(c,low,high,state)
    book['current_full_survey_request_id']=c.last;save()
    for index in range(max_batches):
        result=harvest(c,profile,region,target,out/('harvest-%02d'%index),state,max_blocks=target,survey_rows=rows)
        removed={tuple(r['target'])for r in result['receipts']};rows=[r for r in rows if tuple(r['pos'])not in removed]
        book['batches'].append({'initial':result['initial'],'after':result['verified_count'],'mined':len(result['receipts'])});save()
        if carried(state(),ITEM)>=target:book['phase']='done';break
        if room_for_item(state(),ITEM)<1:book.update(phase='waiting',code='WAIT_CAPACITY');break
        remaining=max_access_blocks-len(book['access'])
        current_state=state();at=[math.floor(v)for v in current_state['pos']]
        if (any(not low[i]<=at[i]<=high[i]for i in range(3))or at[1]>=high[1]):
            book.update(phase='waiting',code='WAIT_SURVEY_REFRAME',current_pos=current_state['pos']);break
        columns={}
        for row in rows:
            x,y,z=row['pos']
            if(x,z)not in columns:columns[(x,z)]=_protected(row['pos'],profile,current_state)
        protected={tuple(row['pos'])for row in rows if columns[(row['pos'][0],row['pos'][2])]}
        protected.update(tuple(pos)for pos in region.get('excluded_targets',[]))
        route=plan(rows,low,high,current_state['pos'],budget=min(8,remaining),protected=protected)
        if route is None:book.update(phase='waiting',code='WAIT_CURRENT_SOURCE');break
        if (not route['opening'] and len(route['air_cells'])==1):
            book.update(phase='waiting',code='WAIT_CURRENT_FACE');break
        needed=Counter('minecraft:cobblestone'if block_id(r)=='minecraft:stone'else block_id(r)for r in route['opening'])
        if any(room_for_item(state(),item)<amount for item,amount in needed.items()):
            book.update(phase='waiting',code='WAIT_CAPACITY',access_drop_requirements=dict(needed));break
        book['planned_access']=route;save()
        _route(c,route['air_cells'],out/('air-route-%02d'%index))
        for original in route['opening']:
            pos=original['pos'];current=_scan(c,[v-2 for v in pos],[v+2 for v in pos],state)
            live=next((r for r in current if r['pos']==pos),None)
            if (live is None or live['state']!=original['state'] or not harvest_context(current,pos)
                    or _protected(pos,profile,state())or tuple(pos)in light_supports(current)):
                raise RuntimeError('Natural wall or protections changed; no mining sent')
            faces=[face for face in ('up','down','north','south','east','west')if visible_face(current,state()['pos'],pos,face)]
            if not faces:raise RuntimeError('Current wall face is occluded; no mining sent')
            tool=max((r for r in state()['inventory']if r.get('slot',99)<36 and r.get('count')==1
                      and r.get('item')in('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')and r.get('durability',0)>=33
                      and not any(e.get('id')=='minecraft:silk_touch'for e in r.get('enchantments',[]))),
                     key=lambda r:(max((e['level']for e in r.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),r['durability']))
            drop='minecraft:cobblestone'if block_id(live)=='minecraft:stone'else block_id(live)
            if room_for_item(state(),drop)<1:raise RuntimeError('Natural wall byproduct has no backpack space')
            _choose_tool(c,tool,state);before=carried(state(),drop)
            old_drops={e['uuid']for e in state().get('entities',[])if e.get('type')=='minecraft:item'}
            book['pending']={'pos':pos,'item':drop,'before':before,'state':live['state'],'face':faces[0]};save()
            try:c.checked('mine_block',pos=pos,face=faces[0],expected_state=live['state'],seconds=20)
            finally:book['pending']['request_id']=c.last;save()
            until=time.monotonic()+5
            while carried(state(),drop)==before and time.monotonic()<until:time.sleep(.15)
            if carried(state(),drop)==before:
                drops=[e for e in state().get('entities',[])if e.get('type')=='minecraft:item'
                       and e.get('uuid')not in old_drops and e.get('stack',{}).get('item')==drop
                       and e['stack'].get('count')==1 and math.dist(e['pos'],pos)<6]
                if len(drops)==1:
                    book['pending']['drop_uuid']=drops[0]['uuid'];save()
                    pickup(c,drops[0],before,out/('access-pickup-%02d'%len(book['access'])),state,item=drop)
            if _scan(c,pos,pos,state)or carried(state(),drop)!=before+1:raise RuntimeError('Wall removal or exact original-drop gain unconfirmed; no replay')
            book['access'].append({**book['pending'],'actual_gain':1});book['pending']=None;save()
            rows=[r for r in rows if r['pos']!=pos]
            print('ACTUAL_CAVE_ACCESS_BLOCK',pos,len(book['access']),flush=True)
        if route['next_body']is not None:
            x,y,z=route['next_body'];move(c,[x+.5,y+.2,z+.5],out/('new-air-%02d'%index),max_straight=8,foot_offset=.2)
    book.setdefault('phase','waiting');book['verified_count']=carried(state(),ITEM);save();return book
