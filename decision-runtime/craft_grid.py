"""Batch homogeneous vanilla recipes with real crafting slots and verified input/output counts."""
import json,time,math
k=None # Bound to the current scoped MaterialClient; never a background global game connection.

def count(s,item):return sum(x['count'] for x in s['inventory'] if x['item']==item and x.get('slot',99)<36)
class InventoryCapacity(RuntimeError):pass
def output_room(s,item,limit):
    return sum(limit if not v['count'] else max(0,limit-v['count']) if v['item']==item else 0
               for v in s['inventory'] if v.get('slot',99)<36)
def compact_once(s):
    """Merge one compatible pair; ordinary pickup swaps are reversed if components differ."""
    m=s['menu'];start=len(m['slots'])-36 if m['type']=='CraftingMenu' else 9
    slots=m['slots'][start:start+36]
    for a in slots:
        if not a['count'] or a.get('max_stack',1)<=1:continue
        for b in slots:
            if b['slot']<=a['slot'] or b['item']!=a['item'] or not b['count'] or a['count']+b['count']>a['max_stack']:continue
            s=click(s,a['slot'])
            if s['menu']['cursor']['count']!=a['count'] or s['menu']['slots'][a['slot']]['count']:raise RuntimeError('Compaction source not confirmed')
            s=click(s,b['slot']);cursor=s['menu']['cursor'];target=s['menu']['slots'][b['slot']]
            if not cursor['count'] and target['count']==a['count']+b['count']:return s,True
            if cursor['item']==a['item'] and cursor['count']==b['count'] and target['item']==a['item'] and target['count']==a['count']:
                s=click(s,b['slot']);s=click(s,a['slot'])
                if s['menu']['cursor']['count'] or s['menu']['slots'][a['slot']]['count']!=a['count'] or s['menu']['slots'][b['slot']]['count']!=b['count']:raise RuntimeError('Compaction rollback not confirmed')
                return s,False
            raise RuntimeError('Inventory changed during compaction; do not repeat')
    return s,False
def checked(op,**args):
    r=k.request(op,**args)
    if r.get('phase')!='done':raise RuntimeError(r.get('detail',op+' failed'))
    return r
def click(s,slot,kind='pickup'):
    cell=s['menu']['slots'][slot]
    return checked('slot_click',menu_id=s['menu']['id'],slot=slot,expected_item=cell['item'],expected_count=cell['count'],kind=kind)
def wait_for_recipe(s,output):
    deadline=time.monotonic()+6
    while s['menu']['slots'][0]['item']!=output and time.monotonic()<deadline:
        time.sleep(.25);s=k.status()
    if s['menu']['slots'][0]['item']!=output:raise RuntimeError('The server did not offer the expected recipe: '+output)
    return s
def take_portion(s,source,amount):
    """Take only the needed recipe inputs using ordinary half-stack/right clicks."""
    if s['menu']['cursor']['count'] or not 0 < amount <= source['count']:
        raise RuntimeError('Expected empty cursor and available ingredient quantity')
    half=(source['count']+1)//2
    button=1 if amount<=half and amount<source['count'] else 0
    picked=half if button else source['count']
    menu_id=s['menu']['id']
    s=checked('slot_click',menu_id=s['menu']['id'],slot=source['slot'],expected_item=source['item'],expected_count=source['count'],kind='pickup',button=button)
    # A completed click request can still contain the preceding inventory snapshot.
    # Observe both sides of the pickup before splitting; never resend the pickup.
    deadline=time.monotonic()+6
    while True:
        m=s['menu'];cursor=m['cursor'];cell=m['slots'][source['slot']]
        if m['id']!=menu_id:raise RuntimeError('Crafting menu changed during ingredient pickup')
        if cursor['item']==source['item'] and cursor['count']==picked and cell['count']==source['count']-picked and (not cell['count'] or cell['item']==source['item']):break
        if time.monotonic()>=deadline:raise RuntimeError('Ingredient pickup not confirmed; no duplicate click')
        time.sleep(.15);s=k.status()
    while s['menu']['cursor']['count']>amount:
        cell=s['menu']['slots'][source['slot']];old=s['menu']['cursor']['count']
        if cell['item'] not in ('minecraft:air',source['item']):raise RuntimeError('Ingredient source slot changed')
        s=checked('slot_click',menu_id=s['menu']['id'],slot=source['slot'],expected_item=cell['item'],expected_count=cell['count'],kind='pickup',button=1)
        deadline=time.monotonic()+3
        while s['menu']['cursor']['count']==old and time.monotonic()<deadline:
            time.sleep(.2);s=k.status()
        if s['menu']['cursor']['count']!=old-1:raise RuntimeError('Ingredient split not confirmed')
    if s['menu']['cursor']['count']!=amount:raise RuntimeError('Incorrect ingredient quantity')
    return s
def batch(ingredient,output,slots,output_per_recipe,target_total=None):
    total=0
    while True:
        s=k.status()
        if target_total is not None and count(s,output)>=target_total:break
        m=s['menu'];n_grid=4 if m['type']=='InventoryMenu' else 9 if m['type']=='CraftingMenu' else 0
        if not n_grid:raise RuntimeError('Open the expected crafting menu')
        if m['cursor']['item']!='minecraft:air' or any(m['slots'][i]['item']!='minecraft:air' for i in range(1,n_grid+1)):
            raise RuntimeError('Cursor or crafting grid is already occupied')
        player_start=len(m['slots'])-36 if m['type']=='CraftingMenu' else 9
        pieces=[x for x in m['slots'][player_start:player_start+36] if x['item']==ingredient]
        source=next((x for x in pieces if x['count']>=len(slots)),None)
        needed=None if target_total is None else math.ceil((target_total-count(s,output))/output_per_recipe)*len(slots)
        if needed is not None:
            enough=[x for x in pieces if x['count']>=needed]
            if enough:source=min(enough,key=lambda x:x['count'])
        if not source:
            if sum(x['count'] for x in pieces)<len(slots) or len(pieces)<2:break
            a,b=pieces[:2];combined=a['count']+b['count'];s=click(s,a['slot']);s=click(s,b['slot'])
            if s['menu']['cursor']['item']!='minecraft:air' or s['menu']['slots'][b['slot']]['count']!=combined:raise RuntimeError('Could not safely consolidate leftover ingredients')
            continue
        before_in=count(s,ingredient);before_out=count(s,output);n=source['count'] if needed is None else min(source['count'],needed)
        s=take_portion(s,source,n)
        s=checked('distribute',menu_id=m['id'],slots=slots,expected_cursor=ingredient,expected_cursor_count=n)
        if s['menu']['cursor']['item']!='minecraft:air':s=click(s,source['slot'])
        s=wait_for_recipe(s,output)
        s=click(s,0,'quick_move')
        # The click acknowledgement can precede the server's inventory update.
        # Wait for this batch's expected output before touching leftover slots.
        expected_gain=(n//len(slots))*output_per_recipe
        deadline=time.monotonic()+6
        while count(s,output)-before_out<expected_gain and time.monotonic()<deadline:
            time.sleep(.3);s=k.status()
        # Return leftovers if the inventory cannot accept the entire batch.
        for slot in slots:
            if s['menu']['slots'][slot]['item']!='minecraft:air':s=click(s,slot,'quick_move')
        consumed=before_in-count(s,ingredient);gained=count(s,output)-before_out
        if consumed<=0 or consumed%len(slots) or gained!=consumed//len(slots)*output_per_recipe:
            raise RuntimeError('Crafting result was not confirmed exactly')
        total+=gained;print(json.dumps({'recipe':output,'consumed':consumed,'produced':gained,'total':total,'verified':True}),flush=True)
    return total
