"""Journaled temporary dirt caps for axis-y wood on a dry floating map plate.

Every cap starts as observed AIR. Only confirmed owned dirt is recovered. All
wood placement and stripping remain normal Kit projection_wood operations.
"""
import json,math,time
from collections import deque
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import finish_beams,_scoped_audit
from work_access import approach_faces
from material_cleanup import register,complete
from owned_air_escape import wait_known_idle,blocks_segment
from lighting_cli import swept_entities
from material_jobs.acquisition import _travel

DIRT='Block{minecraft:dirt}'
RAW='minecraft:cherry_wood'
EXPECTED='Block{minecraft:stripped_cherry_wood}[axis=y]'
FACE={(1,0):'east',(-1,0):'west',(0,1):'south',(0,-1):'north'}


def body_overlaps_cell(feet,cell):
    return all(hi>p and lo<p+1 for lo,hi,p in zip(
        [feet[0]-.35,feet[1],feet[2]-.35],
        [feet[0]+.35,feet[1]+1.81,feet[2]+.35],cell))


def plan_caps(target,observed,matched,low,high,max_caps=4):
    """A short AIR cap bridge rooted above an actual matched noninteractive cube."""
    if type(max_caps)is not int or not 2<=max_caps<=8:
        raise ValueError('A cap bridge is bounded to2..8 actual AIR cells')
    pos=tuple(target);by={tuple(r['pos']):r for r in observed}
    def air(p):return p not in by
    def valid(p):
        row=by.get(p)
        return (low[0]<=p[0]<=high[0]and low[2]<=p[2]<=high[2]
                and air((p[0],p[1]+1,p[2]))
                and (row is None or row.get('fluid')is False and row.get('block_entity')is False))
    if not air(pos)or not valid(pos):return None
    queue=deque([(pos,[pos])]);seen={pos}
    while queue:
        node,path=queue.popleft()
        row=by.get(node)
        if (node in matched and row and row.get('solid')is True
                and row.get('fluid')is False and row.get('block_entity')is False):
            bottom_path=list(reversed(path));caps=[[p[0],p[1]+1,p[2]]for p in bottom_path]
            return {'target':list(pos),'base':list(node),'base_state':row['state'],'caps':caps}
        if len(path)>=max_caps:continue
        for dx,dz in FACE:
            q=(node[0]+dx,node[1],node[2]+dz)
            if q not in seen and valid(q):seen.add(q);queue.append((q,path+[q]))
    return None


def run_one(c,target,out,checkpoint,*,max_caps=4,resume_confirmed=None,consumable_dirt=False):
    if type(consumable_dirt)is not bool:raise ValueError('Dirt consumption mode must be explicit boolean')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    before=checkpoint();key=before['projection_selection']['key'];world=c.world
    low=before['projection_selection']['min'];high=before['projection_selection']['max']
    book={'schema':1,'world_session':world,'task_session':c.task,'placement_key':key,
          'target':list(target),'pending':None,'owned_caps':[],'complete':False,
          'consumable_dirt':consumable_dirt}
    def save():write_json(out/'progress.json',book)
    save()
    def state():
        s=checkpoint()
        if (s['world_session']!=world or s['projection_selection']['key']!=key
                or s['health']!=20 or s['food']<18 or s['manual_movement']or s['screen']
                or not s['guard_armed']or not s['guard_pve_only']):
            raise RuntimeError('Cap construction scope or survival changed')
        return s
    def scan(lo,hi):
        state();r=c.checked('scan',min=lo,max=hi,details=True,seconds=30);wait_known_idle(c)
        if (r['scan_cells_read']!=r['scan_total_cells'] or r['scan_total_cells']!=math.prod(hi[i]-lo[i]+1 for i in range(3))
                or r['scan_start_revision']!=r['scan_end_revision']or r['world_session']!=world):
            raise RuntimeError('Incomplete current cap volume')
        return r
    def at(pos):
        r=scan(pos,pos);return next((v['state']for v in r['blocks']if v['pos']==pos),'AIR')
    def settled(pos,expected,item,total):
        frames=[];deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            actual=at(pos);s=state()
            if actual==expected and inventory_counts(s).get(item,0)==total:
                if not frames or s['time']>frames[-1]['time']:frames.append(s)
                if len(frames)>=2 and frames[-1]['time']-frames[0]['time']>=400:return frames
            else:frames=[]
            time.sleep(.1)
        raise RuntimeError('Cap state/stock conservation unproved; preserve original action')
    audit=c.request('projection_audit')['projection_audit'];_scoped_audit(state(),audit,key,world,before['server'],before['dimension'])
    row=next((r for r in audit['mismatches']if r['pos']==list(target)),None)
    if not row or row['expected']!=EXPECTED or row['actual']!='Block{minecraft:air}'or row['fluid']or row['adjacent_fluid']or not row['neighbors_loaded']:
        raise RuntimeError('Exact missing dry axis-y cherry wood required')
    mismatch={tuple(r['pos'])for r in audit['mismatches']}
    lo=[max(low[0],target[0]-max_caps),target[1],max(low[2],target[2]-max_caps)]
    hi=[min(high[0],target[0]+max_caps),target[1]+2,min(high[2],target[2]+max_caps)]
    volume=scan(lo,hi);write_json(out/'current-cap-volume.json',volume)
    matched={tuple(r['pos'])for r in volume['blocks']if r['pos'][1]==target[1]and tuple(r['pos'])not in mismatch}
    resumed=None
    if resume_confirmed is not None:
        resumed=json.loads(Path(resume_confirmed).read_text())
        if (resumed.get('pending')is not None or resumed.get('world_session')!=world
                or resumed.get('task_session')!=c.task or resumed.get('placement_key')!=key
                or resumed.get('target')!=list(target)or resumed.get('complete')is not False):
            raise RuntimeError('Only exact confirmed same-task caps without pending work may resume')
        plan=resumed['plan'];owned=resumed['owned_caps']
        caps=plan.get('caps',[]);base=plan.get('base',[])
        geometry=(plan.get('target')==list(target)and len(base)==3
            and tuple(base)in matched and 2<=len(caps)<=max_caps
            and caps[0]==[base[0],base[1]+1,base[2]]and caps[-1]==[target[0],target[1]+1,target[2]]
            and all(isinstance(p,list)and len(p)==3 and all(type(v)is int for v in p)
                    and p[1]==target[1]+1 and low[0]<=p[0]<=high[0]and low[2]<=p[2]<=high[2]for p in caps)
            and all(abs(a[0]-b[0])+abs(a[2]-b[2])==1 for a,b in zip(caps,caps[1:])))
        if (not geometry or not owned or owned!=caps[:len(owned)]
                or at(plan['base'])!=plan['base_state']
                or any(at(pos)!=DIRT for pos in owned)
                or any(at(pos)!='AIR'for pos in plan['caps'][len(owned):])):
            raise RuntimeError('Confirmed cap prefix or remaining AIR geometry changed')
        book['owned_caps']=owned[:];book['resumed_confirmed_receipt']=str(Path(resume_confirmed).resolve())
    else:plan=plan_caps(target,volume['blocks'],matched,low,high,max_caps)
    if not plan:raise RuntimeError('No bounded cap bridge above actual matched blocks')
    wood_before=inventory_counts(state()).get(RAW,0);dirt_before=inventory_counts(state()).get('minecraft:dirt',0)
    if resumed is not None:
        if wood_before!=resumed['wood_before']or dirt_before!=resumed['dirt_before']-len(book['owned_caps']):
            raise RuntimeError('Confirmed cap resume stock differs; no mutation')
        dirt_before=resumed['dirt_before']
    if wood_before<1 or dirt_before<len(plan['caps'])+1:raise RuntimeError('Actual raw wood/dirt capacity unavailable')
    book.update(plan=plan,wood_before=wood_before,dirt_before=dirt_before);save()
    cleanup_key='wood-caps:'+str(out.resolve())
    def cleanup():
        if book['pending']:raise RuntimeError('Unknown cap action retained; cleanup must not replay')
        cap_positions=plan['caps']
        for pos in reversed(book['owned_caps'][:]):
            if at(pos)!=DIRT:raise RuntimeError('Owned cap changed; no other block is removed')
            tool=next((r for r in state()['inventory']if r['item']in ('minecraft:diamond_shovel','minecraft:netherite_shovel')and r['count']==1 and r.get('durability',0)>=2),None)
            if tool is None:raise RuntimeError('Actual durable shovel required')
            face=approach_faces(c,pos,DIRT,('up','north','south','east','west'),seconds=30,stand_distance=2.4)
            c.checked('select_item',item=tool['item'],slot=tool['slot'])
            book['pending']={'op':'mine_owned_cap','pos':pos};save()
            r=c.request('mine_block',pos=pos,face=face,expected_state=DIRT,seconds=30)
            if r.get('phase')!='done':raise RuntimeError('Cap mining not confirmed; no second mine')
            if at(pos)!='AIR':raise RuntimeError('Mined cap AIR not confirmed; no repeat')
            book['owned_caps'].remove(pos);book['pending']=None;save()
        if consumable_dirt:
            # Ordinary temporary soil may be spent. Preserve the actual
            # unresolved pickup balance; never label it restored or count it
            # as carried stock. Every support must still be physically AIR.
            after=inventory_counts(state()).get('minecraft:dirt',0)
            if after<dirt_before-len(plan['caps']):
                raise RuntimeError('Dirt consumption exceeds confirmed placed caps')
            book.update(dirt_after=after,unrecovered_dirt_at_finish=max(0,dirt_before-after),
                        additional_dirt_received=max(0,after-dirt_before))
            save();return
        for attempt in range(12):
            q=state();held=inventory_counts(q).get('minecraft:dirt',0)
            if held==dirt_before:return
            if held>dirt_before:raise RuntimeError('Dirt total changed outside owned cleanup')
            drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'
                and e.get('stack',{}).get('item')=='minecraft:dirt'
                and 0<e['stack'].get('count',0)<=dirt_before-held
                and min(math.dist(e['pos'],[v+.5 for v in p])for p in cap_positions)<=10]
            if not drops:raise RuntimeError('Owned caps are AIR but dirt balance is unconfirmed; retain it')
            drop=min(drops,key=lambda e:math.dist(e['pos'],q['pos']))
            point=[math.floor(drop['pos'][0])+.5,drop['pos'][1]+.3,math.floor(drop['pos'][2])+.5]
            lo=[math.floor(drop['pos'][0])-1,min(60,math.floor(drop['pos'][1])-1),math.floor(drop['pos'][2])-1]
            hi=[lo[0]+2,max(68,math.ceil(drop['pos'][1]+3)),lo[2]+2]
            area=scan(lo,hi);water=[v['pos'][1]+1 for v in area['blocks']if v['fluid']and 'minecraft:water' in v['state']]
            if water:point[1]=max(water)+.1
            # A water current can move the drop below a completed plate cell.
            # Pick from a real adjacent AIR body column, not through the plate.
            candidates=[]
            for dx in (-1,0,1):
                for dz in (-1,0,1):
                    candidate=[point[0]+dx,point[1],point[2]+dz]
                    if math.hypot(candidate[0]-drop['pos'][0],candidate[2]-drop['pos'][2])>1.2:continue
                    if not any(not v['fluid']and blocks_segment(v,candidate,candidate)for v in area['blocks']):
                        candidates.append(candidate)
            if not candidates:raise RuntimeError('No observed AIR body column beside dirt drop; balance retained')
            point=min(candidates,key=lambda p:math.hypot(p[0]-drop['pos'][0],p[2]-drop['pos'][2]))
            trace=[];_travel(c,[point[0],max(67,q['pos'][1]),point[2]],state,trace,keep_cruise=True)
            q=state()
            if inventory_counts(q).get('minecraft:dirt',0)==dirt_before:return
            current_drop=next((e for e in q.get('entities',[])if e.get('uuid')==drop['uuid']),None)
            if current_drop is None or math.hypot(current_drop['pos'][0]-point[0],current_drop['pos'][2]-point[2])>1.2:
                continue # Freshly plan the current entity; no stale descent.
            lo=[math.floor(min(a,b)-.35)for a,b in zip(q['pos'],point)]
            hi=[math.ceil(max(a,b)+(1.81 if i==1 else .35))for i,(a,b)in enumerate(zip(q['pos'],point))]
            corridor=scan(lo,hi)
            if any(e.get('hostile')and e.get('alive')for e in corridor.get('scan_entities',[])):
                raise RuntimeError('Current hostile on dirt pickup corridor; preserve balance')
            for row in corridor['blocks']:
                if 'minecraft:lava' in row['state']or row['block_entity']or not row['fluid']and blocks_segment(row,q['pos'],point):
                    raise RuntimeError('No current safe dirt pickup corridor; balance retained')
            q=state()
            if inventory_counts(q).get('minecraft:dirt',0)==dirt_before:return
            book['pending']={'op':'new_known_drop_surface_route','uuid':drop['uuid'],'point':point,'dirt_before':held};save()
            c.checked('navigate',target=point,arrival=.12,seconds=12)
            latest=state()
            if latest['under_water']:raise RuntimeError('Pickup left the observed water surface; no repeat')
            deadline=time.monotonic()+4
            while inventory_counts(state()).get('minecraft:dirt',0)==held and time.monotonic()<deadline:time.sleep(.15)
            latest=state();after=inventory_counts(latest).get('minecraft:dirt',0)
            if not held<after<=dirt_before:raise RuntimeError('No confirmed dirt pickup gain; route not replayed')
            write_json(out/('cleanup-pickup-%02d.json'%attempt),{'drop':drop,'point':point,'corridor':corridor,'actual':latest,'route':trace,'collect_item_replayed':False})
            book['pending']=None;save()
        raise RuntimeError('Owned cap pickup budget ended before actual balance')
    register(c,cleanup_key,cleanup)
    for i,pos in enumerate(plan['caps']):
        if pos in book['owned_caps']:continue
        anchor=plan['base']if i==0 else plan['caps'][i-1]
        expected=plan['base_state']if i==0 else DIRT
        face='up'if i==0 else FACE[(pos[0]-anchor[0],pos[2]-anchor[2])]
        if at(pos)!='AIR' or at(anchor)!=expected:raise RuntimeError('Cap AIR cell or anchor changed')
        approach_faces(c,anchor,expected,(face,),seconds=30,stand_distance=2.4)
        q=state()
        if (pos[0]-.4<q['pos'][0]<pos[0]+1.4 and pos[2]-.4<q['pos'][2]<pos[2]+1.4):
            # ApproachBlock verifies anchor reach, not the future placed cube.
            # Move out of that cube before dispatch; never click/retry a block
            # whose placement is denied by the player's own body.
            destination=None
            directions=[delta for delta,name in FACE.items()if name==face]if face in FACE.values()else list(FACE)
            for dx,dz in directions:
                candidate=[pos[0]+.5+dx,pos[1]+2.4,pos[2]+.5+dz]
                lo=[math.floor(min(q['pos'][0],candidate[0])-.35),math.floor(min(q['pos'][1],candidate[1])),math.floor(min(q['pos'][2],candidate[2])-.35)]
                hi=[math.floor(max(q['pos'][0],candidate[0])+.35),math.ceil(max(q['pos'][1],candidate[1])+1.81),math.floor(max(q['pos'][2],candidate[2])+.35)]
                corridor=scan(lo,hi)
                lifted=[q['pos'][0],candidate[1],q['pos'][2]]
                if (not any(blocks_segment(v,q['pos'],lifted)or blocks_segment(v,lifted,candidate)for v in corridor['blocks'])
                        and not swept_entities(corridor,q['pos'],lifted,lo,hi,c.world,c.rev)
                        and not swept_entities(corridor,lifted,candidate,lo,hi,c.world,c.rev)):
                    destination=candidate;break
            if destination is None:raise RuntimeError('No current clear side pose before cap placement')
            trace=[];_travel(c,destination,state,trace)
            write_json(out/('cap-'+str(i)+'-body-route.json'),trace)
            q=wait_known_idle(c)
            if body_overlaps_cell(q['pos'],pos):raise RuntimeError('Cap target still intersects actual player body')
        c.checked('select_item',item='minecraft:dirt');held=inventory_counts(state()).get('minecraft:dirt',0)
        if at(pos)!='AIR':raise RuntimeError('Cap target changed before placement')
        if body_overlaps_cell(state()['pos'],pos):raise RuntimeError('Actual body changed before cap interaction; no click')
        book['pending']={'op':'place_cap','pos':pos,'anchor':anchor,'face':face,'dirt_before':held};save()
        r=c.request('interact',pos=anchor,face=face,expected_state=expected,expected_hand='minecraft:dirt')
        if r.get('phase')!='done':raise RuntimeError('Cap placement uncertain; no repeat')
        frames=settled(pos,DIRT,'minecraft:dirt',held-1);write_json(out/('cap-'+str(i)+'-confirmed.json'),frames)
        book['owned_caps'].append(pos);book['pending']=None;save()
    book['pending']={'op':'axis_correct_place_and_strip','target':list(target),'wood_before':wood_before};save()
    result=finish_beams(c,limit=1,expected_key=key,expected_world=world,expected_server=before['server'],expected_dimension=before['dimension'],target_item='minecraft:stripped_cherry_wood',target_axis='y')
    write_json(out/'native-beam-result.json',result)
    if len(result['completed'])!=1 or result['completed'][0]['pos']!=list(target):raise RuntimeError('Exact owned-cap beam not completed')
    settled(list(target),EXPECTED,RAW,wood_before-1);book['pending']=None;save()
    cleanup();complete(c,cleanup_key)
    if at(list(target))!=EXPECTED:raise RuntimeError('Completed wood changed during cap cleanup')
    after=inventory_counts(state()).get('minecraft:dirt',0)
    book.update(complete=True,actual_new_cells=1,dirt_restored=after==dirt_before,
                dirt_after=after,unrecovered_dirt_at_finish=max(0,dirt_before-after),
                additional_dirt_received=max(0,after-dirt_before),
                all_caps_removed=True);save();return book
