"""Exact vanilla26.2 north/south closed-gate collision, not whole-voxel occupancy."""
import math

def collision(pos):
 x,y,z=pos;return {'min':[x,y,z+.375],'max':[x+1,y+1.5,z+.625]}
def intersects(a,b):return all(a['max'][i]>b['min'][i]and a['min'][i]<b['max'][i]for i in range(3))
def admitted(scene,pos,uid,*,inward=1):
 try:
  shape=collision(pos);patients=[v for v in scene['scan_entities']if v.get('uuid')==uid]
  if len(patients)!=1:return False
  v=patients[0];box=v['bounds']
  if inward not in(-1,1):return False
  front_clear=box['max'][2]<=shape['min'][2]-.05 if inward==1 else box['min'][2]>=shape['max'][2]+.05
  if(v['type']!='minecraft:villager'or v['health']!=20 or v['is_baby']is not False
     or box['max'][1]-box['min'][1]<1.9 or not front_clear):return False
  for e in scene['scan_entities']:
   box=e['bounds']
   if any(len(box[k])!=3 or any(type(n)not in(int,float)or not math.isfinite(n)for n in box[k])for k in('min','max')):return False
   if intersects(box,shape):return False
  return True
 except(KeyError,TypeError,ValueError):return False
