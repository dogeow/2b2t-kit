"""Store finished fungible materials and fetch raw inputs from approved chests."""
import json,time
from build_supervisor import stocks
from container_access import open_grounded_chest
from kit_runtime.journal import write_json


def audit(client,chests,items):
    """Count freshly opened approved depots; never return a partial stock total."""
    positions=[list(pos) for pos in chests];items=tuple(dict.fromkeys(items))
    if not positions or len({tuple(pos) for pos in positions})!=len(positions):
        raise ValueError('A stock audit needs distinct approved chest positions')
    if not items or any(not isinstance(item,str) or not item.startswith('minecraft:') for item in items):
        raise ValueError('A stock audit needs explicit Minecraft item IDs')
    record={'world_session':client.world,'counts':dict.fromkeys(items,0),
            'visited':[],'complete':False}
    journal=client.out/('depot-audit-'+str(time.time_ns())+'.json')
    def save():write_json(journal,record)
    save()
    for pos in positions:
        state=open_grounded_chest(client,pos)
        menu=state.get('menu',{});slots=menu.get('slots',[])
        if menu.get('type')!='ChestMenu' or len(slots) not in (63,90) or menu.get('cursor',{}).get('count',0):
            raise RuntimeError('Verified depot menu changed during stock audit')
        counts=dict.fromkeys(items,0)
        for row in slots[:-36]:
            if row.get('item') in counts:counts[row['item']]+=row['count']
        client.checked('close_menu')
        record['visited'].append({'pos':pos,'counts':counts,'at_ms':state['time']})
        for item,count in counts.items():record['counts'][item]+=count
        save()
    # The final status check also rejects a disconnect or control handoff that
    # occurred after the last menu receipt. A saved partial audit is not proof.
    record.update(complete=True,observed_at=client.status()['time']);save()
    return record


def capacity(state,item):
    slots=state['menu']['slots'][:-36]
    return sum(64 if not v['count'] else max(0,v.get('max_stack',64)-v['count'])
               if v['item']==item else 0 for v in slots)


def unmet(state,deposit,withdraw):
    held=stocks(state)
    return ({k:held.get(k,0)-n for k,n in deposit.items() if held.get(k,0)>n},
            {k:n-held.get(k,0) for k,n in withdraw.items() if held.get(k,0)<n})


def exchange(client,chests,deposit=None,withdraw=None):
    deposit=deposit or {};withdraw=withdraw or {}
    if set(deposit)&set(withdraw):raise ValueError('A material cannot be deposited and withdrawn in the same exchange')
    if any(not isinstance(v,int) or v<0 for v in (*deposit.values(),*withdraw.values())):raise ValueError('Counts must be nonnegative')
    visited=[]
    for pos in chests:
        before=client.status();to_store,to_fetch=unmet(before,deposit,withdraw)
        if not to_store and not to_fetch:break
        state=open_grounded_chest(client,list(pos));entry={'pos':list(pos),'before':stocks(state)}
        def store_available():
            for item,keep in deposit.items():
                state=client.status();held=stocks(state).get(item,0);room=capacity(state,item)
                if held>keep and room:
                    client.transfer(item,max(keep,held-room),deposit=True)
        store_available()
        for item,target in withdraw.items():
            # Take one source stack, then reuse its freed chest slot for a
            # finished stack. This also works when the backpack is nearly full.
            for _ in range(36):
                state=client.status();held=stocks(state).get(item,0)
                if held>=target:break
                source=next((v for v in state['menu']['slots'][:-36] if v['item']==item and v['count']),None)
                room=sum(64 if not v['count'] else max(0,64-v['count']) if v['item']==item else 0
                         for v in state['inventory'] if v.get('slot',99)<36)
                if source is None or not room:break
                client.transfer(item,min(target,held+source['count'],held+room))
                store_available()
        state=client.status();entry.update(after=stocks(state),at_ms=state.get('time'))
        client.checked('close_menu');visited.append(entry)
        with (client.out/'depot-exchanges.jsonl').open('a') as stream:stream.write(json.dumps(entry,ensure_ascii=False)+'\n')
    store,fetch=unmet(client.status(),deposit,withdraw)
    return {'visited':visited,'remaining_deposit':store,'remaining_withdraw':fetch,
            'complete':not store and not fetch}
