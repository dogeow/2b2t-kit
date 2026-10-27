"""Recognise a small settled guard rise after a known stopped air movement.

Only a snapshot is admitted. The original movement remains incomplete.
"""
import math
def incidental_drops(before,after):
 from material_plan import inventory_counts
 a,b=inventory_counts(before),inventory_counts(after)
 permitted={'minecraft:rotten_flesh','minecraft:bone','minecraft:arrow','minecraft:gunpowder','minecraft:string','minecraft:spider_eye'}
 return not(a-b)and all(k in permitted and 0<v<=64 for k,v in (b-a).items())
def guard_rise(reply,event,state):
 try:
  a,b=reply['pos'],state['pos']
  return (event.get('request_id')==reply.get('id')==state.get('last_request')
   and event.get('phase')==reply.get('phase')=='waiting'
   and event.get('detail')==reply.get('detail')=='air-only path changed; no blocks were excavated'
   and event.get('guard_pause_ms',0)>0 and not state.get('guard_busy')
   and all(type(v)in(int,float)and math.isfinite(v)for v in a+b)
   and len(a)==len(b)==3 and math.hypot(a[0]-b[0],a[2]-b[2])<=.05
   and 0<=b[1]-a[1]<=2)
 except(KeyError,TypeError,ValueError):return False
