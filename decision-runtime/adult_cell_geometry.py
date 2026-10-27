"""Conservative full-width horizontal collision bands for existing adult trade cells.

This proves adult containment, not baby containment or permission to reset a lectern.
Lectern base (16 wide, height2/16) is verified against vanilla26.2 LecternBlock.SHAPE_COLLISION.
"""
from projection_completion import block_state
MIN_ADULT_HEIGHT=1.9

def bands(row,height):
 if not row or row.get('fluid')is not False:return []
 if row.get('solid')is True:return [(height,height+1)]
 kind,p=block_state(row.get('state','Block{minecraft:air}'))
 if kind.endswith('_slab')and p.get('waterlogged')=='false':
  if p.get('type')=='bottom':return [(height,height+.5)]
  if p.get('type')=='top':return [(height+.5,height+1)]
 if kind.endswith('_trapdoor')and p.get('open')=='false'and p.get('waterlogged')=='false':return [(height+.8125,height+1)]if p.get('half')=='top'else[(height,height+.1875)]
 if kind=='minecraft:lectern':return [(height,height+.125)]
 return []

def largest_gap(intervals,ceiling):
 end=0;gap=0
 for low,high in sorted(intervals):
  low=max(0,min(ceiling,low));high=max(0,min(ceiling,high))
  if high<=end:continue
  gap=max(gap,low-end);end=high
 return max(gap,ceiling-end)

def audit(rows,slot):
 counter=slot.get('public_counter_block')or slot.get('previous_work_block')or slot['work_block'];x,floor,z=counter;floor=slot.get('interior_floor_y',floor);inward=1 if slot['id'][1]=='S'else-1
 rear=slot.get('rear_wall_base',[x,floor,z+4*inward]);length=(rear[2]-z)*inward
 if not 2<=length<=5:return {'slot':slot['id'],'verified':False,'issues':[{'reason':'unsupported_explicit_cell_length'}]}
 interior=[z+n*inward for n in range(1,length)];issues=[];ceilings={}
 for zz in interior:
  below=rows.get((x,floor-1,zz),{})
  if below.get('solid')is not True or below.get('fluid')is not False:issues.append({'pos':[x,floor-1,zz],'reason':'floor_unverified'})
  roof=bands(rows.get((x,floor+3,zz)),3)
  if not roof:issues.append({'pos':[x,floor+3,zz],'reason':'closed_roof_unverified'})
  else:ceilings[zz]=min(v[0]for v in roof)
 checks=[]
 def wall(xx,zz,ceiling,label):
  spans=[]
  for h in range(4):spans.extend(bands(rows.get((xx,floor+h,zz)),h))
  gap=largest_gap(spans,ceiling);checks.append({'boundary':[xx,zz],'kind':label,'largest_free_vertical_gap':gap})
  if gap>=MIN_ADULT_HEIGHT:issues.append({'pos':[xx,floor,zz],'reason':'adult_sized_opening','gap':gap,'kind':label})
 for zz in interior:
  ceiling=ceilings.get(zz,4)
  wall(x-1,zz,ceiling,'side');wall(x+1,zz,ceiling,'side')
 wall(x,rear[2],ceilings.get(interior[-1],4),'rear');wall(x,z,ceilings.get(interior[0],4),'front')
 return {'slot':slot['id'],'verified':not issues,'issues':issues,'front_counter':counter,'rear_wall':rear,'checks':checks,'minimum_adult_height':MIN_ADULT_HEIGHT,'scope':'current_adult_collision_containment_only','baby_containment_not_claimed':True,'reset_authorization_not_granted':True}
