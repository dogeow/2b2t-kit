"""Settle only a proved refused output pickup, without replaying a purchase."""
import hashlib,json
from collections import Counter
from pathlib import Path
from material_plan import inventory_counts
from villager_trading import combined
DETAIL='Merchant owner, exact offers, selection or stock changed; no packet sent'
def observable(command,error,book,state,event,selection,world,task):
 try:
  pending=book['pending'];p=pending['params'];m=state['menu'];q=m['merchant']
  return (command['action']=='merchant_buy_one'and command['index']==p['expected_trade_index']
   and book['world_session']==state['world_session']==event['world_session']==selection['world_session']==world
   and book['complete']is False and pending['op']=='slot_click'and p['slot']==2 and p['kind']=='pickup'and p['button']==0
   and pending['request_id']==error['last_request']==state['last_request']==event['request_id']
   and error['native_inflight']is None and error['unconfirmed_native_request']is None and error['error']==DETAIL
   and event['phase']==state['phase']=='error'and event['op']=='slot_click'and event['detail']==DETAIL
   and all(event['params'].get(k)==v for k,v in p.items())
   and event['params']['task_session']==selection['params']['task_session']==task
   and event['inventory_delta']=={} and event['revision_after']==state['control_revision']
   and event['position_after']==state['pos']and event['position_before']==event['position_after']
   and event['health_before']==event['health_after']==state['health']==20
   and len(book['receipts'])==1 and book['receipts'][0]['id']==selection['request_id']
   and selection['op']=='merchant_select_trade'and selection['phase']=='done'and selection['inventory_delta']=={}
   and selection['params']['index']==command['index']and selection['params']['menu_id']==p['menu_id']
   and selection['params']['expected_villager_uuid']==book['uuid']
   and m['type']=='MerchantMenu'and m['material_owned']is True and m['id']==p['menu_id']
   and m['cursor']['count']==0 and q['owned']is True and q['owner_task']==task and q['villager_uuid']==book['uuid']
   and (state['supervision_lease'])['job_session']==task and combined(state)==Counter(book['before'])
   and not state.get('navigating')and not state.get('native_material_busy')and not state.get('pending_scan')
   and isinstance(state.get('movement_keys'),dict)and not any(state['movement_keys'].values()))
 except(KeyError,TypeError,ValueError):return False

def settled(path):
 """Validate a separate terminal abort proof; the refused purchase stays incomplete."""
 try:
  path=Path(path);book=json.loads(path.read_text())
  if(book.get('pending')or{}).get('op')=='merchant_select_trade':return selection_settled(path,book) or selection_closed_after_reconnect(path,book)
  proof=json.loads((path.parent/'prepurchase-abort.json').read_text())
  refusal=proof['refusal'];closed=proof['close_receipt'];close_event=proof['close_event'];frames=proof['settled_frames'];request=book['pending']['request_id']
  if request is None:
   from bridged_trade_abort import bound_request
   request=bound_request(path,book)
   if request is None:return False
  return (proof['abort_settled']is True and proof['purchase_credit']==0
   and proof['original_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
   and refusal['request_id']==request and refusal['op']=='slot_click'and refusal['params']['slot']==2
   and refusal['phase']=='error'and refusal['detail']==DETAIL and refusal['inventory_delta']=={}
   and proof['world_session']==book['world_session']==refusal['world_session']==closed['world_session']
   and proof['uuid']==book['uuid'] and closed['phase']=='done'and close_event['op']=='close_menu'and close_event['phase']=='done'
   and close_event['request_id']==closed['id']and close_event['world_session']==book['world_session']
   and close_event['params']['task_session']==refusal['params']['task_session']
   and len(frames)==2 and frames[0]['time']<frames[1]['time']
   and all(f['world_session']==book['world_session']and f['health']==20 and f['screen']==''
           and f['cursor_count']==0 and Counter(f['inventory'])==Counter(book['before'])for f in frames))
 except(OSError,KeyError,TypeError,ValueError):return reconnect_settled(path)

def observable_selection(command,error,book,state,event,world,task):
 """A refused selection is distinct from a paid output click; no completed selection may exist."""
 try:
  pending=book['pending'];params=pending['params'];menu=state['menu'];merchant=menu['merchant'];lease=state['supervision_lease']
  return(command['action']=='merchant_buy_one'and command['index']==params['index']
   and book['complete']is False and not book.get('receipts')and pending['op']=='merchant_select_trade'
   and pending['request_id']==error['last_request']==state['last_request']==event['request_id']
   and book['world_session']==state['world_session']==event['world_session']==world
   and error['error']==DETAIL and error['native_inflight']is None and error['unconfirmed_native_request']is None
   and event['op']=='merchant_select_trade'and event['phase']=='error'and event['detail']==DETAIL
   and all(event['params'].get(k)==v for k,v in params.items())and event['params']['task_session']==lease['job_session']==task
   and params['expected_villager_uuid']==book['uuid']==merchant['villager_uuid']
   and params['menu_id']==menu['id']and menu['type']=='MerchantMenu'and menu['material_owned']is True
   and merchant['owned']is True and merchant['owner_task']==task
   and menu['cursor']['count']==0 and not any(v['count']for v in menu['slots'][:3])
   and event['inventory_delta']=={}and combined(state)==Counter(book['before'])
   and event['revision_before']==event['revision_after']==state['control_revision']
   and event['position_before']==event['position_after']==state['pos']
   and event['health_before']==event['health_after']==state['health']==20
   and state['connected']is True and state['manual_movement']is False
   and not any(state.get(k)for k in('navigating','native_material_busy','pending_scan')))
 except(KeyError,TypeError,ValueError):return False

def selection_was_unissued(book,error,event,world,task):
 try:
  pending=book['pending'];params=pending['params']
  return(book['world_session']==event['world_session']==world and book['complete']is False and not book.get('receipts')
   and pending['op']=='merchant_select_trade'and pending['request_id']==error['last_request']==event['request_id']
   and error['error']==DETAIL and error['native_inflight']is None and error['unconfirmed_native_request']is None
   and event['op']=='merchant_select_trade'and event['phase']=='error'and event['detail']==DETAIL
   and all(event['params'].get(k)==v for k,v in params.items())and event['params']['task_session']==task
   and params['expected_villager_uuid']==book['uuid']and event['inventory_delta']=={}
   and event['revision_before']==event['revision_after']and event['position_before']==event['position_after']
   and event['health_before']==event['health_after']==20)
 except(KeyError,TypeError,ValueError):return False

def selection_closed_after_reconnect(path, book=None):
    """A new session may proceed only after proving the old selection never reached output pickup."""
    try:
        path = Path(path)
        book = book or json.loads(path.read_text())
        proof = json.loads((path.parent / 'selection-closed-reconnect.json').read_text())
        events = proof['old_events']
        frames = proof['frames']
        pending = book['pending']; old = book['world_session']; new = frames[0]['world_session']
        selected, closed, released = events
        event_path = path.parent.parent / 'control' / 'events.jsonl'
        digest = hashlib.sha256()
        tail = []
        with event_path.open('rb') as stream:
            for line in stream:
                digest.update(line)
                if not line.strip():
                    continue
                event = json.loads(line)
                if not isinstance(event, dict):
                    return False
                selected_here = event.get('request_id') == pending['request_id']
                if tail and (selected_here or len(tail) == 4):
                    return False
                if tail or selected_here:
                    tail.append(event)
        if len(tail) != 4 or proof['events_sha256'] != digest.hexdigest():
            return False
        if ([e.get('op') for e in tail] != ['merchant_select_trade','close_menu','scan','material_job_pause']
                or [tail[0],tail[1],tail[3]] != events
                or any(e.get('world_session') != old or e.get('phase') != 'done' for e in tail)):
            return False
        original_receipts = book['receipts']
        identity = original_receipts[0]['player_uuid']
        return (proof['original_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
            and proof['output_credit'] == 0 and proof['original_replayed'] is False
            and book['complete'] is False and pending['op'] == 'merchant_select_trade'
            and len(original_receipts) == 1 and original_receipts[0]['id'] == pending['request_id']
            and selected['request_id'] == pending['request_id'] and selected['op'] == 'merchant_select_trade'
            and selected['phase'] == 'done' and selected['world_session'] == old
            and closed['op'] == 'close_menu' and closed['phase'] == 'done' and closed['world_session'] == old
            and released['op'] == 'material_job_pause' and released['phase'] == 'done' and released['world_session'] == old
            and all(not e.get('inventory_delta') for e in events)
            and new != old and len(frames) == 3
            and frames[0]['time'] < frames[1]['time'] < frames[2]['time']
            and all(f['world_session'] == new and f['player_uuid'] == identity
                    and f['server'] == original_receipts[0]['server']
                    and f['connected'] is True and f['health'] == 20 and f['screen'] == ''
                    and f['cursor_count'] == 0 and not f['supervision_lease']
                    and Counter(f['inventory']) == Counter(book['before']) for f in frames))
    except (OSError, KeyError, TypeError, ValueError, IndexError):
        return False

def selection_settled(path,book=None):
 try:
  path=Path(path);book=book or json.loads(path.read_text());proof=json.loads((path.parent/'preselection-abort.json').read_text());closed=proof['close_receipt'];event=proof['close_event'];frames=proof['settled_frames'];task=proof['refusal']['params']['task_session']
  return(proof['abort_settled']is True and proof['purchase_credit']==0 and proof['original_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
   and selection_was_unissued(book,proof['original_error'],proof['refusal'],book['world_session'],task)
   and closed['phase']==event['phase']=='done'and closed['id']==event['request_id']and event['op']=='close_menu'
   and event['world_session']==closed['world_session']==book['world_session']and event['params']['task_session']==task
   and len(frames)==2 and frames[0]['time']<frames[1]['time']and all(v['world_session']==book['world_session']and v['health']==20 and v['screen']==''and v['cursor_count']==0 and Counter(v['inventory'])==Counter(book['before'])for v in frames))
 except(OSError,KeyError,TypeError,ValueError):return False

def settle_selection(builder,base):
 import time
 from kit_runtime.journal import write_json
 from villager_trading import combined
 state=builder.check();scope=hashlib.sha256((state['server'].lower().removesuffix(':25565')+'|minecraft:overworld').encode()).hexdigest()[:20];pointer=builder.root/'merchant-trades'/scope/'active.json';path=Path(json.loads(pointer.read_text())['journal']).resolve()
 if not path.is_relative_to(builder.out.resolve()):raise RuntimeError('Original transaction escaped the retained owner')
 original=json.loads(path.read_text());error=json.loads((path.parents[1]/'error.json').read_text());events=[json.loads(v)for v in(builder.out/'control/events.jsonl').read_text().splitlines()];refusal=next(v for v in reversed(events)if v['request_id']==original['pending']['request_id'])
 if not selection_was_unissued(original,error,refusal,builder.q.world,builder.q.lease['job_session']):raise RuntimeError('Original selection may have sent input; no settlement')
 command=json.loads((builder.out/'command.json').read_text());current_error=json.loads((builder.out/command['id']/'error.json').read_text())
 if current_error['error']==DETAIL:builder.q.observe_refused_merchant_selection()
 else:builder.q.observe_refused_selection_registry()
 closed=builder.q.native('close_menu');frames=[];end=time.monotonic()+8
 while len(frames)<2:
  current=builder.q.status();menu=current.get('menu')or{}
  if current['screen']==''and(menu.get('cursor')or{}).get('count',0)==0 and inventory_counts(current)==Counter(original['before'])and(not frames or current['time']>frames[-1]['time']):frames.append({'time':current['time'],'world_session':current['world_session'],'health':current['health'],'screen':current['screen'],'cursor_count':0,'inventory':dict(inventory_counts(current))})
  if time.monotonic()>=end:raise RuntimeError('Closed selection abort did not conserve original inventory')
  time.sleep(.1)
 events=[json.loads(v)for v in(builder.out/'control/events.jsonl').read_text().splitlines()];close_event=next(v for v in reversed(events)if v['request_id']==closed['id']);proof={'abort_settled':True,'purchase_credit':0,'original_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'original_error':error,'refusal':refusal,'close_receipt':closed,'close_event':close_event,'settled_frames':frames,'original_journal_unchanged':True};destination=path.parent/'preselection-abort.json'
 if destination.exists():raise RuntimeError('Original settlement proof already exists; do not overwrite')
 write_json(destination,proof)
 if not selection_settled(path):raise RuntimeError('New abort proof failed validation')
 builder.book.update(selection_abort_proof=str(destination.relative_to(base)),original_purchase_credit=0);builder.save();return proof


def reconnect_settled(path):
    """Prove an unissued output click and payment return after a reconnect.

    The original transaction journal is never altered or marked complete.
    Missing or inconsistent evidence always leaves the fence in place.
    """
    try:
        path=Path(path)
        book=json.loads(path.read_text())
        proof=json.loads((path.parent/'reconnect-abort.json').read_text())
        event=proof['refusal_event'];reply=proof['refusal_reply']
        snapshot=proof['reconnect_snapshot'];reconnected=proof['reconnect_result']
        checks=proof['return_observation'];pending=book['pending'];params=pending['params']
        req=pending['request_id'];old=book['world_session'];new=snapshot['world_session']
        stamps=checks['frames'];identity=reply['player_uuid']
        return (proof['abort_settled'] is True and proof['purchase_credit']==0
            and proof['original_sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
            and book['complete'] is False and pending['op']=='slot_click'
            and params['slot']==2 and params['kind']=='pickup' and params['button']==0
            and reply['id']==event['request_id']==req
            and reply['phase']==event['phase']=='error' and reply['detail']==event['detail']==DETAIL
            and event['op']=='slot_click' and event['world_session']==reply['world_session']==old
            and all(event['params'].get(k)==v for k,v in params.items())
            and event['inventory_delta']=={} and event['revision_before']==event['revision_after']
            and event['position_before']==event['position_after']
            and event['health_before']==event['health_after']==20
            and new!=old and snapshot['connected'] is True and snapshot['health']==20
            and snapshot['player_uuid']==identity and snapshot['server']==reply['server']==reconnected['server']
            and reconnected['connected'] is True and reconnected['world_session']==new
            and reconnected['request_replayed'] is False and reconnected['inventory_credit']==0
            and inventory_counts(snapshot)==Counter(book['before'])
            and checks['original_request']==req and checks['native_outcome']=='rejected_no_packet_sent'
            and checks['inventory_equals_before'] is True and checks['original_replayed'] is False
            and len(stamps)==3 and all(type(t) is int for t in stamps)
            and reply['time'] < snapshot['time'] < stamps[0] < stamps[1] < stamps[2])
    except (OSError,KeyError,TypeError,ValueError):
        return False
