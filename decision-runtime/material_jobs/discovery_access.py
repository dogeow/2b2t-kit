"""Reach the exact registered search origin before ordinary bounded discovery."""
import hashlib
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json
from .protocol import JobBlocked


def stage(client, profile, out, checkpoint):
    from .acquisition import DIRECT_ROUTE_LIMIT, SEGMENT_ROUTE_LIMIT, _travel
    from .navigation import lift_for_travel
    origin = profile.get('search_origin')
    radius = profile.get('search_radius')
    if (not isinstance(origin, list) or len(origin) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in origin)
            or not -62 <= origin[1] <= 315 or type(radius) is not int or not 1 <= radius <= 384):
        raise JobBlocked('资源搜索接近点或原搜索范围未完整登记')
    checkpoint()
    first = client.status()
    path = Path(out)/'discovery-origin-access.json'
    previous = None
    if path.exists():
        previous = json.loads(path.read_text())
        if previous.get('pending') is not None:
            raise JobBlocked('原搜索接近路线尚未确认，不重放')
        if previous.get('complete') is not True:
            raise JobBlocked('原搜索接近路线尚未完成，不重放')
    distance = math.hypot(first['pos'][0]-origin[0], first['pos'][2]-origin[2])
    # A nearby actor already fits the ordinary frontier's original route limit.
    if distance <= max(64, DIRECT_ROUTE_LIMIT-math.sqrt(2)*(radius+16)):
        return False
    count = math.ceil(distance / SEGMENT_ROUTE_LIMIT)
    if not 1 <= count <= 5:
        raise JobBlocked('登记搜索点超过本地接近路线范围，未移动')
    if previous is not None:
        raw=path.read_bytes()
        archive=path.with_name('completed-origin-access-'+hashlib.sha256(raw).hexdigest()[:24]+'.json')
        if not archive.exists():archive.write_bytes(raw)
    book = {'schema':1, 'world_session':client.world, 'origin':origin, 'radius':radius,
            'pending':None, 'complete':False, 'segments':[], 'source_blocks_credited':0}
    write_json(path, book)
    book['pending'] = {'operation':'lift_for_travel'}
    write_json(path, book)
    lifted = lift_for_travel(client)
    start = list(lifted['pos'])
    height = min(315, max(145, start[1], origin[1]))
    trace = []
    for index in range(1, count+1):
        checkpoint()
        ratio = index/count
        target = [start[0]+(origin[0]-start[0])*ratio, height,
                  start[2]+(origin[2]-start[2])*ratio]
        book['pending'] = {'segment':index, 'target':target}
        write_json(path, book)
        _travel(client, target, checkpoint, trace, keep_cruise=True)
        observed = client.status()
        if (observed.get('world_session') != client.world or observed.get('manual_movement')
                or observed.get('navigating') or observed.get('native_material_busy')
                or observed.get('health', 0) < 18
                or math.hypot(observed['pos'][0]-target[0], observed['pos'][2]-target[2]) > 3
                or abs(observed['pos'][1]-target[1]) > 3):
            raise JobBlocked('搜索接近段到达未确认，保留原路线')
        book['segments'].append({'target':target, 'actual':observed['pos'],
                                 'request_id':getattr(client, 'last', None)})
        book['pending'] = None
        write_json(path, book)
    book.update(complete=True, trace=trace)
    write_json(path, book)
    return True
