"""Repair a carried bow through the real owned anvil preview and normal clicks."""
from collections import Counter
from pathlib import Path
import time
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json


from repair_stack_identity import identity, enchantments


def validate_preview(state,left,right,*,minimum_durability,max_cost=8):
    menu=state['menu'];slots=menu['slots'];out=slots[2]
    if menu['type']!='AnvilMenu' or menu['cursor']['count'] or identity(slots[0])!=identity(left) or identity(slots[1])!=identity(right):
        raise ValueError('Exact owned anvil inputs and empty cursor required')
    cost=menu.get('anvil_cost')
    if(type(cost)is not int or not 1<=cost<=max_cost or cost>state.get('experience_level',-1)
       or menu.get('anvil_too_expensive') or menu.get('anvil_result_may_pickup')is not True):
        raise ValueError('Actual anvil level cost is not affordable within the repair budget')
    expected=enchantments(left)
    if any(key.endswith('_curse') and key not in expected for key in enchantments(right)):
        raise ValueError('Repair must not introduce a new curse to the original bow')
    for key,level in enchantments(right).items():expected[key]=max(expected.get(key,0),level)
    if(out.get('item')!='minecraft:bow' or out.get('count')!=1
       or out.get('max_durability')!=384 or out.get('durability',-1)<minimum_durability
       or any(enchantments(out).get(k,0)<v for k,v in expected.items())
       or identity(out)==identity(left)):
        raise ValueError('Preview must improve this bow and preserve all input enchantments')
    return out,cost


def repair(client,left_slot,right_slot,out,*,minimum_durability=384,max_cost=8):
    out=Path(out);out.mkdir(exist_ok=False);path=out/'repair.json';state=client.status();menu=state['menu']
    if(menu['type']!='AnvilMenu' or menu['id']<=0 or menu['cursor']['count']
       or any(v['count']for v in menu['slots'][:3]) or left_slot==right_slot
       or any(type(v)is not int or not 3<=v<len(menu['slots'])for v in(left_slot,right_slot))):
        raise ValueError('Empty owned anvil and two distinct carried source slots required')
    left=dict(menu['slots'][left_slot]);right=dict(menu['slots'][right_slot])
    for row in(left,right):
        if row.get('item')!='minecraft:bow' or row.get('count')!=1 or row.get('max_durability')!=384:raise ValueError('Two actual bows required')
    initial=Counter(v['item']for v in state['inventory']if v.get('slot',99)<36 and v.get('count')and v['item']=='minecraft:bow')['minecraft:bow']
    book={'world_session':client.world,'left':left,'right':right,'minimum_durability':minimum_durability,'max_cost':max_cost,'complete':False,'pending':None}
    def save():write_json(path,book)
    client.owned_material_menu=menu['id'];session=InventorySession(client);save()
    for source,cell in [(left,0),(right,1)]:
        state=client.status();source_now=state['menu']['slots'][source['slot']]
        if identity(source_now)!=identity(source):raise RuntimeError('Original bow changed; no substitute repair')
        book['pending']={'kind':'owned_input','source':source,'cell':cell};save()
        state=session.place_cell(state,source_now,cell,1);book['pending']=None;save()
    until=time.monotonic()+6;last_error=None
    while time.monotonic()<until:
        state=client.status()
        try:preview,cost=validate_preview(state,left,right,minimum_durability=minimum_durability,max_cost=max_cost)
        except ValueError as error:last_error=error;time.sleep(.15);continue
        break
    else:raise RuntimeError(str(last_error or 'Actual repair preview unavailable; owned inputs retained'))
    before_level=state['experience_level'];book.update(preview=preview,actual_cost=cost,level_before=before_level,pending={'kind':'one_result_quick_move','slot':2});save()
    result=session.click(state,2,'quick_move')
    result=session._wait(result,menu['id'],lambda m:not m['cursor']['count']and all(not r['count']for r in m['slots'][:3]),'anvil_output_taken',confirmations=2,fresh=True)
    after=client.status();bows=[v for v in after['inventory']if v.get('slot',99)<36 and v.get('item')=='minecraft:bow'and v.get('count')]
    if(len(bows)!=initial-1 or not any(identity(v)==identity(preview)for v in bows)
       or after.get('experience_level')!=before_level-cost):
        raise RuntimeError('Original result click lacks exact bow and level conservation; do not repeat')
    book.update(complete=True,pending=None,actual_bows=bows,level_after=after['experience_level'],health=after['health']);save();return book
