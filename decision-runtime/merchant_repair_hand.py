"""Keep an already selected, exact damaged Mending tool for trade XP."""
from anvil_enchant_preview import stack_key,enchantments


def selected_tool(state):
    hand=state.get('hand')or{};slot=state.get('selected_slot');item=hand.get('item','')
    if (type(slot)is not int or not 0<=slot<9 or hand.get('count')!=1
            or not (item in ('minecraft:bow','minecraft:crossbow','minecraft:trident')
                    or item.startswith('minecraft:')and item.endswith(('_pickaxe','_axe','_shovel','_hoe','_sword')))
            or type(hand.get('durability'))is not int or type(hand.get('max_durability'))is not int
            or not 0<hand['durability']<hand['max_durability']
            or enchantments(hand).get('minecraft:mending')!=1
            or any(k.endswith('_curse')for k in enchantments(hand))):return None
    row=next((v for v in state.get('inventory',[])if v.get('slot')==slot),None)
    if not row or row.get('count')!=1 or stack_key(row)!=stack_key(hand):return None
    return {'item':item,'slot':slot,'enchantments':enchantments(hand),'durability':hand['durability'],
            'max_durability':hand['max_durability']}


def retained(state,preferred):
    hand=state.get('hand')or{}
    return (state.get('selected_slot')==preferred['slot'] and hand.get('item')==preferred['item']
            and enchantments(hand)==preferred['enchantments']
            and hand.get('max_durability')==preferred['max_durability']
            and type(hand.get('durability'))is int
            and preferred['durability']<=hand['durability']<=preferred['max_durability'])
