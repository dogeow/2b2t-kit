"""Normally operate one unpowered north/south trader gate with real clearance."""
import time
from projection_completion import block_state

ITEM='minecraft:acacia_fence_gate'

def prepare(rows,entities,pos,uid,*,opening):
 row=rows.get(tuple(pos),{});kind,props=block_state(row.get('state',''))
 if(kind!=ITEM or props.get('facing')not in ('north','south')or props.get('in_wall')!='false'
    or props.get('powered')!='false'or props.get('open')not in ('true','false')):
  raise ValueError('Exact unpowered north/south trader gate required')
 if type(opening)is not bool or props['open']==str(opening).lower():
  raise ValueError('Gate is already in the requested state; do not repeat its interaction')
 who=next((v for v in entities if v.get('uuid')==uid),None)
 if(not who or who.get('type')!='minecraft:villager'or who.get('is_baby')is not False or who.get('health')!=20):
  raise ValueError('Exact healthy adult resident required')
 x,y,z=pos;low=[x,y,z+3/8];high=[x+1,y+1.5,z+5/8]
 if not opening:
  if who['bounds']['max'][2]>low[2]:raise ValueError('Resident has not cleared the front of the closing gate')
  for entity in entities:
   if entity.get('type')=='minecraft:item':continue
   box=entity['bounds']
   if all(box['max'][i]>low[i]and box['min'][i]<high[i]for i in range(3)):
    raise ValueError('Closing gate would intersect an entity')
 return {'before':row['state'],'after':row['state'].replace('open='+props['open'],'open='+str(opening).lower()),
         'collision_proxy':{'min':low,'max':high},'opening':opening,'resident_uuid':uid,'pos':pos}

def toggle(builder,pos,uid,*,opening):
 x,y,z=pos;a,rows=builder.scan([x-1,y-1,z-1],[x+1,y+2,z+1]);record=prepare(rows,a['scan_entities'],pos,uid,opening=opening);s=builder.check()
 if not opening:
  low=record['collision_proxy']['min'];high=record['collision_proxy']['max'];own={'min':[s['pos'][0]-.3,s['pos'][1],s['pos'][2]-.3],'max':[s['pos'][0]+.3,s['pos'][1]+1.8,s['pos'][2]+.3]}
  if all(own['max'][i]>low[i]and own['min'][i]<high[i]for i in range(3)):raise ValueError('Operator intersects closing gate')
 record['pending']=False;builder.book.setdefault('trader_gate_operations',[]).append(record);builder.save();builder.n('select_item',item='minecraft:netherite_sword')
 if not opening:
  fresh,fresh_rows=builder.scan([x-1,y-1,z-1],[x+1,y+2,z+1]);latest=prepare(fresh_rows,fresh['scan_entities'],pos,uid,opening=False)
  if latest['before']!=record['before']:raise ValueError('Gate changed during tool selection; no closing input')
  record['clearance_rechecked_after_selection']=True
 record['pending']=True;builder.save();r=builder.n('interact',pos=pos,face='north',expected_state=record['before'],expected_hand='minecraft:netherite_sword');record['request']=r['id'];builder.save();times=[];deadline=time.monotonic()+8
 while len(times)<2:
  frame=builder.n('scan',min=pos,max=pos,details=True,include_predictions=True);current=builder.check();rows={tuple(v['pos']):v for v in frame['blocks']};pred=frame.get('scan_predictions')or{}
  if(rows.get(tuple(pos),{}).get('state')==record['after']and pred.get('complete')is True and pred.get('pending_count')==0 and pred.get('pending_positions')==[] and(not times or current['time']>times[-1])):times.append(current['time'])
  else:times=[]
  if time.monotonic()>deadline:raise RuntimeError('Gate state unresolved; retain original interaction without replay')
  time.sleep(.1)
 record.update(pending=False,times=times);builder.save();return record
