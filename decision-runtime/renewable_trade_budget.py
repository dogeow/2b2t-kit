"""Fund one preserved wanted quote from the existing cane collector and paid librarians."""
from pathlib import Path
import json,math
from material_plan import inventory_counts
from librarian_room import LibrarianRoom,walk_public
from librarian_workflow import seed_cycles
from librarian_public_quote import open_when_reachable
from villager_events import wait_for_frame
from village_public_roof import choose,leave
from kit_runtime.journal import write_json

def trade_workspace(builder):
    from material_stack_consolidation import prepare_fetch
    from queued_village_owner import QueuedVillageOwner
    state=builder.check()
    if sum(v['slot']<36 and not v['count']for v in state['inventory'])>=3:return False
    if state.get('screen'):builder.q.native('close_menu')
    before=inventory_counts(builder.check());result=prepare_fetch(QueuedVillageOwner(builder),['minecraft:emerald','minecraft:bookshelf','minecraft:enchanted_book'])
    if inventory_counts(builder.check())!=before:raise RuntimeError('Workspace merge did not conserve inventory')
    builder.book.setdefault('workspace_merges',[]).append(result);builder.save()
    if sum(v['slot']<36 and not v['count']for v in builder.check()['inventory'])<3:raise RuntimeError('Verified trade workspace still unavailable; no selection sent')
    return True

def merchant(builder,room):
    reply=open_when_reachable(builder,room,lambda:not next(v for v in wait_for_frame(builder.root,builder.check)['villagers']if v['uuid']==room.uid)['sleeping'],seconds=8,distance_limit=2.95)
    if reply is None:raise RuntimeError('Existing paper supplier is not reachable; no purchase')
    m=reply['menu']['merchant']
    if m['trader_xp']<=0:raise RuntimeError('Funding requires an already paid supplier')
    return m

def supply_paper(builder,base,desired,open_roof,close_roof):
    stock=inventory_counts(builder.check());deficit=math.ceil(max(0,desired-stock['minecraft:paper'])/3)*3
    if not deficit:return
    from material_stack_consolidation import prepare_fetch
    from queued_village_owner import QueuedVillageOwner
    merge=prepare_fetch(QueuedVillageOwner(builder),['minecraft:sugar_cane','minecraft:paper','minecraft:emerald'])
    if merge is not None:builder.book.setdefault('supply_workspace_merges',[]).append(merge);builder.save()
    state=builder.check();x=int(state['pos'][0]);floor=64 if x<761015 else 65;_,rows=builder.scan([x-2,floor-1,797811],[x+2,floor+6,797811]);project=json.load(open(base/'project-state.json'));blocked={tuple(v['pos'])for v in project['protected_pending_excavation_targets']if v.get('world_session')==builder.q.world and v.get('native_claim_not_cleared')};entry=choose(rows,x,floor,blocked,low_x=760997 if floor==64 else 761017,high_x=761015 if floor==64 else 761033)
    if entry is None:raise RuntimeError('No clear existing public roof for the supply trip')
    leave(builder,entry,floor,open_roof,close_roof);builder.nav([entry[0]+.5,85.2,entry[2]+.5]);builder.nav([761049.5,85.2,797861.5]);scene,rows=builder.scan([761046,62,797861],[761049,66,797861])
    if not rows[(761046,64,797861)]['state'].startswith('Block{minecraft:chest}'):raise RuntimeError('Original cane collector changed')
    hazards={'minecraft:cactus','minecraft:fire','minecraft:soul_fire','minecraft:campfire','minecraft:soul_campfire','minecraft:magma_block','minecraft:lava','minecraft:powder_snow','minecraft:sweet_berry_bush'}
    if any(v['state'].split('}',1)[0].removeprefix('Block{')in hazards for v in scene['blocks']):raise RuntimeError('Collector approach contains a current hazard; no movement into it')
    builder.nav([761049.5,64.1,797861.5]);builder.nav([761047.5,64.1,797861.5]);builder.send('open_chest_from_pose',pos=[761046,64,797861],pose=[761047.5,64.1,797861.5],face='east',allow_empty=True,allow_hover=True,seconds=35);state=builder.check();available=sum(v['count']for v in state['menu']['slots'][:-36]if v['item']=='minecraft:sugar_cane');stock=inventory_counts(state);free=sum(v['slot']<36 and not v['count']for v in state['inventory']);spare=sum(v.get('max_stack',64)-v['count']for v in state['inventory']if v['slot']<36 and v['item']=='minecraft:sugar_cane'and v['count']);capacity=max(0,free-3)*64+spare
    from cane_stack_fetch import planned_take
    take=planned_take(deficit,available,capacity,state['menu']['slots'][:-36])
    if take<3:raise RuntimeError('No verified cane output or receiving space; no transfer')
    receipt=builder.send('transfer',item='minecraft:sugar_cane',target=stock['minecraft:sugar_cane']+take,seconds=120);builder.book.setdefault('renewable_supply',[]).append({'available_cane':available,'taken':take,'transfer':receipt});builder.save();builder.q.native('close_menu');builder.nav([761047.5,85.2,797861.5]);builder.nav([761021.5,85.2,797850.5]);builder.nav([761021.5,65.1,797850.5]);p=[761022,64,797850];_,rows=builder.scan(p,p)
    if rows[tuple(p)]['state']!='Block{minecraft:crafting_table}':raise RuntimeError('Existing outdoor crafting table changed')
    profile=json.load(open(base/'live-village-121/close-stations-bench-1820.json'));profile['outdoor_workbench'].update(world_session=builder.q.world,proof=str(builder.path.relative_to(base)),source='fresh_native_scan');path=builder.out/(builder.q.prefix+'-paper-bench.json');write_json(path,profile);before=inventory_counts(builder.check());use=max(0,(before['minecraft:sugar_cane']-1)//3*3);result=builder.send('manufacture',targets={'minecraft:paper':before['minecraft:paper']+use},profile=str(path),seconds=300)
    if result.get('complete')is not True:raise RuntimeError('Original paper manufacture incomplete; no repeat')
    builder.q.native('close_menu');builder.book['renewable_supply'][-1].update(paper_added=use,craft=result);builder.save();state=builder.check();builder.nav([state['pos'][0],85.2,state['pos'][2]]);builder.nav([entry[0]+.5,85.2,entry[2]+.5]);builder.nav([entry[0]+.5,floor+5.2,entry[2]+.5]);open_roof(builder,entry,'up',pickup_pose=[entry[0]+.5,floor+.1,entry[2]+.5]);builder.nav([entry[0]+.5,floor+.1,entry[2]+.5]);close_roof(builder,entry)

def funding_priority(seed,layout,*,reserve_only=False):
    waiting=next((v for v in reversed(seed.get('quotes',[]))if v.get('result',{}).get('waiting_for_payment')),None)or seed.get('preserved_wanted_quote')
    if reserve_only:
        if waiting or seed.get('priority_enchantment'):
            raise RuntimeError('An existing wanted quote must use preserved-quote funding')
        return {'funding_purpose':'future_lock_reserve'}
    if waiting is None:raise RuntimeError('No exact preserved wanted quote requires funding')
    wanted=waiting['result']['selected'];uid=waiting['merchant']['villager_uuid'];priority=next(v['id']for v in layout if v['occupant_uuid']==uid)
    return {'priority_slot':priority,'priority_enchantment':wanted['enchantment'],'priority_level':wanted['level'],'preserved_wanted_quote':waiting,'funding_purpose':'preserved_wanted_quote'}

def fund(builder,base,seed,target,open_roof,close_roof,*,paper_keep=96,resume=None,reserve_only=False):
    base=Path(base);book=builder.book;layout=json.load(open(base/'layout-plan.json'))['slots'];last=seed_cycles(seed,builder.q.world,layout)
    if type(target)is not int or not 1<=target<=64:raise ValueError('Bounded ordinary emerald reserve required')
    purpose=funding_priority(seed,layout,reserve_only=reserve_only)
    book.update(cycles=[],last_cycles=last,open_roofs=[],sales=[],new_existing_offers=[],phase='renewable_lock_budget',**purpose);builder.save()
    if resume is not None:
        from copy import deepcopy
        prior=json.load(open(resume))
        if prior.get('world_session')!=builder.q.world or(prior.get('pending')or{}).get('action')!='merchant_buy_one'or any(v.get('pending_reopen')for v in prior.get('sales',[])):raise RuntimeError('Only exact pre-selection workspace refusal may resume')
        command=json.load(open(builder.out/'command.json'));error=json.load(open(builder.out/command['id']/'error.json'))
        observed=builder.q.observe_unstarted_trade_workspace()if error['error']=='Reserve output and existing payment return slots before trade selection'else builder.q.observe_refused_merchant_selection();builder.q.native('close_menu');book.update(sales=deepcopy(prior.get('sales',[])),renewable_supply=deepcopy(prior.get('renewable_supply',[])),resume_zero_input_observation=observed['id'],original_funding_source=str(Path(resume).relative_to(base)));builder.save()
    trade_workspace(builder)
    for name in ['EN01','ES01','WS03']:
        if inventory_counts(builder.check())['minecraft:emerald']>=target:break
        slot=next(v for v in layout if v['id']==name);room=LibrarianRoom.from_slot(slot);walk_public(builder,room);m=merchant(builder,room)
        for _ in range(16):
            if trade_workspace(builder):m=merchant(builder,room)
            stock=inventory_counts(builder.check())
            if stock['minecraft:emerald']>=target:break
            offer=next((o for o in m['offers']if o['cost_a']['item']=='minecraft:paper'and o['cost_a']['count']<=48 and o['cost_b']['count']==0 and o['result']['item']=='minecraft:emerald'and o['result']['count']==1 and not o['out_of_stock']),None)
            if offer is None:break
            price=offer['cost_a']['count']
            if stock['minecraft:paper']<price+paper_keep:
                builder.q.native('close_menu');supply_paper(builder,base,(target-stock['minecraft:emerald'])*price+paper_keep,open_roof,close_roof);walk_public(builder,room);m=merchant(builder,room);continue
            try:paid=builder.send('merchant_buy_one',index=offer['index'],seconds=60)
            except RuntimeError:
                command=json.load(open(builder.out/'command.json'));error=json.load(open(builder.out/command['id']/'error.json'));count=book.get('selection_refusal_count',0)
                if error['error']!='Merchant owner, exact offers, selection or stock changed; no packet sent'or count>=2:raise
                from merchant_preflight_abort import settle_selection
                settled=settle_selection(builder,base);book.update(pending=None,selection_refusal_count=count+1);book.setdefault('zero_input_trade_refusals',[]).append({'command':command,'settlement':book.get('selection_abort_proof'),'purchase_credit':0});builder.save();trade_workspace(builder);m=merchant(builder,room);continue
            if paid.get('complete')is not True or paid.get('pending'):raise RuntimeError('Original paper sale incomplete; never repeat')
            command=json.load(open(builder.out/'command.json'));record={'slot':name,'purchase':paid,'purchase_result':str((builder.out/command['id']/'result.json').relative_to(base)),'pending_reopen':True};book['sales'].append(record);builder.save();builder.q.native('close_menu');fresh=merchant(builder,room)
            if fresh['trader_xp']<=m['trader_xp']:raise RuntimeError('Paid supplier XP growth not observed; no repeated purchase')
            command=json.load(open(builder.out/'command.json'));record.update(pending_reopen=False,merchant=fresh,quote_result=str((builder.out/command['id']/'result.json').relative_to(base)));builder.save();m=fresh;print('REUSED_PAPER_BUDGET_SALE',len(book['sales']),'EMERALDS',paid['after']['minecraft:emerald'],flush=True)
            from villager_trading import candidates
            p=json.load(open(base/'project-state.json'));missing={k:v for k,v in p['enchantment_targets'].items()if k not in p['locked_trades']};missing.update({k:v for k,v in p['optional_enchantment_targets'].items()if k not in p['locked_optional_trades']});found=candidates(m,missing)
            if found:book['new_existing_offers'].append({'slot':name,'offers':found,'paid_sale_index':len(book['sales'])-1});builder.save()
        builder.q.native('close_menu')
    stock=inventory_counts(builder.check())
    if stock['minecraft:emerald']<target or stock['minecraft:paper']<paper_keep or book['open_roofs']:raise RuntimeError('Funding is not complete; known sales retained')
    book.update(complete=True,pending=None,phase='funded_future_lock_reserve'if reserve_only else'funded_preserved_wanted_quote',inventory_after=dict(stock),goal_complete=False);builder.save();return book
