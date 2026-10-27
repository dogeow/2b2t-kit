"""Settle a proved no-packet bridged output refusal; never replay a purchase."""
from collections import Counter
from pathlib import Path
import hashlib,json,time
from material_plan import inventory_counts
from villager_trading import combined
from merchant_preflight_abort import DETAIL
from kit_runtime.journal import write_json


def observable(book,command,event,selection,reply,state,world,task):
    try:
        pending=book['pending'];p=pending['params'];menu=state['menu'];merchant=menu['merchant'];first=book['receipts'][0]
        payments=Counter()
        for row in first['menu']['slots'][:2]:
            if row['count']:payments[row['item']]-=row['count']
        selection_delta=selection['inventory_delta']
        moved_payment=(selection_delta=={}or Counter(selection_delta)==payments
                       and inventory_counts(first)+(-payments)==Counter(book['before']))
        return (command['action']=='native'and command['op']=='slot_click'and command['params']==p
                and pending['op']=='slot_click'and p['slot']==2 and p['kind']=='pickup'and p['button']==0
                and p['expected_cursor']=='minecraft:air'and p['expected_cursor_count']==0
                and book['complete']is False and len(book['receipts'])==1
                and pending.get('request_id')in(None,event['request_id'])
                and event['op']=='slot_click'and event['phase']==reply['phase']==state['phase']=='error'
                and event['detail']==reply['detail']==DETAIL and event['inventory_delta']=={}
                and all(event['params'].get(k)==v for k,v in p.items())
                and event['params']['task_session']==selection['params']['task_session']==task
                and event['request_id']==reply['id']==state['last_request']
                and event['world_session']==reply['world_session']==book['world_session']==state['world_session']==world
                and event['position_before']==event['position_after']==state['pos']
                and reply['pos']==state['pos']and reply['control_revision']==state['control_revision']
                and event['revision_before']==event['revision_after']==state['control_revision']
                and event['health_before']==event['health_after']==state['health']==20
                and not reply.get('outcome_pending')
                and first['id']==selection['request_id']and selection['phase']=='done'
                and first['world_session']==selection['world_session']==world
                and selection['revision_before']==selection['revision_after']==state['control_revision']
                and selection['health_before']==selection['health_after']==20
                and selection['op']=='merchant_select_trade'and moved_payment
                and selection['params']['index']==p['expected_trade_index']
                and selection['params']['menu_id']==p['menu_id']==menu['id']
                and first['menu']['id']==menu['id']
                and selection['params']['expected_villager_uuid']==book['uuid']==merchant['villager_uuid']
                and menu['type']=='MerchantMenu'and menu['material_owned']is True and menu['cursor']['count']==0
                and merchant['owned']is True and merchant['owner_task']==task
                and state['supervision_lease']['job_session']==task
                and combined(state)==Counter(book['before'])and state['connected']is True and state['manual_movement']is False
                and not any(state.get(k)for k in('navigating','native_material_busy','pending_scan'))
                and not any(state['movement_keys'].values()))
    except(KeyError,TypeError,ValueError,AttributeError):return False


def bound_request(path,book):
    """Read an immutable separate binding for legacy bridge journals with null ID."""
    try:
        path=Path(path);binding=json.loads((path.parent/'native-request-binding.json').read_text())
        if (binding['original_sha256']!=hashlib.sha256(path.read_bytes()).hexdigest()
                or binding['journal']!=str(path.resolve())):return None
        if observable(book,binding['command'],binding['refusal'],binding['selection'],binding['native_reply'],
                      binding['observed_state'],binding['world_session'],binding['task_session']):
            return binding['refusal']['request_id']
    except(OSError,ValueError,KeyError,TypeError):return None


def settle(queue,path):
    path=Path(path).resolve();book=json.loads(path.read_text())
    binding=queue.observe_refused_bridged_purchase(path)
    closed=queue.native('close_menu');frames=[];deadline=time.monotonic()+6
    while len(frames)<2:
        state=queue.status(observing=True);menu=state['menu']
        if (state['screen']or menu['cursor']['count']or inventory_counts(state)!=Counter(book['before'])):
            frames=[]
        elif not frames or state['time']>frames[-1]['time']:
            frames.append({'time':state['time'],'world_session':state['world_session'],'health':state['health'],
                           'screen':state['screen'],'cursor_count':menu['cursor']['count'],'inventory':dict(inventory_counts(state))})
        if time.monotonic()>deadline:raise RuntimeError('Refused purchase payment return unconfirmed; no new purchase')
        time.sleep(.1)
    events=[json.loads(v)for v in(queue.out/'control/events.jsonl').read_text().splitlines()]
    close_event=next(v for v in reversed(events)if v['request_id']==closed['id'])
    proof={'abort_settled':True,'purchase_credit':0,'original_sha256':binding['original_sha256'],
           'refusal':binding['refusal'],'close_receipt':closed,'close_event':close_event,'settled_frames':frames,
           'world_session':book['world_session'],'uuid':book['uuid'],'original_journal_unchanged':True}
    destination=path.parent/'prepurchase-abort.json'
    if destination.exists():raise RuntimeError('Existing abort proof must not be overwritten')
    write_json(destination,proof)
    from merchant_preflight_abort import settled
    if not settled(path):raise RuntimeError('New bridged abort proof failed validation')
    return proof
