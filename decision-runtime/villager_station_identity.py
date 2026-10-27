"""Resolve the live claimant of a shared, still-untraded workstation.

This read-only selector never authorizes mining: the native quote, trade-use,
empty-lectern and 1.9-block guards remain mandatory at the eventual input.
"""
from copy import deepcopy
import math

class StationNotReady(RuntimeError):
    pass

def claimant(state, identities, work, world, *, margin=1.35):
    lease=state.get('supervision_lease')or{}
    if (state.get('world_session')!=world or not world or state.get('connected')is not True
            or state.get('health')!=20 or state.get('manual_movement')is not False
            or state.get('screen')!='' or state.get('guard_busy')is not False
            or lease.get('kind')!='materials' or lease.get('world_session')!=world
            or not lease.get('id')or not lease.get('job_session')
            or not isinstance(identities,(set,frozenset))or len(identities)!=2
            or len(work)!=3 or any(type(v)is not int for v in work)
            or type(margin)not in(int,float)or not .5<=margin<=1.75):
        raise StationNotReady('Current healthy sole workstation observer is unavailable')
    actors=[v for v in (state.get('loaded_villagers')or{}).get('villagers',[])if v.get('uuid')in identities]
    if (len(actors)!=2 or {v['uuid']for v in actors}!=identities
            or any(v.get('is_baby')is not False or v.get('health')!=20
                   or (v.get('villager')or{}).get('profession')not in('minecraft:none','minecraft:librarian')for v in actors)):
        raise StationNotReady('Two actual healthy adult candidate identities are required')
    selected=[v for v in actors if v['villager']['profession']=='minecraft:librarian']
    if len(selected)!=1:raise StationNotReady('Exactly one current librarian must be observed')
    actor=selected[0];pos=actor.get('pos')
    if (not isinstance(pos,list)or len(pos)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in pos)
            or math.dist(pos,[work[0]+.5,work[1],work[2]+.5])>margin):
        raise StationNotReady('Current librarian is outside the pre-quote distance margin')
    return deepcopy(actor)

def stable_claimant(frames,identities,work,world,*,margin=1.35):
    if len(frames)!=2:raise StationNotReady('Two independent current observations are required')
    first,last=frames;a=claimant(first,identities,work,world,margin=margin);b=claimant(last,identities,work,world,margin=margin)
    if (a['uuid']!=b['uuid'] or type(first.get('time'))is not int or type(last.get('time'))is not int
            or not 200<=last['time']-first['time']<=2000
            or any(first.get('supervision_lease',{}).get(k)!=last.get('supervision_lease',{}).get(k)
                   for k in('id','job_session','revision','world_session'))
            or math.dist(a['pos'],b['pos'])>.15):
        raise StationNotReady('Claimant identity, lease or position has not settled')
    return b

def awake_claimant(root,state,identities,work,world,*,margin=1.35):
    """Use verified current entity flags, never a clock modulo guess."""
    from villager_events import read
    frame=read(root,state)
    if frame is None:raise StationNotReady('Current villager sleep observations are unavailable')
    observed=[v for v in frame['villagers']if v['uuid']in identities]
    if len(observed)!=2 or {v['uuid']for v in observed}!=identities:
        raise StationNotReady('Sleep observations do not cover both candidate identities')
    if any(v['sleeping']for v in observed):
        raise StationNotReady('Candidate villagers are sleeping; preserve their station without reset')
    return claimant(state,identities,work,world,margin=margin)
