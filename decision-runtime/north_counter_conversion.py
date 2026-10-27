"""Bounded conversion of an untraded east library cell, retaining its original lectern."""
import json,time
from librarian_room import LibrarianRoom
from material_plan import inventory_counts
from projection_completion import block_state
from village_occupied_bed import wake_assigned
from closed_gate_geometry import admitted,collision
from village_public_roof import choose,leave
from kit_runtime.journal import write_json

def counter_columns(z,inward):
 if type(z)is not int or inward not in(-1,1):raise ValueError('Integer workpoint and north/south inward direction required')
 return tuple(z+n*inward for n in(1,2,3))

def convert(c,base,slot,open_roof,close_roof):
 room=LibrarianRoom.from_slot(slot);x,y,z=room.work;assert (slot['id'][0],y)in[('W',64),('E',65)]and room.floor_y==y
 uid=room.uid;front,inner,rear=counter_columns(z,room.inward);record={'slot':slot['id'],'pending':True,'stage':'initial_read_only_checks','old_bed':{'head':slot['bed_head'],'foot':slot['bed_foot']}};c.book.setdefault('conversions',[]).append(record);c.save();p=json.loads((base/'project-state.json').read_text());assert uid not in{v['villager_uuid']for v in[*p['locked_trades'].values(),*p['locked_optional_trades'].values()]};s=c.check();c.nav([s['pos'][0],85.2,s['pos'][2]]);c.nav([x+.5,85.2,s['pos'][2]]);c.nav([x+.5,85.2,rear+.5]);scene,rows=c.scan(*room.bounds());actor=room.actor(scene);foot,head=slot['bed_foot'],slot['bed_head'];assert rows[tuple(room.work)]['state']==room.lectern_state()and rows[(x,y+1,z)]['state']=='Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'and rows[(x,y+2,z)]['solid'];assert all(rows.get((bed[0],bed[1]+dy,bed[2]),{}).get('passable',True)for bed in[head,foot]for dy in[1,2]);assert 'part=foot'in rows[tuple(foot)]['state']and 'part=head'in rows[tuple(head)]['state'];bed_item=block_state(rows[tuple(foot)]['state'])[0];assert bed_item.endswith('_bed');record.update(bed_item=bed_item,bed_before=inventory_counts(s)[bed_item],slab_before=inventory_counts(s)['minecraft:dark_oak_slab']);c.save()
 roof=[x,y+3,rear];c.nav([x+.5,y+5.2,rear+.5]);open_roof(c,roof,'up',pickup_pose=[x+.5,y+.7,rear+.5]);c.nav([x+.5,y+.7,rear+.5]);close_roof(c,roof);c.nav([x+.5,y+.7,front+.5]);c.nav([x+.5,y+.1,front+.5]);wake_assigned(c,slot,bed_part='foot');scene,rows=c.scan(*room.bounds());state=rows[tuple(foot)]['state'];c.n('select_item',item='minecraft:diamond_axe');receipt=c.n('mine_block',pos=foot,face='up',expected_state=state,seconds=12);assert receipt['server_confirmed']and receipt['native_sequence']==receipt['server_ack_sequence'];record.update(stage='bed_removed_once',bed_request=receipt['id']);c.save()
 for zz in[rear+.5,front+.4]:c.n('walk',target=[x+.5,float(y),zz],arrival=.1,restore_flight=False,seconds=20)
 assert inventory_counts(c.check())[bed_item]==record['bed_before']+1;scene,rows=c.scan(*room.bounds());assert tuple(foot)not in rows and tuple(head)not in rows;record['bed_recovered']=True;c.save();cap_state=rows[(x,y+1,z)]['state'];c.n('select_item',item='minecraft:diamond_axe');receipt=c.n('mine_block',pos=[x,y+1,z],face='north'if room.inward==-1 else'south',expected_state=cap_state,seconds=12);assert receipt['server_confirmed']and receipt['native_sequence']==receipt['server_ack_sequence'];record.update(stage='old_cap_removed_original_lectern_retained',old_cap_request=receipt['id']);c.save();variants=['Block{minecraft:oak_trapdoor}[facing='+d+',half=top,open=false,powered=false,waterlogged=false]'for d in['north','south','east','west']];c.place([x,y+1,z],[x,y+2,z],'down',item='minecraft:oak_trapdoor',expected=variants[0],acceptable_states=variants);c.n('walk',target=[x+.5,float(y),front+.4],arrival=.1,restore_flight=False,seconds=15);c.n('walk',target=[x+.5,float(y),rear+.5],arrival=.1,restore_flight=False,seconds=20);record['stage']='wait_gate_actual_collision_clearance';c.save();gate=[x,y,inner];end=time.monotonic()+60;gate_frame=None
 while time.monotonic()<end:
  scene,rows=c.scan(*room.bounds())
  if admitted(scene,gate,uid,inward=room.inward):gate_frame=scene;break
  time.sleep(.5)
 record['gate_installed']=False
 if gate_frame is not None:place_gate(c,room,record,gate_frame,rows)
 return finish_conversion(c,base,slot,record,open_roof,close_roof)

def place_gate(c,room,record,scene,rows):
 x,y,z=room.work;uid=room.uid;front,inner,rear=counter_columns(z,room.inward);gate=[x,y,inner]
 if any('minecraft:wall_torch}'in v['state']for pos,v in rows.items()if pos[0]==x and pos[2]==rear):
  c.nav([x+.5,y+.1,inner+.5+.65*room.inward]);scene,rows=c.scan(*room.bounds())
 end=time.monotonic()+20
 while not admitted(scene,gate,uid,inward=room.inward):
  if time.monotonic()>=end:record['gate_installed']=False;record['gate_deferred']='occupied_after_safe_pose';c.save();return False
  time.sleep(.5);scene,rows=c.scan(*room.bounds())
 assert tuple(gate)not in rows and rows[(x,y-1,inner)]['solid']and rows[(x,y+3,inner)]['solid'];record.update(gate_preflight=scene,gate_collision=collision(gate),gate_use_pending=True);c.save();before=inventory_counts(c.check())['minecraft:oak_fence_gate'];c.n('select_item',item='minecraft:oak_fence_gate');receipt=c.n('interact',pos=[x,y-1,inner],face='up',expected_state=rows[(x,y-1,inner)]['state'],expected_hand='minecraft:oak_fence_gate');record['gate_use_request']=receipt['id'];c.save();end=time.monotonic()+10;stamps=[]
 while len(stamps)<2:
  frame=c.n('scan',min=gate,max=gate,details=True,include_predictions=True);state=c.check();row=frame['blocks'][0]if frame['blocks']else{};pred=frame['scan_predictions'];good=('minecraft:oak_fence_gate}'in row.get('state','')and any('facing='+d in row['state']for d in['north','south'])and 'open=false'in row['state']and 'powered=false'in row['state']and pred['complete']and pred['pending_count']==0 and inventory_counts(state)['minecraft:oak_fence_gate']==before-1)
  if good and(not stamps or state['time']>stamps[-1]):stamps.append(state['time'])
  assert time.monotonic()<end,'Original rear-gate use unconfirmed; no repeat';time.sleep(.1)
 record.update(gate_use_pending=False,gate_installed=True,gate_state=row['state'],gate_confirmed_frames=stamps);c.save()

def finish_conversion(c,base,slot,record,open_roof,close_roof):
 room=LibrarianRoom.from_slot(slot);x,y,z=room.work;front,inner,rear=counter_columns(z,room.inward);gate=[x,y,inner];roof=[x,y+3,rear]
 scene,lighting=c.scan([x,y,rear],[x,y+2,rear]);torch=any('minecraft:wall_torch}'in v['state']for v in lighting.values());mining_z=rear+.5
 c.nav([x+.5,y+(.7 if torch else .1),mining_z]);open_roof(c,roof,'down')
 c.nav([x+.5,y+5.2,rear+.5]);close_roof(c,roof);c.nav([x+.5,85.2,rear+.5]);scene,rows=c.scan([x-2,y-1,797811],[x+2,y+6,797811]);p=json.loads((base/'project-state.json').read_text());blocked={tuple(v['pos'])for v in p['protected_pending_excavation_targets']if v['world_session']==c.q.world and v.get('native_claim_not_cleared')};entry=choose(rows,x,y,blocked,low_x=760997 if slot['id'][0]=='W'else 761017,high_x=761015 if slot['id'][0]=='W'else 761033);assert entry is not None,'No undecorated public roof entry; all lights preserved';c.nav([entry[0]+.5,85.2,entry[2]+.5]);c.nav([entry[0]+.5,y+5.2,entry[2]+.5]);open_roof(c,entry,'up',pickup_pose=[entry[0]+.5,y+.1,entry[2]+.5]);c.nav([entry[0]+.5,y+.1,entry[2]+.5]);close_roof(c,entry);c.n('walk',target=[x+.5,float(y),797811.5],arrival=.1,restore_flight=False,seconds=20);c.n('walk',target=[x+.5,float(y),z+.5-room.inward],arrival=.1,restore_flight=False,seconds=15);end=time.monotonic()+5
 while inventory_counts(c.check())['minecraft:dark_oak_slab']!=record['slab_before']+1:assert time.monotonic()<end,'Original slab pickup unconfirmed; no false credit';time.sleep(.1)
 scene,rows=c.scan(*room.bounds());actor=room.actor(scene);assert rows[tuple(room.work)]['state']==room.lectern_state();record.update(pending=False,stage='cap_and_bed_conversion_complete',old_slab_recovered=True,original_lectern_untouched=True,actual_actor=actor,public_roof_entry=entry);c.save();layout=json.loads((base/'layout-plan.json').read_text());row=next(v for v in layout['slots']if v['id']==slot['id']);row.update(original_bed_coordinates=record['old_bed'],bed_head=None,bed_foot=None,bed_present=False,bed_removed=True,bedless_counter=True,counter_configuration='closed_top_trapdoor_and_full_header',front_barrier_pos=[x,y+1,z],trade_window_clearance=1.8125,access_mode='public_or_front_roof_only_old_bed_roof_blocked_by_gate',near_work_gate_verified=record['gate_installed'],near_work_gate=gate if record['gate_installed']else None,counter_conversion_proof=str(c.path.relative_to(base)));write_json(base/'layout-plan.json',layout);leave(c,entry,y,open_roof,close_roof);return record
