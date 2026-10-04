"""Normal, journaled mud/packed-mud/mud-brick production on one owned backend.

Targets are absolute carried counts. Use c.mud_backend or c.material_backend;
no backend, native controller, source region or game profile is created here.
Vanilla water-cauldron bottle use is supported by the existing interact API.
Open-water BottleItem.use is currently unavailable in the food-only use_item
protocol, and is reported as WAIT_WATER_SOURCE rather than emulated input.
"""
from collections import Counter
import copy
import json
import math
from pathlib import Path
import re
import time

from drop_collection import collect_drop
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from recipe_catalog import RecipeCatalog
from . import colored_sources
from .protocol import JobBlocked, JobPaused

ITEMS=frozenset(('minecraft:mud','minecraft:packed_mud','minecraft:mud_bricks'))
TARGET_SCOPE='absolute_backpack_total'
MAX_TARGET_COUNT=2304
AIR='Block{minecraft:air}'
DIRT='Block{minecraft:dirt}'
MUD='Block{minecraft:mud}'
CAULDRON='Block{minecraft:cauldron}'


class Wait(Exception):
    def __init__(self,code,detail,**extra):
        self.receipt={'phase':'waiting','code':code,'detail':detail,**extra}


def _point(p):return isinstance(p,list) and len(p)==3 and all(type(v) is int for v in p)


def _level(state):
    if state==CAULDRON:return 0
    match=re.fullmatch(r'Block\{minecraft:water_cauldron\}\[level=([123])\]',state)
    return int(match[1]) if match else None


def run(c,profile,item,target_count,out,checkpoint):
    """Make at most four raw mud cells per invocation and64 recipe inputs/batch.

    Fetch uses actual depots. Natural mud/wheat reuse the bounded colored-source
    worker with explicit authorized profiles and fresh dry scans. The synthetic
    station may excavate only its own newly placed dirt/mud; existing blocks and
    unidentified inventory potions are preserved.
    """
    if item not in ITEMS or type(target_count) is not int or not 1<=target_count<=MAX_TARGET_COUNT:
        raise ValueError('Mud target must be an absolute carried count1..2304')
    backend=getattr(c,'mud_backend',None) or getattr(c,'material_backend',None)
    if backend is None or backend.client is not c or backend.profile!=profile:
        raise JobBlocked('Bind mud pipeline to this exact existing backend/client/profile')
    resource_context=getattr(backend,'resource_pipeline_context',None)
    if backend.request.get('mode')=='projection' and not (
            isinstance(resource_context,dict) and resource_context.get('target_scope')==TARGET_SCOPE
            and resource_context.get('projection_key')==backend.request.get('projection_key')
            and resource_context.get('world_session')==backend.request.get('context',{}).get('world_session')):
        return {'phase':'waiting','code':'WAIT_BACKEND','detail':'Mud leaf workflow requires item-mode fetch semantics'}
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'mud-pipeline.json'
    scope={'world_session':c.world,'item':item,'target':target_count,'target_scope':TARGET_SCOPE}
    book=json.loads(path.read_text()) if path.exists() else {
        'schema':1,**scope,'pending':None,'receipts':[],'owned_cell':False}
    if any(book.get(k)!=v for k,v in scope.items()):raise JobPaused('Mud journal scope changed')
    if book.get('pending'):
        return {'phase':'waiting','code':'WAIT_RECONCILE','detail':'Previous mud action unknown; no replay','journal':str(path)}
    catalog=RecipeCatalog(profile['recipe_jar']);actions=0;fetched=set();new_mud=0

    def client():return backend.ensure_client()
    def state():
        checkpoint();s=client().status()
        if (s.get('world_session')!=scope['world_session'] or not s.get('connected')
                or s.get('manual_movement') or s.get('under_water')
                or s.get('health',0)<19 or s.get('food',0)<8
                or not s.get('guard_armed') or not s.get('guard_pve_only') or s.get('guard_busy')):
            raise JobPaused('Mud world, lease, health or dry guard scope changed')
        room_for_item(s,'minecraft:mud')
        return s
    def stock():return inventory_counts(state())
    def scan(lo,hi=None):
        state();reply=client().request('scan',min=lo,max=hi or lo,details=True)
        if reply.get('world_session')!=scope['world_session'] or reply.get('phase') not in (None,'done'):
            raise Wait('WAIT_SOURCE','No current server scan')
        if not isinstance(reply.get('blocks'),list):raise Wait('WAIT_SOURCE','Incomplete source scan')
        return reply['blocks']
    def block(pos):return next((r['state'] for r in scan(pos) if r['pos']==pos),AIR)
    def save():write_json(path,book)
    def operation(kind,fn,validate=None):
        nonlocal actions
        if actions>=64:raise Wait('WAIT_BUDGET','Bounded mud action budget reached')
        before=state();book['pending']={'kind':kind,'before':dict(inventory_counts(before))}
        save();checkpoint();result=fn();actions+=1;after=state()
        phase=(result or {}).get('phase')
        known_wait=phase=='waiting' and ((result.get('code','').startswith('WAIT_') and result.get('code')!='WAIT_RECONCILE')
                                       or result.get('code')=='SOURCE_BATCH'
                                       or kind=='fetch' and 'missing' in result)
        if phase!='done' and not known_wait:
            raise Wait('WAIT_RECONCILE','Native mud action uncertain; no replay',receipt=result)
        if phase=='done' and validate is not None:
            deadline=time.monotonic()+6
            while not validate(before,after):
                if time.monotonic()>=deadline:
                    raise Wait('WAIT_RECONCILE','Mud state/ingredient/output conservation not confirmed')
                checkpoint();time.sleep(.15);after=state()
        book['receipts'].append({'kind':kind,'receipt':result,'after':dict(inventory_counts(after))})
        book['pending']=None;save();return result,before,after
    def fetch(output,target):
        if stock()[output]>=target:return
        if (output,target) in fetched:return
        fetched.add((output,target))
        result,_,_=operation('fetch',lambda:backend.fetch({output:target}))
        if result.get('phase') not in ('done','waiting'):raise Wait('WAIT_SOURCE','Depot fetch incomplete')
    def craft(output,target,recipe_id):
        recipe=next((r for r in catalog.recipes[output] if r.id==recipe_id),None)
        if recipe is None:raise JobBlocked('Current game jar lacks '+recipe_id)
        expected=Counter()
        for _,opts in recipe.cells:
            if len(opts)!=1:raise JobBlocked('Ambiguous mud recipe')
            expected[opts[0]]+=1
        def call():
            original=backend.crafting_catalog;pinned=copy.copy(original);pinned.recipes=copy.copy(original.recipes)
            pinned.recipes[output]=[r for r in original.recipes[output] if r.id==recipe_id]
            backend.crafting_catalog=pinned
            try:return backend.craft({output:target})
            finally:backend.crafting_catalog=original
        def valid(a,b):
            old,new=inventory_counts(a),inventory_counts(b);gain=new[output]-old[output]
            return gain>0 and gain%recipe.count==0 and new[output]>=target and all(old[k]-new[k]==v*(gain//recipe.count) for k,v in expected.items())
        result,_,_=operation('craft',call,valid)
        if result.get('phase')!='done':raise Wait('WAIT_RECONCILE','Craft not finished')
    def require_raw(output,target):
        fetch(output,target)
        if stock()[output]>=target:return
        if output=='minecraft:dirt':
            reply,_,_=operation('dirt',lambda:backend.acquire(output,target),
                               lambda a,b:inventory_counts(b)[output]>=target)
        elif output=='minecraft:wheat':
            fetch('minecraft:wheat_seeds',1)
            reply,_,_=operation('crop',lambda:colored_sources.acquire(client(),output,target,profile,out/'wheat',checkpoint))
        else:raise Wait('WAIT_SOURCE','Missing verified '+output,requirements={output:target})
        if stock()[output]<target:raise Wait(reply.get('code','WAIT_SOURCE'),reply.get('detail','Raw batch still short'),requirements={output:target})

    def station():
        cfg=profile.get('mud_station',{})
        pos,support=cfg.get('pos'),cfg.get('support')
        if (cfg.get('authorized') is not True or not _point(pos) or not _point(support)
                or pos!=[support[0],support[1]+1,support[2]] or not isinstance(cfg.get('support_state'),str)):
            raise Wait('WAIT_SOURCE','Configure an explicitly owned dry mud work cell')
        rows=scan([pos[0]-1,support[1],pos[2]-1],[pos[0]+1,pos[1]+1,pos[2]+1])
        floor=next((r for r in rows if r['pos']==support),None)
        if (floor is None or floor['state']!=cfg['support_state'] or floor.get('solid') is not True
                or any(r.get('fluid') is not False or r.get('block_entity') is not False for r in rows)):
            raise Wait('WAIT_SOURCE','Owned mud station is wet, changed or unsafe')
        actual=next((r['state'] for r in rows if r['pos']==pos),AIR)
        if actual!=AIR and (not book['owned_cell'] or actual not in (DIRT,MUD)):
            raise Wait('WAIT_SOURCE','Preserve pre-existing work-cell blocks')
        return cfg,pos,support,actual
    def bottle(preflight=False):
        fetch('minecraft:glass_bottle',1)
        if stock()['minecraft:glass_bottle']<1:
            require_raw('minecraft:glass',3);craft('minecraft:glass_bottle',1,'glass_bottle')
        source=profile.get('mud_water_source',{})
        pos=source.get('pos')
        if source.get('authorized') is not True or not _point(pos):
            raise Wait('WAIT_WATER_SOURCE','Use an authorized water cauldron; open-water bottle use has no current native API')
        current=block(pos);level=_level(current)
        if level is None:raise Wait('WAIT_WATER_SOURCE','Preserve non-water cauldron/source blocks')
        from work_access import approach_faces
        if level==0:
            fetch('minecraft:water_bucket',1)
            if stock()['minecraft:water_bucket']<1:raise Wait('WAIT_WATER_SOURCE','Empty cauldron needs a real carried water bucket; no invented source refill')
        if preflight:return None
        if level==0:
            face=approach_faces(client(),pos,current,('north','south','east','west','up'),seconds=45)
            client().checked('select_item',item='minecraft:water_bucket')
            operation('fill_cauldron',lambda:client().request('interact',pos=pos,face=face,expected_state=current,expected_hand='minecraft:water_bucket'),
                      lambda a,b:_level(block(pos))==3 and inventory_counts(a)['minecraft:water_bucket']-inventory_counts(b)['minecraft:water_bucket']==1
                      and inventory_counts(b)['minecraft:bucket']-inventory_counts(a)['minecraft:bucket']==1)
            current=block(pos);level=3
        if room_for_item(state(),'minecraft:potion',stack_size=1)<1:raise Wait('WAIT_CAPACITY','Bottle output needs a real free slot')
        face=approach_faces(client(),pos,current,('north','south','east','west','up'),seconds=45)
        client().checked('select_item',item='minecraft:glass_bottle')
        expected_level=level-1
        def valid(a,b):
            old,new=inventory_counts(a),inventory_counts(b)
            return _level(block(pos))==expected_level and old['minecraft:glass_bottle']-new['minecraft:glass_bottle']==1 and new['minecraft:potion']-old['minecraft:potion']==1
        _,before,after=operation('fill_bottle',lambda:client().request('interact',pos=pos,face=face,expected_state=current,expected_hand='minecraft:glass_bottle'),valid)
        old={r['slot']:r for r in before['inventory'] if r.get('slot',99)<36}
        added=[r for r in after['inventory'] if r.get('slot',99)<36 and r.get('item')=='minecraft:potion'
               and r.get('count')==1 and old.get(r['slot'],{}).get('item')!='minecraft:potion']
        if len(added)!=1:
            book['pending']={'kind':'water_slot_identity','before':dict(inventory_counts(before))};save()
            raise Wait('WAIT_RECONCILE','New cauldron-derived water bottle slot is ambiguous')
        return added[0] # No generic old potion is classified as water from water_breathing=False.

    def make_mud(target):
        nonlocal new_mud
        natural=any(r.get('item')=='minecraft:mud' and r.get('authorized') is True for r in profile.get('colored_source_regions',[]))
        if natural:
            reply,_,_=operation('natural_mud',lambda:colored_sources.acquire(client(),'minecraft:mud',target,profile,out/'natural-mud',checkpoint))
            if stock()['minecraft:mud']>=target:return
            if reply.get('code') not in ('WAIT_SOURCE','SOURCE_BATCH'):raise Wait(reply.get('code','WAIT_SOURCE'),reply.get('detail','Natural mud unavailable'))
            if reply.get('code')=='SOURCE_BATCH':raise Wait('WAIT_MUD_BATCH','Known natural mud batch collected',requirements={'minecraft:mud':target})
        while stock()['minecraft:mud']<target:
            if new_mud>=4:raise Wait('WAIT_MUD_BATCH','Four owned mud cells completed; next call rechecks sources')
            cfg,pos,support,actual=station()
            if actual==AIR:require_raw('minecraft:dirt',1)
            if actual!=MUD:bottle(preflight=True)
            from work_access import approach_faces
            if actual==AIR:
                face=approach_faces(client(),support,cfg['support_state'],('up',),seconds=45)
                client().checked('select_item',item='minecraft:dirt')
                operation('place_owned_dirt',lambda:client().request('interact',pos=support,face=face,expected_state=cfg['support_state'],expected_hand='minecraft:dirt'),
                          lambda a,b:block(pos)==DIRT and inventory_counts(a)['minecraft:dirt']-inventory_counts(b)['minecraft:dirt']==1)
                book['owned_cell']=True;save();actual=DIRT
            if actual==DIRT:
                water=bottle()
                face=approach_faces(client(),pos,DIRT,('up','north','south','west','east'),seconds=45)
                current=next((r for r in state()['inventory'] if r.get('slot')==water['slot']),None)
                if current!=water:
                    book['pending']={'kind':'water_slot_identity','expected_row':water};save()
                    raise Wait('WAIT_RECONCILE','Derived water bottle slot changed before conversion')
                client().checked('select_item',item='minecraft:potion',slot=water['slot'])
                operation('water_to_owned_mud',lambda:client().request('interact',pos=pos,face=face,expected_state=DIRT,expected_hand='minecraft:potion'),
                          lambda a,b:block(pos)==MUD and inventory_counts(a)['minecraft:potion']-inventory_counts(b)['minecraft:potion']==1
                          and inventory_counts(b)['minecraft:glass_bottle']-inventory_counts(a)['minecraft:glass_bottle']==1)
            face=approach_faces(client(),pos,MUD,('up','north','south','west','east'),seconds=45)
            tools=[r for r in state()['inventory'] if r.get('slot',99)<36 and r.get('item') in ('minecraft:diamond_shovel','minecraft:netherite_shovel') and r.get('durability',0)>=33]
            if not tools:raise Wait('WAIT_TOOL','A real durable mud shovel is required')
            tool=max(tools,key=lambda r:r['durability']);client().checked('select_item',item=tool['item'],slot=tool['slot'])
            def mine():
                before=state();reply=client().request('mine_block',pos=pos,face=face,expected_state=MUD,seconds=20)
                if reply.get('phase')!='done':return reply
                for drop in state().get('entities',[]):
                    if (drop.get('type')=='minecraft:item' and drop.get('stack',{}).get('item')=='minecraft:mud'
                            and len(drop.get('pos',[]))==3 and math.dist(drop['pos'],pos)<=6
                            and drop.get('uuid') not in {e.get('uuid') for e in before.get('entities',[])}):
                        checkpoint();collect_drop(client(),drop)
                return reply
            operation('mine_owned_mud',mine,lambda a,b:block(pos)==AIR and inventory_counts(b)['minecraft:mud']-inventory_counts(a)['minecraft:mud']==1)
            book['owned_cell']=False;save();new_mud+=1

    def ensure(output,target):
        fetch(output,target)
        held=stock()
        if held[output]>=target:return
        if output=='minecraft:mud':make_mud(target);return
        recipe_id='mud_bricks' if output=='minecraft:mud_bricks' else 'packed_mud'
        recipe=next(r for r in catalog.recipes[output] if r.id==recipe_id)
        rounds=math.ceil((target-held[output])/recipe.count)
        if output=='minecraft:mud_bricks':ensure('minecraft:packed_mud',rounds*4)
        else:
            require_raw('minecraft:wheat',rounds)
            ensure('minecraft:mud',rounds)
        craft(output,target,recipe_id)

    try:
        start=stock()[item]
        if book.get('complete'):
            return {'phase':'done' if start>=target_count else 'blocked','code':'COMPLETED_RECEIPT','journal':str(path)}
        while stock()[item]<target_count:
            ensure(item,min(target_count,stock()[item]+64));fetched.clear()
        after=stock()[item];book.update(complete=True,verified_output=after);save()
        return {'phase':'done','item':item,'before':start,'after':after,'gained':after-start,
                'target_scope':TARGET_SCOPE,'journal':str(path)}
    except Wait as wait:
        return {**wait.receipt,'target_scope':TARGET_SCOPE,'journal':str(path)}
