"""Harvest exposed dry natural blocks from proved air while controlled Flight stays on."""
import math,time,json
from pathlib import Path
from kit_runtime.journal import write_json
from material_trip_policy import room_for_item
from unstarted_mining import rejected_without_mining
from .acquisition import _scan,_safe,block_id,_choose_tool,carried
from .natural_block_pipeline import _dry_natural,_hand_matches
from .roof_harvest import retained_light,light_supports
from .local_air_path import plan,move
from .colored_sources import _protected
ITEM='minecraft:dripstone_block'
TERRACOTTA='minecraft:terracotta'
KNOWN_DROP_OBSERVATION_FAILURES=frozenset((
    'No actual air body position near the current settled drop',
    'New normal-air item pickup unconfirmed; no remine',
    'Original mined item vanished without actual inventory gain',
    'Current mined item stack changed',
    'Mined item remains outside current observation; preserve receipt',
    'Last observed falling-item pose has no current air access',
    'Original item unobserved after one normal air approach; no remine',
    'Current drop fell outside bounded normal-air pickup',
    'Original item removal packet remains unconfirmed; no remine',
))

def context_for(item,rows,target):
    if item==ITEM:return harvest_context(rows,target)
    if item==TERRACOTTA:
        from .terracotta_harvest import natural_context
        return natural_context(rows,target)
    raise ValueError('Unsupported dry hover material')

def visible_face(rows,station,target,face):
    """Conservative voxel ray to the same face point used by native mining."""
    directions={'center':(0,0,0),'up':(0,1,0),'down':(0,-1,0),'east':(1,0,0),'west':(-1,0,0),
                'south':(0,0,1),'north':(0,0,-1)}
    eye=[station[0],station[1]+1.62,station[2]]
    aim=[target[i]+.5+directions[face][i]*.499 for i in range(3)]
    delta=[aim[i]-eye[i]for i in range(3)];cell=[math.floor(v)for v in eye]
    blocked={tuple(r['pos'])for r in rows};steps=[1 if v>0 else -1 for v in delta]
    crossing=[((cell[i]+1-eye[i])/delta[i]if delta[i]>0 else
               (cell[i]-eye[i])/delta[i]if delta[i]<0 else math.inf)for i in range(3)]
    intervals=[abs(1/v)if v else math.inf for v in delta]
    for _ in range(20):
        if tuple(cell)in blocked:return cell==target
        at=min(crossing)
        if at>1:return False
        for i in range(3):
            if abs(crossing[i]-at)<1e-10:cell[i]+=steps[i];crossing[i]+=intervals[i]
    return False

def pickup_offers(rows,low,high,player,drop,*,allow_cone_edges=False,prefer_edges=False,prefer_lower=False):
    cells={tuple(b['pos'])for b in rows if not retained_light(b)};blocked=[b for b in rows if not retained_light(b)]
    x,y,z=map(math.floor,drop);result=[]
    for dx in(-1,0,1):
        for dz in(-1,0,1):
            for dy in(0,-1,-2,1):
                cell=(x+dx,y+dy,z+dz)
                if any(not low[i]<=cell[i]<=high[i]for i in range(3))or cell[1]+1>high[1]:continue
                if cell in cells or(cell[0],cell[1]+1,cell[2])in cells:continue
                point=[cell[0]+.5,cell[1]+.2,cell[2]+.5]
                if math.hypot(point[0]-drop[0],point[2]-drop[2])>1.15 or not -.35<=drop[1]-point[1]<=2.:continue
                try:route=plan(blocked,player,point,low,high,max_straight=2,foot_offset=.2)
                except RuntimeError:continue
                result.append((math.dist(point,drop),point))
    if prefer_lower:
        lower=[pair for pair in result if drop[1]-pair[1][1]>=1.5]
        if lower:return [p for _,p in sorted(lower,key=lambda r:r[0])]
    if result and not prefer_edges:return [p for _,p in sorted(result,key=lambda r:r[0])]
    result=[]
    # An edge inside a fully clear body cell can reach an item wedged beside a
    # cone. Keep the .6-wide body inside that same air cell; do not enter the
    # cone's voxel or infer pickup from geometry. Actual inventory proves it.
    for dx in(-1,0,1):
        for dz in(-1,0,1):
            for dy in(0,-1,-2,1):
                cell=(x+dx,y+dy,z+dz)
                if (any(not low[i]<=cell[i]<=high[i]for i in range(3))or cell[1]+1>high[1]
                        or cell in cells or(cell[0],cell[1]+1,cell[2])in cells):continue
                point=[cell[0]+.5+max(-.18,min(.18,drop[0]-(cell[0]+.5))),cell[1]+.2,
                       cell[2]+.5+max(-.18,min(.18,drop[2]-(cell[2]+.5)))]
                if (max(abs(point[i]-drop[i])for i in(0,2))>1.3
                        or not -.35<=drop[1]-point[1]<=2.):continue
                try:plan(blocked,player,point,low,high,max_straight=2,foot_offset=.2)
                except RuntimeError:continue
                result.append((math.dist(point,drop),point))
    if result or not allow_cone_edges:return [p for _,p in sorted(result,key=lambda r:r[0])]
    from .local_air_path import native_cone_edge_candidate
    from .navigation import _body_sweep
    for dx in range(-2,3):
        for dz in range(-2,3):
            for dy in(0,-1,-2,1):
                cell=(x+dx,y+dy,z+dz)
                if (any(not low[i]<=cell[i]<=high[i]for i in range(3))or cell[1]+1>high[1]
                        or cell in cells or(cell[0],cell[1]+1,cell[2])in cells):continue
                centre=[cell[0]+.5,cell[1]+.2,cell[2]+.5]
                point=[centre[0]+max(-.3,min(.3,drop[0]-centre[0])),centre[1],
                       centre[2]+max(-.3,min(.3,drop[2]-centre[2]))]
                if max(abs(point[i]-drop[i])for i in(0,2))>1.35 or not -.35<=drop[1]-point[1]<=2.:continue
                sl,sh=_body_sweep(centre,point)
                edge_rows=[r for r in rows if all(sl[i]<=r['pos'][i]<=sh[i]for i in range(3))]
                if edge_rows and not native_cone_edge_candidate(edge_rows,centre,point):continue
                try:plan(blocked,player,centre,low,high,max_straight=2,foot_offset=.2)
                except RuntimeError:continue
                result.append((math.dist(point,drop),point))
    return [p for _,p in sorted(result,key=lambda r:r[0])]

def pickup(c,drop,before,out,state,*,item=ITEM,expected_count=1,air_bounds=None,allow_cone_edges=False):
    """Separate normal air movement to current item geometry; no collect-item replay."""
    if (type(expected_count)is not int or not 1<=expected_count<=64
            or expected_count!=1 and not(item in(ITEM,TERRACOTTA,'minecraft:pointed_dripstone','minecraft:bamboo','minecraft:honeycomb','minecraft:glow_ink_sac')or item=='minecraft:clay_ball'and expected_count==4)
            or drop.get('stack',{}).get('item')!=item or drop['stack'].get('count')!=expected_count):
        raise ValueError('Exact observed original stack required; clay remains exactly four balls')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'pickup.json'
    if path.exists():raise RuntimeError('Original normal-air pickup retained; no replay')
    book={'world_session':c.world,'uuid':drop['uuid'],'item':item,'expected_count':expected_count,'before':before,'attempts':[],'collect_item_sent':False};write_json(path,book)
    for index in range(3):
        current=state();live=next((e for e in current.get('entities',[])if e.get('uuid')==drop['uuid']),None)
        if live is None:
            if carried(current,item)==before+expected_count:break
            raise RuntimeError('Original mined item vanished without actual inventory gain')
        if live.get('stack')!=drop['stack']:raise RuntimeError('Current mined item stack changed')
        # A mined item may still be falling through the newly opened wall.
        # Observe its current resting height before selecting a body cell.
        until=time.monotonic()+6;last=list(live['pos']);stable_since=None;visibility_moves=0
        while time.monotonic()<until:
            time.sleep(.15);current=state();next_live=next((e for e in current.get('entities',[])if e.get('uuid')==drop['uuid']),None)
            if next_live is None:
                if carried(current,item)==before+expected_count:break
                # Status intentionally lists entities within16 blocks. Follow
                # the last actually observed item pose through freshly proved
                # air once; missing nearby data is not disappearance proof.
                if visibility_moves>=1:raise RuntimeError('Mined item remains outside current observation; preserve receipt')
                player=current['pos'];low=[math.floor(min(last[i],player[i]))-3 for i in range(3)]
                high=[math.floor(max(last[i],player[i]))+3 for i in range(3)];high[1]+=2
                rows=_scan(c,low,high,state);near=pickup_offers(rows,low,high,player,last)
                if not near:raise RuntimeError('Last observed falling-item pose has no current air access')
                move(c,near[0],out/('observe-last-pose-%d'%index),max_straight=4,foot_offset=.2)
                visibility_moves+=1;until=time.monotonic()+6;current=state()
                next_live=next((e for e in current.get('entities',[])if e.get('uuid')==drop['uuid']),None)
                if next_live is None:
                    if carried(current,item)==before+expected_count:break
                    raise RuntimeError('Original item unobserved after one normal air approach; no remine')
            live=next_live
            if math.dist(live['pos'],last)<=.025:
                if stable_since is None:stable_since=time.monotonic()
                if time.monotonic()-stable_since>=.5:break
            else:stable_since=None
            last=list(live['pos'])
        if carried(current,item)==before+expected_count:break
        p=live['pos'];player=state()['pos']
        if math.hypot(p[0]-player[0],p[2]-player[2])>10 or abs(p[1]-player[1])>60:
            raise RuntimeError('Current drop fell outside bounded normal-air pickup')
        low=[math.floor(min(p[i],player[i]))-3 for i in range(3)]
        high=[math.floor(max(p[i],player[i]))+3 for i in range(3)];high[1]+=2
        rows=_scan(c,low,high,state)
        # The scan reply may carry a newer falling-item position than the
        # preceding snapshots. Plan against that live pose, not the old height.
        latest=state();new_live=next((e for e in latest.get('entities',[])if e.get('uuid')==drop['uuid']),None)
        if new_live is not None:
            if new_live.get('stack')!=drop['stack']:raise RuntimeError('Current mined item stack changed')
            live=new_live;p=list(live['pos']);player=latest['pos']
            book['last_observed_drop_position']=p;write_json(path,book)
            needed_low=[math.floor(min(p[i],player[i]))-3 for i in range(3)]
            needed_high=[math.floor(max(p[i],player[i]))+3 for i in range(3)];needed_high[1]+=2
            # The new position also needs its surrounding routing air. Being
            # just inside the old scan edge does not prove that whole halo.
            if any(needed_low[i]<low[i] or needed_high[i]>high[i]for i in range(3)):continue
        offer_kwargs={'allow_cone_edges':True}if allow_cone_edges else{}
        # An actually reached centre with no inventory gain is evidence that
        # the same centre is insufficient for this settled item. Use the
        # next lower full-air stance or the supported .18 offset next, instead
        # of repeating that identical movement for all three attempts. A farm
        # drop on a ledge was actually received while leaving one cell lower.
        tried=[a['point'] for a in book['attempts']
               if a['after']==before and math.dist(a['settled_drop_position'],p)<=.1]
        if tried:offer_kwargs.update(prefer_edges=True,prefer_lower=not any(p[1]-old[1]>=1.5 for old in tried))
        points=pickup_offers(rows,low,high,player,p,**offer_kwargs)
        points=[point for point in points if all(math.dist(point,old)>.025 for old in tried)]
        route_bounds=None
        if not points and air_bounds is not None:
            low,high=air_bounds['min'],air_bounds['max']
            if math.prod(b-a+1 for a,b in zip(low,high))>30000:raise RuntimeError('Pickup air volume exceeds the bounded limit')
            rows=_scan(c,low,high,state);latest=state()
            live=next((e for e in latest.get('entities',[])if e.get('uuid')==drop['uuid']),None)
            if live is not None:
                if live.get('stack')!=drop['stack']:raise RuntimeError('Current mined item stack changed')
                p=list(live['pos']);player=latest['pos']
                tried=[a['point'] for a in book['attempts']
                       if a['after']==before and math.dist(a['settled_drop_position'],p)<=.1]
                offer_kwargs.pop('prefer_edges',None)
                offer_kwargs.pop('prefer_lower',None)
                if tried:offer_kwargs.update(prefer_edges=True,prefer_lower=not any(p[1]-old[1]>=1.5 for old in tried))
                points=pickup_offers(rows,low,high,player,p,**offer_kwargs)
                points=[point for point in points if all(math.dist(point,old)>.025 for old in tried)]
                route_bounds=air_bounds
        latest=state()
        if carried(latest,item)==before+expected_count and not any(e.get('uuid')==drop['uuid']for e in latest.get('entities',[])):break
        if not points:
            # The server can collect an overlapping item after the last
            # sparse entity/inventory snapshot. Observe that exact gain before
            # declaring an inaccessible item; never excavate or remine here.
            until=time.monotonic()+2
            while time.monotonic()<until:
                current=state()
                if carried(current,item)==before+expected_count and not any(e.get('uuid')==drop['uuid']for e in current.get('entities',[])):break
                if carried(current,item)!=before:raise RuntimeError('Inventory changed during original-drop observation')
                time.sleep(.15)
            else:raise RuntimeError('No actual air body position near the current settled drop')
            break
        point=points[0]
        fractional=any(abs(point[i]-(math.floor(point[i])+.5))>1e-7 for i in (0,2))
        kwargs={'exact_target':True}if fractional else{}
        cone_edge=allow_cone_edges and any(abs(point[i]-(math.floor(point[i])+.5))>.180001 for i in(0,2))
        if cone_edge:kwargs.update(exact_target=True,allow_dry_cone_edge=True)
        if route_bounds is not None:kwargs['scan_bounds']=route_bounds
        move(c,point,out/('normal-air-%d'%index),max_straight=2,foot_offset=.2,**kwargs)
        until=time.monotonic()+3
        while time.monotonic()<until:
            q=state()
            if carried(q,item)==before+expected_count and not any(e.get('uuid')==drop['uuid']for e in q.get('entities',[])):break
            time.sleep(.15)
        book['attempts'].append({'settled_drop_position':p,'point':point,'actual':state()['pos'],'after':carried(state(),item)});write_json(path,book)
        if cone_edge:
            # Return to the proved full air cell before any further route.
            # Both directions retain native real-shape collision admission.
            from .navigation import _air_move,_air_scan,_body_sweep
            from .local_air_path import native_cone_edge_candidate
            centre=[math.floor(point[0])+.5,point[1],math.floor(point[2])+.5]
            actual=state()['pos'];edge_rows=_air_scan(c,*_body_sweep(actual,centre))
            if edge_rows and not native_cone_edge_candidate(edge_rows,actual,centre):
                raise RuntimeError('Cone edge return changed; original pickup evidence retained')
            book['return_to_air_cell_pending']=centre;write_json(path,book)
            _air_move(c,centre,30,arrival=.08)
            book['return_to_air_cell_pending']=None;write_json(path,book)
        if carried(state(),item)==before+expected_count:break
    until=time.monotonic()+3
    while True:
        final=state()
        if carried(final,item)!=before+expected_count:raise RuntimeError('New normal-air item pickup unconfirmed; no remine')
        if not any(e.get('uuid')==drop['uuid']for e in final.get('entities',[])):break
        if time.monotonic()>=until:raise RuntimeError('Original item removal packet remains unconfirmed; no remine')
        time.sleep(.15)
    book.update(confirmed=True,after=before+expected_count);write_json(path,book);return True

def harvest_context(rows,target):
    """Adjacent cones block body routes; their actual supports remain protected."""
    cones=[r for r in rows if block_id(r)=='minecraft:pointed_dripstone']
    from projection_completion import block_state
    for cone in cones:
        if cone['pos'][0]!=target[0]or cone['pos'][2]!=target[2]or abs(cone['pos'][1]-target[1])!=1:continue
        direction=block_state(cone['state'])[1].get('vertical_direction')
        if (direction not in ('up','down')
                or direction=='down' and cone['pos'][1]==target[1]-1
                or direction=='up' and cone['pos'][1]==target[1]+1):return False
    # Never remove the cones from route geometry. Only omit harmless, dry
    # neighboring cones from this material-context classification.
    return _dry_natural([r for r in rows if not retained_light(r)
                        and not(block_id(r)=='minecraft:pointed_dripstone'
                                and r.get('fluid')is False and r.get('block_entity')is False)])


def stations(pos):
    """Ceilings need two clear body cells below, floors an adjacent cell above."""
    x,y,z=pos
    result=[([x+.5,y-2+.2,z+.5],'down')]
    for dx,dz,face in ((1,0,'east'),(-1,0,'west'),(0,1,'south'),(0,-1,'north')):
        for height in (y-2,y-1,y,y+1):
            result.append(([x+dx+.5,height+.2,z+dz+.5],
                           'down'if height<=y-2 else'up'if height>=y+1 else face))
    return result


def known_merged_drop(entities,old_items,deferred,item,target):
    """One newly mined item merged with one owned, known unreceived item."""
    if item not in(ITEM,TERRACOTTA):return None
    current={e.get('uuid'):e for e in entities if e.get('type')=='minecraft:item'};found=[]
    for prior in deferred:
        uuid=prior.get('original_drop_uuid');old=old_items.get(uuid)
        if(not old or prior.get('server_removed')is not True or prior.get('actual_gain')!=0
                or prior.get('inventory_credit')!=0 or prior.get('mining_replayed')is not False
                or old.get('stack',{}).get('item')!=item or old.get('stack',{}).get('count')!=1):continue
        for drop in current.values():
            if(drop.get('stack',{}).get('item')!=item or drop.get('stack',{}).get('count')!=2 or not isinstance(drop.get('pos'),list)
                    or math.dist(drop['pos'],target)>5 or math.dist(drop['pos'],old['pos'])>2):continue
            if(drop['uuid']==uuid or drop['uuid']not in old_items and uuid not in current):
                found.append((drop,prior))
    return found[0]if len(found)==1 else None


def offers(rows,low,high,player,*,item=ITEM):
    cells={tuple(b['pos']):b for b in rows};blocked={tuple(b['pos']):b for b in rows if not retained_light(b)};result=[];lights=light_supports(rows)
    for b in rows:
        p=b['pos']
        if block_id(b)!=item or tuple(p)in lights or not all(low[i]+2<=p[i]<=high[i]-2 for i in range(3)):continue
        local=[cells[(x,y,z)]for x in range(p[0]-2,p[0]+3)
               for y in range(p[1]-2,p[1]+3)for z in range(p[2]-2,p[2]+3)if(x,y,z)in cells]
        if not context_for(item,local,p):continue
        for point,aim_face in stations(p):
                if aim_face=='down' and player[1]>=p[1]+1:continue
                x,y,z=map(math.floor,point)
                if any((x,h,z)in cells for h in(y,y+1)):continue
                if not visible_face(local,point,p,aim_face):continue
                if math.hypot(player[0]-point[0],player[2]-point[2])>12 or abs(player[1]-point[1])>64:continue
                route_low=[max(low[i],math.floor(min(player[i],point[i]))-3)for i in range(3)]
                route_high=[min(high[i],math.floor(max(player[i],point[i]))+3)for i in range(3)]
                local_blocked=[blocked[(rx,ry,rz)]for rx in range(route_low[0],route_high[0]+1)
                               for ry in range(route_low[1],route_high[1]+1)
                               for rz in range(route_low[2],route_high[2]+1)if(rx,ry,rz)in blocked]
                try:route=plan(local_blocked,player,point,route_low,route_high,max_straight=8,foot_offset=.2)
                except RuntimeError:continue
                length=sum(math.dist(a,b)for a,b in zip([player]+route,route))
                result.append({'target':p,'state':b['state'],'station':point,'face':aim_face,'route_length':length})
    return sorted(result,key=lambda r:r['route_length'])

def run(c,profile,region,target_count,out,checkpoint,max_blocks=8,*,survey_rows=None,item=ITEM):
    if region.get('authorized')is not True or region.get('source')!='natural_survey':raise ValueError('Explicit surveyed natural region required')
    if item not in(ITEM,TERRACOTTA):raise ValueError('Unsupported dry hover material')
    exclusions=region.get('excluded_targets',[])
    if(not isinstance(exclusions,list)or len(exclusions)>64 or any(not isinstance(p,list)or len(p)!=3
            or any(type(v)is not int for v in p)for p in exclusions)):raise ValueError('Bounded exact target exclusions required')
    excluded={tuple(p)for p in exclusions}
    if item==TERRACOTTA:
        from .terracotta_harvest import verify_region
        verify_region(c,region,checkpoint,out)
    low,high=region['min'],region['max'];out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'harvest.json'
    if path.exists():raise RuntimeError('Original hover harvest retained; no replay')
    def state():
        checkpoint();q=c.status();_safe(q)
        if q.get('flight')is not True:raise RuntimeError('Dry hover harvest requires actual controlled Flight')
        return q
    book={'world_session':c.world,'item':item,'initial':carried(state(),item),'pending':None,'receipts':[],
          'geometry_scope':'initial_full_scan_then_current_local_and_body_scans'};write_json(path,book)
    rows=list(survey_rows)if survey_rows is not None else None;rejected=set()
    if rows is not None:
        book['planned_from_parent_current_survey']=True;write_json(path,book)
    def choice_key(choice):return(tuple(choice['target']),tuple(choice['station']),choice['face'])
    def refresh_local(local,pos):
        nonlocal rows
        rows=[r for r in rows if not all(abs(r['pos'][i]-pos[i])<=2 for i in range(3))]
        rows.extend(r for r in local if all(low[i]<=r['pos'][i]<=high[i]for i in range(3)))
    def observe_extra_inventory(pos,before,reason):
        nonlocal rows
        if getattr(c,'native_inflight',None)is not None or getattr(c,'unconfirmed_native_request',None)is not None:return False
        q=state();after=carried(q,item)
        if(after<=before+1 or q.get('navigating')or q.get('native_material_busy')
                or _scan(c,pos,pos,state)):return False
        stamp=q.get('time');observed=[];until=time.monotonic()+1.5
        if type(stamp)is not int:return False
        while True:
            final=state();t=final.get('time')
            if(carried(final,item)!=after or type(t)is not int
                    or final.get('navigating')or final.get('native_material_busy')):return False
            if t>stamp and(not observed or t>observed[-1]):observed.append(t)
            if len(observed)>=2:break
            if time.monotonic()>=until:return False
            time.sleep(.05)
        record={**book['pending'],'after':after,'actual_gain':0,'server_removed':True,
                'aggregate_inventory_gain':after-before,'source_allocation_unresolved':True,
                'inventory_credit_to_this_target':0,'original_pickup_error':reason,
                'old_receipts_unchanged':True,'mining_replayed':False}
        book.setdefault('unattributed_pickups',[]).append(record);book['receipts'].append(record)
        book['pending']=None;rows=[r for r in rows if r['pos']!=pos];write_json(path,book)
        c.set_progress(done=after,phase='同种材料实物已入背包；保留原掉落归属记录')
        print('ACTUAL_AGGREGATE_BACKPACK',item,after,'UNALLOCATED',after-before,flush=True);return True
    for index in range(max_blocks):
        q=state()
        if carried(q,item)>=target_count:break
        threats=[e for e in q.get('entities',[])if e.get('hostile')is True
                 and e.get('alive')is not False and e.get('health',1)>0]
        if item==TERRACOTTA and threats:
            book.update(phase='waiting',code='WAIT_SOURCE_HOSTILE',observed_threats=threats);break
        if rows is None:
            rows=_scan(c,low,high,state);book['full_survey_request_id']=c.last;write_json(path,book)
        choices=[r for r in offers(rows,low,high,q['pos'],item=item)if choice_key(r)not in rejected
                 and tuple(r['target'])not in excluded and not _protected(r['target'],profile,q)]
        if not choices:break
        choice=choices[0];pos=choice['target'];before=carried(q,item)
        if room_for_item(q,item)<1:
            book.update(phase='waiting',code='WAIT_CAPACITY');break
        move(c,choice['station'],out/('approach-%02d'%index),max_straight=8,foot_offset=.2)
        local=_scan(c,[v-2 for v in pos],[v+2 for v in pos],state)
        refresh_local(local,pos)
        actual=next((r for r in local if r['pos']==pos),None)
        if actual is None:
            # A fresh complete scan proves no mining was dispatched for this
            # choice. Replan from current geometry instead of leaving the cave.
            book.setdefault('skipped_before_mining',[]).append({'target':pos,
                'reason':'current_target_already_air','scan_request_id':c.last})
            write_json(path,book)
            continue
        if actual['state']!=choice['state']or tuple(pos)in light_supports(local)or not context_for(item,local,pos):
            raise RuntimeError('Natural target or adjacent hazards changed')
        if not visible_face(local,state()['pos'],pos,choice['face']):
            rejected.add(choice_key(choice))
            book.setdefault('skipped_before_mining',[]).append({**choice,'reason':'current_face_occluded','scan_request_id':c.last})
            write_json(path,book);continue
        tools=[r for r in state()['inventory']if r.get('slot',99)<36 and r.get('count')==1
               and r.get('item')in('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')and r.get('durability',0)>=33
               and not any(e.get('id')=='minecraft:silk_touch'for e in r.get('enchantments',[]))]
        if not tools:raise RuntimeError('Actual non-silk pickaxe missing')
        tool=max(tools,key=lambda r:(max((e['level']for e in r.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),r['durability']))
        current=state()
        if not _hand_matches(current,tool,tool['slot']):_choose_tool(c,tool,state)
        baseline=state();planned_before=before;before=carried(baseline,item)
        if before<planned_before:raise RuntimeError('Material stock decreased before mining; no mining sent')
        if before!=planned_before:
            book.setdefault('approach_inventory_observations',[]).append({'before':planned_before,'after':before,
                'mining_sent':False,'source_allocation_unresolved':True});write_json(path,book)
        if before>=target_count:break
        old_items={e['uuid']:e for e in baseline.get('entities',[])if e.get('type')=='minecraft:item'};old=set(old_items)
        book['pending']={**choice,'before':before};write_json(path,book)
        try:reply=c.request('mine_block',pos=pos,face=choice['face'],expected_state=actual['state'],seconds=20)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        if rejected_without_mining(reply,c.last,c.world,pos):
            if carried(state(),item)!=before:raise RuntimeError('Inventory changed during rejected mining; preserve intent')
            rejected.add(choice_key(choice));book.setdefault('rejected_before_mining',[]).append({**book['pending'],'native_proof':reply,'inventory_credit':0})
            book['pending']=None;write_json(path,book);continue
        from terminal_confirmation import verified
        if not verified('mine_block',reply,c.world,c.last,{'pos':pos}):
            raise RuntimeError('Native mining lacks exact server confirmation; preserve original intent')
        q=state();until=time.monotonic()+5
        while carried(q,item)==before and not any(e.get('type')=='minecraft:item'and e.get('uuid')not in old
                and e.get('stack',{}).get('item')==item for e in q.get('entities',[]))and time.monotonic()<until:
            time.sleep(.15);q=state()
        if observe_extra_inventory(pos,before,'extra_current_stock_after_confirmed_mining'):continue
        if carried(q,item)==before:
            drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'and e.get('uuid')not in old
                   and e.get('stack',{}).get('item')==item and e['stack']['count']==1 and math.dist(e['pos'],pos)<5]
            expected_count=1
            if not drops:
                merged=known_merged_drop(q.get('entities',[]),old_items,book.get('unreceived_drops',[]),item,pos)
                if merged:
                    drop,prior=merged;drops=[drop];expected_count=2
                    book['pending']['known_merged_source']={'prior_request_id':prior['request_id'],
                        'original_drop_uuid':prior['original_drop_uuid'],'current_drop_uuid':drop['uuid'],'observed_count':2}
                    write_json(path,book)
            if len(drops)!=1:
                # A missing/merged entity snapshot is not an unknown mine:
                # this send already has exact native ACK and AIR proof. Keep
                # the unreceived item at zero credit and leave that cell out
                # of future targets, rather than aborting the whole cave.
                if (c.native_inflight is not None or getattr(c,'unconfirmed_native_request',None)is not None
                        or _scan(c,pos,pos,state)):
                    raise RuntimeError('Exact newly mined material pickup unconfirmed')
                actual_held=carried(state(),item)
                if actual_held==before+1:
                    book['receipts'].append({**book['pending'],'after':actual_held,'actual_gain':1})
                elif actual_held==before:
                    deferred={**book['pending'],'after':before,'actual_gain':0,'server_removed':True,
                              'pickup_deferred':True,'original_drop_uuid':None,
                              'drop_identity_unconfirmed':True,'inventory_credit':0,'mining_replayed':False}
                    book.setdefault('unreceived_drops',[]).append(deferred);book['receipts'].append(deferred)
                elif observe_extra_inventory(pos,before,'current_stock_after_ambiguous_drop_snapshot'):
                    continue
                else:raise RuntimeError('Exact newly mined material pickup unconfirmed')
                rows=[r for r in rows if r['pos']!=pos];book['pending']=None;write_json(path,book)
                continue
            try:received=pickup(c,drops[0],before,out/('pickup-%02d'%index),state,item=item,expected_count=expected_count)
            except RuntimeError as error:
                if observe_extra_inventory(pos,before,str(error)):continue
                # This exact failure follows only complete scans/confirmed
                # moves. The original mining send is already server-confirmed;
                # retain the missing pickup with zero credit and continue with
                # distinct targets instead of replaying the mine or claiming
                # that an unreceived item is in the backpack.
                if (str(error)not in KNOWN_DROP_OBSERVATION_FAILURES
                        or c.native_inflight is not None or getattr(c,'unconfirmed_native_request',None)is not None):raise
                q=state()
                if q.get('navigating')or q.get('native_material_busy'):raise
                if _scan(c,pos,pos,state):raise
                q=state();late=carried(q,item)
                if late>before+1 and observe_extra_inventory(pos,before,'late_current_stock_after_known_pickup_moves'):continue
                if late not in(before,before+1):raise
                if late==before+1 and not any(e.get('uuid')==drops[0]['uuid']for e in q.get('entities',[])):
                    book['receipts'].append({**book['pending'],'after':late,'actual_gain':1,'late_pickup_verified':True})
                    rows=[r for r in rows if r['pos']!=pos];book['pending']=None;write_json(path,book);continue
                deferred={**book['pending'],'after':before,'actual_gain':0,'server_removed':True,
                          'pickup_deferred':True,'original_drop_uuid':drops[0]['uuid'],'last_observed_drop':drops[0]['pos'],
                          'inventory_credit':0,'mining_replayed':False}
                if late>before:deferred.update(observed_backpack_after=late,source_allocation_unresolved=True)
                book.setdefault('unreceived_drops',[]).append(deferred)
                book['receipts'].append(deferred);book['pending']=None
                rows=[r for r in rows if r['pos']!=pos];write_json(path,book)
                print('ORIGINAL_DROP_DEFERRED_WITHOUT_CREDIT',drops[0]['uuid'],before,flush=True)
                continue
            if not received:raise RuntimeError('Exact newly mined material pickup unconfirmed')
        after=carried(state(),item)
        if observe_extra_inventory(pos,before,'extra_current_stock_after_original_pickup'):continue
        if _scan(c,pos,pos,state)or after!=before+1:raise RuntimeError('Server block removal or exact backpack gain unconfirmed')
        rows=[r for r in rows if r['pos']!=pos]
        book['receipts'].append({**book['pending'],'after':after,'actual_gain':1});book['pending']=None;write_json(path,book)
        c.set_progress(done=after,phase='陶瓦实物已入背包'if item==TERRACOTTA else'滴水石实物已入背包');print('ACTUAL_HOVER_MATERIAL',item,after,flush=True)
    book.update(verified_count=carried(state(),item),full_target_reached=carried(state(),item)>=target_count)
    write_json(path,book);return book
