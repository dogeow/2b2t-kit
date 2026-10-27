"""Bone-meal and shear one owned fern; keep a live parent for the next batch."""
from pathlib import Path
import time
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import cell_at
from projection_completion import block_state

SMALL='Block{minecraft:fern}'
LOWER='Block{minecraft:large_fern}[half=lower]'
UPPER='Block{minecraft:large_fern}[half=upper]'
AIR='Block{minecraft:air}'

def observe(c,pos,value,checkpoint,timeout=6):
    """Wait for delayed block packets without spending another input item."""
    until=time.monotonic()+timeout;stamps=[]
    while True:
        checkpoint();current=cell_at(c,pos)['state'];stamp=c.status()['time']
        if current==value and stamp not in stamps:stamps.append(stamp)
        elif current!=value:stamps=[]
        if len(stamps)>=2:return
        if time.monotonic()>until:raise RuntimeError('Fern world state unconfirmed; no repeat')
        time.sleep(.1)

def produce(c,root,target,out,checkpoint):
    if type(target)is not int or not 1<=target<=32 or len(root)!=3 or any(type(v)is not int for v in root):raise ValueError('Bounded fern nursery required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);x,y,z=root;soil=[x,y-1,z];top=[x,y+1,z]
    checkpoint();support=cell_at(c,soil)
    if block_state(support['state'])[0]not in ('minecraft:grass_block','minecraft:podzol','minecraft:dirt','minecraft:coarse_dirt','minecraft:rooted_dirt')or support.get('fluid')or support.get('block_entity'):
        raise RuntimeError('Nursery requires the recorded dry grass support')
    if any(cell_at(c,[x,yy,z])['state']!=AIR for yy in (y+1,y+2,y+3)):
        raise RuntimeError('Large fern and hovering body need an unchanged clear column')
    actual=cell_at(c,root)['state'];stock=inventory_counts(c.status())
    if actual not in (AIR,SMALL)or actual==AIR and stock['minecraft:fern']<2:raise RuntimeError('Keep one live fern and one carried propagule')
    if stock['minecraft:bone_meal']<target or stock['minecraft:shears']<1:raise RuntimeError('Actual bone meal and shears required')
    book={'world_session':c.world,'root':root,'soil':soil,'pending':None,'cycles':[],
          'inventory_before':dict(stock),'target':target,'complete':False,'parent_preserved':False};path=out/'fern-nursery.json'
    def save():write_json(path,book)
    def verify(pos,value):
        return observe(c,pos,value,checkpoint)
    def above(label):
        checkpoint();c.checked('navigate',target=[x+.5,y+2.2,z+.5],arrival=.15,air_only=True,seconds=20)
        write_json(out/(label+'-above.json'),{'actual':c.status()['pos'],'health':c.status()['health']})
    def plant(label):
        verify(root,AIR);before=inventory_counts(c.status())['minecraft:fern'];c.checked('select_item',item='minecraft:fern')
        book['pending']={'kind':'one_fern_replant','source':soil,'label':label};save()
        try:r=c.checked('interact',pos=soil,face='up',expected_state=support['state'],expected_hand='minecraft:fern')
        finally:book['pending']['request_id']=c.last;save()
        write_json(out/(label+'-plant-native.json'),r);verify(root,SMALL)
        if inventory_counts(c.status())['minecraft:fern']!=before-1:raise RuntimeError('Fern replant stock mismatch')
        book['pending']=None;save()
    save();above('initial')
    if actual==AIR:plant('initial')
    for i in range(target+2):
        checkpoint()
        if inventory_counts(c.status())['minecraft:fern']>=target:break
        above('cycle-%02d'%i);verify(root,SMALL);verify(top,AIR)
        before=inventory_counts(c.status());c.checked('select_item',item='minecraft:bone_meal')
        book['pending']={'kind':'one_fern_bone_meal','cycle':i};save()
        try:r=c.checked('interact',pos=root,face='up',expected_state=SMALL,expected_hand='minecraft:bone_meal')
        finally:book['pending']['request_id']=c.last;save()
        write_json(out/('cycle-%02d-bone-native.json'%i),r);verify(root,LOWER);verify(top,UPPER)
        if inventory_counts(c.status())['minecraft:bone_meal']!=before['minecraft:bone_meal']-1:raise RuntimeError('Bone meal consumption not confirmed')
        c.checked('select_item',item='minecraft:shears')
        if c.status()['hand']['item']!='minecraft:shears':raise RuntimeError('Actual shears must be held before harvesting')
        book['pending']={'kind':'one_large_fern_upper_shear','cycle':i};save()
        try:r=c.checked('mine_block',pos=top,face='up',expected_state=UPPER,seconds=10)
        finally:book['pending']['request_id']=c.last;save()
        write_json(out/('cycle-%02d-shear-native.json'%i),r);verify(root,AIR);verify(top,AIR)
        c.checked('navigate',target=[x+.5,y+.2,z+.5],arrival=.15,air_only=True,seconds=20)
        until=time.monotonic()+5
        while inventory_counts(c.status())['minecraft:fern']!=before['minecraft:fern']+2 and time.monotonic()<until:checkpoint();time.sleep(.15)
        if inventory_counts(c.status())['minecraft:fern']!=before['minecraft:fern']+2:raise RuntimeError('Actual two-fern shear yield not observed')
        book['pending']=None;save();plant('cycle-%02d'%i)
        now=inventory_counts(c.status());row={'cycle':i,'carried_fern':now['minecraft:fern'],'bone_meal':now['minecraft:bone_meal'],'live_parent':True};book['cycles'].append(row);save();print('RENEWABLE_FERN_CYCLE',row,flush=True)
        c.set_progress(done=min(target,now['minecraft:fern']),phase='家中留一株母蕨，已备 %d 株'%now['minecraft:fern'])
    verify(root,SMALL);verify(top,AIR);above('finished')
    now=inventory_counts(c.status())
    if now['minecraft:fern']<target:raise RuntimeError('Bounded nursery batch incomplete')
    book.update(complete=True,pending=None,parent_preserved=True,inventory_after=dict(now));save()
    return {'complete':True,'carried_fern':now['minecraft:fern'],'live_parent':root,'cycles':len(book['cycles']),'proof':str(path)}


def harvest_existing_large_to_parent(c,root,out,checkpoint):
    """Fresh-world replan: harvest the present plant, with no historical fertilization replay."""
    out=Path(out);out.mkdir(parents=True,exist_ok=False);x,y,z=root;upper=[x,y+1,z];soil=[x,y-1,z]
    observe(c,root,LOWER,checkpoint);observe(c,upper,UPPER,checkpoint);before=inventory_counts(c.status())
    c.checked('select_item',item='minecraft:shears')
    if c.status()['hand']['item']!='minecraft:shears':raise RuntimeError('Actual shears required')
    r=c.checked('mine_block',pos=upper,face='up',expected_state=UPPER,seconds=10);write_json(out/'existing-large-shear-native.json',r)
    observe(c,root,AIR,checkpoint);observe(c,upper,AIR,checkpoint)
    c.checked('navigate',target=[x+.5,y+.2,z+.5],arrival=.15,air_only=True,seconds=20)
    until=time.monotonic()+6
    while inventory_counts(c.status())['minecraft:fern']!=before['minecraft:fern']+2 and time.monotonic()<until:checkpoint();time.sleep(.15)
    if inventory_counts(c.status())['minecraft:fern']!=before['minecraft:fern']+2:raise RuntimeError('Existing large fern yield not observed')
    support=cell_at(c,soil);c.checked('select_item',item='minecraft:fern');r=c.checked('interact',pos=soil,face='up',expected_state=support['state'],expected_hand='minecraft:fern');write_json(out/'live-parent-replant-native.json',r)
    observe(c,root,SMALL,checkpoint);now=inventory_counts(c.status())
    if now['minecraft:fern']!=before['minecraft:fern']+1 or now['minecraft:bone_meal']!=before['minecraft:bone_meal']:raise RuntimeError('Fresh parent harvest balance differs')
    result={'complete':True,'world_session':c.world,'root':root,'source':'fresh_actual_large_fern','historical_action_replayed':False,'carried_fern':now['minecraft:fern'],'bone_meal_used':0};write_json(out/'complete.json',result);return result


def recover_first_confirmed_growth(c,source,out,checkpoint):
    """Harvest a late-confirmed first expansion without spending bone meal again."""
    import json
    source=Path(source);old=json.loads(source.read_text());pending=old.get('pending')or{}
    if (old.get('world_session')!=c.world or pending.get('kind')!='one_fern_bone_meal'
            or pending.get('cycle')!=0 or old.get('cycles')!=[]):
        raise RuntimeError('Only the preserved first expansion can use this continuation')
    receipt=json.loads((source.parent/'cycle-00-bone-native.json').read_text())
    if receipt.get('id')!=pending.get('request_id')or receipt.get('phase')!='done' or receipt.get('world_session')!=c.world:
        raise RuntimeError('Original native bone meal receipt is missing or uncertain')
    root=old['root'];x,y,z=root;top=[x,y+1,z];soil=old['soil'];before=inventory_counts(c.status());initial=old['inventory_before']
    if before['minecraft:fern']!=initial['minecraft:fern']-1 or before['minecraft:bone_meal']!=initial['minecraft:bone_meal']-1:
        raise RuntimeError('Original bone meal and propagule balance changed')
    for p,wanted in ((root,LOWER),(top,UPPER)):
        if cell_at(c,p)['state']!=wanted:raise RuntimeError('Actual paired large fern required; do not repeat fertilization')
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    write_json(out/'original-growth-accepted.json',{'source':str(source),'original_bone_meal_replayed':False,'current_large_fern':root,'actual_inventory':dict(before)})
    checkpoint();c.checked('select_item',item='minecraft:shears')
    if c.status()['hand']['item']!='minecraft:shears':raise RuntimeError('Actual shears required')
    r=c.checked('mine_block',pos=top,face='up',expected_state=UPPER,seconds=10);write_json(out/'large-fern-upper-native.json',r)
    for p in (root,top):
        if cell_at(c,p)['state']!=AIR:raise RuntimeError('Shear outcome unconfirmed; no second excavation')
    c.checked('navigate',target=[x+.5,y+.2,z+.5],arrival=.15,air_only=True,seconds=20)
    until=time.monotonic()+6
    while inventory_counts(c.status())['minecraft:fern']!=before['minecraft:fern']+2 and time.monotonic()<until:checkpoint();time.sleep(.15)
    if inventory_counts(c.status())['minecraft:fern']!=before['minecraft:fern']+2:raise RuntimeError('Actual two-fern yield not observed')
    support=cell_at(c,soil);c.checked('select_item',item='minecraft:fern')
    r=c.checked('interact',pos=soil,face='up',expected_state=support['state'],expected_hand='minecraft:fern');write_json(out/'parent-replanted-native.json',r)
    until=time.monotonic()+6;stamps=[]
    while True:
        checkpoint();actual=cell_at(c,root)['state'];q=c.status()
        if actual==SMALL and q['time']not in stamps:stamps.append(q['time'])
        elif actual!=SMALL:stamps=[]
        if len(stamps)>=2:break
        if time.monotonic()>until:raise RuntimeError('Replanted parent not confirmed; no repeated use')
        time.sleep(.1)
    now=inventory_counts(c.status())
    if now['minecraft:fern']!=before['minecraft:fern']+1 or now['minecraft:bone_meal']!=before['minecraft:bone_meal']:
        raise RuntimeError('Resumed propagation stock mismatch')
    result={'complete':True,'original_bone_meal_replayed':False,'carried_fern':now['minecraft:fern'],'live_parent':root,'inventory_after':dict(now)};write_json(out/'complete.json',result);return result
