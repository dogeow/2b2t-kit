"""Take an exact small amount from an owned container, returning the unused cursor stack.
Useful for valuable ingredients; never withdraw an entire stack for a one-item recipe.
"""
import json,time

def take_exact(client,source_slot,amount,reserve_empty=0):
    if not isinstance(amount,int) or isinstance(amount,bool) or not 1<=amount<=16:raise ValueError('Exact transfer is limited to 1..16 items')
    journal=client.out/'exact-transfer-active.json'
    if journal.exists() and not json.loads(journal.read_text()).get('complete'):
        raise RuntimeError('An earlier exact transfer needs inventory recovery; do not repeat')
    state=client.status();menu=state['menu'];slots=menu['slots'];boundary=len(slots)-36
    if menu['type'] not in ('ChestMenu','ShulkerBoxMenu') or menu['cursor']['count'] or not 0<=source_slot<boundary:
        raise RuntimeError('Expected an empty cursor and a container source slot')
    source=slots[source_slot];item=source['item'];count=source['count']
    if count<amount or item=='minecraft:air' or 'contains' in source or source.get('max_stack',64)<16 or 'durability' in source:
        raise RuntimeError('Source stack does not contain the requested ordinary ingredients')
    carried=slots[boundary:];empty=[v for v in carried if not v['count']]
    # The bridge does not expose a complete component fingerprint. An empty slot
    # avoids accidentally swapping two same-ID stacks with different custom data.
    candidates=empty if len(empty)>reserve_empty else []
    if not candidates:raise RuntimeError('Keep inventory space for container recovery')
    dest=candidates[0];dest_id=dest['slot'];dest_count=dest['count'];menu_id=menu['id']
    record={'menu_id':menu_id,'source':source_slot,'destination':dest_id,'item':item,'source_before':count,
            'destination_before':dest_count,'amount':amount,'stage':'prepared','complete':False}
    def save(stage):record['stage']=stage;journal.write_text(json.dumps(record,ensure_ascii=False,indent=2))
    def observe(source_count,destination_count,cursor_count):
        end=time.monotonic()+5
        while time.monotonic()<end:
            m=client.status()['menu']
            if m['id']!=menu_id or m['type']!=menu['type']:raise RuntimeError('Container changed during exact transfer')
            a,b=m['slots'][source_slot],m['slots'][dest_id];cursor=m['cursor']
            if a['count']==source_count and b['count']==destination_count and cursor['count']==cursor_count:
                if source_count and a['item']!=item or destination_count and b['item']!=item or cursor_count and cursor['item']!=item:
                    raise RuntimeError('Item identity changed during exact transfer')
                return m
            time.sleep(.1)
        raise RuntimeError('Exact transfer acknowledgement missing; inspect journal before any retry')
    save('prepared')
    client.checked('slot_click',menu_id=menu_id,slot=source_slot,expected_item=item,expected_count=count,kind='pickup')
    observe(0,dest_count,count);save('source_on_cursor')
    for n in range(amount):
        client.checked('slot_click',menu_id=menu_id,slot=dest_id,expected_item=item if dest_count+n else 'minecraft:air',expected_count=dest_count+n,kind='pickup',button=1)
        observe(0,dest_count+n+1,count-n-1);save('placed_'+str(n+1))
    if count>amount:
        client.checked('slot_click',menu_id=menu_id,slot=source_slot,expected_item='minecraft:air',expected_count=0,kind='pickup')
    observe(count-amount,dest_count+amount,0)
    record['complete']=True;save('returned_remainder')
    with (client.out/'exact-transfers.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
    return record
