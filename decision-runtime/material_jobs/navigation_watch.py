"""Stop an exactly owned stalled flight; never replay or credit the interrupted leg."""
import math
from copy import deepcopy
from kit_runtime.journal import write_json
from .protocol import server_key


class NavigationStalled(RuntimeError):
    pass


def owned_flight(client, state, envelope):
    lease = state.get('supervision_lease') or {}
    stop = state.get('control_stop') or {}
    return bool(isinstance(envelope, dict)
        and envelope.get('op') == 'navigate'
        and state.get('connected') is True and state.get('manual_movement') is False
        and state.get('screen') == '' and not state.get('interface_paused')
        and not state.get('guard_busy') and not state.get('under_water')
        and state.get('flight') is True and state.get('health', 0) >= 19
        and state.get('phase') == 'running' and state.get('op') == 'navigate'
        and state.get('navigating') is True
        and state.get('id') == state.get('last_request') == client.last == envelope.get('request_id')
        and state.get('world_session') == client.world == envelope.get('world_session')
        and type(envelope.get('base_revision')) is int
        and envelope['base_revision'] == client.rev == envelope.get('request_revision')
        and envelope.get('expected_revision') == client.rev + 1 == state.get('control_revision')
        and lease.get('kind') == 'materials'
        and lease.get('id') == envelope.get('lease_id') == getattr(client.heartbeat, 'id', None)
        and lease.get('job_session') == envelope.get('task_session') == client.task
        and lease.get('world_session') == client.world
        and lease.get('revision') == state.get('control_revision')
        and server_key(state.get('server')) == server_key(envelope.get('server'))
        and state.get('dimension') == envelope.get('dimension')
        and not (stop.get('kind') in ('manual', 'emergency')
                 and stop.get('revision') == state.get('control_revision')))


class FlightWatch:
    def __init__(self, seconds=10):
        self.seconds = seconds
        self.reset()

    def reset(self):
        self.anchor = None
        self.since = None
        self.stamp = None

    def poll(self, client, state, envelope, now):
        position = state.get('pos')
        if (not owned_flight(client, state, envelope)
                or not isinstance(position, list) or len(position) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in position)
                or type(state.get('time')) is not int):
            self.reset()
            return False
        if self.anchor is None or math.dist(position, self.anchor) >= .5:
            self.anchor = list(position)
            self.since = now
            self.stamp = state['time']
            return False
        return now - self.since >= self.seconds and state['time'] > self.stamp


def pause_stalled(client, envelope):
    # Re-read immediately before cancellation. A user takeover or a terminal
    # native reply must win over the older stagnation sample.
    state = client.raw()
    if not owned_flight(client, state, envelope):
        return False
    from material_client import Client
    report = {'schema': 1, 'reason': 'no_displacement_for_10_seconds',
              'original_request': deepcopy(envelope), 'position': state['pos'],
              'original_request_replayed': False, 'arrival_credit': False,
              'pause_pending': True}
    path = client.out / ('stalled-flight-' + envelope['request_id'] + '.json')
    write_json(path, report)
    mailbox = client.root / 'request.json'
    if mailbox.exists():
        (client.out / ('stalled-original-' + envelope['request_id'] + '.json')).write_bytes(mailbox.read_bytes())
    client.rev = state['control_revision']
    reply = Client.request(client, 'material_job_pause', task_session=client.task,
                           background_ok=True, release=False, seconds=10)
    actual = client.status(wait_interface=False)
    lease = actual.get('supervision_lease') or {}
    keys = actual.get('movement_keys')
    if (reply.get('phase') != 'done' or reply.get('id') != client.last
            or actual.get('world_session') != client.world
            or actual.get('control_revision') != client.rev
            or actual.get('navigating') is not False
            or not isinstance(keys, dict) or any(keys.values())
            or lease.get('kind') != 'materials' or lease.get('job_session') != client.task
            or lease.get('id') != client.heartbeat.id or lease.get('revision') != client.rev):
        raise RuntimeError('Stalled flight cancellation is unconfirmed; preserve it and do not replay')
    report.update(pause_pending=False, pause_reply=deepcopy(reply),
                  stopped_position=actual['pos'], movement_keys=keys)
    write_json(path, report)
    raise NavigationStalled('航行连续 10 秒没有位移，已停止当前路线；不会重复撞边界')
