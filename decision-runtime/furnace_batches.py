"""Journaled ordinary smelting in already-verified empty furnaces.
No click replay: output conservation and the original world/container scope are checked.
"""
import json,math,re,time
from pathlib import Path
from build_supervisor import stocks
from work_access import approach_faces
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json
from container_access import wait_container_contents
from smelting_fuel import FuelCatalog, policy as fuel_policy, select_fuels, recipe_jar_for_client
from types import SimpleNamespace


def _furnace_row(client,pos,*,same_world=False):
    reply=client.request('scan',min=pos,max=pos)
    rows=reply.get('blocks')
    if (reply.get('phase') not in (None,'done') or not isinstance(rows,list) or len(rows)!=1
            or not isinstance(rows[0],dict) or rows[0].get('pos')!=list(pos) or not isinstance(rows[0].get('state'),str)
            or not rows[0]['state'].startswith('Block{minecraft:furnace}')
            or same_world and (reply.get('world_session')!=getattr(client,'world',None)
                or type(reply.get('control_revision')) is not int
                or reply['control_revision']!=getattr(client,'rev',None))):
        raise RuntimeError('Owned ordinary furnace changed or its fresh scan is unconfirmed')
    return rows[0]


def _owned_open_rejection(client,error,params):
    proof=getattr(client,'last_terminal_evidence',{})
    task,world=getattr(client,'task',None),getattr(client,'world',None)
    sent=proof.get('params',{}) if isinstance(proof,dict) else {}
    return (str(error)=='Target block changed' and isinstance(task,str) and bool(task)
            and isinstance(world,str) and bool(world) and isinstance(sent,dict)
            and proof.get('request_id')==getattr(client,'last',None) and bool(proof.get('request_id'))
            and proof.get('world_session')==world and proof.get('task_session')==task
            and proof.get('op')=='interact' and proof.get('phase')=='error'
            and proof.get('detail')=='Target block changed' and sent.get('task_session')==task
            and all(sent.get(key)==value for key,value in params.items()))


def _closed_material_owner(client):
    state=client.status();menu=state.get('menu') or {}
    if not isinstance(menu,dict):return False
    cursor=menu.get('cursor') or {};lease=state.get('supervision_lease') or {}
    if not all(isinstance(value,dict) for value in (menu,cursor,lease)):return False
    return (state.get('connected') is True and state.get('world_session')==client.world
            and state.get('control_revision')==client.rev and state.get('manual_movement') is False
            and state.get('screen')=='' and menu.get('id')==0 and menu.get('type')=='InventoryMenu'
            and cursor.get('item')=='minecraft:air' and cursor.get('count')==0
            and state.get('guard_armed') is True and state.get('guard_pve_only') is True
            and state.get('guard_busy') is False and isinstance(state.get('health'),(int,float)) and state['health']>=18
            and (state.get('safety_hold') or {}).get('active') is False
            and lease.get('kind')=='materials' and lease.get('job_session')==client.task
            and lease.get('world_session')==client.world and lease.get('revision')==client.rev)


def _lit_only_transition(before,after):
    pattern=r'Block\{minecraft:furnace\}\[facing=(north|south|east|west),lit=(true|false)\]'
    a,b=re.fullmatch(pattern,before),re.fullmatch(pattern,after)
    return a is not None and b is not None and a[1]==b[1] and a[2]!=b[2]


def snapshot(client,pos):
    row=_furnace_row(client,pos,same_world=True);identity=row['state']
    face=approach_faces(client,list(pos),identity,('up','north','south','west','east'),seconds=45,
                        allow_state_change=_lit_only_transition)
    client.checked('select_item',item='minecraft:diamond_sword')
    # Refresh after selection's acknowledgement delay, immediately before use.
    row=_furnace_row(client,pos,same_world=True)
    if row['state']!=identity and not _lit_only_transition(identity,row['state']):
        raise RuntimeError('Owned ordinary furnace identity changed before opening')
    params={'pos':list(pos),'face':face,'expected_state':row['state'],'expected_hand':'minecraft:diamond_sword'}
    try:client.checked('interact',**params)
    except RuntimeError as error:
        # This exact native rejection occurs before any useItemOn is sent.
        # Unknown/time-out/foreign replies never grant permission for another use.
        if not _owned_open_rejection(client,error,params) or not _closed_material_owner(client):raise
        fresh=_furnace_row(client,pos,same_world=True)
        if not _lit_only_transition(row['state'],fresh['state']) or not _closed_material_owner(client):raise
        params['expected_state']=fresh['state']
        client.checked('interact',**params)  # One bounded re-open, not a loading/slot-click retry.
    return wait_container_contents(client,'FurnaceMenu',require_nonempty=False)


def recipe_balance(slots,source,output,loaded,fuel_item="minecraft:coal",loaded_fuel=None):
    if len(slots)!=3 or any(type(r.get('count')) is not int or not 0<=r['count']<=64
                            or r.get('item')=='minecraft:air' and r['count'] for r in slots):return False
    if loaded_fuel is not None and (type(loaded_fuel) is not int or not 0<=loaded_fuel<=64):return False
    inp,fuel,out=slots
    return (inp['item'] in ('minecraft:air',source) and out['item'] in ('minecraft:air',output)
            and fuel['item'] in ('minecraft:air',fuel_item)
            and (loaded_fuel is None or fuel['count']<=loaded_fuel)
            and inp['count']+out['count']==loaded)


def _loading_matches(state,source,output,loaded_source,loaded_fuel,fuel_item="minecraft:coal"):
    menu=state['menu']
    slots=menu['slots'][:3]
    if (menu['type']!='FurnaceMenu' or len(slots)!=3
            or any(type(row['count']) is not int or row['count']<0 for row in slots)
            or any(row['item'] not in ('minecraft:air',item) or row['item']=='minecraft:air' and row['count']
                   for row,item in zip(slots,(source,fuel_item,output)))
            or slots[1]['count']>loaded_fuel):
        raise RuntimeError('Furnace contents changed during batch loading; do not replay')
    return slots[0]['count']+slots[2]['count']==loaded_source


def loading_balance(state,source,output,loaded_source,loaded_fuel,fuel_item="minecraft:coal"):
    """Only this batch may occupy an initially empty furnace; fuel may burn."""
    if not _loading_matches(state,source,output,loaded_source,loaded_fuel,fuel_item):
        raise RuntimeError('Furnace contents changed during batch loading; do not replay')


def wait_loading_balance(client,state,source,output,loaded_source,loaded_fuel,menu_id,fuel_item="minecraft:coal"):
    """Observe split slot updates for at most six seconds, without any clicks."""
    scope={key:state[key] for key in ('world_session','control_revision') if key in state}
    deadline=None
    while True:
        if (state['menu']['id']!=menu_id or state.get('manual_movement')
                or state.get('connected') is False or any(state.get(key)!=value for key,value in scope.items())):
            raise RuntimeError('Container or control changed while observing furnace; no action replay')
        if _loading_matches(state,source,output,loaded_source,loaded_fuel,fuel_item):return state
        now=time.monotonic()
        if deadline is None:deadline=now+6
        if now>=deadline:
            raise RuntimeError('Furnace contents changed: balance did not settle within six seconds; do not replay')
        time.sleep(min(.15,deadline-now));state=client.status()


def load(client,positions,source,output,amount,journal,*,keep=None,recipe_jar=None,fuel_allow_items=None):
    if (source,output) not in [('minecraft:cobblestone','minecraft:stone'),('minecraft:stone','minecraft:smooth_stone')]:
        raise ValueError('Only ordinary construction stone smelting is enabled')
    if not 1<=amount<=len(positions)*64:raise ValueError('Batch does not fit the supplied furnace bank')
    journal=Path(journal)
    if journal.exists():raise RuntimeError('An existing furnace batch must be reconciled, not overwritten')
    parts=distribution(amount,len(positions));jar=recipe_jar_for_client(client,recipe_jar)
    catalog=FuelCatalog(jar) if jar is not None else SimpleNamespace(durations={'minecraft:coal':1600},evidence={'kind':'legacy_coal_only'})
    declared={'fuel_keep':keep}
    if fuel_allow_items is not None:declared['fuel_allow_items']=fuel_allow_items
    owner=getattr(client,'owner',None);profile=getattr(owner,'profile',{}) if owner is not None else {}
    retained,allowed=fuel_policy(catalog,profile,declared,client)
    fuels=select_fuels(catalog,stocks(client.status()),parts,200,source,output,retained,allowed)
    if not fuels['ready']:raise RuntimeError('Fresh source and actual selected fuel must cover the entire batch: '+str(fuels['requirements']))
    entries=[{'pos':list(pos),'amount':n,**choice,'stage':'planned'}
             for pos,n,choice in zip(positions,parts,fuels['entries']) if n]
    job={'world_session':client.world,'source':source,'output':output,'amount':amount,'started':time.time(),'furnaces':entries,'complete':False,'fuel_plan':fuels}
    def save():write_json(journal,job)
    # Persist the entire requested batch before approaching the first furnace.
    # An interrupted approach must not erase the as-yet-unloaded portion.
    save()
    for entry in entries:
        n=entry['amount'];state=snapshot(client,entry['pos']);session=InventorySession(client);menu_id=state['menu']['id']
        if any(v['count'] for v in state['menu']['slots'][:3]):raise RuntimeError('Preserve pre-existing furnace contents')
        entry.update(stage='prepared',loaded_source=0,loaded_fuel=0);save()
        for item,target,count in [(source,0,n),(entry['fuel_item'],1,entry['fuel'])]:
            key='loaded_source' if target==0 else 'loaded_fuel'
            entry['stage']='input_loading' if target==0 else 'fuel_loading';save()
            while entry[key]<count:
                state=client.status()
                state=wait_loading_balance(client,state,source,output,entry['loaded_source'],entry['loaded_fuel'],menu_id,entry['fuel_item'])
                before=stocks(state).get(item,0)
                src=max((v for v in state['menu']['slots'][3:] if v['item']==item and v['count']>0),
                        key=lambda v:v['count'],default=None)
                if src is None:raise RuntimeError('Furnace ingredient disappeared during loading; do not replay')
                part=min(count-entry[key],src['count'])
                if target==1:
                    remaining=amount-sum(e.get('loaded_source',0) for e in entries) if item==source else 0
                    if before-retained.get(item,0)-remaining<part:
                        raise RuntimeError('Selected fuel would spend protected material; no click')
                state=session.place_cell(state,src,target,part,append=True)
                deadline=time.monotonic()+5
                while stocks(state).get(item,0)!=before-part or state['menu']['cursor']['count']:
                    if time.monotonic()>deadline:raise RuntimeError('Furnace load acknowledgement missing; do not replay')
                    time.sleep(.2);state=client.status()
                expected_source=entry['loaded_source']+(part if target==0 else 0)
                expected_fuel=entry['loaded_fuel']+(part if target==1 else 0)
                state=wait_loading_balance(client,state,source,output,expected_source,expected_fuel,menu_id,entry['fuel_item'])
                entry[key]+=part;save()
            entry['stage']='input_loaded' if target==0 else 'loaded';save()
        wait_loading_balance(client,client.status(),source,output,n,entry['loaded_fuel'],menu_id,entry['fuel_item'])
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
    if (type(amount) is not int or amount<1 or not entries
            or any(type(e.get('amount')) is not int or not 1<=e['amount']<=64 for e in entries)
            or sum(e['amount'] for e in entries)!=amount):
        raise RuntimeError('Furnace journal does not cover the entire requested batch')
    if any(e.get('stage') not in ('loaded','output_collected','collected') or e.get('pending') for e in entries):
        raise RuntimeError('Partial furnace loading or collection needs inspection; no replay')
    for entry in entries:
        if entry['stage']=='collected':continue
        state=snapshot(client,entry['pos']);slots=state['menu']['slots'][:3]
        fuel_item=entry.get('fuel_item','minecraft:coal')
        loaded_fuel=entry.get('loaded_fuel',entry.get('fuel'))
        if loaded_fuel is not None and (type(loaded_fuel) is not int or not 0<=loaded_fuel<=64):
            raise RuntimeError('Furnace fuel receipt is malformed; no collection replay')
        if len(slots)!=3 or any(type(r.get('count')) is not int or not 0<=r['count']<=64 for r in slots):
            raise RuntimeError('Furnace slot quantity is invalid')
        session=InventorySession(client)
        if entry['stage']=='loaded':
            if not recipe_balance(slots,job['source'],job['output'],entry['amount'],fuel_item,loaded_fuel):
                raise RuntimeError('Journaled furnace contents changed')
            if slots[0]['count'] or slots[2]['count']!=entry['amount']:
                client.checked('close_menu');return False
            before=stocks(state).get(job['output'],0)
            entry.update(stage='output_collecting',pending={'item':job['output'],'count':entry['amount'],'inventory_before':before})
            write_json(journal,job)
            state=session.click(state,2,'quick_move')
            deadline=time.monotonic()+6
            while stocks(state).get(job['output'],0)!=before+entry['amount'] or state['menu']['slots'][2]['count']:
                if time.monotonic()>deadline:raise RuntimeError('Smelting output receipt missing; do not replay')
                time.sleep(.2);state=client.status()
            entry.update(stage='output_collected',pending=None,output_inventory_after=before+entry['amount'])
            write_json(journal,job)
        slots=state['menu']['slots'][:3]
        if (slots[0]['count'] or slots[2]['count'] or slots[1]['item'] not in ('minecraft:air',fuel_item)
                or loaded_fuel is not None and slots[1]['count']>loaded_fuel):
            raise RuntimeError('Collected furnace or remaining fuel changed')
        remaining=slots[1]['count']
        if remaining:
            before_fuel=stocks(state).get(fuel_item,0)
            entry.update(stage='fuel_returning',pending={'item':fuel_item,'count':remaining,'inventory_before':before_fuel})
            write_json(journal,job);state=session.click(state,1,'quick_move')
            deadline=time.monotonic()+6
            while (stocks(state).get(fuel_item,0)!=before_fuel+remaining
                    or state['menu']['slots'][1]['count'] or state['menu'].get('cursor',{}).get('count',0)):
                if time.monotonic()>deadline:raise RuntimeError('Fuel return receipt missing; do not replay')
                time.sleep(.2);state=client.status()
        entry.update(stage='collected',pending=None,collected_at=time.time(),fuel_returned=remaining)
        if loaded_fuel is not None:entry['fuel_consumed']=loaded_fuel-remaining
        write_json(journal,job);client.checked('close_menu')
    job['complete']=True;write_json(journal,job);return True
