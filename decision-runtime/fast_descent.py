"""Safely shorten a large outdoor descent using ordinary gravity and Meteor Flight.

Only a fully loaded, empty 3x3 column qualifies. The caller retains its native
material safety lease; any uncertain fall ends in guarded flight or logout.
"""

import math
import time


def clear_column(rows):
    return not any(row['state'] != 'Block{minecraft:air}' for row in rows)


def descend_if_clear(client, target_y, braking_margin=16):
    deadline=time.monotonic()+8
    previous=None;stable=0
    while True:
        start=client.status()
        velocity=start.get('velocity',[0,0,0]);pos=start['pos']
        steady=math.hypot(velocity[0],velocity[2])<.02 and (previous is None or
                math.hypot(pos[0]-previous[0],pos[2]-previous[2])<.03)
        stable=stable+1 if steady else 0
        if stable>=3:break
        if time.monotonic()>=deadline:
            return {'used':False,'reason':'Horizontal flight did not settle before freefall'}
        previous=pos;time.sleep(.15)
    x, y, z = start['pos']
    brake_y = target_y + braking_margin
    if start.get('freefall_protocol',0)<1:
        return {'used': False, 'reason': 'Native frame brake is unavailable'}
    if start['health'] < 18 or not start.get('guard_armed') or y-brake_y <= 24:
        return {'used': False, 'reason': 'No long, guarded descent required'}
    low = math.floor(brake_y)
    high = math.ceil(y) + 2
    bx, bz = math.floor(x), math.floor(z)
    observed = client.request('scan', min=[bx-1, low, bz-1], max=[bx+1, high, bz+1], details=True)
    if not clear_column(observed['blocks']):
        return {'used': False, 'reason': 'Descent column contains a block or fluid'}
    latest=client.status()
    if math.hypot(latest['pos'][0]-x,latest['pos'][2]-z)>.12:
        return {'used':False,'reason':'Position changed after descent clearance scan'}
    target = [latest['pos'][0], brake_y, latest['pos'][2]]
    result = client.request('walk', target=target, arrival=.35,
                            restore_flight=False, freefall_brake_y=brake_y, seconds=20)
    after = client.status()
    if result.get('phase') != 'done' or after['health'] < 18 or not after.get('flight') or after['pos'][1]<brake_y-2:
        # The ordinary exact-height navigator re-enables Meteor Flight; do not
        # leave a failed free-fall attempt without braking.
        client.request('navigate', target=[after['pos'][0], after['pos'][1], after['pos'][2]],
                       arrival=2, seconds=15)
        raise RuntimeError('Free-fall brake was not confirmed')
    return {'used': True, 'start_y': y, 'brake_y': after['pos'][1],
            'horizontal': [after['pos'][0], after['pos'][2]], 'health': after['health']}
