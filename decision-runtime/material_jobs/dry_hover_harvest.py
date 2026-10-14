"""Harvest exposed dry natural blocks from proved air while controlled Flight stays on."""
import math,time,json
from pathlib import Path
from kit_runtime.journal import write_json
from material_trip_policy import room_for_item
from .acquisition import _scan,_safe,block_id,_choose_tool,carried
from .natural_block_pipeline import _dry_natural
from .roof_harvest import retained_light,light_supports
from .local_air_path import plan,move
from .colored_sources import _protected
ITEM='minecraft:dripstone_block'

def pickup_offers(rows,low,high,player,drop):
    cells={tuple(b['pos'])for b in rows if not retained_light(b)};blocked=[b for b in rows if not retained_light(b)]
    x,y,z=map(math.floor,drop);result=[]
    for dx in(-1,0,1):
        for dz in(-1,0,1):
            for dy in(0,-1,1):
                cell=(x+dx,y+dy,z+dz)
                if any(not low[i]<=cell[i]<=high[i]for i in range(3))or cell[1]+1>high[1]:continue
                if cell in cells or(cell[0],cell[1]+1,cell[2])in cells:continue
                point=[cell[0]+.5,cell[1]+.2,cell[2]+.5]
                if math.hypot(point[0]-drop[0],point[2]-drop[2])>1.15 or not -.35<=drop[1]-point[1]<=1.8:continue
                try:route=plan(blocked,player,point,low,high,max_straight=2,foot_offset=.2)
                except RuntimeError:continue
                result.append((math.dist(point,drop),point))
    return [p for _,p in sorted(result,key=lambda r:r[0])]

def pickup(c,drop,before,out,state):
    """Separate normal air movement to current item geometry; no collect-item replay."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'pickup.json'
    if path.exists():raise RuntimeError('Original normal-air pickup retained; no replay')
    book={'world_session':c.world,'uuid':drop['uuid'],'before':before,'attempts':[],'collect_item_sent':False};write_json(path,book)
    for index in range(3):
        current=state();live=next((e for e in current.get('entities',[])if e.get('uuid')==drop['uuid']),None)
        if live is None:
            if carried(current,ITEM)==before+1:break
            raise RuntimeError('Original mined item vanished without actual inventory gain')
        if live.get('stack')!=drop['stack']:raise RuntimeError('Current mined item stack changed')
        # A mined item may still be falling through the newly opened wall.
        # Observe its current resting height before selecting a body cell.
        until=time.monotonic()+6;last=list(live['pos']);stable_since=None;visibility_moves=0
        while time.monotonic()<until:
            time.sleep(.15);current=state();next_live=next((e for e in current.get('entities',[])if e.get('uuid')==drop['uuid']),None)
            if next_live is None:
                if carried(current,ITEM)==before+1:break
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
                    if carried(current,ITEM)==before+1:break
                    raise RuntimeError('Original item unobserved after one normal air approach; no remine')
            live=next_live
            if math.dist(live['pos'],last)<=.025:
                if stable_since is None:stable_since=time.monotonic()
                if time.monotonic()-stable_since>=.5:break
            else:stable_since=None
            last=list(live['pos'])
        if carried(current,ITEM)==before+1:break
        p=live['pos'];player=state()['pos']
        if math.hypot(p[0]-player[0],p[2]-player[2])>10 or abs(p[1]-player[1])>60:
            raise RuntimeError('Current drop fell outside bounded normal-air pickup')
        low=[math.floor(min(p[i],player[i]))-3 for i in range(3)]
        high=[math.floor(max(p[i],player[i]))+3 for i in range(3)];high[1]+=2
        rows=_scan(c,low,high,state);points=pickup_offers(rows,low,high,player,p)
        if not points:raise RuntimeError('No actual air body position near the current settled drop')
        point=points[0]
        move(c,point,out/('normal-air-%d'%index),max_straight=2,foot_offset=.2)
        until=time.monotonic()+3
        while time.monotonic()<until:
            q=state()
            if carried(q,ITEM)==before+1 and not any(e.get('uuid')==drop['uuid']for e in q.get('entities',[])):break
            time.sleep(.15)
        book['attempts'].append({'settled_drop_position':p,'point':point,'actual':state()['pos'],'after':carried(state(),ITEM)});write_json(path,book)
        if carried(state(),ITEM)==before+1:break
    if carried(state(),ITEM)!=before+1:raise RuntimeError('New normal-air item pickup unconfirmed; no remine')
    book.update(confirmed=True,after=before+1);write_json(path,book);return True

def offers(rows,low,high,player):
    cells={tuple(b['pos']):b for b in rows};blocked=[b for b in rows if not retained_light(b)];result=[];lights=light_supports(rows)
    for b in rows:
        p=b['pos']
        if block_id(b)!=ITEM or tuple(p)in lights or not all(low[i]+2<=p[i]<=high[i]-2 for i in range(3)):continue
        local=[r for r in rows if all(abs(r['pos'][i]-p[i])<=2 for i in range(3))]
        if not _dry_natural([r for r in local if not retained_light(r)]):continue
        for dx,dz,face in ((1,0,'east'),(-1,0,'west'),(0,1,'south'),(0,-1,'north')):
            for y in(p[1]-1,p[1],p[1]+1):
                x,z=p[0]+dx,p[2]+dz
                if any((x,h,z)in cells for h in(y,y+1)):continue
                point=[x+.5,y+.2,z+.5]
                if math.hypot(player[0]-point[0],player[2]-point[2])>12 or abs(player[1]-point[1])>64:continue
                try:route=plan(blocked,player,point,low,high,max_straight=8,foot_offset=.2)
                except RuntimeError:continue
                length=sum(math.dist(a,b)for a,b in zip([player]+route,route))
                result.append({'target':p,'state':b['state'],'station':point,'face':face,'route_length':length})
    return sorted(result,key=lambda r:r['route_length'])

def run(c,profile,region,target_count,out,checkpoint,max_blocks=8):
    if region.get('authorized')is not True or region.get('source')!='natural_survey':raise ValueError('Explicit surveyed natural region required')
    low,high=region['min'],region['max'];out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'harvest.json'
    if path.exists():raise RuntimeError('Original hover harvest retained; no replay')
    def state():
        checkpoint();q=c.status();_safe(q)
        if q.get('flight')is not True:raise RuntimeError('Dry hover harvest requires actual controlled Flight')
        return q
    book={'world_session':c.world,'initial':carried(state(),ITEM),'pending':None,'receipts':[]};write_json(path,book)
    for index in range(max_blocks):
        q=state()
        if carried(q,ITEM)>=target_count:break
        rows=_scan(c,low,high,state);choices=[r for r in offers(rows,low,high,q['pos'])if not _protected(r['target'],profile,q)]
        if not choices:break
        choice=choices[0];pos=choice['target'];before=carried(q,ITEM)
        if room_for_item(q,ITEM)<1:raise RuntimeError('No actual backpack capacity for dripstone')
        move(c,choice['station'],out/('approach-%02d'%index),max_straight=8,foot_offset=.2)
        local=_scan(c,[v-2 for v in pos],[v+2 for v in pos],state)
        actual=next((r for r in local if r['pos']==pos),None)
        if actual is None:
            # A fresh complete scan proves no mining was dispatched for this
            # choice. Replan from current geometry instead of leaving the cave.
            book.setdefault('skipped_before_mining',[]).append({'target':pos,
                'reason':'current_target_already_air','scan_request_id':c.last})
            write_json(path,book)
            continue
        if actual['state']!=choice['state']or tuple(pos)in light_supports(local)or not _dry_natural([r for r in local if not retained_light(r)]):
            raise RuntimeError('Natural target or adjacent hazards changed')
        tools=[r for r in state()['inventory']if r.get('slot',99)<36 and r.get('count')==1
               and r.get('item')in('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')and r.get('durability',0)>=33
               and not any(e.get('id')=='minecraft:silk_touch'for e in r.get('enchantments',[]))]
        if not tools:raise RuntimeError('Actual non-silk pickaxe missing')
        tool=max(tools,key=lambda r:(max((e['level']for e in r.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),r['durability']))
        _choose_tool(c,tool,state);old={e['uuid']for e in state().get('entities',[])if e.get('type')=='minecraft:item'}
        book['pending']={**choice,'before':before};write_json(path,book)
        try:c.checked('mine_block',pos=pos,face=choice['face'],expected_state=actual['state'],seconds=20)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        q=state();until=time.monotonic()+5
        while carried(q,ITEM)==before and not any(e.get('type')=='minecraft:item'and e.get('uuid')not in old
                and e.get('stack',{}).get('item')==ITEM for e in q.get('entities',[]))and time.monotonic()<until:
            time.sleep(.15);q=state()
        if carried(q,ITEM)==before:
            drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'and e.get('uuid')not in old
                   and e.get('stack',{}).get('item')==ITEM and e['stack']['count']==1 and math.dist(e['pos'],pos)<5]
            if len(drops)!=1 or not pickup(c,drops[0],before,out/('pickup-%02d'%index),state):raise RuntimeError('Exact newly mined dripstone pickup unconfirmed')
        after=carried(state(),ITEM)
        if _scan(c,pos,pos,state)or after!=before+1:raise RuntimeError('Server block removal or exact backpack gain unconfirmed')
        book['receipts'].append({**book['pending'],'after':after,'actual_gain':1});book['pending']=None;write_json(path,book)
        c.set_progress(done=after,phase='滴水石实物已入背包');print('ACTUAL_HOVER_DRIPSTONE',after,flush=True)
    book.update(verified_count=carried(state(),ITEM),full_target_reached=carried(state(),ITEM)>=target_count)
    write_json(path,book);return book
