"""Recover one paid librarian's bed, preserving its counter, resident and materials."""
from pathlib import Path
import json
from librarian_room import LibrarianRoom
from village_public_roof import choose,leave
from village_occupied_bed import wake_assigned
from village_adult_enclosure import audit
from villager_trading import book_matches
from material_plan import inventory_counts
from librarian_workflow import seed_cycles
from kit_runtime.journal import write_json

def plan(slot,keeper,protected,world):
 room=LibrarianRoom.from_slot(slot)
 if room.work[1]!=room.floor_y:raise ValueError('Raised workpoints require their own verified sightline plan')
 if keeper.get('villager_uuid')!=room.uid or keeper.get('server_history_verified')is not True or keeper.get('trader_xp',0)<=0:raise ValueError('Exact paid supplier history required')
 foot,head=slot.get('bed_foot'),slot.get('bed_head');roof=room.private_roof()
 if not isinstance(foot,list)or not isinstance(head,list)or len(foot)!=3 or len(head)!=3:raise ValueError('Actual assigned bed pair required')
 if any(p[0]!=room.work[0]or p[1]!=room.floor_y or not 1<=(p[2]-room.work[2])*room.inward<=room.interior_depth for p in [foot,head])or abs(foot[2]-head[2])!=1:raise ValueError('Bed must stay inside the assigned private room')
 if any(v.get('world_session')==world and v.get('native_claim_not_cleared')and v.get('pos')in [head,foot,roof]for v in protected):raise ValueError('Bed service cannot touch quarantined points')
 return room,foot,head,roof

from bed_recovery_workspace import recovery_space_ready

def recover(c,base,seed,slot_id,enchantment,open_roof,close_roof):
 B=Path(base);project=json.load(open(B/'project-state.json'));layout=json.load(open(B/'layout-plan.json'));slot=next(v for v in layout['slots']if v['id']==slot_id);keeper=project['locked_trades'].get(enchantment)or project['locked_optional_trades'].get(enchantment);room,foot,head,roof=plan(slot,keeper or{},project['protected_pending_excavation_targets'],c.q.world);x,y,z=room.work;state=c.check()
 if not recovery_space_ready(state):
  from material_stack_consolidation import prepare_fetch
  from queued_village_owner import QueuedVillageOwner
  c.book['preflight_inventory_merge']=prepare_fetch(QueuedVillageOwner(c),['minecraft:white_bed']);c.save()
 if not recovery_space_ready(c.check()):raise RuntimeError('Two inventory slots required before any bed or roof mining')
 before=inventory_counts(c.check())
 book=c.book;book.update(cycles=[],last_cycles=seed_cycles(seed,c.q.world,layout['slots']),open_roofs=[],keeper_uuid=room.uid,old_bed={'head':head,'foot':foot},original_lectern_untouched=True,no_new_trade=True);c.save();scene,rows=c.scan(*room.bounds());room.actor(scene);assert rows[tuple(room.work)]['state']==room.lectern_state()
 for bed in [head,foot]:
  assert 'minecraft:white_bed}'in rows[tuple(bed)]['state']and rows[(bed[0],bed[1]-1,bed[2])]['solid']and not rows[(bed[0],bed[1]-1,bed[2])]['fluid']
  assert all(rows.get((bed[0],bed[1]+dy,bed[2]),{}).get('passable',True)for dy in [1,2])
 s=c.check();xx=int(s['pos'][0]);floor=64 if xx<761015 else 65;_,rows=c.scan([xx-2,floor-1,797811],[xx+2,floor+6,797811]);blocked={tuple(v['pos'])for v in project['protected_pending_excavation_targets']if v.get('world_session')==c.q.world and v.get('native_claim_not_cleared')};entry=choose(rows,xx,floor,blocked,low_x=760997 if floor==64 else 761017,high_x=761015 if floor==64 else 761033);assert entry
 leave(c,entry,floor,open_roof,close_roof);c.nav([entry[0]+.5,85.2,entry[2]+.5]);c.nav([x+.5,85.2,797811.5]);c.nav([x+.5,85.2,roof[2]+.5]);c.nav([x+.5,room.floor_y+5.2,roof[2]+.5]);open_roof(c,roof,'up',pickup_pose=[x+.5,room.floor_y+.1,roof[2]+.5]);c.nav([x+.5,room.floor_y+.1,roof[2]+.5]);close_roof(c,roof);wake_assigned(c,slot,bed_part='foot');scene,rows=c.scan(*room.bounds());room.actor(scene);state=rows[tuple(foot)]['state'];assert 'part=foot'in state;c.n('select_item',item='minecraft:diamond_axe');book['stage']='one_bed_mine_pending';c.save();r=c.n('mine_block',pos=foot,face='up',expected_state=state,seconds=12);assert r['server_confirmed']and r['native_sequence']==r['server_ack_sequence'];book.update(stage='one_bed_mined_once',bed_mine_request=r['id'],native_sequence=r['native_sequence'],server_ack_sequence=r['server_ack_sequence']);c.save()
 for zz in [foot[2]+.5,z+.5+room.inward]:
  if inventory_counts(c.check())['minecraft:white_bed']==before['minecraft:white_bed']+1:break
  c.n('walk',target=[x+.5,float(room.floor_y),zz],arrival=.1,restore_flight=False,seconds=20)
 assert inventory_counts(c.check())['minecraft:white_bed']==before['minecraft:white_bed']+1,'Original bed pickup unconfirmed; do not remine';scene,rows=c.scan(*room.bounds());assert tuple(foot)not in rows and tuple(head)not in rows and rows[tuple(room.work)]['state']==room.lectern_state();actor=room.actor(scene);shell=audit(rows,front=list(room.work),floor=room.floor_y,inward=room.inward,depth=room.interior_depth);assert shell['verified'];book.update(bed_recovered=True,enclosure=shell);c.save();c.n('select_item',item='minecraft:netherite_sword');reply=c.send('merchant_open',actor=actor,seconds=35);m=reply['menu']['merchant'];assert m['villager_uuid']==room.uid and m['trader_xp']>0 and any(book_matches(o['result'],enchantment,keeper['level'])for o in m['offers']);command=json.load(open(c.out/'command.json'));book['original_keeper_quote_result']=str((c.out/command['id']/'result.json').relative_to(B));book['merchant']=m;c.save();c.q.native('close_menu');c.nav([x+.5,room.floor_y+.1,roof[2]+.5]);open_roof(c,roof,'down');c.nav([x+.5,room.floor_y+5.2,roof[2]+.5]);close_roof(c,roof);c.nav([x+.5,85.2,roof[2]+.5]);c.nav([entry[0]+.5,85.2,entry[2]+.5]);c.nav([entry[0]+.5,floor+5.2,entry[2]+.5]);open_roof(c,entry,'up',pickup_pose=[entry[0]+.5,floor+.1,entry[2]+.5]);c.nav([entry[0]+.5,floor+.1,entry[2]+.5]);close_roof(c,entry);expected=before.copy();expected['minecraft:white_bed']+=1;assert +expected==inventory_counts(c.check())and not book['open_roofs'];layout=json.load(open(B/'layout-plan.json'));slot=next(v for v in layout['slots']if v['id']==slot_id);slot.update(original_bed_coordinates=book['old_bed'],bed_head=None,bed_foot=None,bed_present=False,bed_removed=True,bedless_counter=True,bed_recovery_proof=str(c.path.relative_to(B)));write_json(B/'layout-plan.json',layout);book.update(complete=True,pending=None,stage='paid_keeper_bed_recovered_roofs_restored',inventory_after=dict(inventory_counts(c.check())),goal_complete=False);c.save();project=json.load(open(B/'project-state.json'));project.setdefault('bedless_trade_pilots',{})[slot_id]={'proof':str(c.path.relative_to(B)),'bed_recovered':True,'original_lectern_and_keeper_preserved':True,'original_maximum_quote_reverified':True,'restock_live_verification_pending':True};write_json(B/'project-state.json',project);return book
