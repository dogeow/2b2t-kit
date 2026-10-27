"""A treatment never permits a new decline after previously observed healing."""
import math

def observe(rows,floors):
 updated=dict(floors)
 for actor in rows:
  uid=actor.get('uuid');h=actor.get('health');minimum=floors.get(uid,20)
  if type(h)not in(int,float)or not math.isfinite(h)or h>20 or h+1e-4<minimum:raise RuntimeError('New resident injury during treatment')
  if uid in floors:updated[uid]=max(minimum,h)
 return updated
