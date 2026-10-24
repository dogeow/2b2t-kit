"""Ground access to the witnessed central cell below the main aisle's floor step."""
from pathlib import Path
import json
import math
from librarian_room import LibrarianRoom


def route(builder,destination,base):
    base=Path(base);project=json.loads((base/'project-state.json').read_text())
    config=project.get('central_library_receiver')or{}
    uid=config.get('occupant_uuid');front=config.get('front')
    if not uid or front!=[761016,64,797809]:return False
    state=builder.check();position=state['pos'];target=[761016.5,64.,797810.5]
    source=(all(type(v)in(int,float)and math.isfinite(v)for v in position)
            and abs(position[0]-target[0])<=.35 and abs(position[1]-64)<=.25
            and abs(position[2]-target[2])<=.4)
    central=destination.uid==uid and list(destination.work)==front
    if not source and not central:return False
    proof_path=(base/(config.get('bedless_proof')or config['admission_proof'])).resolve()
    if not proof_path.is_relative_to(base.resolve()):raise RuntimeError('Central route evidence outside project')
    proof=json.loads(proof_path.read_text())
    if (proof.get('complete')is not True or proof.get('pending')or proof.get('open_roofs')
            or proof.get('world_session')!=builder.q.world or proof.get('patient_uuid')!=uid
            or (proof.get('geometry')or{}).get('verified')is not True):
        raise RuntimeError('Central route needs its same-world completed individual enclosure')
    if any(v.get('pending')for v in builder.book.get('central_public_routes',[])):
        raise RuntimeError('Previous central route remains unresolved; no repeated movement')
    if source and central:return True
    # A registered inset counter is the only admissible source beyond the aisle.
    if central and not 797810<=position[2]<=797813:
        kept={v['villager_uuid']for key in ('locked_trades','locked_optional_trades')for v in project.get(key,{}).values()}
        rooms=[LibrarianRoom.from_slot(v)for v in json.loads((base/'layout-plan.json').read_text())['slots']if v.get('occupant_uuid')in kept]
        rooms=[r for r in rooms if min(math.dist(position,r.public_pose()),math.dist(position,r.public_trade_pose()))<=.45]
        if len(rooms)!=1:raise RuntimeError('Central return is not a witnessed public counter pose')
        _,rows=builder.scan(*rooms[0].bounds());rooms[0].require_caps(rows)
    if not source and(not 760997<=position[0]<=761034 or not 797810<=position[2]<=797813.6
                      or abs(position[1]-(64 if position[0]<761015 else 65))>1.2):
        raise RuntimeError('Central return starts outside the witnessed public gallery')
    record={'pending':True,'world_session':builder.q.world,'source':position,'destination_uuid':destination.uid,'central':central}
    builder.book.setdefault('central_public_routes',[]).append(record);builder.save()
    def walk(point):
        if math.dist(builder.check()['pos'],point)>.22:
            builder.n('walk',target=point,arrival=.1,restore_flight=False,seconds=25)
    if source:
        # Leave along the existing two half steps, preserving two-block headroom.
        walk([761014.5,64.,797810.5]);walk([761014.5,64.,797811.5])
    else:
        floor=64. if position[0]<761015 else 65.
        walk([position[0],floor,797811.5])
        if floor==65:
            walk([761016.5,65.,797811.5])
            # Vanilla ground walking checks support for this one-block descent.
            walk(target)
        else:
            walk([761014.5,64.,797811.5]);walk([761014.5,64.,797810.5]);walk(target)
    record.update(pending=False,ground_only=True,no_airlock_or_mining=True);builder.save()
    return central
