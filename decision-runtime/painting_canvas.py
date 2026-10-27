"""Two recoverable side spacers constrain a normal painting to its original width."""
import time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import cell_at
from drop_collection import collect_drop
from container_hand import select_container_hand


def sides(expected):
    import math
    if expected.get('width')!=3 or expected.get('height')!=3 or expected.get('facing')!=3:
        raise ValueError('Only the original three-wide south-facing canvas is supported')
    x,y,z=map(math.floor,expected['pos']);return[[x-2,y,z],[x+2,y,z]]


def prepare(c,expected,model,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);key=checkpoint()['projection_selection']['key']
    if model.get('placement_key')!=key or not model.get('content_hash')or not model.get('loaded_chunks_verified'):
        raise RuntimeError('Complete actual original model required')
    targets=sides(expected);source={tuple(r['pos'])for r in model['expected']};stock=inventory_counts(c.status())['minecraft:spruce_planks']
    if stock<2:raise RuntimeError('Two recoverable carried planks required')
    book={'world_session':c.world,'placement_key':key,'model_hash':model['content_hash'],'positions':targets,'inventory_before':stock,'placed':[],'pending':None,'restored':False};path=out/'canvas-spacers.json';write_json(path,book)
    for p in targets:
        if tuple(p)in source or not all(a<=v<=b for a,v,b in zip(model['bounds']['min'],p,model['bounds']['max'])):
            raise RuntimeError('Temporary spacer must occupy original air inside the same house')
        checkpoint();anchor=[p[0],p[1],p[2]-1];row=cell_at(c,anchor)
        if cell_at(c,p)['state']!='Block{minecraft:air}'or not row.get('solid')or row.get('fluid')or row.get('block_entity'):
            raise RuntimeError('Original air and dry existing wall required; no existing block removed')
        before=inventory_counts(c.status())['minecraft:spruce_planks'];c.checked('select_item',item='minecraft:spruce_planks');book['pending']={'kind':'one_temporary_spacer','pos':p};write_json(path,book)
        try:r=c.checked('interact',pos=anchor,face='south',expected_state=row['state'],expected_hand='minecraft:spruce_planks')
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        write_json(out/('spacer-%d-native.json'%len(book['placed'])),r);end=time.monotonic()+6;stamps=[]
        while True:
            checkpoint();actual=cell_at(c,p)['state'];q=c.status()
            if actual=='Block{minecraft:spruce_planks}'and inventory_counts(q)['minecraft:spruce_planks']==before-1 and q['time']not in stamps:stamps.append(q['time'])
            elif actual!='Block{minecraft:spruce_planks}':stamps=[]
            if len(stamps)>=2:break
            if time.monotonic()>end:raise RuntimeError('Temporary spacer use unconfirmed; preserve it without retry')
        book['placed'].append(p);book['pending']=None;write_json(path,book)
    return book


def restore(c,book,out,checkpoint):
    out=Path(out);path=out/'canvas-spacers.json'
    if book['pending']or book['world_session']!=c.world:raise RuntimeError('Original temporary work remains unconfirmed')
    for i,p in enumerate(book['placed']):
        checkpoint();before=c.status();stock=inventory_counts(before)['minecraft:spruce_planks']
        if cell_at(c,p)['state']!='Block{minecraft:spruce_planks}':raise RuntimeError('Temporary spacer changed; preserve player changes')
        c.checked('select_item',item='minecraft:diamond_axe');book['pending']={'kind':'one_owned_spacer_removal','pos':p};write_json(path,book)
        try:r=c.checked('mine_block',pos=p,face='south',expected_state='Block{minecraft:spruce_planks}',seconds=15)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        write_json(out/('spacer-%02d-removal-native.json'%i),r);end=time.monotonic()+6
        while inventory_counts(checkpoint())['minecraft:spruce_planks']!=stock+1:
            q=c.status();drops=[e for e in q['entities']if e['type']=='minecraft:item'and e.get('stack',{}).get('item')=='minecraft:spruce_planks'and e['stack']['count']==1 and sum((a-(b+.5))**2 for a,b in zip(e['pos'],p))<16]
            if len(drops)==1:
                if not collect_drop(c,drops[0],before,seconds=15):raise RuntimeError('Owned spacer drop not confirmed recovered')
                # A normal pickup may take longer than the observation window.
                # Confirm the result before applying that old deadline; do not
                # report a completed recovery as pending or repeat the mining.
                if inventory_counts(checkpoint())['minecraft:spruce_planks']==stock+1:break
            if time.monotonic()>end:raise RuntimeError('Spacer material not recovered; do not leave')
            time.sleep(.1)
        if cell_at(c,p)['state']!='Block{minecraft:air}':raise RuntimeError('Original air not restored')
        book['pending']=None;book.setdefault('recovered',[]).append(p);write_json(path,book)
    if inventory_counts(c.status())['minecraft:spruce_planks']!=book['inventory_before']:raise RuntimeError('Temporary plank balance differs')
    book['restored']=True;write_json(path,book);return book
