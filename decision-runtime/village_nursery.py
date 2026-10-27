"""One bounded 2x2 dark-oak supply tree through an existing sole action owner."""
from pathlib import Path
import time,math
from material_plan import inventory_counts
from kit_runtime.journal import write_json

from tree_planting_order import planting_order

def preflight(scan,root,low,high,world):
    volume=1
    for i in range(3):volume*=high[i]-low[i]+1
    if(scan.get('world_session')!=world or not 1<=volume<=50000
            or scan.get('scan_cells_read')!=volume or scan.get('scan_total_cells')!=volume
            or low[1]>root[1]-1 or high[1]<root[1]+18):
        raise RuntimeError('Full current-world nursery bounds are required')
    rows={tuple(v['pos']):v for v in scan['blocks']}
    if len(rows)!=len(scan['blocks']):raise RuntimeError('Duplicate nursery cells')
    for v in rows.values():
        if(v.get('block_entity')or v.get('fluid')or '_log}'in v['state']):
            raise RuntimeError('Nursery contains a container, fluid or existing trunk')
        if v['pos'][1]>=root[1]+2 and not('leaves}'in v['state']and'persistent=false'in v['state']):
            raise RuntimeError('Nursery canopy overlaps existing solid construction')
    for x in(root[0],root[0]+1):
        for z in(root[2],root[2]+1):
            f=rows.get((x,root[1]-1,z),{})
            if(f.get('state')not in('Block{minecraft:grass_block}[snowy=false]','Block{minecraft:dirt}')
                    or not f.get('solid')or(x,root[1],z)in rows or(x,root[1]+1,z)in rows):
                raise RuntimeError('Four empty roots on dry natural soil required')
    return rows

def grow(owner,root,low,high,path):
    path=Path(path)
    if path.exists():raise RuntimeError('Original nursery journal exists; never replay growth')
    book={'complete':False,'pending':None,'world_session':owner.world,'root':root,'min':low,'max':high,
          'plant_receipts':[],'bone_meal_receipts':[],'temporary_supply_tree':True}
    def save():write_json(path,book)
    def native(op,**params):
        book['pending']={'op':op,'params':params};save();r=owner.native(op,**params);book['pending']=None;save();return r
    def scan(lo,hi):
        r=native('scan',min=lo,max=hi,details=True)
        if r['scan_cells_read']!=r['scan_total_cells']:raise RuntimeError('Nursery scan incomplete')
        return r,{tuple(v['pos']):v for v in r['blocks']}
    def stock(expected):
        end=time.monotonic()+6;observed=[]
        while True:
            s=owner.status()
            if inventory_counts(s)==expected:
                if not observed or s['time']>observed[-1]:observed.append(s['time'])
                if len(observed)>=2:return observed
            else:observed=[]
            if time.monotonic()>end:raise RuntimeError('Original planting/fertilizer debit unconfirmed; no repeated input')
            time.sleep(.1)
    try:
        current=inventory_counts(owner.status())
        if current['minecraft:dark_oak_sapling']<4 or current['minecraft:bone_meal']<12:raise RuntimeError('Four real seeds and twelve available bone meal required')
        a,rows=scan(low,high);preflight(a,root,low,high,owner.world)
        protected={p:v['state']for p,v in rows.items()if any(k in v['state']for k in('fence','torch','stone_bricks','trapdoor','cobblestone'))}
        book['protected_before']=[{'pos':list(p),'state':v}for p,v in protected.items()];save()
        plants=[[root[0]+dx,root[1],root[2]+dz]for dx,dz in((0,0),(0,1),(1,0),(1,1))]
        plants=planting_order(plants,owner.status()['pos'])
        book['plant_order']=plants;save()
        for p in plants:
            native('select_item',item='minecraft:dark_oak_sapling');_,rows=scan([p[0],p[1]-1,p[2]],p)
            if tuple(p)in rows:raise RuntimeError('Original root changed before planting')
            before=inventory_counts(owner.status());f=[p[0],p[1]-1,p[2]];book['pending_effect']={'kind':'plant','pos':p,'before':dict(before)};save()
            r=native('interact',pos=f,face='up',expected_state=rows[tuple(f)]['state'],expected_hand='minecraft:dark_oak_sapling')
            _,rows=scan(p,p)
            if not rows[tuple(p)]['state'].startswith('Block{minecraft:dark_oak_sapling}'):raise RuntimeError('Planted root not observed')
            expected=before.copy();expected['minecraft:dark_oak_sapling']-=1;times=stock(+expected)
            book['plant_receipts'].append({'pos':p,'request':r['id'],'times':times});book['pending_effect']=None;save()
        for _ in range(12):
            _,rows=scan(root,[root[0]+1,root[1],root[2]+1])
            if all(rows.get(tuple(p),{}).get('state','').startswith('Block{minecraft:dark_oak_log}')for p in plants):break
            if not all(rows.get(tuple(p),{}).get('state','').startswith('Block{minecraft:dark_oak_sapling}')for p in plants):raise RuntimeError('Four original seedlings changed')
            native('select_item',item='minecraft:bone_meal');before=inventory_counts(owner.status());book['pending_effect']={'kind':'fertilize','before':dict(before)};save()
            r=native('interact',pos=root,face='up',expected_state=rows[tuple(root)]['state'],expected_hand='minecraft:bone_meal')
            expected=before.copy();expected['minecraft:bone_meal']-=1;times=stock(+expected);book['bone_meal_receipts'].append({'request':r['id'],'times':times});book['pending_effect']=None;save()
        a,rows=scan(low,high)
        if not all(rows.get(tuple(p),{}).get('state','').startswith('Block{minecraft:dark_oak_log}')for p in plants):raise RuntimeError('Known fertilizer uses did not grow the tree; preserve seedlings')
        if any(rows.get(p,{}).get('state')!=state for p,state in protected.items()):raise RuntimeError('Protected nursery surroundings changed')
        book.update(complete=True,pending=None,pending_effect=None,state='actual_tree_grown_harvest_pending',grown_logs=[v for v in a['blocks']if v['state'].startswith('Block{minecraft:dark_oak_log}')],after_inventory=dict(inventory_counts(owner.status())),health=owner.status()['health']);save();return book
    except Exception as e:book['error']=repr(e);save();raise
