"""Verified warehouse housekeeping; items are stored, never discarded."""
from build_supervisor import stocks

def visit(client,pos):
    inv=stocks(client.status());marker=next((i for i in ('minecraft:diamond_sword','minecraft:diamond_pickaxe','minecraft:oak_log') if inv.get(i,0)),None)
    if marker is None:raise RuntimeError('No stable carried marker for a no-withdrawal depot visit')
    r=client.fetch(pos,{marker.removeprefix('minecraft:'):1})
    if r.get('phase')!='done':raise RuntimeError(r.get('detail','Cannot reach approved depot'))
    client.open(pos)

def stash(client,positions,item_ids):
    moved={}
    for pos in positions:
        wanted=[i for i in item_ids if stocks(client.status()).get(i,0)>0]
        if not wanted:break
        try:visit(client,pos)
        except RuntimeError as e:
            print('DEPOT_SKIPPED',pos,str(e),flush=True);continue
        try:
            for item in wanted:
                before=stocks(client.status()).get(item,0)
                try:after=client.transfer(item,0,deposit=True)
                except RuntimeError as e:
                    if 'no space' not in str(e):raise
                    continue
                if after<before:moved.setdefault(item,[]).append({'count':before-after,'pos':pos})
        finally:client.checked('close_menu')
    return moved

def store_spares(client,positions,keep):
    """Try approved depots until only the requested carried count remains.

    Ordinary chest quick-move visits the main inventory before the hotbar, so
    explicitly require active tools in the hotbar before storing tool backups.
    """
    moved={}
    for pos in positions:
        wanted={item:n for item,n in keep.items() if stocks(client.status()).get(item,0)>n}
        if not wanted:break
        visit(client,pos)
        try:
            for item,n in wanted.items():
                state=client.status()
                if n<1 or not any(v['item']==item and v['count'] and v.get('slot',99)<9 for v in state['inventory']):
                    raise RuntimeError('Keep an active hotbar tool before storing backups')
                before=stocks(state).get(item,0)
                try:after=client.transfer(item,n,deposit=True)
                except RuntimeError as e:
                    if 'no space' not in str(e):raise
                    after=stocks(client.status()).get(item,0)
                if after<n:raise RuntimeError('Carried tool reserve was not preserved')
                if after<before:moved.setdefault(item,[]).append({'count':before-after,'pos':pos})
        finally:client.checked('close_menu')
    return moved
