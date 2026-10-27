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


def classify_neighbor_state_completion(before,after,expected,targets):
    """Report matched neighbor updates separately; never credit them as placed items or infer their cause."""
    allowed={
        'Block{minecraft:redstone_wire}':{'east','north','south','west','power'},
        'Block{minecraft:repeater}':{'powered','locked'},
        'Block{minecraft:comparator}':{'powered'},
        'Block{minecraft:redstone_torch}':{'lit'},
        'Block{minecraft:redstone_wall_torch}':{'lit'},
        'Block{minecraft:observer}':{'powered'},
        'Block{minecraft:dropper}':{'triggered'},
        'Block{minecraft:hopper}':{'enabled'},
        'Block{minecraft:glass_pane}':{'east','north','south','west'},
        'Block{minecraft:iron_bars}':{'east','north','south','west'},
    }
    def parts(state):
        if not isinstance(state,str)or not state.startswith('Block{')or'}'not in state:return None,{}
        name=state.split('}',1)[0]+'}'
        try:props=dict(v.split('=',1)for v in state.split('[',1)[1][:-1].split(','))if'['in state else{}
        except ValueError:return None,{}
        return name,props
    result=classify(before,after,expected,targets);observed=set()
    for p in result['unexpected']:
        if p in targets or p not in expected or after.get(p)!=expected[p]:continue
        old,old_props=parts(before.get(p));new,new_props=parts(after.get(p))
        changed={key for key in old_props.keys()|new_props.keys()if old_props.get(key)!=new_props.get(key)}
        if old==new and old_props.keys()==new_props.keys()and changed and changed<=allowed.get(old,set()):observed.add(p)
    result['unexpected']-=observed;result['neighbor_state_matches']=observed
    return result


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


def classify_collected_water_sources(before,after,expected,source_targets,fluid_boxes):
    """Explicit bucket collection only. Caller must independently prove each paired bucket transform."""
    import math,re
    if not isinstance(source_targets,set)or not 1<=len(source_targets)<=4:
        raise ValueError('One to four explicit collected sources required')
    if any(p in expected and expected[p]!='Block{minecraft:air}'for p in source_targets):
        raise ValueError('A planned non-air cell cannot become source cleanup')
    if any(before.get(p)!='Block{minecraft:water}[level=0]'for p in source_targets):
        raise ValueError('Each collected source needs its observed plain-source baseline')
    if not isinstance(fluid_boxes,list)or not 1<=len(fluid_boxes)<=4:raise ValueError('Explicit fluid bounds required')
    for b in fluid_boxes:
        if (not isinstance(b,dict)or set(b)!={'min','max'}or any(not isinstance(b[k],list)or len(b[k])!=3 or any(type(v)is not int for v in b[k])for k in ('min','max'))
                or any(b['min'][i]>b['max'][i]for i in range(3))or math.prod(b['max'][i]-b['min'][i]+1 for i in range(3))>5000):
            raise ValueError('Malformed or oversized source cleanup bounds')
    def inside(p):return any(all(b['min'][i]<=p[i]<=b['max'][i]for i in range(3))for b in fluid_boxes)
    if not all(inside(p)for p in source_targets):raise ValueError('Collected source outside declared fluid bounds')
    def water(s):return isinstance(s,str)and re.fullmatch(r'Block\{minecraft:water\}\[level=(?:[0-9]|1[0-5])\]',s)is not None
    def air(s):return s in(None,'Block{minecraft:air}')
    changed={p for p in before.keys()|after.keys()if before.get(p)!=after.get(p)}
    cleared={p for p in source_targets if air(after.get(p))}
    other_sources_lost={p for p,s in before.items()if s=='Block{minecraft:water}[level=0]'and p not in source_targets and after.get(p)!=s}
    updates={p for p in changed-source_targets-other_sources_lost if inside(p)
             and(water(before.get(p))or air(before.get(p)))and(water(after.get(p))or air(after.get(p)))}
    incidental={p for p in changed-source_targets-updates if p not in expected and before.get(p)==DIRT and after.get(p)==GRASS}
    invalid_source_results={p for p in source_targets if not air(after.get(p))and not water(after.get(p))}
    return {'cleared_sources':cleared,'uncleared_sources':source_targets-cleared,'water_updates':updates,
            'incidental_grass':incidental,'other_sources_lost':other_sources_lost,
            'unexpected':changed-source_targets-updates-incidental|invalid_source_results|other_sources_lost}
