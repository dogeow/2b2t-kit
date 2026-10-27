"""Read nearby entities during an owned move without issuing another command."""
import math
import threading

from live_snapshot import read_fresh
from .loaded_squid_survey import read as read_loaded_squids,read_glow


def candidates(state, world, task, entity_type, low_y=50, high_y=64):
    lease = state.get('supervision_lease') or {}
    if (not state.get('connected') or state.get('world_session') != world
            or state.get('manual_movement') or state.get('screen')
            or lease.get('kind') != 'materials' or lease.get('job_session') != task
            or lease.get('world_session') != world):
        return []
    result = []
    for entity in state.get('entities', []):
        p = entity.get('pos')
        if (entity.get('type') != entity_type or entity.get('has_custom_name') is not False
                or entity.get('health', 0) <= 0 or entity.get('alive') is False
                or not isinstance(p, list) or len(p) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
                or not low_y <= p[1] <= high_y or not entity.get('uuid')):
            continue
        result.append(entity)
    return result


class MovingEntityObserver:
    def __init__(self, client, entity_type, *, low_y=50, high_y=64):
        self.client = client
        self.entity_type = entity_type
        self.low_y, self.high_y = low_y, high_y
        self.seen = {}
        self.samples = 0
        self.stop = threading.Event()
        self.thread = None

    def __enter__(self):
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()
        return self

    def _read(self):
        while not self.stop.is_set():
            inflight = getattr(self.client, 'native_inflight', None)
            if inflight and inflight.get('op') == 'navigate':
                try:
                    s = read_fresh(self.client.root, max_age_ms=1000, wait_seconds=.2)
                    # Observe only the original owned request while it is moving.
                    if (s.get('last_request') == inflight.get('request_id')
                            and s.get('phase') == 'running'
                            and math.dist(s.get('velocity', [0, 0, 0]), [0, 0, 0]) > .03):
                        self.samples += 1
                        for e in candidates(s, self.client.world, self.client.task,
                                            self.entity_type, self.low_y, self.high_y):
                            self.seen[e['uuid']] = {**e, 'observed_at': s['time'],
                                'observed_from': s['pos'], 'move_request_id': inflight['request_id']}
                        if self.entity_type == 'minecraft:squid':
                            for e in read_loaded_squids(self.client.root, s):
                                self.seen[e['uuid']] = {**e, 'observed_from': s['pos'],
                                    'move_request_id': inflight['request_id']}
                        elif self.entity_type=='minecraft:glow_squid':
                            for e in read_glow(self.client.root,s):
                                if self.low_y<=e['pos'][1]<=self.high_y:
                                    self.seen[e['uuid']]={**e,'observed_from':s['pos'],'move_request_id':inflight['request_id']}
                except (RuntimeError, KeyError, TypeError, ValueError):
                    pass  # Observation failure never dispatches or replays an action.
            self.stop.wait(.1)

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(timeout=1)
        return False
