"""Harvest above a live wild bamboo base and plant retained propagules normally."""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import cell_at
from work_access import approach_faces
from drop_collection import collect_drop
from .acquisition import block_id
from .colored_sources import _protected
from .local_air_path import move,plan

def pickup_side_poses(rows,base,player,low,high):
    """Keep the whole body inside a proved neighbouring air cell, near drops."""
    result=[];x,y,z=base
    for face,dx,dz in [('west',-.82,0),('east',.82,0),('north',0,-.82),('south',0,.82)]:
        point=[x+.5+dx,y+.1,z+.5+dz]
        try:plan(rows,player,point,low,high,foot_offset=.1)
        except RuntimeError:continue
        # The .18 edge offset reserves .02 beyond the ordinary .6-wide body.
        result.append((face,point))
    return sorted(result,key=lambda v:math.dist(v[1],player))

ITEM='minecraft:bamboo'
def columns(rows):
    by={tuple(v['pos']):v for v in rows};result=[]
    for p,r in by.items():
        x,y,z=p
        if block_id(r)!=ITEM or (x,y-1,z)in by and block_id(by[x,y-1,z])==ITEM:continue
        upper=by.get((x,y+1,z));support=by.get((x,y-1,z))
        if not upper or block_id(upper)!=ITEM or not support or not support.get('solid')or support.get('fluid'):continue
        height=1
        while (x,y+height,z)in by and block_id(by[x,y+height,z])==ITEM:height+=1
        result.append({'base':list(p),'target':[x,y+1,z],'height':height})
    return sorted(result,key=lambda v:-v['height'])

def harvest(c,column,profile,out,checkpoint,*,owned_parent=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);p=column['target'];base=column['base']
    q=checkpoint()
    own=(isinstance(owned_parent,dict)and owned_parent.get('complete')is True
         and owned_parent.get('live_parent')is True and owned_parent.get('world_session')==c.world
         and owned_parent.get('pos')==base and p==[base[0],base[1]+1,base[2]])
    if _protected(p,profile,q)and not own:raise RuntimeError('Wild bamboo overlaps protected construction')
    lower=cell_at(c,base);target=cell_at(c,p)
    if block_id(lower)!=ITEM or block_id(target)!=ITEM:raise RuntimeError('Current living bamboo base and upper segment required')
    face=approach_faces(c,p,target['state'],('west','east','south','north'),seconds=45,stand_distance=2.8)
    q=checkpoint();low=[min(math.floor(q['pos'][i]),base[i])-4 for i in range(3)];high=[max(math.floor(q['pos'][i]),p[i])+4 for i in range(3)];high[1]+=2
    scene=c.request('scan',min=low,max=high,details=True)
    if scene.get('phase')!='done'or scene.get('scan_cells_read')!=math.prod(b-a+1 for a,b in zip(low,high)):raise RuntimeError('Bamboo pickup-side area incomplete')
    choices=pickup_side_poses(scene['blocks'],base,q['pos'],low,high)
    if not choices:raise RuntimeError('No proved full-air bamboo pickup side; no mining sent')
    face,pose=choices[0];move(c,pose,out/'preposition-drop-pickup-side',foot_offset=.1,exact_target=True,scan_bounds={'min':low,'max':high})
    c.checked('select_item',item='minecraft:netherite_sword');before=checkpoint();count=inventory_counts(before)[ITEM]
    old={e['uuid']for e in before.get('entities',[])if e['type']=='minecraft:item'}
    book={'world_session':c.world,'base':base,'target':p,'inventory_before':count,'pending':'one_upper_bamboo_mine','complete':False};path=out/'bamboo.json';write_json(path,book)
    try:r=c.checked('mine_block',pos=p,face=face,expected_state=target['state'],seconds=15)
    finally:book['request_id']=c.last;write_json(path,book)
    write_json(out/'upper-mine-native.json',r)
    if block_id(cell_at(c,base))!=ITEM or cell_at(c,p)['state']!='Block{minecraft:air}':raise RuntimeError('Retained bamboo base or original mining not confirmed')
    end=time.monotonic()+18;seen=set()
    while time.monotonic()<end:
        q=checkpoint();drops=[e for e in q.get('entities',[])if e['type']=='minecraft:item'and e['uuid']not in old and e['uuid']not in seen and e.get('stack',{}).get('item')==ITEM and math.dist(e['pos'],[base[0]+.5,base[1]+1,base[2]+.5])<20]
        if drops:
            for d in drops:
                seen.add(d['uuid']);observed=checkpoint()
                if not collect_drop(c,d,observed,seconds=20):raise RuntimeError('New bamboo drop not confirmed; no repeat harvest')
            if inventory_counts(checkpoint())[ITEM]>count:break
        if inventory_counts(q)[ITEM]>count:break
        time.sleep(.15)
    after=inventory_counts(checkpoint())[ITEM]
    if after<=count:raise RuntimeError('No actual bamboo inventory gain; retain original harvest receipt')
    book.update(pending=None,complete=True,inventory_after=after,base_preserved=block_id(cell_at(c,base))==ITEM);write_json(path,book);return book

def plant(c,pos,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);soil=[pos[0],pos[1]-1,pos[2]];support=cell_at(c,soil)
    if block_id(support)not in('minecraft:grass_block','minecraft:dirt','minecraft:podzol','minecraft:sand')or support.get('fluid')or support.get('block_entity')or cell_at(c,pos)['state']!='Block{minecraft:air}':raise RuntimeError('Unchanged empty dry bamboo nursery cell required')
    before=inventory_counts(checkpoint())[ITEM]
    if before<2:raise RuntimeError('Keep an additional carried bamboo propagule')
    approach_faces(c,soil,support['state'],('up',),seconds=30,stand_distance=2.8);c.checked('select_item',item=ITEM)
    write_json(out/'intent.json',{'world_session':c.world,'pos':pos,'before':before,'pending':'one_normal_bamboo_plant'})
    r=c.checked('interact',pos=soil,face='up',expected_state=support['state'],expected_hand=ITEM);write_json(out/'native-use.json',r)
    until=time.monotonic()+6;stamps=[]
    while True:
        q=checkpoint();actual=cell_at(c,pos)
        if block_id(actual)in('minecraft:bamboo_sapling',ITEM)and inventory_counts(q)[ITEM]==before-1 and q['time']not in stamps:stamps.append(q['time'])
        if len(stamps)>=2:break
        if time.monotonic()>until:raise RuntimeError('Nursery bamboo use unconfirmed; do not repeat')
        time.sleep(.1)
    result={'world_session':c.world,'complete':True,'pos':pos,'actual':actual,'inventory_after':before-1,'live_parent':True};write_json(out/'complete.json',result);return result

def produce(c,parent,target,profile,out,checkpoint):
    """Use normal bone meal and harvest only above this normally planted parent."""
    if(parent.get('world_session')!=c.world or parent.get('complete')is not True or parent.get('live_parent')is not True
       or type(target)is not int or not 1<=target<=32):raise ValueError('Current normally planted parent and finite carried target required')
    root=parent['pos'];out=Path(out);out.mkdir(parents=True,exist_ok=False);path=out/'nursery-production.json';book={'world_session':c.world,'parent':parent,'target':target,'pending':None,'cycles':[],'complete':False};write_json(path,book)
    def height():
        r=c.request('scan',min=root,max=[root[0],root[1]+17,root[2]],details=True)
        if r.get('phase')!='done'or r.get('scan_cells_read')!=18:raise RuntimeError('Current nursery bamboo column incomplete')
        rows={tuple(v['pos']):v for v in r['blocks']};h=0
        while(root[0],root[1]+h,root[2])in rows and block_id(rows[root[0],root[1]+h,root[2]])in(ITEM,'minecraft:bamboo_sapling'):h+=1
        if h<1:raise RuntimeError('Original planted live bamboo parent missing')
        return h
    # First reach the recorded parent from another nursery cell normally.
    # The bounded side scan then covers the actual starting body as well.
    row=cell_at(c,root);approach_faces(c,root,row['state'],('west','east','north','south'),seconds=30,stand_distance=2.8)
    # Stand beside, rather than above, the future growing stalk.
    q=checkpoint();low=[root[0]-4,root[1]-1,root[2]-4];high=[root[0]+4,root[1]+5,root[2]+4]
    r=c.request('scan',min=low,max=high,details=True)
    if r.get('phase')!='done':raise RuntimeError('Bamboo nursery side body area incomplete')
    poses=pickup_side_poses(r['blocks'],root,q['pos'],low,high)
    if not poses:raise RuntimeError('No clear side for growing owned bamboo')
    face,pose=poses[0];move(c,pose,out/'safe-growing-side',foot_offset=.1,exact_target=True,scan_bounds={'min':low,'max':high})
    for cycle in range(12):
        checkpoint()
        if inventory_counts(c.status())[ITEM]>=target:break
        h=height()
        if h<5:
            before=inventory_counts(checkpoint())['minecraft:bone_meal']
            if before<1:raise RuntimeError('No actual bone meal for retained bamboo parent')
            row=cell_at(c,root);c.checked('select_item',item='minecraft:bone_meal');book['pending']={'kind':'one_owned_bamboo_bone_meal','cycle':cycle,'height_before':h};write_json(path,book)
            try:r=c.checked('interact',pos=root,face=face,expected_state=row['state'],expected_hand='minecraft:bone_meal')
            finally:book['pending']['request_id']=c.last;write_json(path,book)
            write_json(out/('bone-%02d-native.json'%cycle),r);until=time.monotonic()+6
            while True:
                checkpoint();now=height()
                if now>h and inventory_counts(c.status())['minecraft:bone_meal']==before-1:break
                if time.monotonic()>until:raise RuntimeError('Owned bamboo fertilization unconfirmed; no repeat')
                time.sleep(.15)
            book['cycles'].append({'kind':'bone_meal','height_before':h,'height_after':now});book['pending']=None;write_json(path,book)
        else:
            result=harvest(c,{'base':root,'target':[root[0],root[1]+1,root[2]]},profile,out/('owned-harvest-%02d'%cycle),checkpoint,owned_parent=parent)
            book['cycles'].append({'kind':'upper_harvest','result':result});write_json(path,book)
    if inventory_counts(checkpoint())[ITEM]<target:raise RuntimeError('Finite owned bamboo batch incomplete')
    book.update(complete=True,carried_bamboo=inventory_counts(c.status())[ITEM],live_parent=cell_at(c,root));write_json(path,book);return book
