"""Recover previously stored construction supplies, checking live stock after every visit."""
from collections import defaultdict
from material_plan import inventory_counts as stocks

def requests_from_receipts(receipts,targets,inventory):
    sources=defaultdict(set)
    for receipt in receipts:
        for item,entries in receipt.items():
            if targets.get(item,0)<=inventory.get(item,0):continue
            for entry in entries:
                if entry.get('count',0)>0:sources[tuple(entry['pos'])].add(item)
    return [(list(pos),{item:targets[item] for item in sorted(items)}) for pos,items in sorted(sources.items())]

def recover_stored(client,placement_key,targets,receipts):
    visits=[]
    for pos,requested in requests_from_receipts(receipts,targets,stocks(client.status())):
        state=client.status()
        if state.get('projection_selection',{}).get('key')!=placement_key:raise RuntimeError('Selected construction changed')
        pending={item:n for item,n in requested.items() if stocks(state).get(item,0)<n}
        # Native visits intentionally cap transfers at eight. Large groups use bounded sub-visits.
        pairs=list(pending.items())
        for offset in range(0,len(pairs),8):
            batch=dict(pairs[offset:offset+8]);before=stocks(client.status())
            result=client.fetch(pos,{i.removeprefix('minecraft:'):n for i,n in batch.items()})
            if result.get('phase')!='done':raise RuntimeError(result.get('detail','Stored supply visit failed'))
            after=stocks(client.status())
            visits.append({'pos':pos,'requested':batch,'received':{i:after.get(i,0)-before.get(i,0) for i in batch},
                           'remaining':{i:n-after.get(i,0) for i,n in batch.items() if after.get(i,0)<n}})
    inventory=stocks(client.status())
    return {'visits':visits,'remaining_targets':{i:n-inventory.get(i,0) for i,n in targets.items() if inventory.get(i,0)<n}}
