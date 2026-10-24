"""Take a bounded exact sequence in ONE portable-box visit, then return it.

Every item click has its own pending journal and two fresh inventory witnesses.
Unknown clicks never advance the sequence or automatically start recovery.
"""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from anvil_enchant_preview import stack_key,enchantments,bag,_wait
from material_plan import inventory_counts
from material_jobs.protocol import server_key
from packed_supplies import (contents,open_box,block,carried_box,clear_player_from_pad,
                              recover_and_return,workspace_requirement,PackedWorkspaceRequired,wait)
from projection_wood import use_with_margin
from material_cleanup import register as register_cleanup
from kit_runtime.journal import write_json


def stacks(rows):
    result=Counter()
    for row in rows:
        if row.get('count'):result[stack_key(row)]+=row['count']
    return result


def take(client,profile_path,slot,requests):
    if (type(slot)is not int or not 0<=slot<27 or not isinstance(requests,list)or not 1<=len(requests)<=8
            or any(not isinstance(v,dict)or v.get('count')!=1 or v.get('max_stack')!=1
                   or not v.get('item','').startswith('minecraft:')
                   or any(k.endswith('_curse')for k in enchantments(v))for v in requests)):
        raise ValueError('Explicit box and 1..8 exact uncursed unstackable items required')
    profile=json.loads(Path(profile_path).read_text());initial=client.status()
    if (server_key(profile.get('server'))!=server_key(client.server)or profile.get('dimension')!=initial.get('dimension')):
        raise ValueError('Current registered Ender workspace required')
    receipt=workspace_requirement(initial)
    free=sum(not v['count']for v in initial['inventory']if v['slot']<36)
    if receipt:raise PackedWorkspaceRequired(receipt)
    if free<len(requests)+2:raise ValueError('Reserve batch outputs and two intact-box workspace slots')
    if any(v['count']and v['item'].endswith('shulker_box')for v in initial['inventory']):
        raise ValueError('Finish the existing carried box before a new batch')
    journal=client.out/'packed-transfer-active.json'
    if journal.exists()and json.loads(journal.read_text())['stage']!='returned':
        raise RuntimeError('Original portable-box journal is unresolved; no withdrawal')
    ender,pad=profile['ender_chest'],profile['shulker_pad'];ground=[pad[0],pad[1]-1,pad[2]]
    floor=block(client,ground)
    if not floor or 'minecraft:grass_block'not in floor or block(client,pad)or block(client,[pad[0],pad[1]+1,pad[2]]):
        raise RuntimeError('Registered temporary grass pad is not empty')
    state=open_box(client,ender,'ChestMenu');source=deepcopy(state['menu']['slots'][slot]);available=stacks(source.get('contains',[]));wanted=stacks(requests)
    if source['count']!=1 or not source['item'].endswith('shulker_box')or any(available[k]<n for k,n in wanted.items()):
        client.checked('close_menu');raise ValueError('Explicit source lacks the complete exact batch; no box taken')
    initial_counts=contents(source['contains']);before=bag(state)
    record={'world_session':client.world,'task_session':client.task,'slot':slot,'item':source['item'],
            'initial_counts':initial_counts,'temporary_position':pad,'stage':'prepared','exact_requests':deepcopy(requests),
            'source':{'position':ender,'slot':slot,'item':source['item'],'count':1,'counts':initial_counts,
                      'visible_stack':source},'batch_completed':0,'pending':None,
            'ownership_preflight':{'world_session':client.world,'cursor_clean':True,'inventory':deepcopy(initial['inventory'])}}
    def save(stage=None):
        if stage:record['stage']=stage
        write_json(journal,record)
    save();record['pending']={'stage':'take_intact_box','slot':slot};save()
    result=client.checked('slot_click',menu_id=state['menu']['id'],slot=slot,expected_item=source['item'],expected_count=1,kind='quick_move')
    wait(client,lambda s:carried_box(s,source['item'],initial_counts)is not None)
    carried=next(v for v in client.status()['inventory']if v['count']and v['item']==source['item'])
    if stacks(carried.get('contains',[]))!=available:raise RuntimeError('Carried source components changed; no placement')
    record.update(pending=None,box_request=result['id']);save('carried')
    register_cleanup(client,str(journal),lambda:recover_and_return(client,record,ender,journal))
    client.checked('close_menu');client.checked('select_item',item=source['item'],slot=carried['slot']);clear_player_from_pad(client,pad)
    def empty_pad():
        if block(client,pad)is not None or block(client,ground)!=floor:raise RuntimeError('Batch placement pad changed')
    use_with_margin(client,ground,floor,source['item'],('up',),empty_pad)
    placed=block(client,pad)
    if 'shulker_box'not in(placed or ''):raise RuntimeError('Original batch box placement unconfirmed')
    record['placed_state']=placed;save('placed');state=open_box(client,pad,'ShulkerBoxMenu');mid=state['menu']['id']
    if stacks(state['menu']['slots'][:27])!=available:raise RuntimeError('Opened original box components changed; no item taken')
    for index,expected in enumerate(requests):
        state=client.status();menu=state['menu']
        if menu['id']!=mid or menu['cursor']['count']:raise RuntimeError('Original batch window/cursor changed')
        row=next((v for v in menu['slots'][:27]if v['count']==1 and stack_key(v)==stack_key(expected)),None)
        if row is None:raise RuntimeError('Exact next item changed; no substitute or click replay')
        target=bag(state);target[stack_key(expected)]+=1
        record['pending']={'stage':'take_exact_item','index':index,'slot':row['slot'],'expected':expected};save()
        result=client.checked('slot_click',menu_id=mid,slot=row['slot'],expected_item=row['item'],expected_count=1,kind='quick_move')
        state,times=_wait(client,lambda s:s['menu']['id']==mid and not s['menu']['cursor']['count']
                          and not s['menu']['slots'][row['slot']]['count']and bag(s)==target)
        record.setdefault('item_receipts',[]).append({'index':index,'request_id':result['id'],'observed_at':times})
        record.update(batch_completed=index+1,pending=None);save()
    state=client.status();remaining=contents(state['menu']['slots'][:27]);taken=Counter()
    for v in requests:taken[v['item']]+=1
    if (bag(state)!=before+wanted or stacks(state['menu']['slots'][:27])!=available-wanted
            or any(initial_counts[k]-remaining.get(k,0)!=taken.get(k,0)for k in initial_counts)):
        raise RuntimeError('Batch inventory/component conservation failed; no cleanup or replay')
    record.update(remaining_counts=remaining,taken=dict(taken),
                  before_drop_uuids=[v['uuid']for v in state.get('entities',[])if v.get('type')=='minecraft:item'],
                  drop_baseline_scope='confirmed_open_box_before_close_and_tool_selection');save('withdrawn')
    client.checked('close_menu');client.checked('select_item',item='minecraft:diamond_pickaxe')
    recovery_tool=deepcopy(client.status().get('hand')or{})
    record['recovery_tool_before']=recovery_tool
    observed=block(client,pad);record['recovery_preflight']={'expected_state':placed,'observed_state':observed};save()
    if observed!=placed:raise RuntimeError('Original batch box changed before recovery')
    save('breaking')
    try:client.checked('recover_shulker',pos=pad,expected_state=placed,face='up',seconds=15)
    except RuntimeError:
        record['recover_terminal']=deepcopy(getattr(client,'last_terminal_evidence',{}))
        record['recover_request_id']=getattr(client,'last',None);save();raise
    save('broken');recover_and_return(client,record,ender,journal)
    accepted=[before+wanted]
    if (recovery_tool.get('item')=='minecraft:diamond_pickaxe'
            and type(recovery_tool.get('durability'))is int and recovery_tool['durability']>1
            and accepted[0][stack_key(recovery_tool)]>0):
        worn=deepcopy(recovery_tool);worn['durability']-=1;after_wear=accepted[0].copy()
        after_wear[stack_key(recovery_tool)]-=1;after_wear[stack_key(worn)]+=1;accepted.append(+after_wear)
    if record['stage']!='returned' or bag(client.status())not in accepted:
        raise RuntimeError('Batch box return or final inventory remains unconfirmed')
    return {'complete':True,'packed_transfer':record,'exact_items_taken':len(requests),'box_visits':1}
