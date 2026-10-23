"""Select ready candidates, preserving the short native keeper quote window."""
import math
def choose_ready(ready,last_used,preferred=None):
 if not ready:return None
 return next((slot for slot in ready if slot['id']==preferred),None)or min(ready,key=lambda slot:last_used.get(slot['id'],0))

def keeper_refresh_key(slot_id,enchantment,previous):
 return f"{slot_id}:{enchantment}:{(previous or{}).get('native_sequence',0)}"


def wake_paid_keeper_candidates(blocked,deferred,actors,flags,now,counts,attempts):
    """Moved paid suppliers within 2.2 of work may retry a read, never authorize reset."""
    awakened=[]
    for name,row in list(deferred.items()):
        key=row['refresh_key']
        if counts.get(key,0)>=3:deferred.pop(name);continue
        actor=actors.get(row['uuid']);flag=flags.get(row['uuid']);job=(actor or{}).get('villager')or{}
        if (row.get('paid_history_verified')is not True or not actor or not flag
            or flag.get('sleeping')is not False or actor.get('health')!=20 or actor.get('is_baby')is not False
            or job.get('profession')!='minecraft:librarian'or now-row['deferred_at']<20):continue
        pos=actor.get('pos');prior=row.get('pos');work=row['work']
        # Public eye is one cell outside the workpoint. A 2.2-cell hint
        # leaves a margin inside the later exact 2.95 eye/body read check.
        if not isinstance(pos,list)or len(pos)!=3 or math.dist(pos,[work[0]+.5,float(work[1]),work[2]+.5])>=2.2:continue
        if isinstance(prior,list)and math.dist(pos,prior)<.35:
            if now-row['deferred_at']>=90:deferred.pop(name)
            continue
        blocked.discard(name);deferred.pop(name);counts[key]=counts.get(key,0)+1;attempts.pop(key,None);awakened.append(name)
    return awakened
