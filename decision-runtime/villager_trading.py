"""Read exact offers and lock one by one ordinary purchase; never reroll a proven trade."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import time,json,hashlib
from kit_runtime.journal import write_json
from material_plan import inventory_counts,quantities

TARGETS={'minecraft:mending':1,'minecraft:infinity':1,'minecraft:unbreaking':3,
         'minecraft:fortune':3,'minecraft:sharpness':5,'minecraft:efficiency':5,'minecraft:looting':3}
COMMON_JOBS={'farmer':'composter','fletcher':'fletching_table','mason':'stonecutter',
             'armorer':'blast_furnace','toolsmith':'smithing_table','weaponsmith':'grindstone',
             'cleric':'brewing_stand','shepherd':'loom'}

def body_distance_from_eye(actor,eye):
    """Nearest point inside a real scanned body, not proof of line of sight.

    Match the native entity interaction sampler's .01 inset. Status-only
    villager rows intentionally lack bounds and cannot supply this evidence.
    """
    import math
    box=actor.get('bounds')or{}
    vectors=[eye,box.get('min'),box.get('max')]
    if any(not isinstance(v,list)or len(v)!=3 or any(type(n)not in(int,float)or not math.isfinite(n)for n in v)for v in vectors):
        raise ValueError('Fresh native entity body and finite eye position required')
    if any(box['min'][i]>=box['max'][i]for i in range(3)):
        raise ValueError('Entity body must have positive size')
    nearest=[]
    for i in range(3):
        skin=min(.01,(box['max'][i]-box['min'][i])/4)
        nearest.append(max(box['min'][i]+skin,min(eye[i],box['max'][i]-skin)))
    return math.dist(eye,nearest)

def book_matches(row,enchantment,level):
    if row.get('item')!='minecraft:enchanted_book' or row.get('count')!=1:return False
    values=row.get('stored_enchantments')or[]
    return (any(v.get('id')==enchantment and v.get('level')==level for v in values)
            and not any(v.get('id')in ('minecraft:binding_curse','minecraft:vanishing_curse')for v in values))

def candidates(merchant,targets=TARGETS):
    if merchant.get('protocol')!=1 or not isinstance(merchant.get('offers'),list):
        raise RuntimeError('Current received merchant offers are unavailable')
    return [{'enchantment':name,'level':level,'offer':deepcopy(offer)}
            for name,level in targets.items()for offer in merchant['offers']
            if not offer.get('out_of_stock') and book_matches(offer.get('result')or{},name,level)]

def lock_payment(merchant,wanted,stock,*,keep=None,max_emeralds=64,max_paper=64):
    """Choose one affordable lock payment only while its wanted book is quoted.

    Selling ordinary paper locks the same librarian without spending emeralds
    or a blank book. This is selection only, never purchase or lock evidence.
    """
    if any(type(n)is not int or not 0<=n<=64 for n in(max_emeralds,max_paper)):
        raise ValueError('Bounded ordinary payment budgets required')
    if merchant.get('protocol')!=1 or any(type(row.get('index'))is not int or row['index']!=i for i,row in enumerate(merchant['offers'])):
        raise RuntimeError('Exact received offer indices required')
    available=quantities(stock);reserved=quantities(keep or{})
    offer=wanted['offer']
    if (not any(row==offer for row in merchant['offers'])or offer.get('out_of_stock')
            or not book_matches(offer.get('result')or{},wanted['enchantment'],wanted['level'])):
        raise RuntimeError('Wanted book is absent from this exact quote; no lock payment')
    def affordable(row):
        costs=Counter()
        for key in('cost_a','cost_b'):
            cost=row.get(key)or{};n=cost.get('count');item=cost.get('item')
            if type(n)is not int or not 0<=n<=64 or not isinstance(item,str):return False
            data=cost.get('stack_data')
            if data is not None and(not isinstance(data,dict)or set(data)-{'id','count'}
                    or data.get('id',item)!=item or data.get('count',n)!=n):return False
            costs[item]+=n
        return (not row.get('out_of_stock')and costs['minecraft:emerald']<=max_emeralds
                and costs['minecraft:paper']<=max_paper
                and all(available[item]-reserved[item]>=n for item,n in costs.items()if n))
    def ordinary(row,cost,result,limit):
        a=row.get('cost_a')or{};b=row.get('cost_b')or{};out=row.get('result')or{}
        return(a.get('item')==cost and type(a.get('count'))is int and 1<=a['count']<=limit
               and b.get('count')==0 and b.get('item')=='minecraft:air'and out.get('item')==result
               and type(out.get('count'))is int and out['count']==1)
    paper=[row for row in merchant['offers']if ordinary(row,'minecraft:paper','minecraft:emerald',max_paper)and affordable(row)]
    if paper:return {'kind':'paper_sale','offer':deepcopy(min(paper,key=lambda r:(r['cost_a']['count'],r['index'])))}
    if affordable(offer):return {'kind':'wanted_book','offer':deepcopy(offer)}
    shelves=[row for row in merchant['offers']if ordinary(row,'minecraft:emerald','minecraft:bookshelf',min(9,max_emeralds))and affordable(row)]
    if shelves:return {'kind':'bookshelf_purchase','offer':deepcopy(min(shelves,key=lambda r:(r['cost_a']['count'],r['index'])))}
    return None

def lock_wanted(c,targets,out,*,keep=None,max_emeralds=64,max_paper=64):
    """One owned quote, at most one purchase, and fresh server lock evidence."""
    if(not isinstance(targets,dict)or any(not isinstance(k,str)or not k.startswith('minecraft:')
            or type(v)is not int or not 1<=v<=255 for k,v in targets.items())):
        raise ValueError('Exact desired enchantments and levels required')
    out=Path(out);out.mkdir(exist_ok=False);path=out/'lock-wanted.json'
    q=c.status();menu,info=owned_info(c,q)
    if menu['cursor']['count']or any(v['count']for v in menu['slots'][:3]):
        raise RuntimeError('Start with an empty merchant payment grid and cursor')
    if (info.get('observation_scope')!='current_server_received_merchant_menu_not_trade_completion'
            or not info.get('opening_request_id')):
        raise RuntimeError('Received server quote required before selecting a lock payment')
    book={'complete':False,'pending':None,'world_session':c.world,'uuid':info['villager_uuid'],
          'quote':deepcopy(info),'locked':False,'book_purchased':False,'goal_complete':False}
    def save():write_json(path,book)
    def step(name,call):
        book['pending']=name;save();value=call();book['pending']=None;save();return value
    save()
    try:
        wanted=candidates(info,targets)
        if(info.get('level')!=1 or info.get('trader_xp')!=0 or any(row.get('uses')!=0 for row in info['offers'])):
            book['already_used_quote_preserved']=True
        elif wanted:
            selected=wanted[0];book['selected']=selected
            payment=lock_payment(info,selected,combined(q),keep=keep,max_emeralds=max_emeralds,max_paper=max_paper)
            if payment and not any(not row['count']for row in menu['slots'][3:]):
                book['waiting_for_output_space']=True;payment=None
            book['payment']=payment;save()
            if payment:
                # Native selection may choose among all same-ID stacks. Do not
                # let an ordinary payment consume named/component-bearing items.
                paying={payment['offer'][key]['item']for key in('cost_a','cost_b')if payment['offer'][key]['count']}
                if any(row.get('count',0)and row.get('item')in paying
                       and set(row)-{'slot','item','count','max_stack'}for row in q['inventory']):
                    raise RuntimeError('Non-plain payment property must be isolated before trading')
                current,now=owned_info(c,c.status())
                if(current['id']!=menu['id']or now!=info):
                    raise RuntimeError('Quoted offers changed; no purchase sent')
                purchase=step('one_purchase',lambda:buy_one(c,payment['offer']['index'],out/'purchase'))
                book['purchase']=purchase;save()
                if purchase.get('complete')is not True or purchase.get('pending'):
                    raise RuntimeError('Original purchase is incomplete; no close, reopen, or repeat')
                step('close_after_purchase',lambda:c.checked('close_menu'))
                actors=[v for v in c.status()['loaded_villagers']['villagers']if v['uuid']==book['uuid']]
                if len(actors)!=1 or actors[0]['is_baby']or actors[0]['health']<19:
                    raise RuntimeError('Purchased librarian unavailable; never repeat the purchase')
                fresh=step('reopen_after_purchase',lambda:open(c,actors[0],out/'reopened'))
                reopened=fresh['menu']['merchant'];book['reopened_merchant']=reopened
                evidence=verify_reopened_lock(purchase,reopened)
                if not any(book_matches(row.get('result')or{},selected['enchantment'],selected['level'])for row in reopened['offers']):
                    raise RuntimeError('Wanted book absent after purchase; no highest-offer credit')
                book.update(locked=True,reopened_lock=evidence,
                            book_purchased=payment['kind']=='wanted_book')
                save()
            elif not book.get('waiting_for_output_space'):book['waiting_for_payment']=True
        else:book['no_wanted_offer']=True
        step('close_owned_menu',lambda:c.checked('close_menu'))
        book.update(complete=True,scope='bounded_quote_and_single_purchase_not_full_trading_center');save();return book
    except Exception as error:
        book['error']=repr(error);save();raise

def owned_info(c,state):
    menu=state.get('menu')or{};info=menu.get('merchant')or{};lease=state.get('supervision_lease')or{}
    if (state.get('world_session')!=c.world or state.get('connected')is not True or state.get('manual_movement')is not False
            or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
            or state.get('health',0)<19 or state.get('guard_busy')
            or menu.get('type')!='MerchantMenu' or menu.get('material_owned')is not True
            or info.get('protocol')!=1 or info.get('owned')is not True or info.get('owner_task')!=c.task
            or lease.get('job_session')!=c.task or not info.get('villager_uuid') or not info.get('offers_fingerprint')):
        raise RuntimeError('Exact healthy current material-owned merchant is required')
    return menu,info

def combined(state):
    """Payment slots and cursor are carried property, not consumed trade inputs."""
    result=inventory_counts(state);menu=state.get('menu')or{}
    for row in list(menu.get('slots',[]))[:2]+[menu.get('cursor')or{}]:
        if row.get('count',0):result[row['item']]+=row['count']
    return +result

def _settle_purchase_hand(c):
    """Menu payment returns can change the selected stack after close_menu.

    Prepare a real carried item once before reopening; never repeat a purchase
    or retry an entity interaction whose outcome is unknown.
    """
    expected=getattr(c,'merchant_purchase_hand_expected_counts',None)
    if not isinstance(expected,dict)or not expected:
        raise RuntimeError('Completed purchase totals required before post-purchase hand preparation')
    expected=Counter(expected)
    trade_items=getattr(c,'merchant_purchase_hand_trade_items',None)
    if not isinstance(trade_items,(tuple,list,set))or not trade_items:
        raise RuntimeError('Completed purchase item identities required before reopening')
    sensitive=set(trade_items)
    def settled(baseline,item=None):
        end=time.monotonic()+4;times=[];signature=None
        while True:
            q=c.status();menu=q.get('menu')or{};lease=q.get('supervision_lease')or{}
            if (q.get('world_session')!=c.world or q.get('connected')is not True or q.get('manual_movement')is not False
                    or q.get('health',0)<19 or q.get('guard_busy') or q.get('guard_armed')is not True
                    or q.get('guard_pve_only')is not True or lease.get('job_session')!=c.task
                    or q.get('screen') or menu.get('type')!='InventoryMenu' or menu.get('cursor',{}).get('count',0)):
                raise RuntimeError('Healthy owned inventory required; no merchant interaction sent')
            counts=inventory_counts(q)
            # Trade inputs/output must be exact. Independent item pickups may
            # add other property; they never supply transaction or goal credit.
            compatible=(all(counts[k]==baseline[k]for k in sensitive)
                        and all(counts[k]>=n for k,n in baseline.items()))
            current=tuple(sorted(counts.items()))
            if compatible and(item is None or q.get('hand',{}).get('item')==item):
                if current!=signature:times=[];signature=current
                if type(q.get('time'))is int and(not times or q['time']>times[-1]):times.append(q['time'])
                if len(times)>=2:return q
            else:times=[];signature=None
            if time.monotonic()>=end:
                raise RuntimeError('Post-purchase hand or inventory changed; no merchant interaction sent')
            time.sleep(.1)
    q=settled(expected)
    before_selection=inventory_counts(q)
    from merchant_repair_hand import selected_tool,retained
    repair_tool=selected_tool(q)
    priorities=((repair_tool['item']if repair_tool else None),'minecraft:netherite_sword','minecraft:diamond_sword','minecraft:diamond_pickaxe',
                'minecraft:netherite_pickaxe',q.get('hand',{}).get('item'))
    item=next((v for v in priorities if v and v!='minecraft:air' and expected[v]>0),None)
    if item is None:raise RuntimeError('No carried interaction item available after the purchase')
    options={'slot':repair_tool['slot']}if repair_tool and repair_tool['item']==item else{}
    c.checked('select_item',item=item,**options)
    after=settled(before_selection,item)
    if options and not retained(after,repair_tool):
        raise RuntimeError('Exact selected repair tool changed; no merchant interaction sent')
    return {'incidental_positive_counts':dict(inventory_counts(after)-expected),
            'incidental_counts_are_trade_credit':False,'selection_request_id':c.last,
            'inventory_observed_at':after['time'],'selected_repair_tool_preserved':bool(options)}

def open(c,actor,out):
    out=Path(out);out.mkdir(exist_ok=False);book={'uuid':actor['uuid'],'world_session':c.world,'pending':True}
    write_json(out/'open.json',book)
    def require_awake():
        if getattr(c,'root',None)is not None:
            from villager_events import read
            frame=read(c.root,c.status())
            asleep=next((v for v in(frame or{}).get('villagers',[])if v.get('uuid')==actor['uuid']and v.get('sleeping')is True),None)
            if asleep:
                book.update(pending=False,interaction_sent=False,refusal='assigned_adult_is_asleep');write_json(out/'open.json',book)
                raise ValueError('Original villager is asleep; wake the assigned bed before opening')
    require_awake()
    if getattr(c,'merchant_purchase_hand_pending',False):
        book['hand_preparation']=_settle_purchase_hand(c)
        write_json(out/'open.json',book)
    require_awake()
    previous=c.last
    try:reply=c.checked('interact_entity',entity_id=actor['id'],expected_uuid=actor['uuid'],expected_hand=c.status()['hand']['item'])
    finally:book['request_id']=c.last if c.last!=previous else None;write_json(out/'open.json',book)
    until=time.monotonic()+8
    while True:
        q=c.status();menu,info=owned_info(c,q)
        if info['villager_uuid']!=actor['uuid']:raise RuntimeError('A different villager opened; no trade')
        if info.get('offers'):break
        if time.monotonic()>until:raise RuntimeError('Original merchant offers are still unavailable; never reopen automatically')
        time.sleep(.1)
    book.update(pending=False,menu_id=menu['id'],offers=info,receipt=reply);write_json(out/'open.json',book)
    c.merchant_purchase_hand_pending=False
    c.merchant_purchase_hand_expected_counts=None
    c.merchant_purchase_hand_trade_items=None
    return q

def settle_closed_trade(c,receipt,*,seconds=20):
    """Observe returned payment stacks after closing a completed trade; never send another purchase."""
    if (receipt.get('complete')is not True or receipt.get('pending')is not None
            or receipt.get('world_session')!=c.world or not isinstance(receipt.get('after'),dict)):
        raise RuntimeError('Completed same-world trade receipt required before payment-return observation')
    expected=quantities(receipt['after']);deadline=time.monotonic()+seconds;stamps=[]
    while len(stamps)<2:
        state=c.request('snapshot');menu=state.get('menu')or{};lease=state.get('supervision_lease')or{}
        if (state.get('connected')is not True or state.get('world_session')!=c.world
                or lease.get('job_session')!=c.task or state.get('health',0)<19
                or state.get('manual_movement')or state.get('screen')!=''
                or menu.get('type')!='InventoryMenu'or menu.get('id')!=0 or menu.get('cursor',{}).get('count')!=0):
            raise RuntimeError('Closed trade control or inventory interface changed; no further purchase')
        if inventory_counts(state)==expected:
            if not stamps or state.get('time')>stamps[-1]:stamps.append(state.get('time'))
        else:stamps=[]
        # A slow native read may deliver the second valid frame after the
        # polling budget. Completed evidence wins; never resend the purchase.
        if len(stamps)>=2:return dict(complete=True,inventory=dict(expected),confirmations=stamps,purchases_sent=0)
        if time.monotonic()>deadline:raise RuntimeError('Closed trade payment returns remain unconfirmed; no further purchase')
        time.sleep(.1)
    return dict(complete=True,inventory=dict(expected),confirmations=stamps,purchases_sent=0)

def buy_one(c,index,out):
    """One output pickup, then its bound receiving stack; unknown clicks are retained."""
    scope=hashlib.sha256((c.server.lower().removesuffix(':25565')+'|minecraft:overworld').encode()).hexdigest()[:20]
    registry=Path(c.root)/'merchant-trades'/scope;registry.mkdir(parents=True,exist_ok=True)
    pointer=registry/'active.json';previous=None
    if pointer.exists():
        previous=json.loads(Path(json.loads(pointer.read_text())['journal']).read_text())
        if not previous.get('complete')or previous.get('pending'):
            from merchant_preflight_abort import settled
            if not settled(json.loads(pointer.read_text())['journal']):
                raise RuntimeError('Original merchant transaction is unresolved; no new purchase or replay')
    out=Path(out);out.mkdir(exist_ok=False);path=out/'one-trade.json';q=c.status();menu,info=owned_info(c,q)
    if (previous and previous.get('complete')is True and not previous.get('pending')
            and previous.get('world_session')==c.world and previous.get('uuid')==info['villager_uuid']
            and previous.get('opening_request_id') and previous['opening_request_id']==info.get('opening_request_id')):
        raise RuntimeError('Reopen this trader for a fresh server quote before another purchase; no selection sent')
    if type(index)is not int or not 0<=index<len(info['offers']):raise ValueError('Exact current offer index required')
    offer=deepcopy(info['offers'][index]);before=combined(q)
    expected=before.copy()
    for cost in (offer['cost_a'],offer['cost_b']):expected[cost['item']]-=cost['count']
    result=offer['result'];expected[result['item']]+=result['count']
    if offer.get('out_of_stock')or any(v<0 for v in expected.values())or menu['cursor']['count']:
        raise RuntimeError('Actual payment or stock is unavailable; no trade sent')
    from merchant_output_destination import choose
    destination_before=choose(menu,offer)
    empty=sum(not v['count']for v in menu['slots'][3:])
    payment_returns=sum(bool(v['count'])for v in menu['slots'][:2])
    if destination_before is None or empty<payment_returns+(0 if destination_before['count']else 1):
        raise RuntimeError('Reserve output and existing payment return slots before trade selection')
    book={'world_session':c.world,'uuid':info['villager_uuid'],'offer':offer,'before':dict(before),
          'expected_after':dict(+expected),'pending':None,'complete':False,'lock_server_verified':False,
          'trader_xp_before':info['trader_xp'],'opening_request_id':info.get('opening_request_id')}
    def save():write_json(path,book)
    def send(op,**params):
        book['pending']={'op':op,'params':params};save();previous=c.last
        try:r=c.checked(op,**params)
        finally:book['pending']['request_id']=c.last if c.last!=previous else None;save()
        book.setdefault('receipts',[]).append(r);save();return r
    def observed(s):
        book.setdefault('verified_stages',[]).append({'pending':deepcopy(book['pending']),'time':s.get('time')})
        book['pending']=None;save();return s
    def observe(predicate):
        until=time.monotonic()+6;times=[];previous=None
        while True:
            s=c.status();m,v=owned_info(c,s)
            if m['id']!=menu['id']or v['villager_uuid']!=book['uuid']:raise RuntimeError('Merchant changed after original input; no replay')
            if predicate(s):
                if s.get('time')!=previous:times.append(s['time']);previous=s['time']
                if len(times)>=2:return s
            else:times=[]
            if time.monotonic()>until:raise RuntimeError('Original merchant input is unconfirmed; preserve it without replay')
            time.sleep(.1)
    save()
    write_json(pointer,{'journal':str(path.resolve()),'world_session':c.world,'uuid':info['villager_uuid']})
    send('merchant_select_trade',menu_id=menu['id'],index=index,
         expected_offers_fingerprint=info['offers_fingerprint'],expected_villager_uuid=book['uuid'])
    q=observe(lambda s:combined(s)==before and s['menu']['slots'][2]['item']==result['item']
              and s['menu']['slots'][2]['count']==result['count'])
    observed(q)
    # Vanilla returns old payments before refilling a selected offer. A slot
    # empty before selection may now hold those returned player items.
    slots=q['menu']['slots'];destination_stack=choose(q['menu'],offer)
    destination=destination_stack['slot']if destination_stack is not None else None
    remaining_payments=sum(slots[i]['count']-cost['count']>0 for i,cost in enumerate((offer['cost_a'],offer['cost_b'])))
    if destination is None or sum(not v['count']for v in slots[3:])<remaining_payments+(0 if destination_stack['count']else 1):
        raise RuntimeError('Prepared trade has no safe output and payment-return capacity; no purchase sent')
    book.update(output_destination=destination,output_destination_before=deepcopy(destination_stack));save()
    # Native code rechecks full item components, both payment slots and exact offers before this single purchase.
    send('slot_click',menu_id=menu['id'],slot=2,kind='pickup',button=0,expected_item=result['item'],
         expected_count=result['count'],expected_cursor='minecraft:air',expected_cursor_count=0,
         expected_offers_fingerprint=q['menu']['merchant']['offers_fingerprint'],expected_trade_index=index)
    q=observe(lambda s:combined(s)==+expected and s['menu']['cursor']['item']==result['item']
              and s['menu']['cursor']['count']==result['count']
              and s['menu']['cursor'].get('stored_enchantments',[])==result.get('stored_enchantments',[]))
    observed(q)
    if q['menu']['slots'][destination]!=destination_stack:raise RuntimeError('Chosen player receiving stack changed; cursor retained')
    send('slot_click',menu_id=menu['id'],slot=destination,kind='pickup',button=0,
         expected_item=destination_stack['item'],expected_count=destination_stack['count'],expected_cursor=result['item'],expected_cursor_count=result['count'])
    q=observe(lambda s:combined(s)==+expected and not s['menu']['cursor']['count']
              and s['menu']['slots'][destination]['item']==result['item']
              and s['menu']['slots'][destination]['count']==destination_stack['count']+result['count']
              and s['menu']['slots'][destination].get('stored_enchantments',[])==result.get('stored_enchantments',[]))
    observed(q)
    book.update(after=dict(combined(q)),do_not_reroll=True,
                proof_scope='normal_single_purchase_and_two_later_client_inventory_frames_not_fresh_server_trade_history')
    save()
    protected=registry/'villagers.json';locked=json.loads(protected.read_text())if protected.exists()else{}
    locked.setdefault(book['uuid'],{'do_not_reroll':True,'observed_purchases':[]})['observed_purchases'].append(str(path.resolve()))
    write_json(protected,locked);book['complete']=True;save()
    c.merchant_purchase_hand_expected_counts=deepcopy(book['after'])
    c.merchant_purchase_hand_trade_items=tuple(v['item']for v in(offer['cost_a'],offer['cost_b'],result)if v['count'])
    c.merchant_purchase_hand_pending=True
    return book

def verify_reopened_lock(purchase,reopened):
    """A later newly opened server menu, not predicted XP, supplies lock evidence."""
    if (not purchase.get('complete')or reopened.get('villager_uuid')!=purchase.get('uuid')
            or reopened.get('protocol')!=1 or reopened.get('trader_xp',0)<=purchase.get('trader_xp_before',0)
            or not purchase.get('opening_request_id')or not reopened.get('opening_request_id')
            or reopened['opening_request_id']==purchase['opening_request_id'] or not reopened.get('offers')
            or reopened.get('observation_scope')!='current_server_received_merchant_menu_not_trade_completion'):
        raise RuntimeError('Fresh server merchant history has not verified the trade lock')
    return {'uuid':purchase['uuid'],'locked':True,'trader_xp':reopened['trader_xp'],
            'proof_scope':'same_villager_newly_opened_server_received_merchant_menu_after_observed_purchase'}
