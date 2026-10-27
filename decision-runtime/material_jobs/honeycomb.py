"""Shear one ripe wild nest with a proved, covered smoke source; keep the nest."""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import cell_at
from projection_completion import block_state
from work_access import approach_faces
from drop_collection import collect_drop
from ground_pickup import clear_body
from .colored_sources import _protected
from .acquisition import block_id

def smoke_plan(rows,nest):
    by={tuple(v['pos']):v for v in rows};x,y,z=nest['pos']
    if block_id(nest)!='minecraft:bee_nest'or block_state(nest['state'])[1].get('honey_level')!='5':return None
    for distance in range(2,6):
        fire=[x,y-distance,z];cover=[x,fire[1]+1,z];soil=by.get((x,fire[1]-1,z))
        if not soil or not soil.get('solid')or soil.get('fluid')or soil.get('block_entity'):continue
        if block_id(soil)not in('minecraft:grass_block','minecraft:dirt','minecraft:stone','minecraft:coarse_dirt','minecraft:podzol'):continue
        if any((x,h,z)in by for h in range(fire[1],y)):continue
        return {'nest':nest,'campfire':fire,'cover':cover,'support':soil,'smoke_distance':distance}
    return None

def harvest(c,plan,profile,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);path=out/'honeycomb.json';nest=plan['nest'];p=nest['pos'];fire=plan['campfire'];cover=plan['cover'];soil=plan['support']
    if _protected(p,profile,checkpoint()):raise RuntimeError('Wild honey nest overlaps protected construction')
    before=inventory_counts(checkpoint())
    if before['minecraft:campfire']!=1 or before['minecraft:stone_slab']<2 or before['minecraft:shears']<1:raise RuntimeError('Actual smoke source, spare cover, and shears required')
    book={'world_session':c.world,'plan':plan,'inventory_before':dict(before),'pending':None,'complete':False,'steps':[]};write_json(path,book)
    def verify(pos,predicate,label):
        end=time.monotonic()+6;stamps=[]
        while True:
            q=checkpoint();r=cell_at(c,pos)
            if predicate(r)and q['time']not in stamps:stamps.append(q['time'])
            if len(stamps)>=2:return r
            if time.monotonic()>end:raise RuntimeError(label+' unconfirmed; no repeated use')
            time.sleep(.1)
    def use(pos,face,expected,item,label):
        checkpoint();c.checked('select_item',item=item);book['pending']={'kind':label};write_json(path,book)
        try:r=c.checked('interact',pos=pos,face=face,expected_state=expected,expected_hand=item)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        write_json(out/(label+'-native.json'),r)
    # Start at a normal native approach, then move to a separately proved side
    # before lighting anything. No work pose can be above the future flame.
    approach_faces(c,soil['pos'],soil['state'],('up',),seconds=45,stand_distance=2.8)
    low=[fire[0]-4,fire[1]-1,fire[2]-4];high=[fire[0]+4,p[1]+3,fire[2]+4]
    scene=c.request('scan',min=low,max=high,details=True)
    if scene.get('phase')!='done'or scene.get('scan_cells_read')!=math.prod(b-a+1 for a,b in zip(low,high)):raise RuntimeError('Actual honey work area not fully loaded')
    by={tuple(v['pos']):v for v in scene['blocks']}
    if cell_at(c,p)['state']!=nest['state']or any((fire[0],h,fire[2])in by for h in range(fire[1],p[1])):raise RuntimeError('Original ripe nest or smoke column changed')
    poses=[[fire[0]+.5+dx,fire[1]+.1,fire[2]+.5+dz]for dx,dz in[(1.5,0),(-1.5,0),(0,1.5),(0,-1.5)]]
    poses=[q for q in poses if clear_body(q,by)]
    if not poses:raise RuntimeError('No flame-separated honey work pose')
    pose=min(poses,key=lambda q:math.dist(q,checkpoint()['pos']))
    c.checked('navigate',target=pose,arrival=.08,air_only=True,seconds=30)
    q=checkpoint()
    if math.hypot(q['pos'][0]-fire[0]-.5,q['pos'][2]-fire[2]-.5)<1.35:raise RuntimeError('Actual work pose too close to future campfire')
    use(soil['pos'],'up',soil['state'],'minecraft:campfire','one_normal_campfire_placement')
    actual_fire=verify(fire,lambda v:block_id(v)=='minecraft:campfire'and block_state(v['state'])[1].get('lit')=='true','Lit campfire')
    if inventory_counts(checkpoint())['minecraft:campfire']!=before['minecraft:campfire']-1:raise RuntimeError('Campfire stock consumption unconfirmed')
    book['steps'].append('campfire_confirmed');book['pending']=None;write_json(path,book)
    use(fire,'up',actual_fire['state'],'minecraft:stone_slab','one_normal_stone_cover_placement')
    cover_row=verify(cover,lambda v:block_id(v)=='minecraft:stone_slab'and block_state(v['state'])[1].get('type')=='bottom','Bee/player fire cover')
    if inventory_counts(checkpoint())['minecraft:stone_slab']!=before['minecraft:stone_slab']-1:raise RuntimeError('Fire cover consumption unconfirmed')
    book['steps'].append('cover_confirmed');book['pending']=None;write_json(path,book)
    # Vanilla CampfireBlock.isSmokeyPos checks 1..5 blocks down; a collision
    # directly above a lit campfire still sees that adjacent smoke source.
    for h in range(cover[1]+1,p[1]):
        if cell_at(c,[p[0],h,p[2]])['state']!='Block{minecraft:air}':raise RuntimeError('Smoke route changed above the cover')
    if block_state(cell_at(c,fire)['state'])[1].get('lit')!='true'or cell_at(c,cover)['state']!=cover_row['state']:raise RuntimeError('Covered smoke source changed')
    face=block_state(nest['state'])[1]['facing'];approach_faces(c,p,nest['state'],(face,),seconds=45,stand_distance=2.8)
    if cell_at(c,p)['state']!=nest['state']:raise RuntimeError('Ripe nest changed before shearing')
    old={e['uuid']for e in checkpoint().get('entities',[])if e['type']=='minecraft:item'}
    use(p,face,nest['state'],'minecraft:shears','one_smoked_nest_shear')
    empty=verify(p,lambda v:block_id(v)=='minecraft:bee_nest'and block_state(v['state'])[1].get('honey_level')=='0','Retained emptied bee nest')
    end=time.monotonic()+15
    while inventory_counts(checkpoint())['minecraft:honeycomb']<before['minecraft:honeycomb']+3:
        q=checkpoint();drops=[e for e in q.get('entities',[])if e['type']=='minecraft:item'and e['uuid']not in old and e.get('stack',{}).get('item')=='minecraft:honeycomb'and math.dist(e['pos'],[v+.5 for v in p])<8]
        for d in drops:
            if not collect_drop(c,d,q,seconds=20):raise RuntimeError('New honeycomb drop not confirmed; no repeated shear')
        if inventory_counts(checkpoint())['minecraft:honeycomb']>=before['minecraft:honeycomb']+3:break
        if time.monotonic()>end:raise RuntimeError('Actual honeycomb inventory unconfirmed')
        time.sleep(.15)
    book['steps'].append('actual_three_honeycomb_and_retained_nest_confirmed');book['pending']=None;write_json(path,book)
    actual_fire=cell_at(c,fire);face=approach_faces(c,fire,actual_fire['state'],('west','east','north','south'),seconds=45,stand_distance=2.8)
    use(fire,face,actual_fire['state'],'minecraft:diamond_shovel','one_campfire_extinguish')
    off=verify(fire,lambda v:block_id(v)=='minecraft:campfire'and block_state(v['state'])[1].get('lit')=='false','Extinguished reusable campfire')
    book.update(pending=None,complete=True,actual_honeycomb_gain=inventory_counts(checkpoint())['minecraft:honeycomb']-before['minecraft:honeycomb'],nest_preserved=True,cover_preserved=True,campfire_extinguished=True,actual_empty_nest=empty,actual_unlit_fire=off);write_json(path,book)
    return book
