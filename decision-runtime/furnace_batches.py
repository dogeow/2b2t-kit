"""Journaled ordinary smelting in already-verified empty furnaces.
No click replay: output conservation and the original world/container scope are checked.
"""
import json,math,time
from pathlib import Path
from build_supervisor import stocks
from work_access import approach_faces
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json
from container_access import wait_container_contents


def snapshot(client,pos):
    rows=client.request('scan',min=pos,max=pos)['blocks']
    row=next((r for r in rows if r['pos']==list(pos)),None)
    if row is None or not row['state'].startswith('Block{minecraft:furnace}'):raise RuntimeError('Owned ordinary furnace changed')
    face=approach_faces(client,list(pos),row['state'],('up','north','south','west','east'),seconds=45)
    # Burning can toggle during the route; refresh the same furnace before use.
    row=client.request('scan',min=pos,max=pos)['blocks'][0]
    if not row['state'].startswith('Block{minecraft:furnace}'):raise RuntimeError('Furnace changed during approach')
    client.checked('select_item',item='minecraft:diamond_sword')
    client.checked('interact',pos=list(pos),face=face,expected_state=row['state'],expected_hand='minecraft:diamond_sword')
    return wait_container_contents(client,'FurnaceMenu',require_nonempty=False)


def recipe_balance(slots,source,output,loaded):
    if len(slots)!=3:return False
    inp,fuel,out=slots
    return (inp['item'] in ('minecraft:air',source) and out['item'] in ('minecraft:air',output)
            and fuel['item'] in ('minecraft:air','minecraft:coal')
            and inp['count']+out['count']==loaded)


def _loading_matches(state,source,output,loaded_source,loaded_fuel):
    menu=state['menu']
    slots=menu['slots'][:3]
    if (menu['type']!='FurnaceMenu' or len(slots)!=3
            or any(type(row['count']) is not int or row['count']<0 for row in slots)
            or any(row['item'] not in ('minecraft:air',item) or row['item']=='minecraft:air' and row['count']
                   for row,item in zip(slots,(source,'minecraft:coal',output)))
            or slots[1]['count']>loaded_fuel):
        raise RuntimeError('Furnace contents changed during batch loading; do not replay')
    return slots[0]['count']+slots[2]['count']==loaded_source


def loading_balance(state,source,output,loaded_source,loaded_fuel):
    """Only this batch may occupy an initially empty furnace; fuel may burn."""
    if not _loading_matches(state,source,output,loaded_source,loaded_fuel):
        raise RuntimeError('Furnace contents changed during batch loading; do not replay')


def wait_loading_balance(client,state,source,output,loaded_source,loaded_fuel,menu_id):
    """Observe split slot updates for at most six seconds, without any clicks."""
    scope={key:state[key] for key in ('world_session','control_revision') if key in state}
    deadline=None
    while True:
        if (state['menu']['id']!=menu_id or state.get('manual_movement')
                or state.get('connected') is False or any(state.get(key)!=value for key,value in scope.items())):
            raise RuntimeError('Container or control changed while observing furnace; no action replay')
        if _loading_matches(state,source,output,loaded_source,loaded_fuel):return state
        now=time.monotonic()
        if deadline is None:deadline=now+6
        if now>=deadline:
            raise RuntimeError('Furnace contents changed: balance did not settle within six seconds; do not replay')
        time.sleep(min(.15,deadline-now));state=client.status()


def load(client,positions,source,output,amount,journal):
    if (source,output) not in [('minecraft:cobblestone','minecraft:stone'),('minecraft:stone','minecraft:smooth_stone')]:
        raise ValueError('Only ordinary construction stone smelting is enabled')
    if not 1<=amount<=len(positions)*64:raise ValueError('Batch does not fit the supplied furnace bank')
    journal=Path(journal)
    if journal.exists():raise RuntimeError('An existing furnace batch must be reconciled, not overwritten')
    needed_fuel=sum(math.ceil(n/8) for n in distribution(amount,len(positions)))
    if stocks(client.status()).get(source,0)<amount or stocks(client.status()).get('minecraft:coal',0)<needed_fuel:
        raise RuntimeError('Fresh source and coal stock must cover the entire batch')
    entries=[{'pos':list(pos),'amount':n,'fuel':math.ceil(n/8),'stage':'planned'}
             for pos,n in zip(positions,distribution(amount,len(positions))) if n]
    job={'world_session':client.world,'source':source,'output':output,'amount':amount,'started':time.time(),'furnaces':entries,'complete':False}
    def save():write_json(journal,job)
    # Persist the entire requested batch before approaching the first furnace.
    # An interrupted approach must not erase the as-yet-unloaded portion.
    save()
    for entry in entries:
        n=entry['amount'];state=snapshot(client,entry['pos']);session=InventorySession(client);menu_id=state['menu']['id']
        if any(v['count'] for v in state['menu']['slots'][:3]):raise RuntimeError('Preserve pre-existing furnace contents')
        entry.update(stage='prepared',loaded_source=0,loaded_fuel=0);save()
        for item,target,count in [(source,0,n),('minecraft:coal',1,entry['fuel'])]:
            key='loaded_source' if target==0 else 'loaded_fuel'
            entry['stage']='input_loading' if target==0 else 'fuel_loading';save()
            while entry[key]<count:
                state=client.status()
                state=wait_loading_balance(client,state,source,output,entry['loaded_source'],entry['loaded_fuel'],menu_id)
                before=stocks(state).get(item,0)
                src=max((v for v in state['menu']['slots'][3:] if v['item']==item and v['count']>0),
                        key=lambda v:v['count'],default=None)
                if src is None:raise RuntimeError('Furnace ingredient disappeared during loading; do not replay')
                part=min(count-entry[key],src['count'])
                state=session.place_cell(state,src,target,part,append=True)
                deadline=time.monotonic()+5
                while stocks(state).get(item,0)!=before-part or state['menu']['cursor']['count']:
                    if time.monotonic()>deadline:raise RuntimeError('Furnace load acknowledgement missing; do not replay')
                    time.sleep(.2);state=client.status()
                expected_source=entry['loaded_source']+(part if target==0 else 0)
                expected_fuel=entry['loaded_fuel']+(part if target==1 else 0)
                state=wait_loading_balance(client,state,source,output,expected_source,expected_fuel,menu_id)
                entry[key]+=part;save()
            entry['stage']='input_loaded' if target==0 else 'loaded';save()
        wait_loading_balance(client,client.status(),source,output,n,entry['loaded_fuel'],menu_id)
        client.checked('close_menu')
    job['loaded_at']=time.time();save();return job


def distribution(amount,count):
    if amount<1 or count<1:raise ValueError('Positive batch and bank required')
    q,r=divmod(amount,count)
    return [q+(i<r) for i in range(count)]


def collect(client,journal):
    journal=Path(journal);job=json.loads(journal.read_text())
    if job['world_session']!=client.world:raise RuntimeError('Reconfirm furnace ownership after a world transition')
    entries=job['furnaces'];amount=job.get('amount')
    if (isinstance(amount,bool) or not isinstance(amount,int) or amount<1 or not entries
            or any(isinstance(e.get('amount'),bool) or not isinstance(e.get('amount'),int) or not 1<=e['amount']<=64 for e in entries)
            or sum(e['amount'] for e in entries)!=amount):
        raise RuntimeError('Furnace journal does not cover the entire requested batch')
    if any(e['stage'] not in ('loaded','collected') for e in entries):
        raise RuntimeError('Partial furnace loading needs inspection')
    for entry in job['furnaces']:
        if entry['stage']=='collected':continue
        if entry['stage']!='loaded':raise RuntimeError('Partial furnace loading needs inspection')
        state=snapshot(client,entry['pos']);slots=state['menu']['slots'][:3]
        if not recipe_balance(slots,job['source'],job['output'],entry['amount']):raise RuntimeError('Journaled furnace contents changed')
        if slots[0]['count'] or slots[2]['count']!=entry['amount']:
            client.checked('close_menu');return False
        before=stocks(state).get(job['output'],0)
        session=InventorySession(client);state=session.click(state,2,'quick_move')
        deadline=time.monotonic()+6
        while stocks(state).get(job['output'],0)!=before+entry['amount'] or state['menu']['slots'][2]['count']:
            if time.monotonic()>deadline:raise RuntimeError('Smelting output receipt missing; do not replay')
            time.sleep(.2);state=client.status()
        if state['menu']['slots'][1]['count']:session.click(state,1,'quick_move')
        entry['stage']='collected';entry['collected_at']=time.time();write_json(journal,job);client.checked('close_menu')
    job['complete']=True;write_json(journal,job);return True
