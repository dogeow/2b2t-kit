"""Separate verified construction changes from observed off-model grass spreading.

Only dirt-to-grass outside every planned non-air cell is incidental. This does
not prove its cause, authorize a replay, or replace queue/stock confirmation.
"""
DIRT='Block{minecraft:dirt}'
GRASS='Block{minecraft:grass_block}[snowy=false]'

def classify(before,after,expected,targets):
    changed={p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)}
    completed={p for p,state in targets.items() if before.get(p)!=state and after.get(p)==state}
    incidental={p for p in changed-completed if p not in expected and p not in targets
                and before.get(p)==DIRT and after.get(p)==GRASS}
    return {'completed':completed,'incidental_grass':incidental,'unexpected':changed-completed-incidental}


def classify_flowing_water(before,after,expected,targets,fluid_boxes):
    """Explicit wet work only: track bounded water/air updates, never lost sources or structures."""
    import math,re
    if not targets or not isinstance(fluid_boxes,list)or not 1<=len(fluid_boxes)<=4:
        raise ValueError('Wet verification needs targets and one to four explicit local fluid boxes')
    for box in fluid_boxes:
        if (not isinstance(box,dict)or set(box)!={'min','max'}
                or any(not isinstance(box[k],list)or len(box[k])!=3
                       or any(type(v)is not int for v in box[k])for k in ('min','max'))
                or any(box['min'][i]>box['max'][i]for i in range(3))
                or math.prod(box['max'][i]-box['min'][i]+1 for i in range(3))>5000):
            raise ValueError('Wet verification scope is malformed or too large')
    def inside(pos):return any(all(b['min'][i]<=pos[i]<=b['max'][i]for i in range(3))for b in fluid_boxes)
    if not all(inside(p)for p in targets):raise ValueError('Every wet target must be inside its fluid scope')
    def water(state):return isinstance(state,str)and re.fullmatch(r'Block\{minecraft:water\}\[level=(?:[0-9]|1[0-5])\]',state)is not None
    def water_or_air(state):return state in (None,'Block{minecraft:air}')or water(state)
    result=classify(before,after,expected,targets)
    sources_lost={p for p,s in before.items()if s=='Block{minecraft:water}[level=0]'and after.get(p)!=s}
    result['completed']-=sources_lost;result['unexpected']|=sources_lost
    updates={p for p in result['unexpected']if p not in targets and p not in sources_lost and inside(p)
             and water_or_air(before.get(p))and water_or_air(after.get(p))}
    result['unexpected']-=updates;result['water_updates']=updates;result['sources_lost']=sources_lost
    return result
