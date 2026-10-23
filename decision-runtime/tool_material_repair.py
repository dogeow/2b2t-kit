"""Repair one diamond axe with two diamonds through one owned anvil operation."""
from collections import Counter
from pathlib import Path
import time
from repair_stack_identity import identity, enchantments
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json


def counts(state):
    result=Counter()
    for row in state['inventory']:
        if row.get('slot',99)<36 and row.get('count'):result[row['item']]+=row['count']
    return result


def validate_preview(state,left,right,*,minimum_durability=1000,max_cost=4):
    menu=state['menu'];rows=menu['slots'];out=rows[2]
    if (menu['type']!='AnvilMenu' or menu['cursor']['count']
            or identity(rows[0])!=identity(left) or identity(rows[1])!=identity(right)
            or left.get('item')!='minecraft:diamond_axe' or left.get('count')!=1
            or left.get('max_durability')!=1561 or right.get('item')!='minecraft:diamond'
            or right.get('count')!=2 or type(left.get('durability'))is not int
            or not 0<left['durability']<=781):
        raise ValueError('Exact damaged diamond axe and two diamond inputs required')
    cost=menu.get('anvil_cost');expected=left['durability']+2*(1561//4)
    if (type(cost)is not int or not 1<=cost<=max_cost or cost>state.get('experience_level',-1)
            or menu.get('anvil_too_expensive') or menu.get('anvil_result_may_pickup')is not True
            or out.get('item')!=left['item'] or out.get('count')!=1
            or out.get('max_durability')!=1561 or out.get('durability')!=expected
            or expected<minimum_durability or enchantments(out)!=enchantments(left)):
        raise ValueError('Actual tool repair preview, cost or enchantment conservation changed')
    return out,cost


def outcome(state,before,preview,level_before,cost):
    expected=Counter(before);expected['minecraft:diamond']-=2;expected+=Counter()
    if counts(state)!=expected or state.get('experience_level')!=level_before-cost:
        return False
    menu=state.get('menu')or{}
    if (menu.get('type')not in('AnvilMenu','InventoryMenu')or menu.get('cursor',{}).get('count')
            or menu['type']=='AnvilMenu'and any(r['count']for r in menu['slots'][:3])):
        return False
    # The normal anvil damage roll can close its window after the output click.
    # Exact returned stack, material and XP conservation still remain mandatory.
    return any(identity(r)==identity(preview)for r in menu['slots'])


def repair(client,pos,out,*,minimum_durability=1000,max_cost=4):
    out=Path(out);out.mkdir(exist_ok=False);path=out/'repair.json'
    initial=client.status()
    if initial.get('screen')or initial['menu']['cursor']['count']:
        raise ValueError('Tool repair must open its own anvil from the world')
    before=counts(initial)
    if before['minecraft:diamond_axe']!=1 or before['minecraft:diamond']!=2:
        raise ValueError('One carried axe and exactly two carried diamonds required')
    scanned=client.checked('scan',min=pos,max=pos,details=True)
    if len(scanned['blocks'])!=1 or not any(scanned['blocks'][0]['state'].startswith('Block{minecraft:'+name+'}')for name in('anvil','chipped_anvil','damaged_anvil')):
        raise ValueError('No actual registered repair anvil; no input moved')
    client.checked('select_item',item='minecraft:netherite_sword')
    opened=client.checked('interact',pos=pos,face='west',expected_state=scanned['blocks'][0]['state'],expected_hand='minecraft:netherite_sword')
    deadline=time.monotonic()+6
    while True:
        state=client.status();m=state['menu']
        if m['type']=='AnvilMenu'and m['id']>0:break
        if time.monotonic()>deadline:raise RuntimeError('Own anvil opening not observed; no replay')
        time.sleep(.1)
    if m['cursor']['count']or any(r['count']for r in m['slots'][:3]):raise RuntimeError('Anvil inputs are not empty; no transfer')
    client.owned_material_menu=m['id']
    from owned_material_menu import owned_menu_result
    owned_menu_result(client,{})
    axes=[r for r in m['slots'][3:]if r['item']=='minecraft:diamond_axe'and r['count']==1]
    diamonds=[r for r in m['slots'][3:]if r['item']=='minecraft:diamond'and r['count']==2]
    if len(axes)!=1 or len(diamonds)!=1:raise RuntimeError('Exact carried input slots changed')
    left,right=dict(axes[0]),dict(diamonds[0]);book={'world_session':client.world,'anvil':pos,'opening_request':opened['id'],'left':left,'right':right,'complete':False,'pending':None,'scope':'owned_anvil_preview_and_two_fresh_conservation_observations'}
    def save():write_json(path,book)
    save();session=InventorySession(client)
    for source,cell,amount in [(left,0,1),(right,1,2)]:
        state=client.status();row=state['menu']['slots'][source['slot']]
        if identity(row)!=identity(source):raise RuntimeError('Source input changed; no substitute')
        book['pending']={'stage':'input','source':source['slot'],'cell':cell,'amount':amount};save();session.place_cell(state,row,cell,amount);book['pending']=None;save()
    deadline=time.monotonic()+6
    while True:
        state=client.status()
        try:preview,cost=validate_preview(state,left,right,minimum_durability=minimum_durability,max_cost=max_cost)
        except ValueError:
            if time.monotonic()>deadline:raise
            time.sleep(.1);continue
        break
    level=state['experience_level'];book.update(preview=preview,cost=cost,level_before=level,pending={'stage':'one_output_click'});save();session.click(state,2,'quick_move');deadline=time.monotonic()+8;times=[]
    while len(times)<2:
        state=client.status()
        if outcome(state,before,preview,level,cost)and(not times or state['time']>times[-1]):times.append(state['time'])
        if time.monotonic()>deadline:raise RuntimeError('Output click lacks exact tool/material/XP conservation; do not repeat')
        time.sleep(.15)
    book.update(complete=True,pending=None,observed_times=times,level_after=state['experience_level'],durability_after=preview['durability'],anvil_window_closed=state['menu']['type']=='InventoryMenu');save()
    if state['menu']['type']=='AnvilMenu':client.checked('close_menu')
    return book
