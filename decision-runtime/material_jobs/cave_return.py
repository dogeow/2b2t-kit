"""Return through a complete freshly scanned cave volume, including detours."""
import math
from pathlib import Path

from kit_runtime.journal import write_json
from .acquisition import _scan
from .local_air_path import plan, move


def route(rows, start, target, low, high):
    if (not isinstance(low, list) or not isinstance(high, list)
            or len(low) != 3 or len(high) != 3
            or any(type(v) is not int for v in low+high)
            or any(a > b for a, b in zip(low, high))
            or not -64 <= low[1] <= high[1] <= 319
            or math.prod(b-a+1 for a, b in zip(low, high)) > 200000):
        raise ValueError('A bounded complete cave survey is required')
    return plan(rows, start, target, low, high, max_straight=8, foot_offset=.2)


def run(client, target, bounds, out, checkpoint):
    out = Path(out); out.mkdir(parents=True, exist_ok=False)
    checkpoint(); start = client.status()['pos']
    low, high = list(bounds['min']), list(bounds['max'])
    # Settled drops can move the player a few cells beyond the source window.
    # Observe the added air; never interpret the old box as a physical wall.
    for i in range(3):
        if start[i]<low[i] or start[i]>high[i]+1:
            if not low[i]-8<=start[i]<=high[i]+9:raise ValueError('Exit start left the bounded cave neighborhood')
            low[i]=min(low[i],math.floor(start[i])-3);high[i]=max(high[i],math.ceil(start[i])+3)
    low[1]=max(-64,low[1]);high[1]=min(319,high[1])
    if math.prod(b-a+1 for a,b in zip(low,high))>200000:raise ValueError('Bounded cave return survey is too large')
    # Endpoint-only boxes can omit the only connected detour. Use the supplied
    # cave volume, never historical clearance or excavate an alternate exit.
    yz=(high[1]-low[1]+1)*(high[2]-low[2]+1)
    if yz>50000:raise ValueError('One cave scan slice exceeds native limits')
    width=max(1,50000//yz);rows=[];reads=[]
    for x in range(low[0],high[0]+1,width):
        a=[x,low[1],low[2]];b=[min(high[0],x+width-1),high[1],high[2]]
        rows.extend(_scan(client,a,b,checkpoint));reads.append({'min':a,'max':b,'request_id':client.last})
    if math.dist(client.status()['pos'],start)>.2:raise RuntimeError('Player moved during the complete cave exit survey')
    points = route(rows, start, target, low, high)
    write_json(out/'route.json', {'world_session': client.world,
        'scan_request_id': client.last, 'scan_requests':reads,'bounds': {'min':low,'max':high}, 'start': start,
        'target': target, 'points': points, 'historical_clearance_used': False})
    for index, point in enumerate(points):
        checkpoint()
        if math.dist(client.status()['pos'], point) > .3:
            move(client, point, out/('leg-%02d'%index), max_straight=8, foot_offset=.2)
    return points
