"""Stage the existing native gravel collector above registered open water."""
import math
from pathlib import Path
from kit_runtime.journal import write_json
from .protocol import JobBlocked


def target(profile):
    spec = profile.get('gravel_staging')
    if spec is None:
        return None
    point = spec.get('target') if isinstance(spec, dict) else None
    if (not isinstance(spec, dict) or spec.get('authorized') is not True
            or spec.get('source') != 'verified_open_water'
            or not isinstance(point, list) or len(point) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)
            or not all(-29999984 <= point[i] <= 29999984 for i in (0, 2))
            or not 80 <= point[1] <= 315):
        raise JobBlocked('沙砾出发点缺少有效的已核验水域登记')
    return point


def stage(backend):
    point = target(backend.profile)
    if point is None:
        return False
    from .acquisition import _travel
    backend.prepare_travel()
    client = backend.ensure_client()
    trace = []
    out = Path(backend.out)/'gravel-preflight'
    out.mkdir(parents=True, exist_ok=True)
    try:
        _travel(client, point, backend.checkpoint, trace, keep_cruise=True)
        current = client.status()
        if (current.get('world_session') != client.world or current.get('under_water')
                or current.get('manual_movement') or current.get('guard_busy')
                or current.get('health', 0) < 19 or math.dist(current['pos'], point) > 3
                or current.get('navigating') or current.get('native_material_busy')):
            raise JobBlocked('沙砾出发点尚未确认到达，未启动新潜水')
        return True
    finally:
        write_json(out/'open-water-staging-travel.json', trace)
