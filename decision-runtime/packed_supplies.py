"""Withdraw ordinary materials from a player's observed ender-chest shulkers.

Temporarily place one intact box on an empty, verified pad, take materials,
recover it, and put it back in the same ender slot. Journal all transitions.
"""
from collections import Counter
import json,time
from material_plan import inventory_counts
from inventory_exact import take_exact
from projection_wood import use_with_margin
from drop_collection import collect_drop
from material_cleanup import register as register_cleanup,complete as cleanup_complete
from container_access import wait_container_contents

# Before pickup: the intact box, an output/splitting slot, and recovery room.
# Placing the box releases its slot; callers may then reserve the other two.
REQUIRED_FREE_SLOTS=3

def workspace_requirement(state):
    """Read-only admission check shared by planning and the actual box action."""
    rows=[v for v in state.get('inventory',[]) if 0<=v.get('slot',-1)<36]
    if (len(rows)!=36 or len({v['slot'] for v in rows})!=36
            or any(type(v.get('count')) is not int or v['count']<0 for v in rows)):
        return {'phase':'waiting','code':'packed_inventory_unknown','required_free_slots':REQUIRED_FREE_SLOTS,
                'free_slots':None,'missing_free_slots':None,'detail':'背包空槽尚未完整确认，未取出潜影盒'}
    free=sum(not v['count'] for v in rows)
    if free<REQUIRED_FREE_SLOTS:
        return {'phase':'waiting','code':'packed_workspace_required','required_free_slots':REQUIRED_FREE_SLOTS,
                'free_slots':free,'missing_free_slots':REQUIRED_FREE_SLOTS-free,
                'detail':f'潜影盒取料需要 {REQUIRED_FREE_SLOTS} 个空槽，当前 {free} 个；先腾出 {REQUIRED_FREE_SLOTS-free} 格，尚未取出潜影盒'}
    return None

class PackedWorkspaceRequired(RuntimeError):
    """Pre-mutation refusal only; uncertain portable-box operations never use it."""
    def __init__(self,receipt):
        self.receipt=receipt
        super().__init__(receipt['detail'])

VALUABLE={'minecraft:diamond','minecraft:diamond_block','minecraft:emerald','minecraft:emerald_block',
          'minecraft:bone_block',
          'minecraft:netherite_ingot','minecraft:netherite_block','minecraft:blaze_rod','minecraft:blaze_powder'}
def contents(rows):
    result=Counter()
    for row in rows:
        if row.get('count') and row['item']!='minecraft:air':result[row['item']]+=row['count']
    return dict(result)
def matching_source(rows,material,required_stored_enchantments=None,minimum_durability=None,required_enchantments=None):
    required=(required_stored_enchantments or {}).get(material,{})
    ordinary=(required_enchantments or {}).get(material,{})
    minimum=(minimum_durability or {}).get(material,0)
    for row in rows:
        if row['item']!=material or not row['count']:continue
        if row.get('durability',0)<minimum:continue
        actual={v['id']:v['level'] for v in row.get('stored_enchantments',[])}
        equipped={v['id']:v['level'] for v in row.get('enchantments',[])}
        if (all(actual.get(name,0)>=level for name,level in required.items())
                and all(equipped.get(name,0)>=level for name,level in ordinary.items())):return row
    return None
def matching_count(rows,material,required_stored_enchantments=None,minimum_durability=None,required_enchantments=None):
    return sum(row['count'] for row in rows if matching_source([row],material,
               required_stored_enchantments,minimum_durability,required_enchantments) is not None)
def choose_box(slots,targets,carried):
    candidates=[]
    for row in slots:
        if not row.get('item','').endswith('shulker_box') or row.get('count')!=1:continue
        have=contents(row.get('contains',[]));needed={i:min(n-carried.get(i,0),have.get(i,0)) for i,n in targets.items() if n>carried.get(i,0) and have.get(i,0)>0}
        if needed:candidates.append((sum(needed.values()),row['slot'],needed))
    return max(candidates,key=lambda r:(r[0],-r[1]),default=None)
def wait(client,predicate):
    until=time.monotonic()+7
    while time.monotonic()<until:
        s=client.status()
        if predicate(s):return s
        time.sleep(.2)
    raise RuntimeError('Packed stock confirmation missing; inspect the saved stage before retrying')
def block(client,pos):
    rows=client.request('scan',min=pos,max=pos)['blocks'];return rows[0]['state'] if rows else None

def player_intersects_pad(player_pos,pad):
    return (abs(player_pos[0]-(pad[0]+.5))<.81
            and abs(player_pos[2]-(pad[2]+.5))<.81
            and player_pos[1]<pad[1]+1
            and player_pos[1]+1.8>pad[1])

def clear_player_from_pad(client,pad):
    if not player_intersects_pad(client.status()['pos'],pad):return
    for dx,dz in ((2,0),(-2,0),(0,2),(0,-2)):
        x,z=pad[0]+dx,pad[2]+dz
        rows=client.request('scan',min=[x,pad[1]-1,z],max=[x,pad[1]+2,z],details=True)['blocks']
        observed={tuple(v['pos']):v for v in rows}
        floor=observed.get((x,pad[1]-1,z))
        if (floor is None or not floor.get('solid') or floor.get('fluid')
                or any((x,y,z) in observed for y in (pad[1],pad[1]+1,pad[1]+2))):
            continue
        moved=client.request('navigate',target=[x+.5,pad[1]+.02,z+.5],arrival=1,seconds=20)
        if moved.get('phase')=='done' and not player_intersects_pad(client.status()['pos'],pad):return
    raise RuntimeError('No verified player-clear position for temporary shulker placement')

def open_box(client,pos,kind):
    state=block(client,pos)
    allowed='minecraft:ender_chest' in (state or '') if kind=='ChestMenu' else 'shulker_box' in (state or '')
    if not allowed:raise RuntimeError('Expected portable-stock container changed')
    client.checked('select_item',item='minecraft:diamond_sword')
    use_with_margin(client,pos,state,'minecraft:diamond_sword',('up','north','south','west','east','down'))
    s=wait_container_contents(client,kind)
    client.owned_material_menu=s['menu']['id'];return s

def owned_drop(entities,item,pad,before_ids,known_uuid=None):
    # Dropped shulkers may omit CONTAINER data. Identity comes from the new drop
    # near our verified block removal; contents are checked after pickup instead.
    candidates=[e for e in entities if e.get('type')=='minecraft:item' and e.get('stack',{}).get('item')==item
                and e['stack'].get('count')==1 and e.get('uuid') not in before_ids
                and sum((a-b)**2 for a,b in zip(e.get('pos',[]),pad))<9 and len(e.get('pos',[]))==3]
    if known_uuid:candidates=[e for e in candidates if e['uuid']==known_uuid]
    if len(candidates)>1:raise RuntimeError('Multiple new portable-box drops; do not guess ownership')
    return candidates[0] if candidates else None

def carried_box(state,item,expected):
    return next((v for v in state['inventory'] if v.get('count')==1 and v['item']==item and contents(v.get('contains',[]))==expected),None)

def _observed_inventory(rows):
    if not isinstance(rows,list) or any(not isinstance(v,dict) or type(v.get('slot')) is not int
            or not isinstance(v.get('item'),str) or type(v.get('count')) is not int or v['count']<0 for v in rows):return False
    slots=[v['slot'] for v in rows]
    return len(slots)==len(set(slots)) and set(range(36)).issubset(slots)

def _clean_cursor(state):
    menu=state.get('menu');cursor=menu.get('cursor') if isinstance(menu,dict) else None
    if not isinstance(cursor,dict):return False
    return type(cursor.get('count')) is int and cursor['count']==0 and cursor.get('item')=='minecraft:air'

def _owned_recover_failure(record):
    receipt=record.get('recover_terminal',{})
    if not isinstance(receipt,dict):return False
    world=record.get('world_session')
    params=receipt.get('params',{})
    return (isinstance(params,dict) and isinstance(world,str) and bool(world) and isinstance(receipt.get('request_id'),str)
            and bool(receipt['request_id']) and receipt.get('request_id')==record.get('recover_request_id')
            and receipt.get('world_session')==world and receipt.get('op')=='recover_shulker'
            and receipt.get('phase') in ('error','stopped','waiting')
            and params.get('pos')==record.get('temporary_position')
            and isinstance(record.get('placed_state'),str) and record['item'] in record['placed_state']
            and params.get('expected_state')==record['placed_state'])

def reconcile_recovered_box(client,record,ender,journal):
    """One read-only check after an owned terminal failure; never retry mining/pickup.

    Legacy records without an actual preflight and exact native receipt stay
    blocked. A run manifest's world ID alone does not prove box ownership.
    """
    if record.get('stage')!='breaking' or not _owned_recover_failure(record):
        raise RuntimeError('Portable-box recovery lacks an owned terminal failure; preserve the journal')
    world=record['world_session'];item=record['item'];pad=record['temporary_position']
    preflight=record.get('ownership_preflight',{});source=record.get('source',{})
    if not isinstance(preflight,dict) or not isinstance(source,dict):
        raise RuntimeError('Portable-box preflight/source ownership is unproven; preserve the journal')
    before=preflight.get('inventory')
    if (preflight.get('world_session')!=world or not _observed_inventory(before)
            or preflight.get('cursor_clean') is not True
            or any(v['count'] and v['item'].endswith('shulker_box') for v in before)
            or not isinstance(pad,list) or len(pad)!=3 or any(type(v) is not int for v in pad)
            or source.get('position')!=ender or source.get('slot')!=record['slot']
            or type(source.get('slot')) is not int or not 0<=source['slot']<27
            or source.get('item')!=item or type(source.get('count')) is not int or source['count']!=1
            or not item.endswith('shulker_box') or source.get('counts')!=record['initial_counts']
            or 'remaining_counts' not in record):
        raise RuntimeError('Portable-box preflight/source ownership is unproven; preserve the journal')
    remaining=record['remaining_counts'];initial=record['initial_counts'];taken=record.get('taken',{})
    if (not isinstance(remaining,dict) or not isinstance(initial,dict) or not isinstance(taken,dict)
            or any(type(n) is not int or n<0 for counts in (remaining,initial,taken) for n in counts.values())
            or any(i not in initial for counts in (remaining,taken) for i in counts)
            or any(initial[i]-remaining.get(i,0)!=taken.get(i,0) for i in initial)):
        raise RuntimeError('Portable-box remaining contents lack confirmed conservation')
    def carried(state):
        if state.get('world_session')!=world or not state.get('connected'):
            raise RuntimeError('Portable-box recovery belongs to another world or disconnected state')
        rows=state.get('inventory')
        if not _clean_cursor(state) or not _observed_inventory(rows):
            raise RuntimeError('Portable-box recovery needs a clean cursor and complete inventory')
        boxes=[v for v in rows if v['count'] and v['item'].endswith('shulker_box')]
        if (len(boxes)!=1 or boxes[0]['item']!=item or boxes[0]['count']!=1
                or not isinstance(boxes[0].get('contains'),list)
                or any(not isinstance(v,dict) or not isinstance(v.get('item'),str)
                    or type(v.get('count')) is not int or v['count']<0 for v in boxes[0]['contains'])
                or contents(boxes[0]['contains'])!=remaining):
            raise RuntimeError('Portable-box carried identity or remaining contents are missing/ambiguous')
        return boxes[0]
    carried(client.status())
    scan=client.request('scan',min=pad,max=pad)
    if (scan.get('world_session')!=world or scan.get('phase') not in (None,'done')
            or scan.get('blocks')!=[]):
        raise RuntimeError('Portable-box pad is occupied or its fresh scan is unconfirmed')
    box=carried(client.status())
    record['recovery_reconciliation']={'scope':'owned_terminal_failure_empty_pad_unique_carried_contents',
        'world_session':world,'recover_request_id':record['recover_request_id'],'inventory_slot':box['slot']}
    record['stage']='recovered';journal.write_text(json.dumps(record,ensure_ascii=False,indent=2))

def recover_and_return(client,record,ender,journal):
    if record['stage']=='returned':return
    item=record['item'];remaining=record.get('remaining_counts',record['initial_counts']);slot=record['slot'];pad=record['temporary_position']
    def save(stage):record['stage']=stage;journal.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    if record['stage']=='breaking':reconcile_recovered_box(client,record,ender,journal)
    if record['stage']=='broken':
        until=time.monotonic()+12
        while time.monotonic()<until:
            state=client.status()
            if carried_box(state,item,remaining):break
            drop=owned_drop(state.get('entities',[]),item,pad,set(record.get('before_drop_uuids',[])),record.get('drop_uuid'))
            if drop:
                record['drop_uuid']=drop['uuid'];save('broken')
                if not collect_drop(client,drop,observation=state):raise RuntimeError('Owned portable box still needs recovery; inventory must be checked before any retry')
            else:time.sleep(.2)
        wait(client,lambda s:carried_box(s,item,remaining) is not None);save('recovered')
    if record['stage'] not in ('carried','recovered'):
        raise RuntimeError('Portable box remains safely placed or has an uncertain operation; inspect its journal before further mining')
    wait(client,lambda s:carried_box(s,item,remaining) is not None)
    if client.status()['menu']['cursor']['count']:raise RuntimeError('Cursor must be recovered before returning the box')
    if client.status().get('screen'):client.checked('close_menu')
    state=open_box(client,ender,'ChestMenu')
    if state['menu']['slots'][slot]['count']:raise RuntimeError('Original ender slot changed; preserve its current contents')
    boundary=len(state['menu']['slots'])-36;carried=next(v for v in state['menu']['slots'][boundary:] if v['item']==item and v['count']==1 and contents(v.get('contains',[]))==remaining)
    client.checked('slot_click',menu_id=state['menu']['id'],slot=carried['slot'],expected_item=item,expected_count=1,kind='pickup')
    client.checked('slot_click',menu_id=state['menu']['id'],slot=slot,expected_item='minecraft:air',expected_count=0,kind='pickup')
    wait(client,lambda s:s['menu']['cursor']['count']==0 and s['menu']['slots'][slot]['item']==item and contents(s['menu']['slots'][slot].get('contains',[]))==remaining)
    save('returned');client.checked('close_menu');cleanup_complete(client,str(journal))
    with (client.out/'packed-transfers.jsonl').open('a') as stream:stream.write(json.dumps(record,ensure_ascii=False)+'\n')
    print('PACKED_RETURNED',slot,record.get('taken',{}),flush=True)

def take_box(client,ender,pad,slot,targets,required_stored_enchantments=None,minimum_durability=None,required_enchantments=None):
    journal=client.out/'packed-transfer-active.json'
    if journal.exists() and json.loads(journal.read_text()).get('stage')!='returned':
        raise RuntimeError('An earlier portable box needs inspected recovery before another withdrawal')
    state=client.status()
    for material,target in targets.items():
        filtered=((required_stored_enchantments or {}).get(material)
                  or (required_enchantments or {}).get(material) or (minimum_durability or {}).get(material))
        if (filtered and target<=inventory_counts(state)[material]
                and matching_source(state['inventory'],material,required_stored_enchantments,
                                    minimum_durability,required_enchantments) is None):
            raise RuntimeError('Existing item count has no matching equipment; request current total plus the additional items')
    if any(v.get('count') and v['item'].endswith('shulker_box') for v in state['inventory']):raise RuntimeError('Keep existing carried shulker boxes outside this operation')
    space=workspace_requirement(state)
    if space:raise PackedWorkspaceRequired(space)
    ground=[pad[0],pad[1]-1,pad[2]];ground_state=block(client,ground)
    if block(client,pad) or block(client,[pad[0],pad[1]+1,pad[2]]) or not ground_state or 'minecraft:grass_block' not in ground_state:
        raise RuntimeError('Temporary shulker pad is no longer empty grass')
    s=open_box(client,ender,'ChestMenu');source=s['menu']['slots'][slot];item=source['item'];initial=contents(source.get('contains',[]))
    if source['count']!=1 or not item.endswith('shulker_box') or not initial:raise RuntimeError('Observed source box changed')
    wanted={i:n for i,n in targets.items() if n>inventory_counts(s)[i] and initial.get(i,0)>0}
    if not wanted:client.checked('close_menu');return None
    record={'slot':slot,'item':item,'initial_counts':initial,'requested':wanted,'temporary_position':pad,'stage':'prepared',
            'world_session':state.get('world_session'),
            'ownership_preflight':{'world_session':state.get('world_session'),'cursor_clean':_clean_cursor(state),
                'inventory':[{key:v.get(key) for key in ('slot','item','count')} for v in state['inventory']]},
            'source':{'position':ender,'slot':slot,'item':item,'count':source['count'],'counts':initial},
            'required_stored_enchantments':required_stored_enchantments or {},
            'required_enchantments':required_enchantments or {},'minimum_durability':minimum_durability or {}}
    def save(stage):record['stage']=stage;journal.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    save('prepared')
    client.checked('slot_click',menu_id=s['menu']['id'],slot=slot,expected_item=item,expected_count=1,kind='quick_move')
    wait(client,lambda s:any(v.get('count')==1 and v['item']==item and contents(v.get('contains',[]))==initial for v in s['inventory']))
    save('carried');register_cleanup(client,str(journal),lambda:recover_and_return(client,record,ender,journal));client.checked('close_menu');client.checked('select_item',item=item)
    clear_player_from_pad(client,pad)
    def pad_empty():
        if block(client,pad) is not None or block(client,ground)!=ground_state:raise RuntimeError('Temporary pad changed before box placement')
    use_with_margin(client,ground,ground_state,item,('up',),pad_empty)
    placed=block(client,pad)
    if 'shulker_box' not in (placed or ''):raise RuntimeError('Box placement is not confirmed')
    record['placed_state']=placed;save('placed');s=open_box(client,pad,'ShulkerBoxMenu')
    if contents(s['menu']['slots'][:27])!=initial:raise RuntimeError('Opened contents differ from the observed carried box')
    before=inventory_counts(s)
    for material,target in wanted.items():
        for _ in range(8):
            live=client.status();need=target-inventory_counts(live)[material]
            if need<=0:break
            src=matching_source(live['menu']['slots'][:27],material,
                                required_stored_enchantments,minimum_durability,required_enchantments)
            if src is None:
                if ((required_stored_enchantments or {}).get(material) or (required_enchantments or {}).get(material)
                        or (minimum_durability or {}).get(material)):
                    record.setdefault('deferred',{})[material]='No observed item satisfies the requested enchantments and durability'
                break
            free=sum(v['slot']<36 and not v['count'] for v in live['inventory'])
            if free<=1:record.setdefault('deferred',{})[material]='Reserve a free slot for the intact box';break
            if (material in VALUABLE or (required_stored_enchantments or {}).get(material)
                    or (required_enchantments or {}).get(material) or (minimum_durability or {}).get(material)):
                if src.get('max_stack',64)==1 and src['count']==1 and need==1:
                    # A uniquely identified unstackable item is already an
                    # exact one-item transfer; inventory_exact intentionally
                    # handles ordinary stackable ingredients only.
                    carried_before=inventory_counts(live)[material]
                    qualified_before=matching_count(live['inventory'],material,required_stored_enchantments,
                                                    minimum_durability,required_enchantments)
                    client.checked('slot_click',menu_id=live['menu']['id'],slot=src['slot'],
                                   expected_item=material,expected_count=1,kind='quick_move')
                    def received(state):
                        menu=state['menu']
                        if menu['id']!=live['menu']['id'] or menu['type']!='ShulkerBoxMenu':
                            raise RuntimeError('Portable equipment container changed; do not repeat withdrawal')
                        return (not menu['cursor']['count'] and not menu['slots'][src['slot']]['count']
                                and inventory_counts(state)[material]==carried_before+1
                                and matching_count(state['inventory'],material,required_stored_enchantments,
                                                   minimum_durability,required_enchantments)==qualified_before+1)
                    wait(client,received)
                else:
                    take_exact(client,src['slot'],min(need,src['count'],16),reserve_empty=1)
            else:client.transfer(material,target)
    s=client.status();remaining=contents(s['menu']['slots'][:27]);after=inventory_counts(s)
    taken={i:after[i]-before[i] for i in initial}
    if any(initial[i]-remaining.get(i,0)!=taken[i] for i in initial) or any(i not in initial for i in remaining):
        raise RuntimeError('Box-to-inventory conservation did not match')
    # Observe drops while the exact open-box contents are still confirmed and
    # before selecting a pick can activate an external mining module.
    record.update(remaining_counts=remaining,taken={i:n for i,n in taken.items() if n},
        before_drop_uuids=[e['uuid'] for e in s.get('entities',[]) if e.get('type')=='minecraft:item'],
        drop_baseline_scope='confirmed_open_box_before_close_and_tool_selection')
    save('withdrawn');client.checked('close_menu')
    client.checked('select_item',item='minecraft:diamond_pickaxe')
    observed=block(client,pad)
    record['recovery_preflight']={'expected_state':placed,'observed_state':observed}
    save('withdrawn')
    if observed!=placed:
        raise RuntimeError('Portable-box pad changed before recovery; preserve the journal without mining or pickup')
    save('breaking')
    previous=getattr(client,'last_terminal_evidence',{}).get('request_id')
    try:client.checked('recover_shulker',pos=pad,expected_state=placed,face='up',seconds=15)
    except RuntimeError:
        receipt=getattr(client,'last_terminal_evidence',{})
        request_id=receipt.get('request_id')
        if not request_id or request_id==previous or request_id!=getattr(client,'last',None):raise
        evidence={'recover_request_id':request_id,
            'recover_terminal':{key:receipt.get(key) for key in ('request_id','world_session','op','phase','params','detail')}}
        if not _owned_recover_failure({**record,**evidence}):raise
        record.update(evidence)
        save('breaking')
        reconcile_recovered_box(client,record,ender,journal)
    else:save('broken')
    recover_and_return(client,record,ender,journal)
    return record
