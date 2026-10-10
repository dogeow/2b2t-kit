"""Normal, journaled mud/packed-mud/mud-brick production on one owned backend.

Targets are absolute carried counts. Use c.mud_backend or c.material_backend;
no backend, native controller, source region or game profile is created here.
Registered source water uses the native single-use bottle_fill protocol.
Existing cauldron-only profiles retain their normal interact route.
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
COARSE_DIRT='Block{minecraft:coarse_dirt}'
GRASS='Block{minecraft:grass_block}[snowy=false]'
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
    """Make a bounded mud stock visit with four-cell recipe/input sub-batches.

    Fetch uses actual depots. Natural mud/wheat reuse the bounded colored-source
    worker with explicit authorized profiles and fresh dry scans. The synthetic
    Item tasks retain four cells; projection stock visits allow sixteen cells
    and a bounded256-action budget. The station may excavate only its own dirt/mud; existing blocks and
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
    prepare=getattr(backend,'prepare_mud_inventory',None)
    if (callable(prepare) and inventory_counts(c.status()).get(item,0)<target_count
            and book.get('owned_cell')is False and book.get('derived_water_slot')is None):
        book['pending']={'kind':'inventory_staging','before':dict(inventory_counts(c.status()))}
        write_json(path,book);checkpoint();prepared=prepare()
        if not isinstance(prepared,dict)or prepared.get('phase')not in ('done','waiting'):
            raise JobBlocked('Mud inventory staging result unknown; preserve journal')
        book['receipts'].append({'kind':'inventory_staging','receipt':prepared,
                                 'after':dict(inventory_counts(c.status()))})
        book['pending']=None;write_json(path,book)
        if prepared['phase']!='done':
            return {**prepared,'target_scope':TARGET_SCOPE,'journal':str(path),'safe_to_leave':True}
    cell_budget=16 if backend.request.get('mode')=='projection' else 4
    action_budget=256 if cell_budget==16 else 64
    catalog=RecipeCatalog(profile['recipe_jar']);actions=0;fetched=set();new_mud=0
    from .mud_batch import carried_visit_target
    bulk=carried_visit_target(backend.request,profile,c.status(),item,target_count) is not None
    initial=inventory_counts(c.status());gain=max(0,target_count-initial[item])
    visit_units=min(cell_budget,max(0,math.ceil(gain/4)*4-initial['minecraft:packed_mud']))if item=='minecraft:mud_bricks'else 0
    bulk_inputs_ready=False
    bulk_wheat_ready=False
    feedstock = profile.get('mud_station', {}).get('feedstock_item', 'minecraft:dirt')
    if feedstock not in ('minecraft:dirt', 'minecraft:coarse_dirt'):
        raise JobBlocked('Mud feedstock must be ordinary dirt or registered coarse dirt')
    feedstock_state = COARSE_DIRT if feedstock == 'minecraft:coarse_dirt' else DIRT

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
    def select(item,slot=None):
        retained=book.get('derived_water_slot');before=state()
        client().checked('select_item',item=item,**({'slot':slot}if slot is not None else {}))
        if retained is None:return
        rows=state()['inventory'];current=next((r for r in rows if r.get('slot')==retained['slot']),None)
        if current==retained:return
        old={r['slot']:r for r in before['inventory']}
        payload=lambda r:{k:v for k,v in r.items()if k!='slot'}
        moved=[r for r in rows if r.get('slot',99)<36 and payload(r)==payload(retained)
               and payload(old.get(r['slot'],{}))!=payload(retained)]
        changed=[r['slot']for r in rows if payload(r)!=payload(old.get(r['slot'],{}))]
        if (len(moved)!=1 or set(changed)!={retained['slot'],moved[0]['slot']}
                or payload(current or {})!=payload(old[moved[0]['slot']])):
            raise Wait('WAIT_RECONCILE','Derived water selection swap identity is unproved')
        book['derived_water_slot']=moved[0];save()
    def operation(kind,fn,validate=None):
        nonlocal actions
        if actions>=action_budget:raise Wait('WAIT_BUDGET','Bounded mud action budget reached')
        before=state();book['pending']={'kind':kind,'before':dict(inventory_counts(before))}
        save();checkpoint();result=fn();actions+=1;after=state()
        book['pending'].update(returned_receipt=result,after=dict(inventory_counts(after)));save()
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
        # A filled bucket is consumed by the cauldron. A later empty cauldron
        # is a new supply demand, not permission to reuse a cached fetched count.
        if output!='minecraft:water_bucket' and (output,target) in fetched:return
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
        if output=='minecraft:coarse_dirt':
            recipe=next((r for r in catalog.recipes[output] if r.id=='coarse_dirt'),None)
            if recipe is None:raise JobBlocked('Current game jar lacks coarse_dirt')
            rounds=math.ceil((target-stock()[output])/recipe.count)
            ingredients=Counter(opts[0] for _,opts in recipe.cells if len(opts)==1)
            if ingredients!={'minecraft:dirt':2,'minecraft:gravel':2}or recipe.count!=4:
                raise JobBlocked('Unexpected coarse dirt recipe; preserve materials')
            for raw,amount in ingredients.items():require_raw(raw,amount*rounds)
            craft(output,target,'coarse_dirt');return
        if output in ('minecraft:dirt','minecraft:gravel'):
            reply,_,_=operation('dirt',lambda:backend.acquire(output,target),
                               lambda a,b:inventory_counts(b)[output]>=target)
        elif output=='minecraft:wheat':
            fetch('minecraft:wheat_seeds',1)
            registered=getattr(backend,'acquire_registered_wheat',None)
            reply,_,_=operation('crop',lambda:registered(target,out/'wheat',checkpoint) if callable(registered)
                               else colored_sources.acquire(client(),output,target,profile,out/'wheat',checkpoint))
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
        natural_support = (floor is not None and floor['state'] in (DIRT, GRASS)
                           and cfg['support_state'] in (DIRT, GRASS))
        if (floor is None or floor['state']!=cfg['support_state'] and not natural_support or floor.get('solid') is not True
                or any(r.get('fluid') is not False or r.get('block_entity') is not False for r in rows)):
            raise Wait('WAIT_SOURCE','Owned mud station is wet, changed or unsafe')
        actual=next((r['state'] for r in rows if r['pos']==pos),AIR)
        if actual!=AIR and (not book['owned_cell'] or actual not in (DIRT,COARSE_DIRT,GRASS,MUD)):
            raise Wait('WAIT_SOURCE','Preserve pre-existing work-cell blocks')
        # Interact against the exact newly observed support, including the
        # natural dirt/grass transition; never send the older expected state.
        return dict(cfg, support_state=floor['state']),pos,support,actual
    def bottle(preflight=False):
        retained=book.get('derived_water_slot')
        if retained is not None:
            if not isinstance(retained,dict):
                raise Wait('WAIT_RECONCILE','Retained cauldron-derived water identity is incomplete')
            actual=next((r for r in state()['inventory'] if r.get('slot')==retained.get('slot')),None)
            if (retained.get('item')!='minecraft:potion'
                    or retained.get('count')!=1 or actual!=retained):
                raise Wait('WAIT_RECONCILE','Retained cauldron-derived water slot changed; preserve potion')
            return None if preflight else retained
        fetch('minecraft:glass_bottle',1)
        if stock()['minecraft:glass_bottle']<1:
            require_raw('minecraft:glass',3);craft('minecraft:glass_bottle',1,'glass_bottle')
        if profile.get('mud_bucket_source',{}).get('authorized') is True:
            from .mud_water_supply import bottle_source,fill_bottle
            bottle_source(backend)
            if state().get('bottle_water_protocol',0)<1:
                raise Wait('WAIT_WATER_SOURCE','Update Kit for direct registered sea-water bottle fill')
            if preflight:return None
            result,_,_=operation('fill_bottle',lambda:fill_bottle(backend))
            retained=result['derived_water_slot']
            actual=next((r for r in state()['inventory']if r.get('slot')==retained['slot']),None)
            if actual!=retained:
                book['pending']={'kind':'water_slot_identity','before':dict(stock())};save()
                raise Wait('WAIT_RECONCILE','New source-water bottle slot changed; preserve potion')
            book['derived_water_slot']=retained;save();return retained
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
        client().checked('select_item',item='minecraft:glass_bottle')
        selected=state();hand=selected.get('hand')or{}
        replaces_hand=hand.get('item')=='minecraft:glass_bottle' and hand.get('count')==1
        if not replaces_hand and room_for_item(selected,'minecraft:potion',stack_size=1)<1:
            raise Wait('WAIT_CAPACITY','Stacked bottle output needs a real free slot')
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
        book['derived_water_slot']=added[0];save()
        return added[0] # No generic old potion is classified as water from water_breathing=False.

    def make_mud(target):
        nonlocal new_mud,bulk_inputs_ready
        natural=any(r.get('item')=='minecraft:mud' and r.get('authorized') is True for r in profile.get('colored_source_regions',[]))
        if natural:
            reply,_,_=operation('natural_mud',lambda:colored_sources.acquire(client(),'minecraft:mud',target,profile,out/'natural-mud',checkpoint))
            if stock()['minecraft:mud']>=target:return
            if reply.get('code') not in ('WAIT_SOURCE','SOURCE_BATCH'):raise Wait(reply.get('code','WAIT_SOURCE'),reply.get('detail','Natural mud unavailable'))
            if reply.get('code')=='SOURCE_BATCH':raise Wait('WAIT_MUD_BATCH','Known natural mud batch collected',requirements={'minecraft:mud':target})
        cfg=profile.get('mud_station',{});work=cfg.get('pos');floor=cfg.get('support')
        if (cfg.get('authorized')is not True or not _point(work)or not _point(floor)
                or work!=[floor[0],floor[1]+1,floor[2]]or not isinstance(cfg.get('support_state'),str)):
            raise Wait('WAIT_SOURCE','Configure an explicitly owned dry mud work cell')
        if bulk and not bulk_inputs_ready:
            # Prepare only the current16-cell visit. Actual recipes, each cell
            # and all output deltas still use the existing four-unit worker.
            desired=max(0,visit_units-inventory_counts(state())['minecraft:mud'])
            if feedstock=='minecraft:coarse_dirt':require_raw(feedstock,desired)
            else:fetch(feedstock,desired)
            if inventory_counts(state())[feedstock]<desired:
                raise Wait('WAIT_SOURCE','Registered feedstock did not fill this real work visit',requirements={feedstock:desired})
            bulk_inputs_ready=True
        if math.hypot(state()['pos'][0]-work[0],state()['pos'][2]-work[2])>32:
            from .navigation import lift_for_travel
            from .acquisition import _travel
            backend.prepare_travel();c=client();lift_for_travel(c);trace=[]
            _travel(c,[work[0]+.5,max(c.status()['pos'][1],work[1]+24),work[2]+.5],checkpoint,trace,keep_cruise=True)
            write_json(out/'registered-mud-station-loading-travel.json',trace)
        while stock()['minecraft:mud']<target:
            if new_mud>=cell_budget:raise Wait('WAIT_MUD_BATCH','Owned mud stock batch completed; next call rechecks sources')
            cfg,pos,support,actual=station()
            if actual==AIR:
                current=state();held=inventory_counts(current)
                dirt_target=min(4,cell_budget-new_mud,target-held['minecraft:mud'])
                # Carry this invocation's real demand together. A new dirt
                # stack consumes an empty slot; leave room for the mud output.
                output_room=room_for_item(current,'minecraft:mud')
                if not held[feedstock]:output_room-=64
                if output_room<1:dirt_target=1
                require_raw(feedstock,dirt_target)
            if actual!=MUD:
                # Fill before placing dirt, shortening its exposed growth window.
                water=bottle()
            from work_access import approach_faces
            if actual==GRASS:
                face=approach_faces(client(),pos,GRASS,('up','north','south','west','east'),seconds=45)
                tools=[r for r in state()['inventory'] if r.get('slot',99)<36
                       and r.get('item') in ('minecraft:diamond_shovel','minecraft:netherite_shovel')
                       and r.get('durability',0)>=33 and not any(
                           e.get('id')=='minecraft:silk_touch' and e.get('level',0)>0
                           for e in r.get('enchantments',[]))]
                if not tools:raise Wait('WAIT_TOOL','Owned grass recovery requires a durable ordinary shovel')
                tool=max(tools,key=lambda r:r['durability']);select(tool['item'],tool['slot'])
                def recover_grass():
                    before=state();reply=client().request('mine_block',pos=pos,face=face,expected_state=GRASS,seconds=20)
                    if reply.get('phase')!='done':return reply
                    for drop in state().get('entities',[]):
                        if (drop.get('type')=='minecraft:item' and drop.get('stack',{}).get('item')=='minecraft:dirt'
                                and len(drop.get('pos',[]))==3 and math.dist(drop['pos'],pos)<=6
                                and drop.get('uuid') not in {e.get('uuid') for e in before.get('entities',[])}):
                            collect_drop(client(),drop)
                    return reply
                operation('recover_owned_grass',recover_grass,
                          lambda a,b:block(pos)==AIR and inventory_counts(b)['minecraft:dirt']-inventory_counts(a)['minecraft:dirt']==1)
                book['owned_cell']=False;save();actual=AIR
            if actual==AIR:
                # A pickup can leave the player inside this now-empty work cell.
                # Native approach may consider that pose already in reach, but
                # normal placement rejects collision with our own body.
                pose=state()['pos']
                if (pos[0]-.35<pose[0]<pos[0]+1.35 and pos[2]-.35<pose[2]<pos[2]+1.35
                        and pose[1]<pos[1]+1 and pose[1]+1.8>pos[1]):
                    approach=cfg.get('approach')
                    if (not isinstance(approach,list)or len(approach)!=3
                            or any(type(v)not in (int,float)or not math.isfinite(v)for v in approach)
                            or math.dist(pose,approach)>4):
                        raise Wait('WAIT_SOURCE','Owned mud placement requires a registered adjacent stand')
                    client().checked('navigate',target=approach,arrival=.15,air_only=True,seconds=15)
                    pose=state()['pos']
                    if pos[0]-.35<pose[0]<pos[0]+1.35 and pos[2]-.35<pose[2]<pos[2]+1.35:
                        raise Wait('WAIT_SOURCE','Actual adjacent mud stand still overlaps the work cell')
                face=approach_faces(client(),support,cfg['support_state'],('up',),seconds=45)
                select(feedstock)
                operation('place_owned_dirt' if feedstock_state==DIRT else 'place_owned_coarse_dirt',
                          lambda:client().request('interact',pos=support,face=face,expected_state=cfg['support_state'],expected_hand=feedstock),
                          lambda a,b:block(pos)==feedstock_state and inventory_counts(a)[feedstock]-inventory_counts(b)[feedstock]==1)
                book['owned_cell']=True;save();actual=feedstock_state
            if actual in (DIRT,COARSE_DIRT):
                try:
                    face=approach_faces(client(),pos,actual,('up','north','south','west','east'),seconds=45)
                except RuntimeError:
                    if book['owned_cell'] and block(pos)==GRASS:
                        raise Wait('WAIT_MUD_BATCH','Owned dirt grew grass; retained water remains for ordinary recovery')
                    raise
                water=book['derived_water_slot']
                current=next((r for r in state()['inventory'] if r.get('slot')==water['slot']),None)
                if current!=water:
                    book['pending']={'kind':'water_slot_identity','expected_row':water};save()
                    raise Wait('WAIT_RECONCILE','Derived water bottle slot changed before conversion')
                select('minecraft:potion',water['slot'])
                operation('water_to_owned_mud',lambda:client().request('interact',pos=pos,face=face,expected_state=actual,expected_hand='minecraft:potion'),
                          lambda a,b:block(pos)==MUD and inventory_counts(a)['minecraft:potion']-inventory_counts(b)['minecraft:potion']==1
                          and inventory_counts(b)['minecraft:glass_bottle']-inventory_counts(a)['minecraft:glass_bottle']==1)
                book['derived_water_slot']=None;save()
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
                        checkpoint();picked=collect_drop(client(),drop)
                        if not picked:
                            terminal=getattr(client(),'last_terminal_evidence',{})or{}
                            if (terminal.get('op')=='scan'and terminal.get('phase')=='done'
                                    and terminal.get('request_id')==getattr(client(),'last',None)
                                    and terminal.get('world_session')==scope['world_session']
                                    and terminal.get('task_session')==getattr(client(),'task',None)
                                    and getattr(client(),'unconfirmed_native_request',None)is None
                                    and getattr(client(),'native_inflight',None)is None):
                                from drop_pickup_settle import settle
                                settle(client(),drop,inventory_counts(before).get('minecraft:mud',0))
                return reply
            operation('mine_owned_mud',mine,lambda a,b:block(pos)==AIR and inventory_counts(b)['minecraft:mud']-inventory_counts(a)['minecraft:mud']==1)
            book['owned_cell']=False;save();new_mud+=1

    def ensure(output,target):
        nonlocal bulk_wheat_ready
        fetch(output,target)
        held=stock()
        if held[output]>=target:return
        if output=='minecraft:mud':make_mud(target);return
        recipe_id='mud_bricks' if output=='minecraft:mud_bricks' else 'packed_mud'
        recipe=next(r for r in catalog.recipes[output] if r.id==recipe_id)
        rounds=math.ceil((target-held[output])/recipe.count)
        if output=='minecraft:mud_bricks':ensure('minecraft:packed_mud',rounds*4)
        else:
            if bulk:
                if not bulk_wheat_ready:
                    fetch('minecraft:wheat',visit_units);bulk_wheat_ready=True
                    if stock()['minecraft:wheat']<visit_units:
                        require_raw('minecraft:wheat',visit_units)
                if stock()['minecraft:wheat']<rounds:
                    raise Wait('WAIT_SOURCE','Registered wheat is short for the next real recipe',requirements={'minecraft:wheat':rounds})
            else:require_raw('minecraft:wheat',rounds)
            ensure('minecraft:mud',rounds)
        craft(output,target,recipe_id)

    try:
        start=stock()[item]
        if book.get('complete'):
            return {'phase':'done' if start>=target_count else 'blocked','code':'COMPLETED_RECEIPT','journal':str(path)}
        while stock()[item]<target_count:
            # Match derived recipe demand to the real four-cell source budget.
            # A large goal must not require 64 wheat before producing any stock.
            increment=4 if item in ('minecraft:packed_mud','minecraft:mud_bricks') else 64
            ensure(item,min(target_count,stock()[item]+increment));fetched.clear()
        after=stock()[item];book.update(complete=True,verified_output=after);save()
        return {'phase':'done','item':item,'before':start,'after':after,'gained':after-start,
                'target_scope':TARGET_SCOPE,'journal':str(path)}
    except Wait as wait:
        return {**wait.receipt,'target_scope':TARGET_SCOPE,'journal':str(path),
                'safe_to_leave':book.get('owned_cell') is False and book.get('pending') is None
                                and book.get('derived_water_slot') is None}
