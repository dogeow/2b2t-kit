"""Craft mixed vanilla recipes through the real 3x3 grid, validating every batch."""
import math,time,json
k=None
from craft_grid import checked,click,take_portion,wait_for_recipe,count,compact_once,output_room,InventoryCapacity

def mixed(recipe,output,output_per_recipe,target_total):
    """recipe maps item IDs to their 1-based crafting-grid slots."""
    while True:
        s=k.status();m=s['menu']
        remaining=target_total-count(s,output)
        if remaining<=0:return s
        if m['type'] not in ('CraftingMenu','InventoryMenu') or m['cursor']['item']!='minecraft:air':raise RuntimeError('Expected clear workbench cursor')
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
            pickup=(source['count']+1)//2 if amount<source['count'] and amount<=(source['count']+1)//2 else source['count']
            if amount+2 < pickup-amount+2:
                s=click(s,source['slot'])
                for cell_id in slots:
                    for _ in range(rounds):
                        cell=s['menu']['slots'][cell_id]
                        s=checked('slot_click',menu_id=m['id'],slot=cell_id,expected_item=cell['item'],expected_count=cell['count'],kind='pickup',button=1)
                if s['menu']['cursor']['count']:s=click(s,source['slot'])
            else:
                s=take_portion(s,source,amount)
                s=checked('distribute',menu_id=m['id'],slots=slots,expected_cursor=item,expected_cursor_count=amount)
            if s['menu']['cursor']['item']!='minecraft:air':raise RuntimeError('Distribution did not clear cursor')
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
