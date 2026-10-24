"""Consolidate plain carried target stacks through one registered depot route."""
import math
import time
from contextlib import contextmanager
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_jobs.protocol import JobBlocked


def run_inventory(backend,item,minimum):
    """Merge plain carried stacks in place using the existing exact transfer primitive."""
    c=backend.ensure_client();initial=c.status();plan=offer(initial,item,minimum)
    if plan is None:return None
    from kit_runtime.inventory import InventorySession
    from kit_runtime.storage import move_amount
    before=dict(inventory_counts(initial))
    with backend.action('plain_inventory_merge')as(c,out):
        path=out/'inventory-merge.json'
        if path.exists():raise JobBlocked('Original inventory merge journal must be retained; no replay')
        book={'item':item,'before':before,'pending':None,'complete':False,'moves':[]}
        write_json(path,book);session=InventorySession(c)
        for _ in range(35):
            s=c.status();menu=s.get('menu')or{};rows=menu.get('slots',[])
            if(menu.get('id')!=0 or menu.get('type')!='InventoryMenu'or len(rows)!=46
                    or menu.get('cursor',{}).get('count')!=0 or any(r['count']for r in rows[:5])):
                raise JobBlocked('Inventory merge requires clear current ordinary inventory; no repeated click')
            if dict(inventory_counts(s))!=before:raise JobBlocked('Inventory changed during plain stack merge')
            if sum(not r['count']for r in s['inventory']if r['slot']<36)>=minimum:break
            stacks=[r for r in rows[9:45]if r['item']==item and r['count']>0]
            if any(set(r)!={'slot','item','count','max_stack'}for r in stacks):
                raise JobBlocked('Plain inventory stack metadata changed; preserve pending receipt')
            pairs=[(a,b,min(a['count'],b['max_stack']-b['count']))for a in stacks for b in stacks
                   if a['slot']!=b['slot'] and b['count']<b['max_stack']]
            if not pairs:raise JobBlocked('No plain stack merge remains')
            # A full bag can have enough aggregate space without any two
            # fragments fitting together. Fill one destination partially, then
            # merge the smaller remainder; never discard a stack for room.
            a,b,amount=min(pairs,key=lambda pair:(pair[2]!=pair[0]['count'],pair[0]['count'],-pair[1]['count']))
            book['pending']={'source':a,'destination':b,'amount':amount};write_json(path,book)
            returned=move_amount(session,s,a,b,amount)
            current=session._wait(returned,menu['id'],lambda m:m['cursor']['count']==0
                and m['slots'][a['slot']]['count']==a['count']-amount
                and m['slots'][b['slot']]['item']==item
                and m['slots'][b['slot']]['count']==amount+b['count'],
                'plain_merge_later_frames',confirmations=2,fresh=True)
            if dict(inventory_counts(current))!=before:raise JobBlocked('Plain stack merge conservation unproved')
            book['moves'].append(book['pending']);book['pending']=None;write_json(path,book)
        final=c.status();free=sum(not r['count']for r in final['inventory']if r['slot']<36)
        if free<minimum or dict(inventory_counts(final))!=before:raise JobBlocked('Inventory merge workspace unproved')
        book.update(complete=True,free_slots=free,inventory_credit=0,depot_visits=0);write_json(path,book)
        return {'phase':'done','item':item,**plan,'free_slots':free,'inventory_credit':0,'depot_visits':0}


def offer(state,item,minimum):
    rows=[r for r in state.get('inventory',[])if r.get('slot',99)<36]
    if len(rows)!=36 or {r.get('slot')for r in rows}!=set(range(36)):return None
    stacks=[r for r in rows if r.get('item')==item and r.get('count',0)>0]
    if (not stacks or any(set(r)!={'slot','item','count','max_stack'}for r in stacks)
            or len({r['max_stack']for r in stacks})!=1):return None
    size=stacks[0]['max_stack']
    if type(size)is not int or not 1<=size<=99 or any(type(r['count'])is not int or not 1<=r['count']<=size for r in stacks):return None
    total=sum(r['count']for r in stacks)
    freed=len(stacks)-math.ceil(total/size);empty=sum(not r.get('count',0)for r in rows)
    return {'total':total,'before_stacks':len(stacks),'freed_slots':freed}if empty<minimum<=empty+freed else None


def prepare_fetch(client,items):
    """Reuse the caller's lease to recover workspace before a storage trip.

    This is an opportunistic lower bound, not a promise that every future
    source fits. In particular, non-stackable or large requests may need more
    space; the ordinary transfer still checks actual receiving capacity.
    """
    items=tuple(dict.fromkeys(items))
    if not items:return None
    initial=client.status();menu=initial.get('menu')or{}
    if(initial.get('screen')or initial.get('manual_movement')is True
            or menu.get('type')!='InventoryMenu'or menu.get('id')!=0
            or len(menu.get('slots',[]))!=46 or menu.get('cursor',{}).get('count')!=0
            or any(r['count']for r in menu['slots'][:5])):return None
    wanted=min(36,len(items)+1);before=dict(inventory_counts(initial));moves=[]
    class ExistingOwner:
        def ensure_client(self):return client
        @contextmanager
        def action(self,name):
            out=Path(client.out)/('fetch-inventory-merge-'+str(time.time_ns()))
            out.mkdir(exist_ok=False);yield client,out
    backend=ExistingOwner()
    for _ in range(35):
        s=client.status();rows=[r for r in s.get('inventory',[])if r.get('slot',99)<36]
        if len(rows)!=36:break
        free=sum(not r['count']for r in rows)
        if free>=wanted:break
        choices=[]
        for item in sorted({r['item']for r in rows if r.get('count',0)}):
            for minimum in range(wanted,free,-1):
                if offer(s,item,minimum)is not None:
                    choices.append((minimum-free,item,minimum));break
        if not choices:break
        _,item,minimum=max(choices,key=lambda p:(p[0],p[1]))
        moves.append(run_inventory(backend,item,minimum))
    if not moves:return None
    final=client.status()
    if dict(inventory_counts(final))!=before:raise JobBlocked('Fetch workspace changed carried item totals')
    return {'phase':'done','free_slots':sum(not r['count']for r in final['inventory']if r['slot']<36),
            'requested_minimum':wanted,'inventory_credit':0,'depot_visits':0,'merges':moves}


def run(backend,item,minimum):
    c=backend.ensure_client();plan=offer(c.status(),item,minimum)
    if plan is None:return None
    from material_storage_index import select_destinations
    from material_depots import exchange
    route=select_destinations(c,backend.profile['depots'],{item:0})
    if not route['positions']:return None
    with backend.action('plain_stack_consolidation')as(c,out):
        write_json(out/'local-route.json',route);backend.prepare_travel();backend.stage_near_base(route['positions'])
        deposited=exchange(c,route['positions'],deposit={item:0});write_json(out/'deposit.json',deposited)
        if not deposited['complete']or inventory_counts(c.status())[item]!=0:
            raise JobBlocked('Stack consolidation deposit incomplete; retain original receipt')
        withdrawn=exchange(c,route['positions'],withdraw={item:plan['total']});write_json(out/'withdrawal.json',withdrawn)
        state=c.status();rows=[r for r in state['inventory']if r.get('slot',99)<36 and r.get('item')==item]
        if not withdrawn['complete']or inventory_counts(state)[item]!=plan['total']or len(rows)!=plan['before_stacks']-plan['freed_slots']:
            raise JobBlocked('Stack consolidation inventory conservation unproved')
        result={'phase':'done','item':item,**plan,'free_slots':sum(not r.get('count',0)for r in state['inventory']if r['slot']<36),
                'warehouse_inventory_credit':0,'deposit_and_withdrawal_updated_local_cache':True}
        write_json(out/'result.json',result);return result
