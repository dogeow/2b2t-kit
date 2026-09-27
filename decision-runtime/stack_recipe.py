"""Batch ordinary stackable recipes with explicit per-cell pickup/place actions.

No drag distribution, guessed recipes, or ambiguous action replays. The plan
comes from RecipeCatalog, and completion requires exact input/output balances.
"""
import copy
import json
import math
import time
from kit_runtime.inventory import InventorySession
from craft_grid import InventoryCapacity,count

STACKABLE_OUTPUTS={'minecraft:bone_meal','minecraft:white_dye','minecraft:white_concrete_powder',
    'minecraft:stick','minecraft:arrow','minecraft:furnace','minecraft:blast_furnace','minecraft:andesite','minecraft:polished_andesite',
    'minecraft:polished_deepslate','minecraft:deepslate_bricks','minecraft:deepslate_tiles'}

def supported(spec):
    return spec.get('output') in STACKABLE_OUTPUTS


def split_cost(size,needed):
    half=(size+1)//2
    picked=half if needed<=half and needed<size else size
    return min(2+picked-needed,2+needed)


def plan_batch(state,spec,max_rounds=32):
    menu=state['menu']
    if menu['type']!='CraftingMenu' or menu['cursor']['count'] or any(v['count'] for v in menu['slots'][1:10]):
        raise RuntimeError('Expected an open clear workbench')
    cells=[cell for slots in spec['ingredients'].values() for cell in slots]
    if not cells or len(set(cells))!=len(cells) or not all(1<=cell<=9 for cell in cells):
        raise ValueError('Invalid recipe cells')
    if not 1<=max_rounds<=64 or not 1<=spec['produces']<=64:
        raise ValueError('Invalid batch count')
    for rounds in range(max_rounds,0,-1):
        slots=copy.deepcopy(menu['slots'][-36:]);actions=[]
        for item,positions in spec['ingredients'].items():
            for cell in positions:
                available=[v for v in slots if v['item']==item and v['count']>=rounds]
                if not available:break
                source=min(available,key=lambda v:(split_cost(v['count'],rounds),v['slot']))
                actions.append({'source':source['slot'],'source_count':source['count'],
                                'item':item,'cell':cell,'count':rounds})
                source['count']-=rounds
                if not source['count']:source['item']='minecraft:air'
            else:continue
            break
        if len(actions)!=len(cells):continue
        # Inventory slots emptied by moving inputs into the grid are available
        # for the output. Never demand that capacity already exist beforehand.
        room=sum(64 if not v['count'] else 64-v['count'] if v['item']==spec['output'] else 0 for v in slots)
        if room>=rounds*spec['produces']:
            return {'rounds':rounds,'produced':rounds*spec['produces'],'actions':actions}
    raise InventoryCapacity('No complete recipe batch fits current stacks and output capacity')


def settled_result(before,state,spec,batch):
    menu=state['menu']
    if menu['id']!=before['menu']['id']:raise RuntimeError('Workbench changed during batch')
    return (not menu['cursor']['count'] and not any(v['count'] for v in menu['slots'][1:10])
            and count(state,spec['output'])-count(before,spec['output'])==batch['produced']
            and all(count(before,item)-count(state,item)==batch['rounds']*len(cells)
                    for item,cells in spec['ingredients'].items()))


def place_cell(client,state,source,cell,amount):
    """Compatibility entry point; all state belongs to the supplied client."""
    return InventorySession(client).place_cell(state,source,cell,amount)


def execute(client,spec,target_total,max_rounds=64):
    if not supported(spec):raise ValueError('This output is not an ordinary supported stackable recipe')
    if spec.get('missing_for_one'):raise RuntimeError('Recipe ingredients are missing')
    session=InventorySession(client)
    while True:
        before=client.status();remaining=target_total-count(before,spec['output'])
        if remaining<=0:return before
        batch=plan_batch(before,spec,min(max_rounds,math.ceil(remaining/spec['produces'])))
        state=before
        try:
            for action in batch['actions']:
                source=state['menu']['slots'][action['source']]
                if source['item']!=action['item'] or source['count']!=action['source_count']:
                    raise RuntimeError('Ingredient source changed after batch planning')
                state=session.place_cell(state,source,action['cell'],action['count'])
                state=session.wait_grid(state,before['menu']['id'],action['item'],[action['cell']],action['count'])
            state=session.wait_recipe(state,spec['output'])
            if state['menu']['slots'][0]['count']!=spec['produces']:
                raise RuntimeError('Server offered an unexpected recipe output quantity')
            state=session.click(state,0,'quick_move')
            deadline=time.monotonic()+8;confirmations=0
            while True:
                if settled_result(before,state,spec,batch):
                    confirmations+=1
                    if confirmations>=2:break
                else:confirmations=0
                if time.monotonic()>=deadline:raise RuntimeError('Batch balances not confirmed; do not replay output click')
                time.sleep(.2);state=client.status()
            event={'recipe':spec['recipe_id'],'output':spec['output'],'rounds':batch['rounds'],
                   'produced':batch['produced'],'total':count(state,spec['output']),
                   'time':state.get('time'),'verified':True}
            with (client.out/'stack-recipe-events.jsonl').open('a') as stream:stream.write(json.dumps(event)+'\n')
            print('STACK_CRAFT',json.dumps(event),flush=True)
        except Exception as error:
            (client.out/'stack-recipe-failure.json').write_text(json.dumps({'recipe':spec,'batch':batch,'error':str(error),'before':before},ensure_ascii=False,indent=2))
            raise
