"""An ordinary temporary side-supported fence with verified actual clearance.

The conservative proxy contains the vanilla east/west-connected fence shape;
it intentionally does not treat the otherwise empty target cell as a full cube.
"""
import time
from material_plan import inventory_counts
from projection_completion import block_state

ITEM='minecraft:acacia_fence'
PROPERTIES={'east':'true','north':'false','south':'false','waterlogged':'false','west':'true'}

def prepare(rows,entities,pos,uid,*,inward=1,rear_piston=False):
 x,y,z=pos
 if inward not in (-1,1):raise ValueError('Fence inward direction must be north or south')
 properties=dict(PROPERTIES)
 if rear_piston:
  facing='north'if inward==1 else'south'
  if rows.get((x,y,z+inward),{}).get('state')!='Block{minecraft:piston}[extended=false,facing='+facing+']':
   raise ValueError('Exact unpowered inward-facing rear piston required')
  properties['south'if inward==1 else'north']='true'
 if(tuple(pos)in rows or any((x,y,z+dz)in rows for dz in (-1,1)if not rear_piston or dz!=inward)
    or any(rows.get((x+dx,y,z),{}).get('state')!='Block{minecraft:dark_oak_planks}'for dx in (-1,1))):
  raise ValueError('Fence requires empty north/south cells and both full wooden side walls')
 low=[x,y,z if rear_piston and inward==-1 else z+3/8];high=[x+1,y+1.5,z+1 if rear_piston and inward==1 else z+5/8]
 who=next((e for e in entities if e.get('uuid')==uid),None)
 if inward not in (-1,1):raise ValueError('Fence inward direction must be north or south')
 if(not who or who.get('type')!='minecraft:villager'or who.get('health')!=20 or who.get('is_baby')is not False
    or(inward==1 and who['bounds']['max'][2]>low[2])or(inward==-1 and who['bounds']['min'][2]<high[2])):
  raise ValueError('Adult resident must already be in front of the fence shape')
 for e in entities:
  if e.get('type')=='minecraft:item':continue
  box=e['bounds']
  if all(box['max'][i]>low[i]and box['min'][i]<high[i]for i in range(3)):
   raise ValueError('Fence shape would intersect a loaded entity')
 return {'pos':pos,'collision_proxy':{'min':low,'max':high},'resident_uuid':uid,'expected_properties':properties}

def place(builder,pos,uid,*,inward=1,rear_piston=False):
 x,y,z=pos;scene,rows=builder.scan([x-1,y,z-1],[x+1,y,z+1]);record=prepare(rows,scene['scan_entities'],pos,uid,inward=inward,rear_piston=rear_piston)
 state=builder.check();before=inventory_counts(state)[ITEM]
 if before<1:raise ValueError('One carried fence is required')
 own={'min':[state['pos'][0]-.3,state['pos'][1],state['pos'][2]-.3],
      'max':[state['pos'][0]+.3,state['pos'][1]+1.8,state['pos'][2]+.3]}
 proxy=record['collision_proxy']
 if all(own['max'][i]>proxy['min'][i]and own['min'][i]<proxy['max'][i]for i in range(3)):
  raise ValueError('Operator intersects the fence shape')
 slot=next(v['slot']for v in state['inventory']if v['item']==ITEM and v['count'])
 builder.n('select_item',item=ITEM,slot=slot);assert builder.check()['hand']['item']==ITEM
 record.update(pending=True,material_before=before)
 builder.book.setdefault('temporary_fence_barriers',[]).append(record);builder.save()
 r=builder.n('interact',pos=[x-1,y,z],face='east',expected_state=rows[(x-1,y,z)]['state'],expected_hand=ITEM)
 record['request_id']=r['id'];builder.save();times=[];end=time.monotonic()+8
 while len(times)<2:
  f=builder.n('scan',min=pos,max=pos,details=True,include_predictions=True);s=builder.check();pred=f.get('scan_predictions')or{}
  row=next((v for v in f['blocks']if v['pos']==pos),{})
  try:kind,props=block_state(row.get('state',''))
  except(ValueError,TypeError):kind,props=None,{}
  if(kind==ITEM and props==record['expected_properties'] and pred.get('complete')is True and pred.get('pending_count')==0
     and pred.get('pending_positions')==[] and inventory_counts(s)[ITEM]==before-1
     and(not times or s['time']>times[-1])):times.append(s['time'])
  assert time.monotonic()<end,'Original fence interaction retained; no repeated placement'
  time.sleep(.1)
 record.update(pending=False,observed_times=times,material_after=before-1);builder.save();return record
