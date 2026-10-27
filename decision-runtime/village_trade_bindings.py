"""Bind a server-verified maximum book to its actual resident and counter."""
from copy import deepcopy
from collections import Counter
from villager_trading import book_matches,verify_reopened_lock,TARGETS

def bind_verified_book(project,layout,slot_id,result,proof):
    p,l=deepcopy(project),deepcopy(layout)
    if result.get('locked')is not True:raise ValueError('A verified locked transaction is required')
    selected=result['selected'];name=selected['enchantment'];level=selected['level'];uid=result['uuid']
    if p['enchantment_targets'].get(name)!=level:raise ValueError('Only a requested maximum level may be bound')
    row=next(v for v in l['slots']if v['id']==slot_id)
    if row.get('occupant_uuid')!=uid:raise ValueError('Purchase resident does not match this counter')
    verify_reopened_lock(result['purchase'],result['reopened_merchant'])
    if not any(book_matches(o.get('result',{}),name,level)for o in result['reopened_merchant']['offers']):raise ValueError('Maximum book absent from the reopened server quote')
    previous=p['locked_trades'].get(name)
    if previous and any(previous.get(k)!=v for k,v in {'villager_uuid':uid,'level':level,'proof':proof}.items()):raise ValueError('A different verified book binding already exists')
    if any(k!=name and v['villager_uuid']==uid for k,v in p['locked_trades'].items()):raise ValueError('This counter already has another primary book binding')
    cost=Counter()
    for key in ['cost_a','cost_b']:cost[selected['offer'][key]['item']]+=selected['offer'][key]['count']
    payment=result.get('payment')or{};paid=Counter()
    for key in ['cost_a','cost_b']:
        item=payment.get('offer',{}).get(key)or{}
        if item.get('count'):paid[item['item']]+=item['count']
    p['locked_trades'][name]={'level':level,'villager_uuid':uid,'cost_emerald':cost['minecraft:emerald'],'cost_book':cost['minecraft:book'],'server_history_verified':True,'trader_xp':result['reopened_merchant']['trader_xp'],'proof':proof,'book_purchased':result['book_purchased'],'location':slot_id+'_fixed_cell','workstation_restock_verified':False,'lock_payment_kind':payment.get('kind'),'actual_lock_payment':dict(paid)}
    locked_ids={v['villager_uuid']for v in p['locked_trades'].values()}
    other=next((v for v in l['slots']if v['id']!=slot_id and v.get('occupant_uuid')not in locked_ids and v.get('role',{}).get('enchantment')==name),None)
    if other:row['role'],other['role']=other['role'],row['role']
    # Existing locks can have stale or blank planned labels. Their permanent
    # server-verified binding determines the label, never the old plan.
    for enchantment,locked in p['locked_trades'].items():
        rows=[v for v in l['slots']if v.get('occupant_uuid')==locked['villager_uuid']]
        if len(rows)!=1:raise ValueError('Every verified resident needs exactly one assigned counter')
        actual=rows[0];actual['role']={'kind':'librarian','block':'minecraft:lectern','enchantment':enchantment,'level':locked['level'],'original_user_priority':enchantment in TARGETS};actual.update(locked_enchantment=enchantment,locked_level=locked['level'])
    row.update(trade_verified=True,trade_proof=proof,workstation_restock_verified=False)
    assigned={v.get('role',{}).get('enchantment')for v in l['slots']}
    p['unassigned_librarian_roles']={k:v for k,v in p['enchantment_targets'].items()if k not in assigned and k not in p['locked_trades']}
    return p,l
