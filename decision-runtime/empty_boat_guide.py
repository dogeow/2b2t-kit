"""Guide an empty leashed receiver; boarding ends this mode before another input.

Ordinary ground contact is permitted for the empty boat. Cargo transport still
uses the separate full passenger corridor kernel. Unknown pilot inputs stop.
"""
import math,time
from pathlib import Path
from vehicle_observation import read_frame
from kit_runtime.journal import write_json
from boat_towing import next_pilot,envelope,HAZARDS

def next_empty(here,target,boat):
 proposed=next_pilot(here,target,boat)
 flat=math.hypot(target[0]-here[0],target[2]-here[2]);dy=target[1]-here[1]
 if abs(dy)>.25 and not(dy<0 and flat>.25):
  proposed=[here[0],here[1]+math.copysign(min(3,abs(dy)),dy),here[2]]
 if math.dist(proposed,boat)>8.5:
  lo,hi=0.,1.
  for _ in range(40):
   ratio=(lo+hi)/2;p=[here[i]+(proposed[i]-here[i])*ratio for i in range(3)]
   if math.dist(p,boat)<=8.5:lo=ratio
   else:hi=ratio
  proposed=[here[i]+(proposed[i]-here[i])*lo for i in range(3)]
 if math.dist(proposed,here)<.05:raise RuntimeError('Empty receiver has no safe movement slack')
 return proposed

def harmless_contact(rows):
 return all(r.get('state','').split('}',1)[0].removeprefix('Block{')not in
            HAZARDS|{'minecraft:lava','minecraft:nether_portal','minecraft:end_portal'} for r in rows)

def eligible(s,b):
 return (s.get('health')==20 and s.get('food',0)>=18 and s.get('connected')is True
  and s.get('manual_movement')is False and not s.get('screen')and s.get('guard_armed')is True
  and s.get('guard_pve_only')is True and b.get('alive')is True and b.get('passengers')==[]
  and b.get('leashed')is True and b.get('leash_resolved')is True
  and b.get('leash_holder',{}).get('uuid')==s.get('player_uuid')
  and b.get('type','').endswith('_boat')and 'chest'not in b.get('type',''))

def guide(c,uuid,route,path,stop=None):
 path=Path(path);assert not path.exists()and 1<=len(route)<=8
 book={'world_session':c.world,'uuid':uuid,'route':route,'complete':False,'pending':None,'legs':[]};write_json(path,book)
 def observe():
  s=c.status();f=read_frame(c.root,s);assert f is not None
  b=next(v for v in f['vehicles']if v['uuid']==uuid)
  if not eligible(s,b):raise RuntimeError('Empty receiver changed; no next pilot input')
  if math.dist(s['pos'],b['pos'])>=9:raise RuntimeError('Empty receiver leash is stretched; stop')
  return s,b
 for target in route:
  s,b=observe();assert len(target)==3 and math.dist(s['pos'],target)<=64
  while math.dist(s['pos'],target)>.25:
   if stop and stop(s,b):book.update(complete=True,stopped_for_observation=True);write_json(path,book);return book
   p=next_empty(s['pos'],target,b['pos']);low,high=envelope(s,b,p)
   scene=c.checked('scan',min=low,max=high,details=True)
   if(scene.get('scan_cells_read')!=scene.get('scan_total_cells')or not harmless_contact(scene['blocks'])):
    raise RuntimeError('Empty receiver corridor contains a hazard or unloaded cells')
   s,b=observe();book['pending']={'from':s['pos'],'target':p};write_json(path,book)
   r=c.checked('navigate',target=p,arrival=.15,air_only=True,seconds=20)
   if r.get('phase')!='done':raise RuntimeError('Original empty-guide pilot move did not complete')
   book['legs'].append({'request':r['id'],'target':p});book['pending']=None;write_json(path,book)
   end=time.monotonic()+8
   while True:
    s,b=observe()
    if math.dist(s['pos'],b['pos'])<=6.75:break
    if time.monotonic()>end:raise RuntimeError('Empty receiver did not follow; no further movement')
    time.sleep(.15)
 book.update(complete=True,boat_after=b);write_json(path,book);return book
