"""Use a witnessed public aisle pose for a lectern beneath a closed trade cap."""
from projection_completion import block_state
import math

def candidate(pos,target,expected):
 if not isinstance(pos,list)or len(pos)!=3:return None
 kind,props=block_state(expected)
 if kind!='minecraft:lectern'or props.get('facing')not in ('north','south'):return None
 x,y,z=target;outward=-1 if props['facing']=='north'else 1
 if abs(pos[0]-(x+.5))>.2 or abs(pos[1]-y)>.25 or not .7<=(pos[2]-(z+.5))*outward<=1.3:return None
 return [x+.5,y+.3,z+.5+2*outward]

def clear(rows,entities,target,pose,player_uuid):
 x,y,z=target;outward=-1 if pose[2]<z else 1
 cap=rows.get((x,y+1,z),{}).get('state','')
 try:kind,props=block_state(cap)
 except ValueError:return False
 valid=(kind.endswith('_slab')and props.get('type')=='bottom'
        or kind.endswith('_trapdoor')and props.get('half')=='top'and props.get('open')=='false')
 if(not valid or props.get('waterlogged')!='false'
    or rows.get((x,y+2,z),{}).get('solid')is not True):return False
 for step in (1,2):
  col=z+step*outward;floor=rows.get((x,y-1,col),{})
  if floor.get('solid')is not True or floor.get('fluid')is not False:return False
  if any((x,h,col)in rows for h in range(y,math.ceil(pose[1]+1.8))):return False
 low=[x,y+.1,min(z+.5+outward,pose[2])-.3];high=[x+1,pose[1]+1.8,max(z+.5+outward,pose[2])+.3]
 for e in entities:
  if e.get('type')=='minecraft:item'or e.get('uuid')==player_uuid:continue
  box=e.get('bounds')or{}
  if not all(k in box for k in ('min','max')):return False
  if all(box['max'][i]>low[i]and box['min'][i]<high[i]for i in range(3)):return False
 return True

def direct_from_low_top_cap(rows,origin,target):
 try:
  x,y,z=target;outward=-1 if origin[2]<z+.5 else 1
  if(not isinstance(origin,list)or len(origin)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in origin)
     or abs(origin[0]-(x+.5))>.2 or not y-.01<=origin[1]<=y+.1
     or not .7<=(origin[2]-(z+.5))*outward<=1.3):return False
  kind,props=block_state(rows.get((x,y+1,z),{}).get('state','Block{minecraft:air}'))
  if not(kind.endswith('_trapdoor')and props.get('half')=='top'and props.get('open')=='false'and props.get('waterlogged')=='false'):return False
  floor=rows.get((x,y-1,z+outward),{})
  return(floor.get('solid')is True and floor.get('fluid')is False
         and all((x,h,z+outward)not in rows for h in(y,y+1))
         and origin[1]+1.62<y+1.8125-.03)
 except(KeyError,TypeError,ValueError):return False

def staged_ground_retreat(rows,entities,origin,target,pose,player_uuid):
 """A ground retreat beneath a second top cap precedes any upward movement."""
 try:
  x,y,z=target;outward=-1 if pose[2]<z else 1
  if not y-.01<=origin[1]<=y+.01:return None
  for col in (z,z+outward):
   kind,props=block_state(rows.get((x,y+1,col),{}).get('state','Block{minecraft:air}'))
   if not(kind.endswith('_trapdoor')and props.get('half')=='top'and props.get('open')=='false'and props.get('waterlogged')=='false'):return None
   if rows.get((x,y+2,col),{}).get('solid')is not True:return None
  if (x,y,z+outward)in rows:return None
  for step in (1,2,3):
   col=z+step*outward;floor=rows.get((x,y-1,col),{})
   if floor.get('solid')is not True or floor.get('fluid')is not False:return None
   if step>=2 and any((x,h,col)in rows for h in range(y,y+3)):return None
  low=[x,y,min(z+outward,z+3*outward)];high=[x+1,y+3,max(z+outward,z+3*outward)+1]
  for entity in entities:
   if entity.get('type')=='minecraft:item'or entity.get('uuid')==player_uuid:continue
   bounds=entity.get('bounds')or{}
   if not all(k in bounds for k in ('min','max')):return None
   if all(bounds['max'][i]>low[i]and bounds['min'][i]<high[i]for i in range(3)):return None
  return [x+.5,float(y),pose[2]+.19*outward]
 except(KeyError,TypeError,ValueError):return None


def approach(builder,target,expected):
 s=builder.check();origin=s.get('pos');pose=candidate(origin,target,expected)
 if pose is None:return None
 x,y,z=target;outward=-1 if pose[2]<z else 1
 a,rows=builder.scan([x,y-1,min(z,z+3*outward)],[x,y+2,max(z,z+3*outward)])
 if direct_from_low_top_cap(rows,origin,target):
  builder.book.setdefault('direct_top_cap_print_admissions',[]).append({'target':target,'origin':origin,'scan_time':a['time'],'no_reposition':True});builder.save();return None
 staged=staged_ground_retreat(rows,a['scan_entities'],origin,target,pose,s.get('player_uuid'))
 if not clear(rows,a['scan_entities'],target,pose,s.get('player_uuid'))and staged is None:return None
 record={'origin':list(origin),'placement_pose':pose,'target':target,'pending':True};builder.book.setdefault('public_lectern_access',[]).append(record);builder.save()
 if staged is not None:
  record['staged_ground_retreat']=staged;builder.save();builder.n('walk',target=staged,arrival=.1,restore_flight=False,seconds=15)
  actual=builder.check()['pos'];near=z+outward
  if not(abs(actual[1]-y)<=.05 and(actual[2]+.3<near-.05 if outward<0 else actual[2]-.3>near+1+.05)):
   raise RuntimeError('Ground retreat did not clear the low cap; no upward movement sent')
 builder.nav(pose);return record

def restore(builder,record):
 if record is not None:
  if record.get('staged_ground_retreat'):
   pose=record['placement_pose'];floor=record['target'][1];builder.nav([pose[0],float(floor),pose[2]]);builder.n('walk',target=record['origin'],arrival=.1,restore_flight=False,seconds=15)
  else:builder.nav(record['origin'])
  record['pending']=False;builder.save()
