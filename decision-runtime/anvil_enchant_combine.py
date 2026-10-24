"""One planned anvil output, after two exact current cost/result observations.

The output is clicked at most once. Any uncertain receipt remains pending;
there is no retry, substitution or automatic menu cleanup on an exception.
"""
from copy import deepcopy
from pathlib import Path
from anvil_enchant_preview import (validate_inputs,stack_key,bag,menu_slot,
                                   inspect_preview,_wait)
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json
from owned_material_menu import owned_menu_result


def run(client,pos,left_slot,right_slot,left,right,expected,cost,out,*,face='up'):
    if type(cost)is not int or not 1<=cost<=39:
        raise ValueError('Explicit planned legal anvil cost 1..39 required')
    validate_inputs(left,right,expected)
    ls,rs=menu_slot(left_slot),menu_slot(right_slot)
    if ls==rs or face not in ('up','north','south','east','west'):
        raise ValueError('Distinct inputs and reachable ordinary face required')
    if not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos):
        raise ValueError('Exact owned anvil position required')
    initial=client.status();level=initial['experience_level'];held={v['slot']:v for v in initial['inventory']}
    if (initial.get('screen') or initial['menu']['cursor']['count'] or level<cost
            or not initial.get('hand',{}).get('item','').endswith('_sword')
            or any(held.get(slot,{}).get('count')!=1 or stack_key(held[slot])!=stack_key(row)
                   for slot,row in ((left_slot,left),(right_slot,right)))):
        raise ValueError('Exact carried inputs, adequate levels and a clean owned stance required')
    # One empty destination for shift-click; do not move armor or replace slots.
    if not any(not row['count'] for slot,row in held.items()if 0<=slot<36):
        raise ValueError('Reserve an empty carried output slot before combining')
    before=bag(initial);out=Path(out);out.mkdir(exist_ok=False);path=out/'combine.json'
    record={'complete':False,'pending':None,'world_session':client.world,'task_session':client.task,
            'anvil':pos,'left':deepcopy(left),'right':deepcopy(right),'planned_cost':cost,
            'expected_enchantments':expected,'level_before':level,'output_clicks':0,
            'input_slots':{'left':left_slot,'right':right_slot}}
    def save():write_json(path,record)
    save();scan=client.checked('scan',min=pos,max=pos,details=True)
    blocks=scan.get('blocks',[])
    if len(blocks)!=1 or not any(blocks[0]['state'].startswith('Block{minecraft:'+k+'}')
                                  for k in ('anvil','chipped_anvil','damaged_anvil')):
        raise ValueError('Owned anvil changed; no inputs moved')
    record['pending']='open_owned_anvil';save()
    opened=client.checked('interact',pos=pos,face=face,expected_state=blocks[0]['state'],expected_hand=initial['hand']['item'])
    state,_=_wait(client,lambda s:s['menu']['type']=='AnvilMenu'and s['menu']['id']>0)
    menu=state['menu'];mid=menu['id']
    if len(menu['slots'])!=39 or menu['cursor']['count'] or any(r['count']for r in menu['slots'][:3]):
        raise RuntimeError('Anvil opening differs; no input/output sent')
    client.owned_material_menu=mid;owned_menu_result(client,{})
    record.update(menu_id=mid,opening_request=opened['id'],pending=None);save();session=InventorySession(client)
    for slot,cell,row in ((ls,0,left),(rs,1,right)):
        state=client.status();actual=state['menu']['slots'][slot]
        if state['menu']['id']!=mid or actual['count']!=1 or stack_key(actual)!=stack_key(row):
            raise RuntimeError('Bound input changed; no substitute or next click')
        record['pending']={'stage':'place_input','cell':cell,'source':slot};save()
        session.place_cell(state,actual,cell,1)
        _wait(client,lambda s,cell=cell,row=row:s['menu']['id']==mid and not s['menu']['cursor']['count']
              and s['menu']['slots'][cell]['count']==1 and stack_key(s['menu']['slots'][cell])==stack_key(row))
        record['pending']=None;save()
    def accepted(s):
        if s['menu']['id']!=mid:raise RuntimeError('Owned combine window changed; no output sent')
        preview=inspect_preview(s,left,right,expected)
        return (preview['preview_accepted'] and preview['cost_levels']==cost
                and not preview['too_expensive'] and preview['affordable_now']
                and s['experience_level']==level)
    state,times=_wait(client,accepted)
    output=deepcopy(state['menu']['slots'][2]);after=before.copy()
    after[stack_key(left)]-=1;after[stack_key(right)]-=1;after[stack_key(output)]+=1
    after=+after
    record.update(actual_cost=state['menu']['anvil_cost'],preview_times=times,expected_output=output,
                  pending={'stage':'take_output_once','menu_id':mid,'slot':2},output_clicks=1);save()
    result=session.click(state,2,'quick_move')
    final,times=_wait(client,lambda s:s['menu']['id']==mid and not s['menu']['cursor']['count']
                      and all(not r['count']for r in s['menu']['slots'][:3])
                      and bag(s)==after and s['experience_level']==level-cost)
    record.update(output_request=result['id'],output_confirmations=times,pending='close_empty_owned_anvil');save()
    closed=client.checked('close_menu')
    final,times=_wait(client,lambda s:not s.get('screen') and s['menu']['id']==0
                      and bag(s)==after and s['experience_level']==level-cost)
    candidates=[v for v in final['inventory']if v['count']==1 and stack_key(v)==stack_key(output)]
    record.update(complete=True,pending=None,closed_request=closed['id'],closed_times=times,
                  level_after=final['experience_level'],experience_levels_spent=cost,
                  output_inventory_slots=[v['slot']for v in candidates],visible_inventory_conserved=True)
    save();owned_menu_result(client,{});return record
