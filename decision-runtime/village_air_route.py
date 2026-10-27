"""Route small village air moves through observed space before sending input."""
import math
from material_jobs.local_air_path import plan
from boat_towing import HAZARDS


def move(builder, target):
    start = builder.check()['pos']
    if (not isinstance(target, list) or len(target) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in target)
            or math.hypot(target[0] - start[0], target[2] - start[2]) > 24
            or abs(target[1] - start[1]) > 64):
        raise ValueError('Observed village route must remain local')
    low = [math.floor(min(a, b)) - 3 for a, b in zip(start, target)]
    high = [math.floor(max(a, b)) + 3 for a, b in zip(start, target)]
    if math.prod(b - a + 1 for a, b in zip(low, high)) > 30000:
        raise ValueError('Village air route survey is too large')
    scene, rows = builder.scan(low, high)
    obstacles=[row for row in rows.values()if row.get('passable')is not True or row.get('fluid')
               or row.get('block_entity')is not False
               or row.get('state','').split('}',1)[0].removeprefix('Block{')in HAZARDS]
    route = plan(obstacles, start, target, low, high, foot_offset=.1, max_straight=8)
    if route[-1] != target:
        route.append(target)
    entry = {'from': start, 'target': target, 'scan_time': scene['time'], 'route': route,
             'mining_sent': False, 'complete': False, 'completed_legs': 0}
    builder.book.setdefault('observed_air_routes', []).append(entry)
    builder.save()
    for point in route:
        if math.dist(builder.check()['pos'], point) < .12:
            continue
        builder.n('navigate', target=point, arrival=.1, air_only=True, seconds=40)
        entry['completed_legs'] += 1
        builder.save()
    entry['complete'] = True
    builder.save()
    return entry
