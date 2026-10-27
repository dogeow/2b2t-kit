"""Wake only a freshly identified resident in its own occupied overworld bed."""
import time
from village_sleeping_beds import current_claims
from villager_events import read


def wake_claim(scene, flags, slot, dimension):
    # BedBlock.useWithoutItem handles an occupied bed before player sleep.
    # Raw clock modulo is not evidence of the server's resident schedule.
    if dimension != 'minecraft:overworld':
        raise ValueError('Occupied-bed interaction is restricted to the overworld')
    uid = slot['occupant_uuid']
    claims = current_claims(scene, flags, {uid})
    if not claims:
        raise ValueError('Own resident is not freshly observed asleep')
    claim = claims[uid]
    if claim['head'] != slot['bed_head'] or claim['foot'] != slot['bed_foot']:
        raise ValueError('Actual occupied bed differs from the assigned stall')
    if any(v.get('uuid') != uid and v.get('sleeping') is True
           and v.get('sleeping_pos') == claim['head'] for v in flags['villagers']):
        raise ValueError('Occupied bed has ambiguous resident ownership')
    return claim


def wake_assigned(builder, slot, *, bed_part='foot', bed_face='up'):
    """One ordinary bed use followed by real pose observations; no repeat on timeout."""
    if bed_part not in ('foot','head'):
        raise ValueError('An actual assigned bed head or foot is required')
    if bed_face not in ('up','north','south','east','west'):
        raise ValueError('A normal visible bed face is required')
    uid = slot['occupant_uuid']
    state = builder.check()
    frame = read(builder.root, state)
    flag = next(v for v in frame['villagers'] if v['uuid'] == uid)
    if flag['sleeping'] is False:
        return True
    builder.n('select_item', item='minecraft:netherite_sword')
    foot, head = slot['bed_foot'], slot['bed_head']
    lo = [min(foot[i], head[i]) - 1 for i in range(3)]
    hi = [max(foot[i], head[i]) + (1 if i != 1 else 3) for i in range(3)]
    scene, _ = builder.scan(lo, hi)
    state = builder.check()
    frame = read(builder.root, state)
    flag = next(v for v in frame['villagers'] if v['uuid'] == uid)
    if flag['sleeping'] is False:
        return True
    claim = wake_claim(scene, frame, slot, state['dimension'])
    record = dict(villager_uuid=uid, claim=claim, bed_part=bed_part, bed_face=bed_face, pending=True)
    builder.book.setdefault('occupied_bed_wakes', []).append(record)
    builder.save()
    result = builder.n('interact', pos=claim[bed_part], face=bed_face,
                       expected_state=claim[bed_part+'_state'], expected_hand='minecraft:netherite_sword')
    record['request_id'] = result['id']
    builder.save()
    deadline = time.monotonic() + 5
    while True:
        state = builder.check()
        frame = read(builder.root, state)
        flag = next(v for v in frame['villagers'] if v['uuid'] == uid)
        if flag['entity_id'] != claim['entity_id']:
            raise RuntimeError('Resident identity changed after original wake')
        if flag['sleeping'] is False:
            record.update(pending=False, awake_at=state['time'])
            builder.save()
            return True
        if time.monotonic() >= deadline:
            raise RuntimeError('Original occupied-bed wake unconfirmed; do not repeat input')
        time.sleep(.1)
