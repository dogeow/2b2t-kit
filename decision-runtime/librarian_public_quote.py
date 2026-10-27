"""Wait for a real reachable resident; observe only proved pre-input refusals."""
import time,math
from villager_trading import body_distance_from_eye


def open_when_reachable(builder, room, awake, *, seconds=30, max_attempts=2, distance_limit=2.7, wait_for_reach=False):
    if type(wait_for_reach)is not bool:raise ValueError('Explicit bounded reach-wait policy required')
    if not 0 < seconds <= 60 or type(max_attempts) is not int or not 1 <= max_attempts <= 2:
        raise ValueError('Bounded public quote observation required')
    if type(distance_limit) not in (int, float) or not 0 < distance_limit <= 2.95:
        raise ValueError('Public distance must retain a margin inside native reach')
    deadline = time.monotonic() + seconds
    attempts = 0
    records = builder.book.setdefault('public_quote_admissions', [])
    waits = builder.book.setdefault('public_quote_wait_counts', {'unclaimed': 0})
    while time.monotonic() < deadline:
        state = builder.check()
        if not awake():
            time.sleep(.2)
            continue
        cohort = (state.get('loaded_villagers') or {}).get('villagers')
        if isinstance(cohort, list):
            exact = [v for v in cohort if v.get('uuid') == room.uid]
            if len(exact) != 1 or exact[0].get('villager', {}).get('profession') != 'minecraft:librarian':
                # Snapshots are already maintained by the sole controller. An
                # unclaimed resident cannot yield a quote; scanning its whole
                # room every poll just delays the next useful action.
                waits['unclaimed'] += 1
                time.sleep(.2)
                continue
        if wait_for_reach and isinstance(cohort,list) and len(exact)==1:
            point=exact[0].get('pos');eye=[state['pos'][0],state['pos'][1]+1.62,state['pos'][2]]
            # A loose ordinary-adult envelope is only a scan hint. Every actual
            # interaction still requires the freshly scanned real body below.
            if isinstance(point,list)and len(point)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in point):
                delta=[max(abs(point[0]-eye[0])-.5,0),max(point[1]-eye[1],eye[1]-(point[1]+2.1),0),max(abs(point[2]-eye[2])-.5,0)]
                if math.hypot(*delta)>distance_limit:
                    waits['out_of_reach_hints']=waits.get('out_of_reach_hints',0)+1;time.sleep(.2);continue
        scene, _ = builder.scan(*room.bounds())
        actor = room.actor(scene)
        if actor['villager']['profession'] != 'minecraft:librarian':
            time.sleep(.2)
            continue
        eye = [state['pos'][0], state['pos'][1] + 1.62, state['pos'][2]]
        distance = body_distance_from_eye(actor, eye)
        if distance > distance_limit:
            # A fresh body scan already proves this pose cannot open the
            # merchant. Let the planner visit another cell or choose a new
            # pose instead of rescanning the same room until the timeout.
            waits['out_of_reach'] = waits.get('out_of_reach', 0) + 1
            builder.save()
            if wait_for_reach:
                time.sleep(.2)
                continue
            return None
        if builder.check().get('hand',{}).get('item')!='minecraft:netherite_sword':
            builder.n('select_item', item='minecraft:netherite_sword')
        attempts += 1
        record = dict(uuid=room.uid, distance=distance, attempt=attempts, pending=True)
        records.append(record)
        builder.save()
        try:
            reply = builder.q.send('merchant_open', actor=actor, seconds=35)
        except RuntimeError:
            # The existing observer checks the audited host, native terminal,
            # unchanged inventory/position/revision and absence of unknown input.
            # If any condition fails it raises, retaining the original request.
            observation = builder.q.observe_merchant_reach_refusal()
            record.update(pending=False, pre_input_refusal_observed=observation['id'])
            builder.save()
            if attempts >= max_attempts:
                return None
            time.sleep(.2)
            continue
        if reply['menu']['merchant']['villager_uuid'] != room.uid:
            raise RuntimeError('Different merchant opened; no trade or retry')
        record.update(pending=False, opened_at=reply['time'])
        builder.save()
        return reply
    builder.save()
    return None
