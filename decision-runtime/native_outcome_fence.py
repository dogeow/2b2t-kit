"""Retain a dispatched native identity until its exact response is observed.

The base client clears its transient inflight value after a timeout. This fence
keeps that timeout identity so a caller cannot turn a stale outer DONE status
into another operation, cleanup, or replay. Native health protection remains
independent of this Python controller.
"""
from copy import deepcopy
import json
from material_client import MaterialClient

_READ_TERMINALS = frozenset(('scan','snapshot','navigate','walk','approach_block',
                            'select_item','close_menu','material_job_park'))


def exact_idle_terminal(client, state):
    terminal = getattr(client, 'last_terminal_evidence', None) or {}
    lease = state.get('supervision_lease') or {}
    phase = terminal.get('phase')
    known = (phase == 'done'
             or terminal.get('op') == 'snapshot' and phase is None
             or phase in ('waiting','stopped','error') and terminal.get('op') in _READ_TERMINALS)
    return bool(getattr(client, 'unconfirmed_native_request', None) is None
                and isinstance(client.last, str) and client.last
                and terminal.get('request_id') == client.last and known
                and terminal.get('task_session') == client.task
                and terminal.get('world_session') == client.world
                and type(terminal.get('revision_after')) is int
                and terminal['revision_after'] == state.get('control_revision')
                and state.get('connected') is True and state.get('world_session') == client.world
                and state.get('last_request') == client.last and state.get('manual_movement') is False
                and state.get('pending_scan') is None and not state.get('navigating')
                and not state.get('native_material_busy') and not client.native_inflight
                and lease.get('kind') == 'materials' and lease.get('id') == client.heartbeat.id
                and lease.get('job_session') == client.task and lease.get('world_session') == client.world
                and lease.get('revision') == state.get('control_revision'))


class RetainedUnknownMaterialClient(MaterialClient):
    unconfirmed_native_request = None

    def request(self, op, **params):
        if self.unconfirmed_native_request is not None:
            raise RuntimeError('Original native request outcome is unknown; preserve it without another operation')
        before = getattr(self, 'last', None)
        try:
            return super().request(op, **params)
        except BaseException:
            last = getattr(self, 'last', None)
            terminal = getattr(self, 'last_terminal_evidence', None) or {}
            if last != before and terminal.get('request_id') != last:
                self.unconfirmed_native_request = {'request_id': last, 'op': op,
                    'params': deepcopy(params), 'world_session': self.world,
                    'task_session': self.task, 'lease_id': self.heartbeat.id,
                    'original_request_replayed': False}
                path = self.out / 'unconfirmed-native-request.json'
                path.write_text(json.dumps(self.unconfirmed_native_request, ensure_ascii=False, indent=2)+'\n')
                mailbox = self.root / 'request.json'
                if mailbox.exists():
                    (self.out/'preserved-original-mailbox.json').write_bytes(mailbox.read_bytes())
            raise

    def finish(self):
        if not exact_idle_terminal(self, self.raw()):
            raise RuntimeError('Exact idle native outcome is unproved; no finish or recovery operation sent')
        return super().finish()
