"""Finite alternating-column dry probe; never mine the current support column."""
from collections import Counter
from pathlib import Path
import math,time
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from projection_wood import cell_at
from work_access import approach_faces
from kit_runtime.journal import write_json
from .acquisition import _choose_tool
from .colored_sources import _protected
from .roof_harvest import light_supports

DROPS={'minecraft:stone':'minecraft:cobblestone','minecraft:granite':'minecraft:granite','minecraft:andesite':'minecraft:andesite','minecraft:diorite':'minecraft:diorite','minecraft:dripstone_block':'minecraft:dripstone_block'}
def bid(r):return r.get('state','').split('}')[0].removeprefix('Block{')
def run(c,plan,profile,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);path=out/'probe.json'
    if plan.get('world_session')!=c.world or plan.get('maximum_new_mines')!=32 or not 0<=plan.get('actual_planned_mines',999)<=32:raise ValueError('Current finite32-block dry probe plan required')
    floor=plan['start_floor'];before=checkpoint();book={'world_session':c.world,'plan':plan,'inventory_before':dict(inventory_counts(before)),'pending':None,'mines':[],'moves':[],'complete':False};write_json(path,book)
    if not floor or cell_at(c,floor['pos'])['state']!=floor['state']:raise RuntimeError('Actual probe start floor changed')
    approach_faces(c,floor['pos'],floor['state'],('up',),seconds=60,stand_distance=.65)
    picks=[r for r in checkpoint()['inventory']if r.get('slot',99)<36 and r.get('count')==1 and r.get('item')in('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')and r.get('durability',0)>=96 and not any(e['id']=='minecraft:silk_touch'for e in r.get('enchantments',[]))]
    if not picks:raise RuntimeError('Owned non-Silk pickaxe with96 durability required')
    tool=max(picks,key=lambda r:(max((e['level']for e in r.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),r['durability']));_choose_tool(c,tool,checkpoint)
    def move_to(point,label):
        q=checkpoint();book['pending']={'kind':'one_normal_probe_air_move','target':point,'label':label};write_json(path,book)
        try:r=c.checked('navigate',target=point,arrival=.08,air_only=True,seconds=20)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        write_json(out/(label+'-native.json'),r);q=checkpoint();book['moves'].append({'target':point,'actual':q['pos'],'request_id':c.last});book['pending']=None;write_json(path,book)
    move_to(plan['start_pose'],'verified-start-pose')
    for index,step in enumerate(plan['steps']):
        q=checkpoint();standing=step['standing_column'];target_col=step['target_column'];expected=Counter();counts=inventory_counts(q)
        if(q.get('health')!=20 or q.get('guard_busy')or not q.get('flight')or q.get('under_water')or abs(q['pos'][0]-standing[0]-.5)>.2 or abs(q['pos'][2]-standing[2]-.5)>.2):raise RuntimeError('Current protected standing column changed before excavation')
        for row in step['mines']:
            p=row['pos'];item=DROPS.get(bid(row));q=checkpoint()
            if item is None or _protected(p,profile,q)or p[0]==math.floor(q['pos'][0])and p[2]==math.floor(q['pos'][2]):raise RuntimeError('Never excavate a protected or currently occupied support column')
            if len(book['mines'])>=32 or room_for_item(q,item)<2:raise RuntimeError('Finite mine budget or retained-drop capacity exhausted')
            scan=c.request('scan',min=[v-1 for v in p],max=[v+1 for v in p],details=True)
            if scan.get('phase')!='done'or scan.get('scan_cells_read')!=27:raise RuntimeError('Immediate natural target neighbourhood incomplete')
            by={tuple(v['pos']):v for v in scan['blocks']};actual=by.get(tuple(p))
            if not actual or actual['state']!=row['state']or actual.get('fluid')or actual.get('block_entity')or tuple(p)in light_supports(scan['blocks']):raise RuntimeError('Current target or retained light changed; no mine')
            if any(v.get('fluid')or v.get('block_entity')or bid(v)in('minecraft:gravel','minecraft:sand','minecraft:red_sand')for k,v in by.items()if sum(abs(k[i]-p[i])for i in range(3))==1):
                book.update(boundary_reached=True,boundary_target=p,pending=None);write_json(path,book);return book
            current_tools=[r for r in checkpoint()['inventory']if r.get('slot',99)<36 and r.get('count')==1 and r.get('item')in('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')and r.get('durability',0)>=65-len(book['mines'])and not any(e['id']=='minecraft:silk_touch'for e in r.get('enchantments',[]))]
            if not current_tools:raise RuntimeError('Current carried pickaxe reserve changed')
            tool=max(current_tools,key=lambda r:(max((e['level']for e in r.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),r['durability']))
            _choose_tool(c,tool,checkpoint);book['pending']={'kind':'one_new_dry_natural_mine','pos':p,'expected_state':row['state']};write_json(path,book)
            try:r=c.checked('mine_block',pos=p,face='up',expected_state=row['state'],seconds=15)
            finally:book['pending']['request_id']=c.last;write_json(path,book)
            if(r.get('server_confirmed')is not True or r.get('mining_target')!=p or r.get('server_observed_state')!='Block{minecraft:air}'):raise RuntimeError('Current mine lacks exact server removal proof; no repeat')
            write_json(out/('mine-%02d-native.json'%len(book['mines'])),r);book['mines'].append({'pos':p,'item':item,'request_id':c.last,'server_confirmed':True});expected[item]+=1;book['pending']=None;write_json(path,book)
        # Horizontal above the old floor, then vertical in the newly opened
        # column. A diagonal down sweep would intersect the preserved floor.
        q=checkpoint();level=[target_col[0]+.5,q['pos'][1],target_col[2]+.5];move_to(level,'step-%02d-horizontal'%index);move_to(step['next_pose'],'step-%02d-lower'%index)
        end=time.monotonic()+4
        while any(inventory_counts(checkpoint())[i]<counts[i]+n for i,n in expected.items()):
            if time.monotonic()>end:raise RuntimeError('Current ordinary byproducts not in inventory; no further excavation')
            time.sleep(.15)
        c.set_progress(phase='既有采区短探路 · 已开%d／最多32块，当前Y%d'%(len(book['mines']),math.floor(checkpoint()['pos'][1])))
    q=checkpoint();book.update(complete=True,target_y_reached=q['pos'][1]<plan['target_y']+.4,actual=q['pos'],inventory_after=dict(inventory_counts(q)),all_byproducts_retained=True);write_json(path,book);return book
