"""Reusable, checkpointed librarian trading loop over the retained native owner.

This module does not acquire a Minecraft lease. Unknown receipts, health,
manual takeover, current containment and native useful-book policy remain guarded.
"""
from pathlib import Path
from copy import deepcopy
from librarian_quote_observation import unwanted_quote_observation
import json,time,math
from librarian_room import LibrarianRoom,walk_public as walk_public_route
from librarian_reset_enclosure import require_enclosed_reset
from librarian_public_quote import open_when_reachable
from librarian_duplicate_reset import reset_allowed
from villager_events import wait_for_frame
from material_plan import inventory_counts
from kit_runtime.journal import write_json
from village_keeper_registration import register
from librarian_round_robin import choose_ready,keeper_refresh_key,wake_paid_keeper_candidates


def seed_cycles(proof,world,layout):
    from held_airlock_return import require_restored
    require_restored(proof)
    if(proof.get('complete')is not True or proof.get('world_session')!=world or proof.get('pending')
       or proof.get('open_roofs')or any(v.get('pending')for v in proof.get('cycles',[]))
       or any(v.get('pending')for v in proof.get('public_quote_admissions',[]))):
        raise RuntimeError('Previous workflow is not a completely settled same-world receipt; no resume')
    records=deepcopy(proof.get('last_cycles')or{})
    for row in proof.get('cycles',[]):records[row['slot']]=deepcopy(row)
    return validate_cycles(records,world,layout)

def validate_cycles(records,world,layout):
    records=deepcopy(records)
    slots={v['id']:v for v in layout}
    for name,row in records.items():
        seq=row.get('native_sequence');admission=row.get('admission')or{}
        if(name not in slots or row.get('pending')is not False or row.get('station_restored')is not True
           or type(seq)is not int or seq<=0 or row.get('server_ack_sequence')!=seq
           or admission.get('world_session')!=world or admission.get('villager_uuid')!=slots[name]['occupant_uuid']):
            raise RuntimeError('Previous cycle lacks exact resident, native ACK or restored workstation')
    return records


def priority_quote_changed(seed, reply, slot):
    """Only the same untraded resident's owned current-world quote retires a priority."""
    from villager_trading import book_matches
    merchant=(reply.get('menu')or{}).get('merchant')or{}
    if (seed.get('complete')is not True or seed.get('pending') or seed.get('open_roofs')
        or seed.get('stop_reason')!='preserved_wanted_quote_changed'
        or seed.get('priority_slot')!=slot['id'] or not seed.get('priority_enchantment')
        or reply.get('world_session')!=seed.get('world_session')
        or merchant.get('protocol')!=1 or merchant.get('owned')is not True
        or merchant.get('villager_uuid')!=slot['occupant_uuid']
        or merchant.get('trader_xp')!=0 or not merchant.get('offers')):
        raise RuntimeError('No exact owned current-world quote proves the priority obsolete')
    if any(book_matches(o['result'],seed['priority_enchantment'],seed['priority_level'])for o in merchant['offers']):
        raise RuntimeError('Wanted quote still exists; retain its priority')
    return True


def wake_sleeping_candidates(blocked,sleeping,flags):
    """A pure sleeping observation may be reconsidered only after a fresh awake flag."""
    awakened=[]
    for slot,keeper in list(sleeping.items()):
        if keeper in flags and flags[keeper].get('sleeping')is False:
            blocked.discard(slot);sleeping.pop(slot);awakened.append(slot)
    return awakened


def wake_reachable_candidates(blocked,deferred,actors,flags,slots,now,counts):
    """Reconsider only a visibly moved, awake untraded resident; never replay a request."""
    awakened=[]
    for name,row in list(deferred.items()):
        slot=slots.get(name);actor=actors.get(row['uuid']);flag=flags.get(row['uuid'])
        if counts.get(name,0)>=3:deferred.pop(name);continue
        if not slot or not actor or not flag or flag.get('sleeping')is not False:continue
        job=actor.get('villager')or{};position=actor.get('pos');prior=row.get('pos')
        if (job.get('profession')!='minecraft:librarian'or job.get('entity_xp')!=0
            or now-row['deferred_at']<20 or counts.get(name,0)>=3
            or not isinstance(position,list)or not isinstance(prior,list)
            or len(position)!=3 or len(prior)!=3):continue
        room=LibrarianRoom.from_slot(slot);x,y,z=room.work
        if math.dist(position,prior)<.35 or math.dist(position,[x+.5,float(y),z+.5])>=1.25:continue
        blocked.discard(name);deferred.pop(name);counts[name]=counts.get(name,0)+1;awakened.append(name)
    return awakened




def keeper_flag_after_approach(keeper,walk,frame,*,wake=None):
    """Load the exact supplier first; an optional witnessed bed wake is never retried."""
    walk(keeper)
    flags=[v for v in frame()['villagers']if v['uuid']==keeper.uid]
    if len(flags)==1 and flags[0].get('sleeping')is True and wake is not None:
        wake()
        flags=[v for v in frame()['villagers']if v['uuid']==keeper.uid]
    return flags[0]if len(flags)==1 else None


def run(c,base,seed,stop_marker,*,max_cycles=40):
    if max_cycles is not None and(type(max_cycles)is not int or not 1<=max_cycles<=80):raise ValueError('Bounded journal segment required')
    B=Path(base);N=c.out;R=c.root;stop_marker=Path(stop_marker);b=c.book
    layout=json.load(open(B/'layout-plan.json'))['slots']
    last_cycle=seed_cycles(seed,c.q.world,layout)
    slots=[v for v in layout if (v.get('near_work_gate_verified')is True or v.get('bedless_enclosure_verified')is True or v.get('public_reset_enclosure_verified')is True)and v['id'][0]in'WE']
    if not slots:raise RuntimeError('No verified prepared library cells')
    metrics={'claim_wait_seconds':0.,'supplier_wait_seconds':0.,'evidence_read_seconds':0.}
    b.update(open_roofs=[],cycles=[],quotes=[],new_locked=[],normal_health_guard=True,last_cycles=last_cycle,metrics=metrics,workflow_version=1);c.save()
    last_used={};blocked=set();sleeping_sources={};reach_deferrals={};reach_counts={};keeper_deferrals={};keeper_counts={};slot_lookup={v['id']:v for v in slots};room=None;preferred=seed.get('priority_slot');b["sleeping_source_deferrals"]=sleeping_sources;b['reach_deferrals']=reach_deferrals;b['reach_reactivation_counts']=reach_counts;b['paid_keeper_deferrals']=keeper_deferrals;b['paid_keeper_reactivation_counts']=keeper_counts
    for key in('priority_slot','priority_enchantment','priority_level','preserved_wanted_quote'):
        if key in seed:b[key]=deepcopy(seed[key])
    c.save()
    def walk_public(destination):walk_public_route(c,destination)
    def frame_now():
        start=time.monotonic()
        try:return wait_for_frame(R,c.check)
        finally:metrics['evidence_read_seconds']+=time.monotonic()-start
    native_attestations={}
    def refresh_native_keeper(name):
     from villager_trading import book_matches,body_distance_from_eye
     p=json.load(open(B/'project-state.json'));kept=p['locked_trades'].get(name)or p['locked_optional_trades'].get(name)
     if not kept:return False
     keeper_slot=next(v for v in json.load(open(B/'layout-plan.json'))['slots']if v['occupant_uuid']==kept['villager_uuid']);keeper=LibrarianRoom.from_slot(keeper_slot)
     from village_occupied_bed import wake_assigned
     wake=(lambda:wake_assigned(c,keeper_slot,bed_part='foot',bed_face='up'))if keeper_slot.get('bed_head')and keeper_slot.get('bed_foot')else None
     flag=keeper_flag_after_approach(keeper,walk_public,frame_now,wake=wake)
     if flag is None:
      b.setdefault('unobserved_keeper_after_approach',[]).append({'slot':slot['id'],'keeper_uuid':keeper.uid});c.save();walk_public(room);return False
     if flag['sleeping']:
      sleeping_sources[slot['id']]=keeper.uid;walk_public(room);return False
     # Raised lecterns occlude the floor-height eye. Reuse the verified public
     # head-gallery pose, keeping the body 5 mm outside the counter block.
     raised=keeper.work[1]>keeper.floor_y
     if raised:c.nav(keeper.public_trade_pose())
     def lower_public_pose():
      if raised:c.nav([keeper.work[0]+.5,keeper.floor_y+.1,797811.5])
     scene,rows=c.scan(*keeper.bounds());actor=keeper.actor(scene);s=c.check();eye=[s['pos'][0],s['pos'][1]+1.62,s['pos'][2]]
     if body_distance_from_eye(actor,eye)>2.95 and not raised:
      pose=keeper.public_trade_pose();pose[1]=float(keeper.floor_y);target_eye=[pose[0],pose[1]+1.62,pose[2]]
      if body_distance_from_eye(actor,target_eye)<=2.95:
       keeper.require_caps(rows);c.n('walk',target=pose,arrival=.04,restore_flight=False,seconds=15);scene,_=c.scan(*keeper.bounds());actor=keeper.actor(scene);s=c.check();eye=[s['pos'][0],s['pos'][1]+1.62,s['pos'][2]];b.setdefault('paid_keeper_window_approaches',[]).append({'keeper':keeper.uid,'actual_eye_distance':body_distance_from_eye(actor,eye),'pose':s['pos']});c.save()
     if body_distance_from_eye(actor,eye)>2.95:lower_public_pose();walk_public(room);return False
     c.n('select_item',item='minecraft:netherite_sword')
     try:reply=c.send('merchant_open',actor=actor,seconds=35)
     except RuntimeError:
      c.q.observe_merchant_reach_refusal();lower_public_pose();walk_public(room);return False
     m=reply['menu']['merchant'];assert m['villager_uuid']==keeper.uid and m['trader_xp']>0 and any(book_matches(o['result'],name,kept['level'])for o in m['offers']);command=json.load(open(N/'command.json'));path=N/command['id']/'result.json';cert=N/(name.split(':')[1]+'-existing-native-'+m['opening_request_id']+'.json');write_json(cert,{'complete':True,'pending':None,'open_roofs':[],'world_session':c.q.world,'keeper_uuid':keeper.uid,'merchant':m,'immutable_quote_result':str(path.relative_to(B)),'original_lock_proof':kept['proof'],'no_new_trade':True});c.q.native('close_menu');p=json.load(open(B/'project-state.json'));p['confirmed_duplicate_keepers'][name]={'proof':str(cert.relative_to(B))};write_json(B/'project-state.json',p);native_attestations[name]=reply;lower_public_pose();b.setdefault('keeper_rechecks',[]).append({'name':name,'proof':str(cert.relative_to(B)),'time':reply['time']});c.save();walk_public(room);return True

    def awake():return not next(v for v in frame_now()['villagers']if v['uuid']==uid)['sleeping']
    def actor_status():return next(v for v in c.check()['loaded_villagers']['villagers']if v['uuid']==uid)
    last_report=0;wait_started=None;wait_key='claim_wait_seconds';started_run=time.monotonic()
    while max_cycles is None or len(b['cycles'])<max_cycles:
     if stop_marker.exists():b['stop_reason']='cooperative_stop_between_fully_restored_cycles';break
     frame=frame_now();s=c.check();p=json.load(open(B/'project-state.json'));kept={v['villager_uuid']for v in [*p['locked_trades'].values(),*p['locked_optional_trades'].values()]};actors={v['uuid']:v for v in s['loaded_villagers']['villagers']};flags={v['uuid']:v for v in frame['villagers']};ready=[]
     wake_sleeping_candidates(blocked,sleeping_sources,flags)
     keeper_ready=wake_paid_keeper_candidates(blocked,keeper_deferrals,actors,flags,time.monotonic(),keeper_counts,b.setdefault('native_keeper_refresh_attempts',{}))
     if keeper_ready:b.setdefault('paid_keeper_reactivations',[]).append({'slots':keeper_ready,'time':s['time']});c.save()
     reactivated=wake_reachable_candidates(blocked,reach_deferrals,actors,flags,slot_lookup,time.monotonic(),reach_counts)
     if reactivated:b.setdefault('reach_reactivations',[]).append({'slots':reactivated,'time':s['time']});c.save()
     for candidate in slots:
      r=LibrarianRoom.from_slot(candidate);actor=actors.get(r.uid);flag=flags.get(r.uid)
      if candidate['id']in blocked or r.uid in kept or not actor or not flag:continue
      if not flag['sleeping']and actor['villager']['profession']=='minecraft:librarian'and actor['villager']['entity_xp']==0 and math.dist(actor['pos'],[r.work[0]+.5,float(r.work[1]),r.work[2]+.5])<1.65:ready.append(candidate)
     if not any(k not in p['locked_trades']for k in p['enchantment_targets']):b['stop_reason']='required_enchantments_ready';break
     if seed.get('priority_enchantment')and seed['priority_enchantment']in p['locked_trades']:preferred=None
     if preferred and any(v['id']==preferred and v['occupant_uuid']not in kept for v in slots):ready=[v for v in ready if v['id']==preferred]
     active=[v for v in slots if v['occupant_uuid']not in kept]
     if active and all(v['id']in blocked for v in active)and not sleeping_sources and not reach_deferrals and not keeper_deferrals:b['stop_reason']='all_remaining_candidates_require_keeper_recheck_or_reach_route';break
     if not active:b['stop_reason']='all_prepared_candidates_locked';break
     if not ready:
      new_wait_key='supplier_wait_seconds'if active and all(v['id']in blocked for v in active)else'claim_wait_seconds'
      if wait_started is not None and wait_key!=new_wait_key:metrics[wait_key]+=time.monotonic()-wait_started;wait_started=None
      if wait_started is None:wait_started=time.monotonic();wait_key=new_wait_key;b['wait_started_at']=time.time();b['wait_kind']=wait_key
      if time.monotonic()-last_report>=15:b.update(phase='waiting_for_any_actual_reclaimed_resident',ready_count=0);c.save();print('ROUND_ROBIN_WAIT',len(b['cycles']),flush=True);last_report=time.monotonic()
      time.sleep(.5);continue
     if wait_started is not None:metrics[wait_key]+=time.monotonic()-wait_started;wait_started=None;b.pop('wait_started_at',None)
     visit_started=time.monotonic();visit_action_start=len(c.q.efficiency.rows)
     slot=choose_ready(ready,last_used,preferred);preferred=None;last_used[slot['id']]=time.monotonic();room=LibrarianRoom.from_slot(slot);uid=room.uid;x,y,z=room.work;gate=[x,y,z+2*room.inward];walk_public(room)
     print('ROUND_ROBIN_SELECTED',slot['id'],flush=True)
     reply=open_when_reachable(c,room,awake,seconds=8,distance_limit=2.95)
     if not reply:
      blocked.add(slot['id']);current_actor=next((v for v in c.check()['loaded_villagers']['villagers']if v['uuid']==uid),None)
      if current_actor:reach_deferrals[slot['id']]={'uuid':uid,'pos':deepcopy(current_actor['pos']),'deferred_at':time.monotonic()};c.save()
      continue
     m=reply['menu']['merchant'];p=json.load(open(B/'project-state.json'))
     if slot['id']==seed.get('priority_slot')and seed.get('priority_enchantment')not in p['locked_trades']:
      from villager_trading import book_matches
      if not any(book_matches(o['result'],seed['priority_enchantment'],seed['priority_level'])for o in m['offers']):
       c.q.native('close_menu');b['stop_reason']='preserved_wanted_quote_changed';break
     targets={k:v for k,v in p['enchantment_targets'].items()if k not in p['locked_trades']};targets.update({k:v for k,v in p['optional_enchantment_targets'].items()if k not in p['locked_optional_trades']});result=unwanted_quote_observation(m,targets,c.check(),expected_uuid=uid,expected_world=c.q.world)
     if result is None:result=c.send('merchant_lock_wanted',targets=targets,max_emeralds=64,max_paper=48,keep={'minecraft:book':1},seconds=90)
     b['quotes'].append({'merchant':m,'result':result});c.save();print('PRIVATE_CURRENT_BOOK',[(o['result'].get('stored_enchantments'),o['cost_a']['count'])for o in m['offers']],flush=True)
     if result.get('locked'):
      cmd=json.load(open(N/'command.json'));certificate=register(B,N,slot,result,N/cmd['id']/'result.json',slot['id']+'-keeper-'+cmd['id']+'.json',c.q.world);b['new_locked'].append(certificate);c.save()
     if c.q.status()['screen']=='MerchantScreen':c.q.native('close_menu')
     if result.get('locked'):continue
     if result.get('waiting_for_payment')or result.get('waiting_for_output_space'):b['stop_reason']='payment_attention';break
     from villager_trading import TARGETS as NATIVE_KEEPERS,book_matches
     maxima={**p['enchantment_targets'],**p['optional_enchantment_targets']};relevant=[name for name,level in maxima.items()if any(book_matches(o['result'],name,level)for o in m['offers'])];proofs={k:json.load(open(B/p['confirmed_duplicate_keepers'][k]['proof']))for k in relevant if k in p['confirmed_duplicate_keepers']};native_names=[name for name in relevant if name in NATIVE_KEEPERS]
     from keeper_history_scope import load as load_keeper_history
     observed_state=c.check();history_scopes={name:load_keeper_history(B,proofs[name],observed_state)for name in relevant if name in proofs and name not in NATIVE_KEEPERS}
     b.setdefault('reused_keeper_history',{}).update({name:value for name,value in history_scopes.items()if value is not None});c.save()
     if not reset_allowed(m,p['enchantment_targets'],{**p['locked_trades'],**p['locked_optional_trades']},proofs,observed_state,native_attestations=native_attestations,keeper_history_scopes=history_scopes):
      attempts=b.setdefault('native_keeper_refresh_attempts',{});name=relevant[0]if len(relevant)==1 else None
      key=keeper_refresh_key(slot['id'],name,last_cycle.get(slot['id']))if name else None
      if name and attempts.get(key,0)<2:
       attempts[key]=attempts.get(key,0)+1;c.save()
       if refresh_native_keeper(name):preferred=slot['id'];continue
       if slot['id']in sleeping_sources:attempts[key]-=1
      blocked.add(slot['id']);b.setdefault('blocked_duplicates',[]).append({'slot':slot['id'],'relevant':relevant})
      if name and slot['id']not in sleeping_sources:
       kept=p['locked_trades'].get(name)or p['locked_optional_trades'].get(name)
       if kept:
        keeper_slot=next(v for v in layout if v['occupant_uuid']==kept['villager_uuid']);keeper_room=LibrarianRoom.from_slot(keeper_slot);current=next((v for v in c.check()['loaded_villagers']['villagers']if v['uuid']==keeper_room.uid),None)
        keeper_deferrals[slot['id']]={'uuid':keeper_room.uid,'work':list(keeper_room.work),'pos':deepcopy(current['pos'])if current else None,'deferred_at':time.monotonic(),'refresh_key':key,'paid_history_verified':kept.get('server_history_verified')is True and kept.get('trader_xp',0)>0}
      c.save();continue

     from librarian_repeat_quote import fresh_generation
     if not fresh_generation(m,last_cycle.get(slot['id'])):b['stop_reason']='unproved_generation_not_remined';break
     scene,rows=c.scan(*room.bounds());
     if slot.get('near_work_gate_verified'):assert 'open=false'in rows[tuple(gate)]['state']
     admission=require_enclosed_reset(scene,room);a=room.actor(scene)
     if math.dist(a['pos'],[x+.5,float(y),z+.5])>=1.75:continue
     before=inventory_counts(c.check())['minecraft:lectern'];old_ids={v['uuid']for v in c.check().get('entities',[])};entry={'slot':slot['id'],'pending':True,'before':before,'old_fingerprint':m['offers_fingerprint'],'old_opening':m['opening_request_id'],'admission':admission};b['cycles'].append(entry);c.save();
     if c.check().get('hand',{}).get('item')!='minecraft:diamond_axe':c.n('select_item',item='minecraft:diamond_axe')
     started=time.monotonic();r=c.n('mine_block',pos=list(room.work),face='south'if c.check()['pos'][2]>z+.5 else'north',expected_state=room.lectern_state(),reset_empty_lectern=True,expected_villager_uuid=uid,expected_quote_opening=m['opening_request_id'],expected_offers_fingerprint=m['offers_fingerprint'],allow_verified_duplicate_reset=bool(native_names),seconds=12);assert r['server_confirmed']and r['native_sequence']==r['server_ack_sequence'];entry.update(mine_request=r['id'],native_sequence=r['native_sequence'],server_ack_sequence=r['server_ack_sequence']);c.save()
     if inventory_counts(c.check())['minecraft:lectern']!=before+1:
      for waypoint in[[x+.5,float(y),z+.5],[x+.5,float(y),z+.5-room.inward],[x+.5,float(y),z+.5+room.inward*.9]]:
       c.n('walk',target=waypoint,arrival=.1,restore_flight=False,seconds=15);wait_until=time.monotonic()+1.5
       while inventory_counts(c.check())['minecraft:lectern']!=before+1 and time.monotonic()<wait_until:time.sleep(.1)
       if inventory_counts(c.check())['minecraft:lectern']==before+1:break
     assert inventory_counts(c.check())['minecraft:lectern']==before+1,'Ground passage pickup missing; no collector or mine replay'
     c.n('walk',target=[x+.5,float(y),z+.5-room.inward],arrival=.1,restore_flight=False,seconds=15)
     end=time.monotonic()+5;released=False
     while time.monotonic()<end:
      if actor_status()['villager']['profession']=='minecraft:none':released=True;break
      time.sleep(.1)
     c.place(list(room.work),[x,y-1,z],'up',item='minecraft:lectern',expected=room.lectern_state());entry.update(pending=False,station_restored=True,unemployment_observed=released,cycle_seconds=time.monotonic()-started,candidate_seconds=time.monotonic()-visit_started,candidate_commands=len(c.q.efficiency.rows)-visit_action_start);last_fingerprint=m['offers_fingerprint'];c.save();print('PRIVATE_RESET_AND_PRINT_CONFIRMED',len(b['cycles']),entry['cycle_seconds'],released,flush=True)
     if not released:b['stop_reason']='original_job_release_not_seen_station_restored';break
     last_cycle[slot['id']]=entry;b['last_cycles']=last_cycle;c.save()
    if wait_started is not None:metrics[wait_key]+=time.monotonic()-wait_started;b.pop('wait_started_at',None)
    metrics['run_seconds']=time.monotonic()-started_run
    b.setdefault('stop_reason','segment_limit')
    from held_airlock_return import require_restored
    require_restored(b)
    assert not b['open_roofs'];b.update(complete=True,phase='workflow_segment_finished',inventory_after=dict(inventory_counts(c.check())),goal_complete=False);c.save();print('BOUNDED_PRIVATE_BATCH_FINISHED',len(b['cycles']),b['new_locked'],b.get('stop_reason'),flush=True)
    return b
