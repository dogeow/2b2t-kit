"""Conserved service-roof travel between a separate reserve counter and the main gallery."""
from pathlib import Path
import json,math
from material_plan import inventory_counts
from village_public_roof import choose,leave
from stone_service import recover as stone_open,close_roof as stone_close

def service_geometry(configuration):
    work=configuration['work_block']
    if configuration.get('public_counter',work)!=work and not all(k in configuration for k in ('service_roof','service_pose')):
        raise ValueError('An inset counter needs its separately verified service column')
    roof=configuration.get('service_roof',[work[0],work[1]+3,work[2]+1])
    pose=configuration.get('service_pose',[work[0]+.5,work[1]+.1,work[2]+1.5])
    if(not isinstance(roof,list)or len(roof)!=3 or any(type(v)is not int for v in roof)
       or not isinstance(pose,list)or len(pose)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in pose)
       or roof[0]+.5!=pose[0]or roof[2]+.5!=pose[2]or abs(pose[1]-(roof[1]-2.9))>.001):
        raise ValueError('Exact floor-height public service column required')
    return roof,pose

def clear_service_column(builder,roof):
    floor=roof[1]-3
    _,rows=builder.scan([roof[0],floor-1,roof[2]],[roof[0],roof[1],roof[2]])
    base=rows.get((roof[0],floor-1,roof[2]),{})
    if(base.get('solid')is not True or base.get('fluid')is not False
       or rows.get(tuple(roof),{}).get('state')!='Block{minecraft:cobblestone}'
       or any((roof[0],y,roof[2])in rows for y in range(floor,roof[1]))):
        raise RuntimeError('Service column is obstructed; no roof mining sent')

def at_reserve_gallery(pos,work):
    return (isinstance(pos,list)and len(pos)==3 and all(type(v)in(int,float)for v in pos)
            and work[0]-1<=pos[0]<work[0]+1 and abs(pos[1]-work[1])<=.25
            and work[2]+1<=pos[2]<work[2]+3)

def route(builder,destination,base,wood_open,wood_close):
    base=Path(base);project=json.loads((base/'project-state.json').read_text());configuration=project.get('reserve_library_counter')
    if not configuration:return False
    work=configuration['work_block'];reserve=(destination.uid==configuration['uuid']and list(destination.work)==work)
    source_reserve=at_reserve_gallery(builder.check()['pos'],work)
    if not reserve and not source_reserve:return False
    proof=json.loads((base/configuration['proof']).read_text())
    if(proof.get('complete')is not True or proof.get('pending')or proof.get('open_roofs')
       or proof.get('world_session')!=builder.q.world
       or not(configuration.get('enclosure_verified')is True or configuration.get('two_column_enclosure_verified')is True)):
        raise RuntimeError('Reserve service route lacks its same-world completed construction')
    if any(r.get('pending')for r in builder.book.get('district_routes',[])):
        raise RuntimeError('Original district route remains unresolved')
    if configuration.get('walking_airlock_verified')is True:
        path=(base/configuration['walking_airlock_proof']).resolve()
        if not path.is_relative_to(base.resolve()):raise RuntimeError('Walking evidence outside project')
        evidence=json.loads(path.read_text())
        if(evidence.get('complete')is not True or evidence.get('pending')or evidence.get('open_roofs')
           or evidence.get('world_session')!=builder.q.world or evidence.get('inventory_conserved')is not True
           or not evidence.get('airlock_crossings')or any(r.get('pending')is not False or r.get('lever_restored')is not True or r.get('both_doors_closed')is not True for r in evidence['airlock_crossings'])):
            raise RuntimeError('Walking route lacks completed same-world restored-door evidence')
        if configuration.get('held_return_gate_enabled')is True:
            held_path=(base/configuration['held_return_gate_proof']).resolve()
            if not held_path.is_relative_to(base.resolve()):raise RuntimeError('Held gate evidence outside project')
            held=json.loads(held_path.read_text());gate=held.get('held_return_gate')or{};age=held.get('keeper_age_after_source_quote_ms')
            if(held.get('complete')is not True or held.get('pending')or held.get('open_roofs')
               or held.get('world_session')!=builder.q.world or held.get('inventory_conserved')is not True
               or gate.get('phase')!='closed'or gate.get('pending')is not False or gate.get('both_doors_closed')is not True
               or type(age)is not int or not 0<=age<=20000):raise RuntimeError('Held gate route lacks restored same-world timed evidence')
        from library_airlock_route import route as walking_route,record_walk_inventory
        position=builder.check()['pos']
        if reserve and not source_reserve and not 797810<=position[2]<=797813:
            from librarian_room import LibrarianRoom
            keepers={v['villager_uuid']for group in ('locked_trades','locked_optional_trades')for v in project[group].values()}
            candidates=[]
            for slot in json.loads((base/'layout-plan.json').read_text())['slots']:
                if slot.get('occupant_uuid')not in keepers:continue
                room=LibrarianRoom.from_slot(slot)
                if min(math.dist(position,pose)for pose in (room.public_pose(),room.public_trade_pose()))<=.45:candidates.append(room)
            if len(candidates)!=1:raise RuntimeError('Return source is not an exact registered public counter pose')
            room=candidates[0];_,rows=builder.scan(*room.bounds());room.require_caps(rows);before_alignment=inventory_counts(builder.check())
            builder.n('walk',target=[room.work[0]+.5,64. if room.work[0]<761015 else 65.,797811.5],arrival=.1,restore_flight=False,seconds=20);record_walk_inventory(builder,before_alignment)
            builder.book.setdefault('public_counter_return_alignments',[]).append({'keeper_uuid':room.uid,'from':position,'witnessed_pose':room.public_pose()});builder.save()
        return walking_route(builder,destination,configuration)
    reserve_roof,reserve_pose=service_geometry(configuration)
    def walk(point):builder.n('walk',target=point,arrival=.1,restore_flight=False,seconds=25)
    if reserve and source_reserve:
        point=destination.public_pose();point[1]=float(destination.floor_y);walk(point);return True
    before=inventory_counts(builder.check());record={'pending':True,'source':'reserve'if source_reserve else'main','target':'reserve'if reserve else'main','world_session':builder.q.world};builder.book.setdefault('district_routes',[]).append(record);builder.save()
    protected={tuple(v['pos'])for key in ('protected_pending_excavation_targets','protected_pending_placement_targets')for v in project.get(key,[])if v.get('world_session')==builder.q.world and v.get('native_claim_not_cleared')}
    if tuple(reserve_roof)in protected:raise RuntimeError('Reserve service roof is quarantined')
    if source_reserve:
        clear_service_column(builder,reserve_roof);walk([reserve_pose[0],float(work[1]),reserve_pose[2]]);builder.nav(reserve_pose);stone_open(builder,reserve_roof,'down',protected,roof=True);builder.nav([reserve_pose[0],work[1]+5.2,reserve_pose[2]]);stone_close(builder,reserve_roof)
        builder.nav([reserve_pose[0],85.2,reserve_pose[2]]);x=761022;floor=65
    else:
        position=builder.check()['pos'];x=int(position[0]);floor=64 if x<761015 else 65
        if not 760997<=x<=761033 or not 797808<=position[2]<=797815 or abs(position[1]-floor)>1.2:
            raise RuntimeError('Source is outside a witnessed main-gallery approach')
    _,rows=builder.scan([x-2,floor-1,797811],[x+2,floor+6,797811]);entry=choose(rows,x,floor,protected,low_x=760997 if floor==64 else 761017,high_x=761015 if floor==64 else 761033)
    if entry is None:raise RuntimeError('No current clear main service roof')
    record['main_roof']=entry;builder.save()
    if source_reserve:
        builder.nav([entry[0]+.5,85.2,entry[2]+.5]);builder.nav([entry[0]+.5,floor+5.2,entry[2]+.5]);wood_open(builder,entry,'up',pickup_pose=[entry[0]+.5,floor+.1,entry[2]+.5]);builder.nav([entry[0]+.5,floor+.1,entry[2]+.5]);wood_close(builder,entry)
    else:
        leave(builder,entry,floor,wood_open,wood_close);builder.nav([entry[0]+.5,85.2,entry[2]+.5]);builder.nav([reserve_pose[0],85.2,reserve_pose[2]]);builder.nav([reserve_pose[0],work[1]+5.2,reserve_pose[2]]);clear_service_column(builder,reserve_roof);stone_open(builder,reserve_roof,'up',protected,pickup_pose=reserve_pose,roof=True);builder.nav(reserve_pose);stone_close(builder,reserve_roof)
    if builder.book.get('open_roofs')or inventory_counts(builder.check())!=before:
        raise RuntimeError('District service roofs or inventory remain unconfirmed')
    record.update(pending=False,material_conserved=True,all_roofs_restored=True);builder.save()
    if reserve:
        point=destination.public_pose();point[1]=float(destination.floor_y);walk(point)
    return reserve
