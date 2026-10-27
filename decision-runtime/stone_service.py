"""Conserved recovery of one witnessed plain cobblestone service block."""
import time
from material_plan import inventory_counts
from bed_recovery_workspace import plain_recovery_space_ready
from block_recovery import pickup

def recover(builder,position,face,protected=(),*,pickup_pose=None,roof=False,item='minecraft:cobblestone'):
 if item not in ('minecraft:cobblestone','minecraft:cobbled_deepslate'):
  raise ValueError('Only witnessed plain service stone is supported')
 position=list(position)
 if position in [list(v)for v in protected]:raise ValueError('Quarantined service target')
 if any(r.get('pending')for r in builder.book.get('stone_service',[])):
  raise RuntimeError('Previous stone service remains unresolved')
 _,rows=builder.scan(position,position);expected='Block{'+item+'}';row=rows.get(tuple(position),{})
 if(row.get('state')!=expected or row.get('solid')is not True or row.get('fluid')is not False or row.get('block_entity')is not False):raise ValueError('Exact plain cobblestone required')
 if not plain_recovery_space_ready(builder.check(),item):raise RuntimeError('Stone recovery space unavailable; no mining')
 builder.n('select_item',item='minecraft:diamond_pickaxe');state=builder.check()
 if not plain_recovery_space_ready(state,item):raise RuntimeError('Stone recovery space changed; no mining')
 before=inventory_counts(state)[item];old_ids={e['uuid']for e in state.get('entities',[])}
 record={'position':position,'item':item,'pending':True,'before':before,'roof':roof};builder.book.setdefault('stone_service',[]).append(record);builder.save()
 reply=builder.n('mine_block',pos=position,face=face,expected_state=expected,seconds=12)
 if not(reply.get('server_confirmed')is True and type(reply.get('native_sequence'))is int and reply['native_sequence']>0 and reply.get('server_ack_sequence')==reply['native_sequence']):raise RuntimeError('Original stone mine lacks native ACK; no repeat')
 record.update(request=reply['id'],native_sequence=reply['native_sequence'],server_ack_sequence=reply['server_ack_sequence']);builder.save()
 if roof:builder.book.setdefault('open_roofs',[]).append(position);builder.save()
 if pickup_pose is not None and inventory_counts(builder.check())[item]!=before+1:builder.nav(pickup_pose)
 end=time.monotonic()+2
 while inventory_counts(builder.check())[item]==before and time.monotonic()<end:time.sleep(.1)
 if inventory_counts(builder.check())[item]!=before+1:pickup(builder,item,before,old_ids,position)
 if inventory_counts(builder.check())[item]!=before+1:raise RuntimeError('Original stone pickup unconfirmed')
 record.update(pending=False,after=before+1);builder.save();return record

def close_roof(builder,position):
 position=list(position)
 if position not in builder.book.get('open_roofs',[]):raise ValueError('No outstanding borrowed stone roof')
 _,rows=builder.scan([position[0]-1,position[1],position[2]-1],[position[0]+1,position[1],position[2]+1]);expected='Block{minecraft:cobblestone}'
 if tuple(position)in rows:raise RuntimeError('Borrowed roof target changed')
 for dx,dz,face in [(-1,0,'east'),(1,0,'west'),(0,-1,'south'),(0,1,'north')]:
  support=[position[0]+dx,position[1],position[2]+dz]
  if rows.get(tuple(support),{}).get('state')==expected:break
 else:raise RuntimeError('No witnessed original stone roof support')
 builder.place(position,support,face,item='minecraft:cobblestone',expected=expected)
 builder.book['open_roofs'].remove(position);builder.save()
