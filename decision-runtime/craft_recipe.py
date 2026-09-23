"""Craft mixed vanilla recipes through the real 3x3 grid, validating every batch."""
import math,time,json
k=None
from craft_grid import checked,click,take_portion,wait_for_recipe,count,compact_once,output_room,InventoryCapacity

SAFE_SINGLE_ROUND={'minecraft:bone_meal','minecraft:white_dye','minecraft:polished_andesite',
                   'minecraft:spruce_planks','minecraft:chest','minecraft:hopper'}

def safe_single_round(output):
    return output.endswith('_concrete_powder') or output in SAFE_SINGLE_ROUND


def wait_clear_cursor(state, menu_id):
    """A click reply may precede the server's cursor update; observe, never re-click."""
    deadline=time.monotonic()+6
    while state['menu']['cursor']['count']:
        if state['menu']['id']!=menu_id:
            raise RuntimeError('Crafting menu changed before cursor was returned')
        if time.monotonic()>=deadline:
            raise RuntimeError('Distribution did not clear cursor')
        time.sleep(.15);state=k.status()
    return state


def wait_cursor_count(state, menu_id, item, count):
    deadline=time.monotonic()+6
    while True:
        menu=state['menu'];cursor=menu['cursor']
        if menu['id']!=menu_id:raise RuntimeError('Crafting menu changed while returning ingredient')
        if cursor['item']==item and cursor['count']==count:return state
        if time.monotonic()>=deadline:raise RuntimeError('Ingredient cursor was not confirmed; no duplicate click')
        time.sleep(.15);state=k.status()


def wait_grid_placed(state, menu_id, item, slots, count_each):
    deadline=time.monotonic()+6
    confirmations=0
    while True:
        menu=state['menu']
        if menu['id']!=menu_id:raise RuntimeError('Crafting menu changed during ingredient distribution')
        if not menu['cursor']['count'] and all(menu['slots'][i]['item']==item and menu['slots'][i]['count']==count_each for i in slots):
            confirmations+=1
            if confirmations>=2:return state
        else:confirmations=0
        if time.monotonic()>=deadline:raise RuntimeError('Ingredient grid was not confirmed; no repeated distribution')
        time.sleep(.2);state=k.status()


def bounded_rounds(output, proposed):
    return min(proposed, 1) if safe_single_round(output) else proposed

def pin_chest_planks(plan, item):
    """Pin every tag-resolved chest cell to one ample plank type, without losing cells."""
    cells=sorted(slot for ingredient,positions in plan['ingredients'].items() for slot in positions)
    if plan['output']!='minecraft:chest' or not item.startswith('minecraft:') or not item.endswith('_planks') \
       or any(not ingredient.startswith('minecraft:') or not ingredient.endswith('_planks') for ingredient in plan['ingredients']) \
       or cells!=[1,2,3,4,6,7,8,9]:
        raise ValueError('Not an ordinary eight-plank chest recipe')
    return {**plan,'ingredients':{item:cells}}

def pin_furnace_cobblestone(plan):
    """Use a full cobblestone stack for all eight furnace cells when available."""
    cells=sorted(slot for positions in plan['ingredients'].values() for slot in positions)
    allowed={'minecraft:cobblestone','minecraft:cobbled_deepslate','minecraft:blackstone'}
    if plan['output']!='minecraft:furnace' or not set(plan['ingredients'])<=allowed or cells!=[1,2,3,4,6,7,8,9]:
        raise ValueError('Not an ordinary eight-stone furnace recipe')
    return {**plan,'ingredients':{'minecraft:cobblestone':cells}}

def mixed(recipe,output,output_per_recipe,target_total):
    """recipe maps item IDs to their 1-based crafting-grid slots."""
    while True:
        s=k.status();m=s['menu']
        remaining=target_total-count(s,output)
        if remaining<=0:return s
        if m['type'] not in ('CraftingMenu','InventoryMenu') or m['cursor']['item']!='minecraft:air':raise RuntimeError('Expected clear workbench cursor')
        if m['type']=='InventoryMenu' and s.get('screen')!='InventoryScreen':
            raise RuntimeError('Open the inventory screen or a verified workbench before clicking its crafting grid')
        if any(m['slots'][i]['item']!='minecraft:air' for i in range(1,10 if m['type']=='CraftingMenu' else 5)):raise RuntimeError('Crafting grid occupied')
        known=next((v['max_stack'] for v in s['inventory'] if v.get('slot',99)<36 and v['item']==output and v['count']),None)
        room=output_room(s,output,known or output_per_recipe)
        if room<output_per_recipe:
            s,merged=compact_once(s)
            if merged:continue
            raise InventoryCapacity('No output space; place or store finished materials first')
        start=len(m['slots'])-36 if m['type']=='CraftingMenu' else 9
        sources={item:sorted((x for x in m['slots'][start:start+36] if x['item']==item),key=lambda x:-x['count']) for item in recipe}
        if any(not v for v in sources.values()):raise RuntimeError('Missing recipe ingredient')
        rounds=min(math.ceil(remaining/output_per_recipe),room//output_per_recipe,1 if known is None else 64,*(sources[i][0]['count']//len(v) for i,v in recipe.items()))
        # Mixed concrete inputs use four separate gravel and sand cells. A
        # single ordinary recipe per transaction avoids optimistic multi-stack
        # QUICK_CRAFT acknowledgements being mistaken for server confirmation.
        rounds=bounded_rounds(output,rounds)
        if rounds<1:
            # Combine only matching item stacks, verifying the result before retrying the recipe.
            short=next(i for i,cells in recipe.items() if sources[i][0]['count']<len(cells))
            if sum(v['count'] for v in sources[short])<len(recipe[short]):raise RuntimeError('Missing recipe ingredient: '+short)
            a,b=sources[short][:2];combined=a['count']+b['count'];s=click(s,a['slot']);s=click(s,b['slot'])
            if s['menu']['cursor']['count'] or s['menu']['slots'][b['slot']]['count']!=combined:raise RuntimeError('Ingredient consolidation not confirmed')
            continue
        before={i:count(s,i) for i in recipe};old_output=count(s,output)
        for item,slots in recipe.items():
            amount=rounds*len(slots);source=next(v for v in s['menu']['slots'][start:start+36] if v['item']==item and v['count']>=amount)
            if len(slots)==1 and rounds==1:
                # A one-cell ingredient needs no half-stack split. Split loops
                # can race the server on successive right-clicks; place one
                # directly, then return the verified remainder to its source.
                s=click(s,source['slot'])
                s=wait_cursor_count(s,m['id'],item,source['count'])
                cell=s['menu']['slots'][slots[0]]
                s=checked('slot_click',menu_id=m['id'],slot=slots[0],expected_item=cell['item'],
                          expected_count=cell['count'],kind='pickup',button=1)
                if source['count']>1:
                    s=wait_cursor_count(s,m['id'],item,source['count']-1)
                    s=click(s,source['slot'])
                s=wait_clear_cursor(s,m['id'])
                s=wait_grid_placed(s,m['id'],item,slots,rounds)
                continue
            pickup=(source['count']+1)//2 if amount<source['count'] and amount<=(source['count']+1)//2 else source['count']
            if safe_single_round(output) or amount+2 < pickup-amount+2:
                s=click(s,source['slot'])
                for cell_id in slots:
                    for _ in range(rounds):
                        cell=s['menu']['slots'][cell_id]
                        s=checked('slot_click',menu_id=m['id'],slot=cell_id,expected_item=cell['item'],expected_count=cell['count'],kind='pickup',button=1)
                remaining=source['count']-amount
                if remaining:
                    s=wait_cursor_count(s,m['id'],item,remaining)
                    s=click(s,source['slot'])
            else:
                s=take_portion(s,source,amount)
                s=checked('distribute',menu_id=m['id'],slots=slots,expected_cursor=item,expected_cursor_count=amount)
            s=wait_clear_cursor(s,m['id'])
            s=wait_grid_placed(s,m['id'],item,slots,rounds)
        s=wait_for_recipe(s,output);s=click(s,0,'quick_move')
        until=time.monotonic()+8
        while count(s,output)-old_output<rounds*output_per_recipe and time.monotonic()<until:
            time.sleep(.3);s=k.status()
        for cells in recipe.values():
            for slot in cells:
                if s['menu']['slots'][slot]['item']!='minecraft:air':s=click(s,slot,'quick_move')
        made=count(s,output)-old_output
        if made<=0 or made%output_per_recipe:raise RuntimeError('Output not verified')
        executed=made//output_per_recipe
        if any(before[i]-count(s,i)!=executed*len(cells) for i,cells in recipe.items()):raise RuntimeError('Ingredient/output counts differ')
        print(json.dumps({'recipe':output,'produced':made,'inventory_total':count(s,output),'verified':True}),flush=True)


def execute(client,plan,target_total):
    global k
    import craft_grid
    k=client;craft_grid.k=client
    if plan['missing_for_one']:raise RuntimeError('Missing ingredients: '+str(plan['missing_for_one']))
    try:
        result=mixed(plan['ingredients'],plan['output'],plan['produces'],target_total)
        with (client.out/'craft-recipe-events.jsonl').open('a') as stream:
            stream.write(json.dumps({'time':int(time.time()*1000),'recipe':plan['recipe_id'],'output':plan['output'],'target_total':target_total,'verified_inventory_total':count(result,plan['output'])})+'\n')
        return result
    except Exception as error:
        record={'time':int(time.time()*1000),'plan':plan,'target_total':target_total,'error':str(error)}
        try:record['snapshot']=client.raw()
        except Exception:pass
        (client.out/'craft-failure-latest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2))
        raise
