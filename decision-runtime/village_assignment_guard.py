"""Check current loaded adults against witnessed private stalls and founders."""
import math

def uncontained_adults(state,policy,home):
    assigned=policy.get('adult_assignment_bounds')
    if assigned is None:return []
    if policy.get('world_session')!=state.get('world_session'):
        raise RuntimeError('Reverify village containment in the current world before installing workstations')
    shared=policy.get('shared_adult_bounds')or{}
    if not isinstance(assigned,dict)or not isinstance(shared,dict)or not assigned:
        raise RuntimeError('Current witnessed adult assignments are unavailable')
    def inside(point,bounds):
        low=bounds.get('min');high=bounds.get('max_exclusive')
        if(not isinstance(low,list)or not isinstance(high,list)
                or len(low)!=3 or len(high)!=3 or any(type(v)is not int for v in low+high)
                or any(a>=b for a,b in zip(low,high))):raise RuntimeError('Malformed witnessed village bounds')
        return all(a<=p<b for a,p,b in zip(low,point,high))
    result=[]
    for row in state.get('loaded_villagers',{}).get('villagers',[]):
        if row.get('is_baby')is True:continue
        uid=row.get('uuid');point=row.get('pos')
        if(not isinstance(uid,str)or not isinstance(point,list)or len(point)!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in point)):
            raise RuntimeError('Current adult position is incomplete')
        expected=assigned.get(uid,shared.get(uid))
        if expected is not None:
            if not inside(point,expected):result.append(uid)
        elif inside(point,home):result.append(uid)
    return sorted(set(result))


def wait_for_containment(read,policy,home,initial,*,timeout=2.0,interval=.1,clock=None,pause=None):
    """Wait without input for a transient position; persistent displacement still fails."""
    import time
    if not 0<=timeout<=2 or not 0<interval<=.5:raise ValueError('Bounded read-only containment wait required')
    clock=clock or time.monotonic;pause=pause or time.sleep
    end=clock()+timeout;state=initial
    while True:
        missing=uncontained_adults(state,policy,home)
        if not missing or clock()>=end:return state,missing
        pause(min(interval,max(0,end-clock())))
        state=read()
