"""Observed air travel at one work height, without a cruise-height detour."""
import math
from pathlib import Path

from kit_runtime.journal import write_json
from .navigation import _body_sweep, settled_state
from .protocol import JobBlocked


def move(client, target, directory):
    """Return blocked before dispatch, or preserve an original uncertain move."""
    start = client.status()['pos']
    if (not isinstance(target, list) or len(target) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in target)
            or abs(target[1] - start[1]) > .45
            or math.hypot(target[0] - start[0], target[2] - start[2]) > 96):
        raise JobBlocked('同高度空气路线需要附近、同一作业高度的目标')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'level-air-route.json'
    if path.exists():
        raise JobBlocked('保留原同高度路线回执，不重放')
    low, high = _body_sweep(start, target)
    total = math.prod(b - a + 1 for a, b in zip(low, high))
    if total > 50000:
        raise JobBlocked('同高度路线的当前世界扫描超出范围')
    proof = client.request('scan', min=low, max=high, details=True)
    if (proof.get('phase') not in (None, 'done')
            or proof.get('world_session') != client.world
            or proof.get('scan_cells_read') != total
            or proof.get('scan_total_cells') != total
            or not isinstance(proof.get('blocks'), list)):
        raise JobBlocked('同高度空气通道尚未完整确认')
    book = {'world_session': client.world, 'start': start, 'target': target,
            'scan_request_id': proof.get('id'), 'pending': None, 'complete': False}
    if proof['blocks']:
        book['blocked'] = True
        write_json(path, book)
        return book
    book['pending'] = {'op': 'navigate', 'target': target}
    write_json(path, book)
    reply = client.request('navigate', target=target, arrival=.2,
                           air_only=True, seconds=90)
    book['request_id'] = getattr(client, 'last', None)
    book['reply_phase'] = reply.get('phase')
    write_json(path, book)
    if reply.get('phase') != 'done':
        raise JobBlocked('原同高度移动未确认，保留回执，不重新发送')
    actual = settled_state(client, target, .45)
    book.update(pending=None, complete=True, actual=actual['pos'])
    write_json(path, book)
    return book
