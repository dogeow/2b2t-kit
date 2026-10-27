"""Open only the exact few dry wall cells of a currently surveyed cave route."""
from pathlib import Path
from collections import Counter
import math,time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from .acquisition import _choose_tool
from .local_air_path import move
from .dry_hover_harvest import visible_face
from .colored_sources import _protected
from .roof_harvest import light_supports
from .dry_cave_probe import DROPS,bid

def air_cells(c,cells,out,checkpoint):
    kept=[cells[0]];direction=None
    for i in range(1,len(cells)):
        d=tuple(cells[i][a]-cells[i-1][a]for a in range(3))
        if direction is not None and d!=direction and kept[-1]!=cells[i-1]:kept.append(cells[i-1])
        if math.dist(kept[-1],cells[i])>=6:kept.append(cells[i])
        direction=d
    if kept[-1]!=cells[-1]:kept.append(cells[-1])
    out=Path(out);out.mkdir(parents=True,exist_ok=False);write_json(out/'route.json',{'world_session':c.world,'actual_air_cells':cells,'waypoints':kept,'block_mutations':0})
    for i,p in enumerate(kept):
        checkpoint();point=[p[0]+.5,p[1]+.1,p[2]+.5]
        if math.dist(checkpoint()['pos'],point)<=.15:continue
        move(c,point,out/('leg-%02d'%i),foot_offset=.1,max_straight=6,max_horizontal=12,exact_target=True)

def run(c,plan,profile,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);path=out/'connection.json';cells=plan['path'];wanted={tuple(b['pos']):b for b in plan['needed_blocks']}
    if plan['world_session']!=c.world or not 1<=len(wanted)<=8 or cells[0]!=[math.floor(v)for v in checkpoint()['pos']]:raise ValueError('Current surveyed connection of at most8 exact dry wall blocks required')
    book={'world_session':c.world,'source_plan':plan,'pending':None,'mines':[],'air_routes':[],'complete':False};write_json(path,book);removed=set();start=0
    for i,cell in enumerate(cells[1:],1):
        blockers=[wanted[p]for p in[(cell[0],cell[1]+1,cell[2]),tuple(cell)]if p in wanted and p not in removed]
        if not blockers:continue
        air_cells(c,cells[start:i],out/('existing-air-%02d'%i),checkpoint);book['air_routes'].append(cells[start:i]);write_json(path,book)
        before=inventory_counts(checkpoint());expected=Counter()
        for row in blockers:
            q=checkpoint();p=row['pos'];item=DROPS.get(bid(row));foot=[math.floor(q['pos'][0]),math.floor(q['pos'][1])-1,math.floor(q['pos'][2])]
            if item is None or p==foot or _protected(p,profile,q)or q.get('health')!=20 or q.get('guard_busy')or q.get('under_water')or not q.get('flight')or room_for_item(q,item)<2:raise RuntimeError('Current dry wall, capacity or support protection changed')
            r=c.request('scan',min=[v-1 for v in p],max=[v+1 for v in p],details=True)
            if r.get('phase')!='done'or r.get('scan_cells_read')!=27:raise RuntimeError('Current exact wall neighbourhood incomplete')
            by={tuple(v['pos']):v for v in r['blocks']};live=by.get(tuple(p))
            if not live or live['state']!=row['state']or live.get('fluid')or live.get('block_entity')or tuple(p)in light_supports(r['blocks']):raise RuntimeError('Planned dry wall cell changed; no mine')
            if any(v.get('fluid')or v.get('block_entity')or bid(v)in('minecraft:gravel','minecraft:sand','minecraft:red_sand')for k,v in by.items()if sum(abs(k[a]-p[a])for a in range(3))==1):raise RuntimeError('Water, container or falling-block boundary protected')
            tools=[t for t in q['inventory']if t.get('slot',99)<36 and t.get('count')==1 and t.get('item')in('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')and t.get('durability',0)>=42 and not any(e['id']=='minecraft:silk_touch'for e in t.get('enchantments',[]))]
            if not tools:raise RuntimeError('Actual suitable carried pickaxe missing')
            tool=max(tools,key=lambda t:(max((e['level']for e in t.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),t['durability']));_choose_tool(c,tool,checkpoint)
            faces=[f for f in('up','down','east','west','north','south')if visible_face(r['blocks'],checkpoint()['pos'],p,f)]
            if not faces:raise RuntimeError('No actual visible face of this dry wall; no mine')
            book['pending']={'kind':'one_exact_new_dry_wall_removal','pos':p,'expected_state':row['state']};write_json(path,book)
            try:reply=c.checked('mine_block',pos=p,face=faces[0],expected_state=row['state'],seconds=15)
            finally:book['pending']['request_id']=c.last;write_json(path,book)
            if reply.get('server_confirmed')is not True or reply.get('mining_target')!=p or reply.get('server_observed_state')!='Block{minecraft:air}':raise RuntimeError('Original wall removal unconfirmed; no retry')
            write_json(out/('wall-%d-native.json'%len(book['mines'])),reply);removed.add(tuple(p));expected[item]+=1;book['mines'].append({'pos':p,'item':item,'request_id':c.last});book['pending']=None;write_json(path,book)
        air_cells(c,[cells[i-1],cell],out/('newly-confirmed-air-%02d'%i),checkpoint)
        end=time.monotonic()+4
        while any(inventory_counts(checkpoint())[item]<before[item]+amount for item,amount in expected.items()):
            if time.monotonic()>end:raise RuntimeError('Exact wall byproducts not retained; no next opening')
            time.sleep(.15)
        start=i
    air_cells(c,cells[start:],out/'existing-final-air-to-water',checkpoint);q=checkpoint();book.update(complete=True,pending=None,actual=q['pos'],all_byproducts_retained=True,new_mines=len(removed));write_json(path,book);return book
