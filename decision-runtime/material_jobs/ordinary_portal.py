"""Build one ordinary fourteen-obsidian utility portal on a proved empty grass plot."""
import time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import cell_at,use_with_margin
from .local_air_path import move

AIR='Block{minecraft:air}'
OBSIDIAN='Block{minecraft:obsidian}'


def frame(root):
    if len(root)!=3 or any(type(v)is not int for v in root):raise ValueError('Integer full-frame origin required')
    x,y,z=root
    return [[x+u,y,z]for u in range(4)]+[[x+u,y+v,z]for u in(0,3)for v in(1,2,3)]+[[x+u,y+4,z]for u in range(4)]


def empty_grass_plot(rows,root):
    positions=frame(root);cells=rows if isinstance(rows,dict)else{tuple(r['pos']):r for r in rows};x,y,z=root
    for u in range(4):
        support=cells.get((x+u,y-1,z),{})
        if (not support.get('state','').startswith('Block{minecraft:grass_block}')or not support.get('solid')
                or support.get('fluid')or support.get('block_entity')):return False
    core=[[x+u,y+v,z]for u in(1,2)for v in(1,2,3)]
    if any(tuple(p)in cells for p in positions+core):return False
    # Access may pass through untouched collision-free grass. Frame and portal
    # cells themselves must be air; no plant is replaced or harvested.
    soft={'minecraft:short_grass','minecraft:tall_grass','minecraft:fern','minecraft:large_fern'}
    from projection_completion import block_state
    for u in range(-2,6):
        for v in range(6):
            for d in range(-2,3):
                row=cells.get((x+u,y+v,z+d))
                if row and(block_state(row['state'])[0]not in soft or row.get('passable')is not True
                           or row.get('fluid')is not False or row.get('block_entity')is not False):return False
    return True


def outside_regions(root,regions):
    x,_,z=root
    for region in regions:
        lo,hi=region.get('min'),region.get('max')
        if (not isinstance(lo,list)or not isinstance(hi,list)or len(lo)!=3 or len(hi)!=3
                or any(type(v)is not int for v in lo+hi)):
            raise ValueError('Existing protected region bounds must be retained exactly')
        if not(x+6<lo[0]or x-3>hi[0]or z+4<lo[2]or z-4>hi[2]):return False
    return True


def build(c,root,out,checkpoint,*,protected_regions=()):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);q=checkpoint()
    if q['dimension']!='minecraft:overworld'or q['health']!=20 or inventory_counts(q)['minecraft:obsidian']<14:
        raise RuntimeError('Full actual obsidian batch and healthy Overworld owner required')
    x,y,z=root;selection=q.get('projection_selection')or{};low,high=selection.get('min'),selection.get('max')
    if not outside_regions(root,protected_regions):raise RuntimeError('Portal and all access stances must remain outside existing protected regions')
    if low and not(x+5<low[0]or x-2>high[0]or z+2<low[2]or z-2>high[2]):
        raise RuntimeError('Utility portal must be outside the original construction footprint')
    lo=[x-2,y-1,z-2];hi=[x+5,y+5,z+2];scan=c.request('scan',min=lo,max=hi,details=True)
    if scan.get('phase')!='done'or not empty_grass_plot(scan['blocks'],root):raise RuntimeError('Actual empty dry grass plot required; no blocks removed')
    before=inventory_counts(q)['minecraft:obsidian'];positions=frame(root);book={'world_session':c.world,'root':root,'frame':positions,'before_obsidian':before,'placed':[],'pending':None,'complete':False,'mining_sent':False};path=out/'portal-build.json';write_json(path,book)
    for i,p in enumerate(positions):
        checkpoint();stock=inventory_counts(c.status())['minecraft:obsidian'];assert stock==before-i
        if cell_at(c,p)['state']!=AIR:raise RuntimeError('Frame target changed; preserve the new block')
        anchor=[p[0],p[1]-1,p[2]];face='up';support=cell_at(c,anchor)
        if support['state']!=OBSIDIAN and not(p[1]==y and support['state'].startswith('Block{minecraft:grass_block}')):
            anchor=[p[0]-1,p[1],p[2]];face='east';support=cell_at(c,anchor)
            if support['state']!=OBSIDIAN:raise RuntimeError('Previously verified ordinary frame support missing')
        c.checked('select_item',item='minecraft:obsidian');book['pending']={'kind':'one_normal_obsidian_placement','pos':p,'stock_before':stock};write_json(path,book)
        def unchanged():
            checkpoint()
            if cell_at(c,p)['state']!=AIR or inventory_counts(c.status())['minecraft:obsidian']!=stock:raise RuntimeError('Frame cell or stock changed before use')
        try:use_with_margin(c,anchor,support['state'],'minecraft:obsidian',(face,),unchanged)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        end=time.monotonic()+6;stamps=[]
        while True:
            checkpoint();actual=cell_at(c,p)['state'];q=c.status()
            if actual==OBSIDIAN and inventory_counts(q)['minecraft:obsidian']==stock-1 and q['time']not in stamps:stamps.append(q['time'])
            elif actual!=OBSIDIAN:stamps=[]
            if len(stamps)>=2:break
            if time.monotonic()>end:raise RuntimeError('Original obsidian placement unconfirmed; no repeat')
            time.sleep(.1)
        book['placed'].append({'pos':p,'actual':actual,'inventory_after':stock-1,'ordinary_world_and_stock_checks':True});book['pending']=None;write_json(path,book)
        c.set_progress(done=i+1,phase='原版下界门框 %d／14'%(i+1))
    for p in positions:
        if cell_at(c,p)['state']!=OBSIDIAN:raise RuntimeError('Completed frame changed before lighting')
    core=[[x+u,y+v,z]for u in(1,2)for v in(1,2,3)]
    if any(cell_at(c,p)['state']!=AIR for p in core):raise RuntimeError('Portal interior changed; no ignition')
    move(c,[x+1.5,y+1.1,z-2.5],out/'outside-ignition-pose',foot_offset=.1,max_horizontal=24,exact_target=True)
    c.checked('select_item',item='minecraft:flint_and_steel');book['pending']={'kind':'one_normal_portal_ignition','core':core};write_json(path,book)
    try:r=c.checked('interact',pos=[x+1,y,z],face='up',expected_state=OBSIDIAN,expected_hand='minecraft:flint_and_steel')
    finally:book['pending']['request_id']=c.last;write_json(path,book)
    write_json(out/'native-ignition-use.json',r);end=time.monotonic()+6;stamps=[]
    while True:
        checkpoint();matches=all(cell_at(c,p)['state']=='Block{minecraft:nether_portal}[axis=x]'for p in core);q=c.status()
        if matches and q['time']not in stamps:stamps.append(q['time'])
        elif not matches:stamps=[]
        if len(stamps)>=2:break
        if time.monotonic()>end:raise RuntimeError('Original portal ignition unconfirmed; no repeated fire use')
        time.sleep(.1)
    book.update(complete=True,pending=None,actual_obsidian=inventory_counts(q)['minecraft:obsidian'],entry_root=core[0],axis='x',health=q['health']);write_json(path,book);return book
