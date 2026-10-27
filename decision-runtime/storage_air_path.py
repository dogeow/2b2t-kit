"""Keep both floor/ceiling margin and turns in a proved storage air corridor."""
import math

def flight_nodes(nodes):
 if(not isinstance(nodes,list)or not nodes or any(not isinstance(p,list)or len(p)!=3
    or any(type(v)not in(int,float)or not math.isfinite(v)for v in p)for p in nodes)):
  raise ValueError('Finite explicit storage air nodes required')
 points=[[p[0],p[1]+.1,p[2]]for p in nodes];out=[]
 for point in points:
  if len(out)>=2:
   a,b=out[-2:];vertical=all(abs(p[0]-a[0])<1e-7 and abs(p[2]-a[2])<1e-7 for p in [b,point])
   if vertical and (b[1]-a[1])*(point[1]-b[1])>0 and abs(point[1]-a[1])<=16:
    out[-1]=point;continue
  out.append(point)
 return out
