"""Batch ordinary stackable recipes with exact group or per-cell transactions.

No guessed recipes or ambiguous action replays. The plan
comes from RecipeCatalog, and completion requires exact input/output balances.
"""
import copy
import json
import math
import time
from kit_runtime.inventory import InventorySession
from craft_grid import InventoryCapacity,count

STACKABLE_OUTPUTS={'minecraft:bone_meal','minecraft:white_dye','minecraft:white_concrete_powder',
    'minecraft:torch','minecraft:golden_apple','minecraft:gold_ingot',
    'minecraft:oak_planks','minecraft:spruce_planks','minecraft:cherry_planks','minecraft:diorite',
    'minecraft:stick','minecraft:arrow','minecraft:furnace','minecraft:blast_furnace','minecraft:andesite','minecraft:polished_andesite',
    'minecraft:polished_deepslate','minecraft:deepslate_bricks','minecraft:deepslate_tiles'}
WOOD_INPUTS={'minecraft:cherry_wood':'minecraft:cherry_log',
             'minecraft:stripped_cherry_wood':'minecraft:stripped_cherry_log'}
PLANK_INPUTS={f'minecraft:{wood}_planks':frozenset(f'minecraft:{prefix}{wood}_{kind}'
              for prefix in ('','stripped_')for kind in ('log','wood'))
              for wood in ('acacia','dark_oak')}
COLORS=('white','orange','magenta','light_blue','yellow','lime','pink','gray',
        'light_gray','cyan','purple','blue','brown','green','red','black')
COLOR_OUTPUTS={f'minecraft:{color}_{kind}':(color,kind)
               for color in COLORS for kind in ('concrete_powder','terracotta')
               if kind!='concrete_powder'or color!='white'}


def _color_recipe(spec):
    color,kind=COLOR_OUTPUTS[spec['output']];ingredients=spec.get('ingredients')or{}
    if (type(spec.get('width'))is not int or spec['width']!=3
            or type(spec.get('produces'))is not int or spec['produces']!=8
            or not isinstance(ingredients,dict)
            or any(not isinstance(cells,list)or any(type(cell)is not int for cell in cells)
                   for cells in ingredients.values())):return False
    dye=f'minecraft:{color}_dye'
    if kind=='terracotta':
        return ingredients=={'minecraft:terracotta':[1,2,3,4,6,7,8,9],dye:[5]}
    return (set(ingredients)=={'minecraft:sand','minecraft:gravel',dye}
            and len(ingredients['minecraft:sand'])==len(ingredients['minecraft:gravel'])==4
            and len(ingredients[dye])==1
            and sorted(cell for cells in ingredients.values()for cell in cells)==list(range(1,10)))

def supported(spec):
    if spec.get('output')in COLOR_OUTPUTS:return _color_recipe(spec)
    if spec.get('output') in PLANK_INPUTS:
        ingredients=spec.get('ingredients')or{}
        return bool(spec.get('width')in(2,3)and type(spec.get('produces'))is int and spec['produces']==4
            and isinstance(ingredients,dict)and len(ingredients)==1
            and next(iter(ingredients))in PLANK_INPUTS[spec['output']]
            and next(iter(ingredients.values()))==[1]
            and type(next(iter(ingredients.values()))[0])is int)
    if spec.get('output')=='minecraft:coarse_dirt':
        ingredients=spec.get('ingredients')or{}
        return bool(spec.get('width')in(2,3)and spec.get('produces')==4
            and set(ingredients)=={'minecraft:dirt','minecraft:gravel'}
            and all(isinstance(v,list)and len(v)==2 for v in ingredients.values())
            and sorted(cell for values in ingredients.values()for cell in values)==[1,2,3,4])
    if spec.get('output')=='minecraft:packed_mud':
        ingredients=spec.get('ingredients')or{}
        return bool(spec.get('width')in (2,3)and spec.get('produces')==1
            and set(ingredients)=={'minecraft:mud','minecraft:wheat'}
            and all(isinstance(v,list)and len(v)==1 for v in ingredients.values())
            and sorted(cell for values in ingredients.values()for cell in values)==[1,2])
    if spec.get('output')=='minecraft:mud_bricks':
        cells=[1,2,3,4]if spec.get('width')==2 else[1,2,4,5]if spec.get('width')==3 else None
        return bool(cells and spec.get('produces')==4
            and spec.get('ingredients')=={'minecraft:packed_mud':cells})
    if spec.get('output') in WOOD_INPUTS:
        raw=WOOD_INPUTS[spec['output']]
        cells=[1,2,3,4] if spec.get('width')==2 else [1,2,4,5] if spec.get('width')==3 else None
        return bool(cells and spec.get('produces')==3 and spec.get('ingredients')=={raw:cells})
    return spec.get('output') in STACKABLE_OUTPUTS


def split_cost(size,needed):
    half=(size+1)//2
    picked=half if needed<=half and needed<size else size
    return min(2+picked-needed,2+needed)


def grouped_batch(menu,spec,max_rounds):
    """Use vanilla group distribution only for exact full/half ingredient stacks.

    A partial 40+24 pair can produce ten rounds then six, without returning
    twenty items one at a time. Other recipes retain their ordinary cell path.
    """
    if spec.get('output')not in COLOR_OUTPUTS or not _color_recipe(spec):return None
    for rounds in range(max_rounds,0,-1):
        slots=copy.deepcopy(menu['slots'][-36:]);actions=[]
        for item,cells in spec['ingredients'].items():
            amount=rounds*len(cells)
            available=[v for v in slots if v['item']==item and v['count']>=amount
                       and (len(cells)==1 or v['count']==amount or (v['count']+1)//2==amount)]
            if not available:break
            source=min(available,key=lambda v:(split_cost(v['count'],amount),v['slot']))
            actions.append({'source':source['slot'],'source_count':source['count'],
                            'item':item,'cells':list(cells),'count':rounds})
            source['count']-=amount
            if not source['count']:source['item']='minecraft:air'
        else:
            room=sum(64 if not v['count'] else 64-v['count'] if v['item']==spec['output']else 0 for v in slots)
            if room>=rounds*spec['produces']:
                return {'rounds':rounds,'produced':rounds*spec['produces'],'actions':actions,'distribution':'exact_groups'}
    return None


def plan_batch(state,spec,max_rounds=32,*,grouped=True):
    menu=state['menu']
    if menu['type']!='CraftingMenu' or menu['cursor']['count'] or any(v['count'] for v in menu['slots'][1:10]):
        raise RuntimeError('Expected an open clear workbench')
    cells=[cell for slots in spec['ingredients'].values() for cell in slots]
    if not cells or len(set(cells))!=len(cells) or not all(1<=cell<=9 for cell in cells):
        raise ValueError('Invalid recipe cells')
    if not 1<=max_rounds<=64 or not 1<=spec['produces']<=64:
        raise ValueError('Invalid batch count')
    group=grouped_batch(menu,spec,max_rounds) if grouped else None
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
            if group is not None:
                ordinary_cost=1+sum(split_cost(a['source_count'],a['count']) for a in actions)
                group_cost=1+sum(2 if len(a['cells'])>1 else split_cost(a['source_count'],a['count']) for a in group['actions'])
                if group['rounds']*ordinary_cost>=rounds*group_cost:return group
            return {'rounds':rounds,'produced':rounds*spec['produces'],'actions':actions}
    if group is not None:return group
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
        batch=plan_batch(before,spec,min(max_rounds,math.ceil(remaining/spec['produces'])),
                         grouped=getattr(client,'sdk_inventory_confirmation',False)is not True)
        state=before
        try:
            for action in batch['actions']:
                source=state['menu']['slots'][action['source']]
                if source['item']!=action['item'] or source['count']!=action['source_count']:
                    raise RuntimeError('Ingredient source changed after batch planning')
                cells=action.get('cells',[action.get('cell')])
                if len(cells)>1:state=session.distribute_exact(state,source,cells,action['count'])
                else:state=session.place_cell(state,source,cells[0],action['count'])
                state=session.wait_grid(state,before['menu']['id'],action['item'],cells,action['count'])
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
                   'distribution':batch.get('distribution','per_cell'),
                   'time':state.get('time'),'verified':True}
            with (client.out/'stack-recipe-events.jsonl').open('a') as stream:stream.write(json.dumps(event)+'\n')
            print('STACK_CRAFT',json.dumps(event),flush=True)
        except Exception as error:
            (client.out/'stack-recipe-failure.json').write_text(json.dumps({'recipe':spec,'batch':batch,'error':str(error),'before':before},ensure_ascii=False,indent=2))
            raise
