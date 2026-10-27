"""Prepare existing untraded cells with the same verified conversion and native owner."""
from pathlib import Path
from copy import deepcopy
import json
from librarian_room import LibrarianRoom
from librarian_workflow import seed_cycles
from material_plan import inventory_counts
from north_counter_conversion import convert
from village_public_roof import choose,leave

def prepare(builder,base,seed,names,open_roof,close_roof):
    base=Path(base);book=builder.book;layout=json.load(open(base/'layout-plan.json'))['slots'];last=seed_cycles(seed,builder.q.world,layout);p=json.load(open(base/'project-state.json'));kept={v['villager_uuid']for v in[*p['locked_trades'].values(),*p['locked_optional_trades'].values()]}
    if not names or len(set(names))!=len(names):raise ValueError('Distinct existing cell names required')
    slots=[next(v for v in layout if v['id']==name)for name in names]
    if any(v['occupant_uuid']in kept or v.get('near_work_gate_verified')or not v.get('bed_head')or not v.get('bed_foot')for v in slots):raise RuntimeError('Prepare only existing untraded, unconverted cells')
    stock=inventory_counts(builder.check())
    book.update(last_cycles=deepcopy(last),cycles=[],open_roofs=[],deferred_cells=[],phase='prepare_existing_cells');builder.save()
    state=builder.check();x=int(state['pos'][0]);floor=64 if x<761015 else 65
    if abs(state['pos'][1]-floor)>.2:raise RuntimeError('Preparation starts from the known ground public hall')
    _,rows=builder.scan([x-2,floor-1,797811],[x+2,floor+6,797811]);blocked={tuple(v['pos'])for v in p['protected_pending_excavation_targets']if v.get('world_session')==builder.q.world and v.get('native_claim_not_cleared')};entry=choose(rows,x,floor,blocked,low_x=760997 if floor==64 else 761017,high_x=761015 if floor==64 else 761033)
    if entry is None:raise RuntimeError('No clear public roof; lighting preserved')
    leave(builder,entry,floor,open_roof,close_roof)
    supply_parts(builder,base,len(slots))
    for slot in slots:
        room=LibrarianRoom.from_slot(slot);xx,yy,zz=room.work;roof=[xx,yy+3,zz+3*room.inward]
        from counter_preparation_plan import roof_light_plan
        _,lighting=builder.scan([xx-1,yy+3,roof[2]-1],[xx+1,yy+5,roof[2]+1]);plan=roof_light_plan(lighting,roof)
        if plan['kind']=='defer':
            book['deferred_cells'].append({'slot':slot['id'],'reason':'unsupported_roof_or_decoration_preserved'});builder.save();continue
        light=move_roof_light(builder,plan)if plan['kind']=='temporary_torch'else None
        result=convert(builder,base,slot,open_roof,close_roof);entry=result['public_roof_entry'];floor=yy
        if light:restore_roof_light(builder,light)
        print('REUSED_CELL_PREPARATION',slot['id'],result['gate_installed'],flush=True)
    # Return through a previously observed, fully restored public column.
    builder.nav([entry[0]+.5,85.2,entry[2]+.5]);builder.nav([entry[0]+.5,floor+5.2,entry[2]+.5]);open_roof(builder,entry,'up',pickup_pose=[entry[0]+.5,floor+.1,entry[2]+.5]);builder.nav([entry[0]+.5,floor+.1,entry[2]+.5]);close_roof(builder,entry)
    if book['open_roofs']:raise RuntimeError('Preparation has an unrestored roof')
    book.update(complete=True,pending=None,phase='existing_cells_prepared',inventory_after=dict(inventory_counts(builder.check())),goal_complete=False);builder.save();return book

def finish_refused_gate(builder,base,source,open_roof,close_roof):
    from librarian_workflow import validate_cycles
    from north_counter_conversion import place_gate,finish_conversion
    from closed_gate_geometry import admitted
    import time
    base=Path(base);prior=json.load(open(source));book=builder.book
    pending=[v for v in prior.get('conversions',[])if v.get('pending')]
    if prior.get('world_session')!=builder.q.world or prior.get('open_roofs')or len(pending)!=1:raise RuntimeError('One exact same-world partial cell required')
    record=deepcopy(pending[0])
    if record['stage']!='wait_gate_actual_collision_clearance'or record.get('gate_installed')or not record.get('bed_recovered')or not record.get('gate_use_pending'):raise RuntimeError('Partial cell has no exact initial gate-face refusal')
    layout=json.load(open(base/'layout-plan.json'))['slots'];slot=next(v for v in layout if v['id']==record['slot']);room=LibrarianRoom.from_slot(slot);x,y,z=room.work;inner=z+2*room.inward;command=json.load(open(builder.out/'command.json'))
    if command.get('op')!='interact'or command['params'].get('pos')!=[x,y-1,inner]or command['params'].get('expected_hand')!='minecraft:oak_fence_gate':raise RuntimeError('Original gate target changed')
    observed=builder.q.observe_refused_interaction_face()
    book.update(cycles=[],last_cycles=validate_cycles(prior['last_cycles'],builder.q.world,layout),conversions=[record],open_roofs=[],original_partial_service=str(Path(source).relative_to(base)),gate_zero_input_observation=observed['id']);record.update(gate_use_pending=False,original_refused_gate_command=command,original_refused_gate_credit=0);builder.save()
    scene,rows=builder.scan(*room.bounds())
    if any(tuple(v)in rows for v in record['old_bed'].values())or rows[tuple(room.work)]['state']!=room.lectern_state()or 'half=top,open=false'not in rows[(x,y+1,z)]['state']:raise RuntimeError('Already recovered bed/cap changed; no repeat excavation')
    if inventory_counts(builder.check())[record['bed_item']]!=record['bed_before']+1:raise RuntimeError('Recovered bed conservation changed')
    # Stay behind the real gate collision plane and outside the rear wall-torch outline.
    pose=[x+.5,y+.1,inner+.5+.65*room.inward];builder.nav(pose)
    end=time.monotonic()+60
    while True:
        scene,rows=builder.scan(*room.bounds())
        if admitted(scene,[x,y,inner],room.uid,inward=room.inward):break
        if time.monotonic()>=end:raise RuntimeError('Gate collision occupied; no use sent')
        time.sleep(.5)
    place_gate(builder,room,record,scene,rows);result=finish_conversion(builder,base,slot,record,open_roof,close_roof);entry=result['public_roof_entry'];floor=room.floor_y
    builder.nav([entry[0]+.5,85.2,entry[2]+.5]);builder.nav([entry[0]+.5,floor+5.2,entry[2]+.5]);open_roof(builder,entry,'up',pickup_pose=[entry[0]+.5,floor+.1,entry[2]+.5]);builder.nav([entry[0]+.5,floor+.1,entry[2]+.5]);close_roof(builder,entry)
    if book['open_roofs']:raise RuntimeError('Preparation retains an open roof')
    book.update(complete=True,pending=None,phase='existing_cell_gate_finished',goal_complete=False);builder.save();return book

def supply_parts(builder,base,count):
    from counter_preparation_plan import oak_planks_needed
    from kit_runtime.journal import write_json
    stock=inventory_counts(builder.check());need=oak_planks_needed(stock,count)
    if stock['minecraft:oak_fence_gate']>=count and stock['minecraft:oak_trapdoor']>=count:return
    if need:
        state=builder.check();builder.nav([state['pos'][0],85.2,state['pos'][2]]);builder.nav([761019.5,85.2,797851.5]);scene,rows=builder.scan([761019,64,797851],[761019,68,797851])
        if not rows[(761019,64,797851)]['state'].startswith('Block{minecraft:chest}')or any((761019,h,797851)in rows for h in range(65,69)):raise RuntimeError('Known wood chest is not clear; no storage use')
        builder.nav([761019.5,65.1,797851.5]);builder.send('open_chest_from_pose',pos=[761019,64,797851],pose=[761019.5,65.1,797851.5],face='up',allow_top_face=True,allow_hover=True,allow_empty=True,seconds=30);available=sum(v['count']for v in builder.check()['menu']['slots'][:-36]if v['item']=='minecraft:oak_planks');assert available>=need,'Known chest lacks required oak planks; no transfer sent';result=builder.send('transfer',item='minecraft:oak_planks',target=stock['minecraft:oak_planks']+need,deposit=False,seconds=30);builder.book['parts_wood_transfer']=result;builder.save();builder.q.native('close_menu')
    state=builder.check();builder.nav([state['pos'][0],85.2,state['pos'][2]]);builder.nav([761021.5,85.2,797850.5]);builder.nav([761021.5,65.1,797850.5]);p=[761022,64,797850];_,rows=builder.scan(p,p)
    if rows[tuple(p)]['state']!='Block{minecraft:crafting_table}':raise RuntimeError('Existing outdoor crafting table changed')
    profile=json.load(open(Path(base)/'live-village-121/close-stations-bench-1820.json'));profile['outdoor_workbench'].update(world_session=builder.q.world,proof=str(builder.path.relative_to(base)),source='fresh_native_scan');path=builder.out/(builder.q.prefix+'-bench.json');write_json(path,profile);result=builder.send('manufacture',targets={'minecraft:oak_fence_gate':count,'minecraft:oak_trapdoor':count},profile=str(path),seconds=180)
    if result.get('complete')is not True:raise RuntimeError('Original parts craft is incomplete; no repeat')
    builder.book['parts_manufacture']=result;builder.save()
    if builder.q.status(observing=True).get('screen'):builder.q.native('close_menu')
    after=inventory_counts(builder.check())
    if after['minecraft:oak_fence_gate']<count or after['minecraft:oak_trapdoor']<count:raise RuntimeError('Actual prepared parts missing')
    state=builder.check();builder.nav([state['pos'][0],85.2,state['pos'][2]])

def remove_roof_torch(builder,pos,record,label):
    import time
    before=inventory_counts(builder.check())['minecraft:torch'];builder.nav([pos[0]+.5,pos[1]+.1,pos[2]+.5]);builder.n('select_item',item='minecraft:diamond_axe');record['pending']=label;builder.save();reply=builder.n('mine_block',pos=pos,face='up',expected_state='Block{minecraft:torch}',seconds=12)
    if not reply['server_confirmed']or reply['native_sequence']!=reply['server_ack_sequence']:raise RuntimeError('Original torch excavation lacks server ACK')
    record[label+'_request']=reply['id'];builder.save();end=time.monotonic()+6
    while inventory_counts(builder.check())['minecraft:torch']!=before+1:
        if time.monotonic()>=end:raise RuntimeError('Original torch pickup unconfirmed; no repeat excavation')
        time.sleep(.1)
    record['pending']=None;builder.save()

def move_roof_light(builder,plan):
    original=plan['original'];temp=plan['temporary'];record={'original':original,'temporary':temp,'before':inventory_counts(builder.check())['minecraft:torch'],'pending':'temporary_light'};builder.book.setdefault('roof_light_transfers',[]).append(record);builder.save()
    builder.nav([original[0]+.5,85.2,original[2]+.5]);builder.nav([original[0]+.5,original[1]+1.2,original[2]+.5]);builder.place(temp,[temp[0],temp[1]-1,temp[2]],'up',item='minecraft:torch',expected='Block{minecraft:torch}');record.update(temporary_light_verified=True,pending=None);builder.save();remove_roof_torch(builder,original,record,'remove_original');return record

def restore_roof_light(builder,record):
    original=record['original'];temp=record['temporary'];record['pending']='restore_original';builder.save();builder.nav([original[0]+.5,85.2,original[2]+.5]);builder.nav([original[0]+.5,original[1]+1.2,original[2]+.5]);builder.place(original,[original[0],original[1]-1,original[2]],'up',item='minecraft:torch',expected='Block{minecraft:torch}');record['pending']=None;builder.save();remove_roof_torch(builder,temp,record,'remove_temporary')
    if inventory_counts(builder.check())['minecraft:torch']!=record['before']:raise RuntimeError('Lighting conservation changed')
    record.update(complete=True,pending=None,original_restored=True,temporary_removed=True);builder.save()

def preserve_unconfirmed_gate(builder,base,source,open_roof,close_roof):
    from librarian_workflow import validate_cycles
    from north_counter_conversion import finish_conversion
    from librarian_reset_enclosure import require_enclosed_reset
    from kit_runtime.journal import write_json
    base=Path(base);prior=json.load(open(source));records=[v for v in prior.get('conversions',[])if v.get('pending')];book=builder.book
    if prior.get('world_session')!=builder.q.world or prior.get('open_roofs')or len(records)!=1:raise RuntimeError('One exact closed-roof partial cell required')
    record=deepcopy(records[0]);layout=json.load(open(base/'layout-plan.json'))['slots'];slot=next(v for v in layout if v['id']==record['slot']);room=LibrarianRoom.from_slot(slot);x,y,z=room.work;target=[x,y,z+2*room.inward];support=[x,y-1,target[2]]
    if not record.get('gate_use_pending')or not record.get('bed_recovered')or record.get('gate_installed'):raise RuntimeError('No unconfirmed original gate use to preserve')
    events=[json.loads(v)for v in(builder.out/'control/events.jsonl').read_text().splitlines()];event=next(v for v in reversed(events)if v.get('request_id')==record['gate_use_request'])
    if event.get('world_session')!=builder.q.world or event.get('params',{}).get('task_session')!=builder.q.lease['job_session'] or event.get('op')!='interact'or event.get('phase')!='done'or event['params'].get('pos')!=support or event['params'].get('expected_hand')!='minecraft:oak_fence_gate':raise RuntimeError('Original use lacks its exact completed operation receipt')
    p=json.load(open(base/'project-state.json'));entry={'world_session':builder.q.world,'target':target,'support':support,'request_id':record['gate_use_request'],'source':str(Path(source).relative_to(base)),'claim_not_cleared':True,'old_placement_credit':0}
    pending=p.setdefault('protected_pending_placement_targets',[])
    if not any(v.get('request_id')==entry['request_id']for v in pending):pending.append(entry);write_json(base/'project-state.json',p)
    book.update(cycles=[],last_cycles=validate_cycles(prior['last_cycles'],builder.q.world,layout),conversions=[record],open_roofs=[],retained_original_placement=entry,roof_light_transfers=deepcopy(prior.get('roof_light_transfers',[])));record.update(gate_installed=False,gate_outcome_retained=True);builder.save()
    result=finish_conversion(builder,base,slot,record,open_roof,close_roof)
    for light in book['roof_light_transfers']:
        if not light.get('complete'):restore_roof_light(builder,light)
    entry_roof=result['public_roof_entry'];floor=room.floor_y;builder.nav([entry_roof[0]+.5,85.2,entry_roof[2]+.5]);builder.nav([entry_roof[0]+.5,floor+5.2,entry_roof[2]+.5]);open_roof(builder,entry_roof,'up',pickup_pose=[entry_roof[0]+.5,floor+.1,entry_roof[2]+.5]);builder.nav([entry_roof[0]+.5,floor+.1,entry_roof[2]+.5]);close_roof(builder,entry_roof)
    scene,_=builder.scan(*room.bounds());admission=require_enclosed_reset(scene,room)
    layout=json.load(open(base/'layout-plan.json'));row=next(v for v in layout['slots']if v['id']==slot['id']);row.update(bedless_enclosure_verified=True,bedless_enclosure_proof=str(builder.path.relative_to(base)),near_work_gate_verified=False,near_work_gate=None,retained_gate_placement=entry);write_json(base/'layout-plan.json',layout)
    book.update(complete=True,pending=None,phase='independent_enclosure_verified_gate_outcome_retained',enclosure_admission=admission,goal_complete=False);builder.save();return book

def repair_counter_header(builder,base,seed,name):
    """Repair only an intact room's missing upper header; no workstation input."""
    from librarian_reset_enclosure import require_enclosed_reset
    from kit_runtime.journal import write_json
    base=Path(base);layout=json.load(open(base/'layout-plan.json'))['slots'];last=seed_cycles(seed,builder.q.world,layout);slot=next(v for v in layout if v['id']==name);room=LibrarianRoom.from_slot(slot);x,y,z=room.work
    project=json.load(open(base/'project-state.json'))
    if room.floor_y!=y or not any(v.get('world_session')==builder.q.world and v.get('pos')==[x,y,z] and v.get('native_claim_not_cleared')for v in project['protected_pending_excavation_targets']):raise RuntimeError('This repair requires the original quarantined workpoint')
    builder.book.update(cycles=[],last_cycles=last,open_roofs=[],scope='missing_header_only_original_workpoint_not_touched',original_workpoint=[x,y,z],original_claim_retained=True);builder.save()
    from librarian_room import walk_public
    walk_public(builder,room);scene,rows=builder.scan(*room.bounds())
    if tuple(room.work)in rows or (x,y+2,z)in rows or rows[(x,y+3,z)]['state']!='Block{minecraft:dark_oak_planks}'or rows[(x,y+1,z)]['state']!='Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]':raise RuntimeError('Exact surveyed air workpoint and missing header changed')
    before=inventory_counts(builder.check())['minecraft:dark_oak_planks'];builder.place([x,y+2,z],[x,y+3,z],'down');scene,rows=builder.scan(*room.bounds());admission=require_enclosed_reset(scene,room)
    if tuple(room.work)in rows or inventory_counts(builder.check())['minecraft:dark_oak_planks']!=before-1:raise RuntimeError('Header or untouched original workstation conservation differs')
    builder.book.update(header_admission=admission,scene_after=scene,complete=True,pending=None,goal_complete=False,old_placement_credit=0);builder.save();return builder.book
