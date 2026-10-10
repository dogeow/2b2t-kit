"""Consolidate plain carried target stacks through one registered depot route."""
import math

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_jobs.protocol import JobBlocked


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
