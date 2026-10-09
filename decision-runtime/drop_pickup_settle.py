"""One short native adjustment after a known terminal pickup approach, never a pickup replay."""
import math
import time
from ground_pickup import clear_body, hazard
from material_plan import inventory_counts


def poses(origin, drop, rows):
    cells = {tuple(r['pos']): r for r in rows}
    result = []
    for x in range(math.floor(drop[0])-1, math.floor(drop[0])+2):
        for z in range(math.floor(drop[2])-1, math.floor(drop[2])+2):
            for y in range(math.floor(drop[1])-1, math.floor(drop[1])+2):
                p = [x+.5, y, z+.5]
                floor = cells.get((x, y-1, z))
                if (abs(y-drop[1]) > .25 or abs(y-origin[1]) > 1.1 or math.dist(origin,p) > 3 or not floor
                        or not floor.get('solid') or floor.get('block_entity') or hazard(floor)
                        or not clear_body(p,cells)):
                    continue
                result.append(p)
    return sorted(result,key=lambda p:(math.dist(p,drop),math.dist(p,origin)))


def settle(client, drop, before):
    state = client.status()
    current = next((e for e in state.get('entities',[])if e.get('uuid')==drop['uuid']), None)
    if not current or current.get('stack') != drop.get('stack'):
        return False
    lo=[math.floor(min(a,b))-2 for a,b in zip(state['pos'],current['pos'])]
    hi=[math.ceil(max(a,b))+3 for a,b in zip(state['pos'],current['pos'])]
    scan=client.request('scan',min=lo,max=hi,details=True)
    if scan.get('phase')!='done' or scan.get('world_session')!=client.world:
        return False
    candidates=poses(state['pos'],current['pos'],scan['blocks'])
    if not candidates:return False
    # Normal walking naturally steps down one supported block; a diagonal air sweep
    # can intersect the old ledge even when this ordinary ground movement is legal.
    result=client.request('walk',target=candidates[0],arrival=.08,restore_flight=True,seconds=10)
    if result.get('phase')!='done':return False
    end=time.monotonic()+3
    item=drop['stack']['item'];amount=drop['stack']['count']
    while time.monotonic()<end:
        state=client.status()
        if (inventory_counts(state).get(item,0)==before+amount
                and not any(e.get('uuid')==drop['uuid']for e in state.get('entities',[]))):return True
        time.sleep(.15)
    return False
