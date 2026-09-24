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

VALUABLE={'minecraft:diamond','minecraft:diamond_block','minecraft:emerald','minecraft:emerald_block',
          'minecraft:bone_block',
          'minecraft:netherite_ingot','minecraft:netherite_block','minecraft:blaze_rod','minecraft:blaze_powder'}
def contents(rows):
    result=Counter()
    for row in rows:
        if row.get('count') and row['item']!='minecraft:air':result[row['item']]+=row['count']
    return dict(result)
def matching_source(rows,material,required_stored_enchantments=None):
    required=(required_stored_enchantments or {}).get(material,{})
    for row in rows:
        if row['item']!=material or not row['count']:continue
        actual={v['id']:v['level'] for v in row.get('stored_enchantments',[])}
        if all(actual.get(name,0)>=level for name,level in required.items()):return row
    return None
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

def open_box(client,pos,kind):
    state=block(client,pos)
    allowed='minecraft:ender_chest' in (state or '') if kind=='ChestMenu' else 'shulker_box' in (state or '')
    if not allowed:raise RuntimeError('Expected portable-stock container changed')
    client.checked('select_item',item='minecraft:diamond_sword')
    use_with_margin(client,pos,state,'minecraft:diamond_sword',('up','north','south','west','east','down'))
    s=wait(client,lambda s:s['menu']['type']==kind and not s['menu']['cursor']['count'])
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

def recover_and_return(client,record,ender,journal):
    if record['stage']=='returned':return
    item=record['item'];remaining=record.get('remaining_counts',record['initial_counts']);slot=record['slot'];pad=record['temporary_position']
    def save(stage):record['stage']=stage;journal.write_text(json.dumps(record,ensure_ascii=False,indent=2))
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

def take_box(client,ender,pad,slot,targets,required_stored_enchantments=None):
    journal=client.out/'packed-transfer-active.json'
    if journal.exists() and json.loads(journal.read_text()).get('stage')!='returned':
        raise RuntimeError('An earlier portable box needs inspected recovery before another withdrawal')
    state=client.status()
    if any(v.get('count') and v['item'].endswith('shulker_box') for v in state['inventory']):raise RuntimeError('Keep existing carried shulker boxes outside this operation')
    if sum(v['slot']<36 and not v['count'] for v in state['inventory'])<3:raise RuntimeError('Three free slots are needed for safe portable-stock handling')
    ground=[pad[0],pad[1]-1,pad[2]];ground_state=block(client,ground)
    if block(client,pad) or block(client,[pad[0],pad[1]+1,pad[2]]) or not ground_state or 'minecraft:grass_block' not in ground_state:
        raise RuntimeError('Temporary shulker pad is no longer empty grass')
    s=open_box(client,ender,'ChestMenu');source=s['menu']['slots'][slot];item=source['item'];initial=contents(source.get('contains',[]))
    if source['count']!=1 or not item.endswith('shulker_box') or not initial:raise RuntimeError('Observed source box changed')
    wanted={i:n for i,n in targets.items() if n>inventory_counts(s)[i] and initial.get(i,0)>0}
    if not wanted:client.checked('close_menu');return None
    record={'slot':slot,'item':item,'initial_counts':initial,'requested':wanted,'temporary_position':pad,'stage':'prepared'}
    def save(stage):record['stage']=stage;journal.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    save('prepared')
    client.checked('slot_click',menu_id=s['menu']['id'],slot=slot,expected_item=item,expected_count=1,kind='quick_move')
    wait(client,lambda s:any(v.get('count')==1 and v['item']==item and contents(v.get('contains',[]))==initial for v in s['inventory']))
    save('carried');register_cleanup(client,str(journal),lambda:recover_and_return(client,record,ender,journal));client.checked('close_menu');client.checked('select_item',item=item)
    def pad_empty():
        if block(client,pad) is not None or block(client,ground)!=ground_state:raise RuntimeError('Temporary pad changed before box placement')
    use_with_margin(client,ground,ground_state,item,('up',),pad_empty)
    placed=block(client,pad)
    if 'shulker_box' not in (placed or ''):raise RuntimeError('Box placement is not confirmed')
    save('placed');s=open_box(client,pad,'ShulkerBoxMenu')
    if contents(s['menu']['slots'][:27])!=initial:raise RuntimeError('Opened contents differ from the observed carried box')
    before=inventory_counts(s)
    for material,target in wanted.items():
        for _ in range(8):
            live=client.status();need=target-inventory_counts(live)[material]
            if need<=0:break
            src=matching_source(live['menu']['slots'][:27],material,
                                required_stored_enchantments)
            if src is None:break
            free=sum(v['slot']<36 and not v['count'] for v in live['inventory'])
            if free<=1:record.setdefault('deferred',{})[material]='Reserve a free slot for the intact box';break
            if material in VALUABLE or (required_stored_enchantments or {}).get(material):
                if src.get('max_stack',64)==1 and src['count']==1 and need==1:
                    # A uniquely identified unstackable item is already an
                    # exact one-item transfer; inventory_exact intentionally
                    # handles ordinary stackable ingredients only.
                    client.checked('slot_click',menu_id=live['menu']['id'],slot=src['slot'],
                                   expected_item=material,expected_count=1,kind='quick_move')
                    selected=(required_stored_enchantments or {}).get(material,{})
                    if selected and not any(v['item']==material and v['count']==1 and
                                            all({e['id']:e['level'] for e in v.get('stored_enchantments',[])}.get(k,0)>=n
                                                for k,n in selected.items())
                                            for v in client.status()['inventory']):
                        raise RuntimeError('Selected unstackable enchantment was not confirmed in inventory')
                else:
                    take_exact(client,src['slot'],min(need,src['count'],16),reserve_empty=1)
            else:client.transfer(material,target)
    s=client.status();remaining=contents(s['menu']['slots'][:27]);after=inventory_counts(s)
    taken={i:after[i]-before[i] for i in initial}
    if any(initial[i]-remaining.get(i,0)!=taken[i] for i in initial) or any(i not in initial for i in remaining):
        raise RuntimeError('Box-to-inventory conservation did not match')
    record.update(remaining_counts=remaining,taken={i:n for i,n in taken.items() if n});save('withdrawn');client.checked('close_menu')
    client.checked('select_item',item='minecraft:diamond_pickaxe')
    record['before_drop_uuids']=[e['uuid'] for e in client.status().get('entities',[]) if e.get('type')=='minecraft:item']
    save('breaking')
    client.checked('recover_shulker',pos=pad,expected_state=placed,face='up',seconds=15);save('broken')
    recover_and_return(client,record,ender,journal)
    return record
