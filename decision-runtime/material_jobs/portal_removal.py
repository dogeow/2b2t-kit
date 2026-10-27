"""Remove only a user's exact cancelled portal frame with ordinary mining."""
from pathlib import Path
import math,time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from .ordinary_portal import frame
from .acquisition import _scan,_choose_tool
from .local_air_path import move
from .roof_harvest import light_supports

OBSIDIAN='minecraft:obsidian'
STATE='Block{minecraft:obsidian}'

def targets(authorization,world):
    a=authorization
    if (a.get('world_session')!=world or a.get('server')!='simpcraft.com'
            or a.get('dimension')!='minecraft:overworld' or a.get('no_dimension_entry')is not True
            or not a.get('user_instruction') or a.get('maximum_mines')!=14 or a.get('expected_state')!=STATE):
        raise ValueError('Explicit exact14 Overworld portal-removal authorization required')
    wanted=frame(a['root']);actual=a.get('targets',[])
    if len(actual)!=14 or len(set(map(tuple,actual)))!=14 or set(map(tuple,actual))!=set(map(tuple,wanted)):
        raise ValueError('Only the14 original frame cells may be removed')
    return wanted

def remove(c,authorization,out,checkpoint):
    wanted=targets(authorization,c.world);root=authorization['root'];x,y,z=root
    out=Path(out);out.mkdir(parents=True,exist_ok=False);file=out/'removal.json'
    def state():
        q=checkpoint()
        if (q.get('dimension')!='minecraft:overworld' or q.get('world_session')!=c.world
                or q.get('health')!=20 or q.get('under_water') or not q.get('flight')or q.get('guard_busy')):
            raise RuntimeError('Current healthy guarded Overworld owner required')
        return q
    initial=state();before=inventory_counts(initial)[OBSIDIAN]
    rows=_scan(c,[x,y,z],[x+3,y+4,z],state);by={tuple(r['pos']):r for r in rows}
    existing=[p for p in wanted if tuple(p)in by]
    if any(by[tuple(p)]['state']!=STATE or by[tuple(p)].get('fluid')or by[tuple(p)].get('block_entity')for p in existing):
        raise RuntimeError('Original frame cell contains another block; preserve it')
    book={'world_session':c.world,'authorization':authorization,'initial_obsidian':before,
          'already_absent':[p for p in wanted if p not in existing],'mines':[],
          'pending':None,'portal_extinguished':False,'dimension_entry_dispatched':False,'complete':False}
    write_json(file,book)
    core=[[x+u,y+v,z]for u in(1,2)for v in(1,2,3)]
    def extinguished():return not _scan(c,[x+1,y+1,z],[x+2,y+3,z],state)
    def mine(p):
        q=state();local=_scan(c,[v-1 for v in p],[v+1 for v in p],state)
        live=next((r for r in local if r['pos']==p),None)
        if (p not in wanted or not live or live['state']!=STATE or live.get('fluid')or live.get('block_entity')
                or tuple(p)in light_supports(local)or p==[math.floor(q['pos'][0]),math.floor(q['pos'][1])-1,math.floor(q['pos'][2])]):
            raise RuntimeError('Exact original obsidian target or current footing changed')
        if any(r.get('fluid')for r in local if sum(abs(r['pos'][i]-p[i])for i in range(3))==1):
            raise RuntimeError('Liquid boundary retained')
        q=state()
        tools=[r for r in q['inventory']if 0<=r.get('slot',99)<36 and r.get('count')==1
               and r.get('item')in('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')and r.get('durability',0)>=96]
        if not tools or room_for_item(q,OBSIDIAN)<1:raise RuntimeError('Actual pickaxe reserve or recovery space missing')
        tool=max(tools,key=lambda r:(max((e['level']for e in r.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),r['durability']))
        _choose_tool(c,tool,state);book['pending']={'kind':'one_original_frame_mine','pos':p,'before':inventory_counts(state())[OBSIDIAN]};write_json(file,book)
        try:r=c.request('mine_block',pos=p,face='north',expected_state=STATE,seconds=20)
        finally:book['pending']['request_id']=c.last;write_json(file,book)
        write_json(out/('mine-%02d-native.json'%len(book['mines'])),r)
        if (r.get('id')!=c.last or r.get('world_session')!=c.world or r.get('phase')!='done'
                or r.get('server_confirmed')is not True or r.get('mining_target')!=p
                or r.get('server_observed_state')!='Block{minecraft:air}'):
            raise RuntimeError('Original obsidian removal unconfirmed; never replay')
        book['mines'].append({**book['pending'],'server_confirmed':True});book['pending']=None;write_json(file,book)
    def collect(label):
        required=before+len(book['mines']);until=time.monotonic()+5
        while inventory_counts(state())[OBSIDIAN]<required:
            if time.monotonic()>=until:
                q=state();drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'
                    and e.get('stack',{}).get('item')==OBSIDIAN and x-2<=e['pos'][0]<=x+5
                    and y-2<=e['pos'][1]<=y+6 and z-2<=e['pos'][2]<=z+2]
                if not drops:raise RuntimeError('Original obsidian not yet recovered; no further mining')
                from drop_collection import collect_drop
                drop=min(drops,key=lambda e:math.dist(e['pos'],q['pos']))
                if not collect_drop(c,drop,observation=q,seconds=20):raise RuntimeError('Observed original obsidian pickup unconfirmed')
                if inventory_counts(state())[OBSIDIAN]<required:raise RuntimeError('Recovered obsidian count still incomplete')
                break
            time.sleep(.15)
        book['recovered_new_obsidian']=inventory_counts(state())[OBSIDIAN]-before;write_json(file,book)
    # Break an essential side cell before approaching any former portal space.
    essential=[p for p in existing if(p[0]in(x,x+3)and y<p[1]<y+4)
               or(p[0]in(x+1,x+2)and p[1]in(y,y+4))]
    first=[x,y+1,z]if[x,y+1,z]in essential else essential[0]if essential else None
    if first:
        mine(first);existing.remove(first)
    until=time.monotonic()+6
    while not extinguished():
        if time.monotonic()>until:raise RuntimeError('Portal interior has not vanished; do not approach or enter')
        time.sleep(.15)
    book['portal_extinguished']=True;write_json(file,book)
    if first:
        move(c,[first[0]+.5,y+.1,z-.5],out/'first-safe-front-pickup',max_straight=2,foot_offset=.1,max_horizontal=12,exact_target=True)
        collect('first')
    for i,p in enumerate(sorted(existing,key=lambda p:(-p[1],p[0]))):
        point=[p[0]+.5,y+.1,z-.5]
        if math.dist(state()['pos'],point)>.15:
            move(c,point,out/('front-pose-%02d'%i),max_straight=2,foot_offset=.1,max_horizontal=12,exact_target=True)
        mine(p);collect(str(i));c.set_progress(done=len(book['mines']),phase='下界门已拆%d／14块，黑曜石已回收'%len(book['mines']))
    checks=[]
    for _ in range(2):
        observed=_scan(c,[x,y,z],[x+3,y+4,z],state)
        if observed:raise RuntimeError('Frame or portal cells still occupied; no completion claim')
        checks.append({'request_id':c.last,'time':state()['time'],'blocks':observed});time.sleep(.15)
    q=state();book.update(complete=True,actual_obsidian=inventory_counts(q)[OBSIDIAN],
        recovered_new_obsidian=inventory_counts(q)[OBSIDIAN]-before,final_frame_and_portal_checks=checks,
        removed_frame_cells=len(book['mines']),final_pos=q['pos'],health=q['health'])
    write_json(file,book);return book
