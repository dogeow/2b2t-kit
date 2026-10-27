"""Reconcile only a strictly proved zero-proposal interval, preserving its original receipt."""
from copy import deepcopy
import json
from pathlib import Path
from librarian_room import LibrarianRoom
from material_plan import inventory_counts

def restore_zero_proposal(builder,base,source):
    base=Path(base);out=builder.out;book=builder.book;original=json.load(open(source));command=json.load(open(out/'command.json'))
    if(command.get('op')!='professional_print'or (original.get('pending')or{}).get('op')!='professional_print'
       or original.get('world_session')!=builder.q.world or original.get('open_roofs')):raise RuntimeError('No exact same-world stopped printer')
    pending=[v for v in original.get('cycles',[])if v.get('pending')]
    transactions=[v for v in original.get('verified_workstation_placements',[])if v.get('pending')]
    if len(pending)!=1 or len(transactions)!=1:raise RuntimeError('Recovery needs one exact pending original cycle')
    cycle=pending[0];tx=transactions[0];slot=next(v for v in json.load(open(base/'layout-plan.json'))['slots']if v['id']==cycle['slot']);room=LibrarianRoom.from_slot(slot)
    if(tx['position']!=list(room.work)or cycle['native_sequence']!=cycle['server_ack_sequence']or cycle['native_sequence']<=0
       or cycle['admission']['villager_uuid']!=room.uid):raise RuntimeError('Original mine/placement scope mismatch')
    terminal=json.load(open(out/command['id']/'result.json'))
    # This observer accepts only conserved inventory, zero proposals, no outstanding
    # server confirmation and the exact original lease/revision. It sends a snapshot only.
    observed=builder.q.observe_zero_proposal_printer()
    book.update(original_source=str(Path(source).relative_to(base)),original_command=command,zero_proposal_observation=observed['id'],old_placement_credit=0,cycles=[],open_roofs=[]);builder.save()
    builder.n('projection_batch_clear',placement_key=terminal['placement_key'])
    frame=builder.n('scan',min=list(room.work),max=list(room.work),details=True,include_predictions=True)
    if frame['blocks']or not frame['scan_predictions']['complete']or frame['scan_predictions']['pending_count']!=0:raise RuntimeError('Target is not prediction-free air; no replacement input')
    if inventory_counts(builder.check())['minecraft:lectern']!=tx['material_before']:raise RuntimeError('Original carried lectern conservation changed')
    actor=next(v for v in builder.check()['loaded_villagers']['villagers']if v['uuid']==room.uid);released=actor['villager']['profession']=='minecraft:none'
    x,y,z=room.work;pose=[x+.5,y+.3,z+.5-room.inward*2]
    reposition=getattr(builder,'reposition_zero_proposal_print',None)
    used_ground_fallback=reposition(room)if reposition is not None else False
    if not used_ground_fallback:builder.nav(pose)
    builder.place(list(room.work),[x,y-1,z],'up',item='minecraft:lectern',expected=room.lectern_state())
    if inventory_counts(builder.check())['minecraft:lectern']!=cycle['before']:raise RuntimeError('Restored workstation lacks material conservation')
    if used_ground_fallback:
        from librarian_room import walk_public
        walk_public(builder,room)
    else:builder.n('walk',target=[x+.5,float(y),z+.5-room.inward],arrival=.1,restore_flight=False,seconds=20)
    resolved=deepcopy(cycle);resolved.update(pending=False,station_restored=True,unemployment_observed=released,restoration_proof=str(builder.path.relative_to(base)),original_zero_proposal_credit=0)
    history=deepcopy(original.get('last_cycles')or{})
    for prior in original.get('cycles',[]):
        if prior.get('pending')is False and prior.get('station_restored')is True:history[prior['slot']]=deepcopy(prior)
    history[slot['id']]=resolved
    book.update(complete=True,pending=None,phase='zero_proposal_workstation_restored',last_cycles=history,reconciled_original_cycle=resolved,goal_complete=False);builder.save();return book
